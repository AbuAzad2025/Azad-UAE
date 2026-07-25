"""Integration verification for the indexing + telemetry directive (Modules 1-3).

Covers:
  * telemetry interception of unbalanced GL postings (CRITICAL_FINANCIAL)
  * telemetry interception of handled 500s (SOFTWARE_EXCEPTION + request context)
  * POST /api/v1/telemetry/logs client ingest (202/400, category stripping,
    server-side tenant resolution)
  * zero console noise: telemetry logger stays NullHandler-bound between tests
  * PostgreSQL-gated index presence (all 14) + EXPLAIN usage on hot paths
    (test schema comes from db.create_all(), so the migration's own index
    definitions are applied idempotently before asserting)
  * scripts/audit_indexes.py main() sanity (exits 0; clean skip on non-PG)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text as sa_text

from extensions import db
from utils.logger import TELEMETRY_LOGGER_NAME, _TelemetryEventFormatter, clear_context, log_event

_MIGRATION_MODULE = "migrations.versions.i6c2e91a3d47_add_tenant_leading_indexes"

# Keep in sync with the migration's _BTREE_INDEXES + _PG_SPECIAL_INDEXES.
EXPECTED_INDEX_NAMES = [
    "idx_sales_tenant_date",
    "idx_sale_lines_tenant_sale",
    "idx_sale_lines_tenant_product",
    "idx_products_tenant_active_name",
    "idx_customers_tenant_name",
    "idx_gl_entries_tenant_date",
    "idx_gl_lines_tenant_entry",
    "idx_gl_lines_tenant_account",
    "idx_gl_accounts_tenant_active_code",
    "idx_audit_logs_tenant_created",
    "idx_pos_sessions_tenant_open",
    "idx_products_tenant_lower_sku",
    "idx_products_fts_gin",
    "idx_customers_fts_gin",
]

_ORIGIN_HEADER = {"Origin": "http://localhost:5000"}


class _TelemetryCapture(logging.Handler):
    """Parse each formatted telemetry record back into a dict."""

    def __init__(self):
        super().__init__()
        self.entries: list[dict] = []
        self.setFormatter(_TelemetryEventFormatter())

    def emit(self, record):
        self.entries.append(json.loads(self.format(record)))


@pytest.fixture()
def telemetry_capture():
    """Attach a capture handler to the telemetry logger; restore state after."""
    logger = logging.getLogger(TELEMETRY_LOGGER_NAME)
    previous_handlers = logger.handlers[:]
    handler = _TelemetryCapture()
    logger.handlers.clear()
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.handlers.clear()
        for previous in previous_handlers:
            logger.addHandler(previous)
        clear_context()


def _load_migration_indexes():
    module = __import__(_MIGRATION_MODULE, fromlist=["_BTREE_INDEXES"])
    return module._BTREE_INDEXES + module._PG_SPECIAL_INDEXES, module._ALL_INDEX_NAMES


def _ensure_migration_indexes(engine):
    """Apply the migration's index definitions (idempotent) on the test DB.

    The test schema is built with db.create_all(), so the three migration-only
    indexes (functional LOWER + 2 GIN) are created here exactly as upgrade()
    would create them on a migrated database.
    """
    indexes, _ = _load_migration_indexes()
    with engine.begin() as conn:
        for name, table, tail in indexes:
            conn.execute(sa_text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {tail}"))


@pytest.fixture()
def pg_engine(app):
    with app.app_context():
        if db.engine.dialect.name != "postgresql":
            pytest.skip("PostgreSQL-gated index verification")
        yield db.engine


def _explain_plan(conn, sql, params):
    conn.execute(sa_text("SET enable_seqscan = off"))
    rows = conn.execute(sa_text(f"EXPLAIN {sql}"), params).fetchall()
    conn.execute(sa_text("SET enable_seqscan = on"))
    return "\n".join(row[0] for row in rows)


class TestTelemetryInterceptsUnbalancedGL:
    def test_unbalanced_journal_entry_emits_critical_financial(
        self, db_session, sample_tenant, sample_gl_accounts, mocker, telemetry_capture
    ):
        from services.gl_posting import UnbalancedJournalEntryError
        from services.gl_service import GLService

        mocker.patch("services.gl_helpers.assert_period_open")
        bad_lines = [
            {"account": "1111", "debit": Decimal("100"), "credit": Decimal("0")},
            {"account": "4101", "debit": Decimal("0"), "credit": Decimal("50")},
        ]
        with pytest.raises(UnbalancedJournalEntryError):
            GLService.create_journal_entry(
                datetime(2026, 6, 15, tzinfo=timezone.utc),
                "Unbalanced telemetry probe",
                bad_lines,
                tenant_id=sample_tenant.id,
            )

        matches = [e for e in telemetry_capture.entries if e["category"] == "CRITICAL_FINANCIAL"]
        assert len(matches) == 1
        entry = matches[0]
        assert entry["level"] == "CRITICAL"
        assert entry["tenant_id"] == sample_tenant.id
        assert entry["event"] == "gl_unbalanced_entry"
        assert entry["total_debit"] == "100"
        assert entry["total_credit"] == "50"


class TestTelemetryIntercepts5xx:
    def test_handled_500_emits_software_exception(self, app, auth_client, mocker, telemetry_capture):
        """An exception raised in the request pipeline (outside any route-level
        try/except) is intercepted by the app's Flask error handler, which must
        emit SOFTWARE_EXCEPTION carrying the full request context.

        The low-stock route itself swallows service errors, so the explosion is
        planted in the permission decorator via User.has_permission: it raises
        once, only for this route's code ("view_reports"), then delegates back
        to the real implementation so the 500 template can render normally.
        """
        from models.user import User

        real_has_permission = User.has_permission
        armed = {"exploded": False}

        def _explosive_has_permission(self, permission_code):
            if permission_code == "view_reports" and not armed["exploded"]:
                armed["exploded"] = True
                raise RuntimeError("telemetry probe")
            return real_has_permission(self, permission_code)

        mocker.patch.object(User, "has_permission", _explosive_has_permission)

        resp = auth_client.get("/api/products/low-stock")
        assert resp.status_code == 500
        assert armed["exploded"], "decorator explosion never fired"

        matches = [e for e in telemetry_capture.entries if e["category"] == "SOFTWARE_EXCEPTION"]
        assert matches, "expected a SOFTWARE_EXCEPTION telemetry event"
        entry = matches[-1]
        assert entry["level"] == "CRITICAL"
        assert entry["exception"]["type"] == "RuntimeError"
        assert "telemetry probe" in entry["exception"]["traceback"]
        assert entry["endpoint"] == "api.products_low_stock"
        assert entry["method"] == "GET"
        assert entry["request_id"]
        assert entry["tenant_id"] is not None


class TestClientLogIngest:
    def test_valid_batch_authenticated(self, auth_client, sample_user, telemetry_capture):
        payload = {
            "events": [
                {
                    "category": "SOFTWARE_EXCEPTION",
                    "message": "TypeError: cannot read properties of null",
                    "level": "ERROR",
                    "url": "http://localhost:5000/sales",
                    "stack": "TypeError: ...\n    at render (app.js:10)",
                    "breadcrumbs": [{"type": "click", "tag": "button", "text": "Save"}],
                    "client_ts": "2026-07-26T00:00:00.000Z",
                    "extra": {"kind": "error", "lineno": 10},
                },
                {"category": "HARDWARE_WARN", "message": "scale disconnected"},
            ]
        }
        resp = auth_client.post("/api/v1/telemetry/logs", json=payload, headers=_ORIGIN_HEADER)
        assert resp.status_code == 202
        assert resp.get_json()["accepted"] == 2

        entries = [e for e in telemetry_capture.entries if e.get("source") == "frontend"]
        assert len(entries) == 2
        assert all(e["tenant_id"] == sample_user.tenant_id for e in entries)
        assert all(e["user_id"] == sample_user.id for e in entries)
        first, second = entries
        assert first["category"] == "SOFTWARE_EXCEPTION"
        assert first["level"] == "ERROR"
        assert first["client_extra"] == {"kind": "error", "lineno": 10}
        assert first["breadcrumbs"] == [{"type": "click", "tag": "button", "text": "Save"}]
        assert first["stack"].startswith("TypeError")
        assert first["client_ts"] == "2026-07-26T00:00:00.000Z"
        assert second["category"] == "HARDWARE_WARN"
        assert second["level"] == "WARNING"

    def test_valid_batch_anonymous_tenant_none(self, client, telemetry_capture):
        resp = client.post(
            "/api/v1/telemetry/logs",
            json={"events": [{"category": "SOFTWARE_EXCEPTION", "message": "public page crash"}]},
            headers=_ORIGIN_HEADER,
        )
        assert resp.status_code == 202
        assert resp.get_json()["accepted"] == 1
        entries = [e for e in telemetry_capture.entries if e.get("source") == "frontend"]
        assert len(entries) == 1
        assert entries[0]["tenant_id"] is None
        assert entries[0]["user_id"] is None

    def test_malformed_payloads_rejected_without_500(self, client, telemetry_capture):
        bad_payloads = [
            {"events": "not-a-list"},
            {"events": []},
            {"wrong_key": []},
            {"events": [{"message": f"e{i}"} for i in range(51)]},
        ]
        for payload in bad_payloads:
            resp = client.post("/api/v1/telemetry/logs", json=payload, headers=_ORIGIN_HEADER)
            assert resp.status_code == 400, payload
        resp = client.post(
            "/api/v1/telemetry/logs",
            data="not json at all",
            content_type="application/json",
            headers=_ORIGIN_HEADER,
        )
        assert resp.status_code == 400
        assert [e for e in telemetry_capture.entries if e.get("source") == "frontend"] == []

    def test_server_only_categories_stripped(self, client, telemetry_capture):
        payload = {
            "events": [
                {"category": "SECURITY_ALERT", "message": "spoofed security event"},
                {"category": "CRITICAL_FINANCIAL", "message": "spoofed financial event"},
                {"category": "SOMETHING_ELSE", "message": "unknown category"},
            ]
        }
        resp = client.post("/api/v1/telemetry/logs", json=payload, headers=_ORIGIN_HEADER)
        assert resp.status_code == 202
        assert resp.get_json()["accepted"] == 3
        entries = [e for e in telemetry_capture.entries if e.get("source") == "frontend"]
        assert [e["category"] for e in entries] == ["SOFTWARE_EXCEPTION"] * 3


class TestZeroConsoleNoise:
    def test_logger_is_silent_by_default(self, capsys):
        logger = logging.getLogger(TELEMETRY_LOGGER_NAME)
        # pytest attaches its LogCaptureHandler to every non-propagating logger
        # for the duration of each test phase (_pytest/logging.py catching_logs).
        # That is harness infrastructure, not app output — the gate targets only
        # handlers the app itself (or a leaked fixture) attached.
        app_handlers = [h for h in logger.handlers if type(h).__module__ != "_pytest.logging"]
        assert app_handlers, "telemetry logger must never be handler-less"
        assert all(isinstance(h, logging.NullHandler) for h in app_handlers)
        assert logger.propagate is False
        log_event("QUIET_PROBE", "must not surface anywhere", tenant_id=1)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
        clear_context()


class TestMigrationIndexDefinitions:
    def test_migration_defines_expected_fourteen(self):
        _, all_names = _load_migration_indexes()
        assert all_names == EXPECTED_INDEX_NAMES


@pytest.mark.usefixtures("pg_engine")
class TestIndexPresencePg:
    @pytest.mark.parametrize("index_name", EXPECTED_INDEX_NAMES)
    def test_index_present_in_pg_indexes(self, pg_engine, index_name):
        _ensure_migration_indexes(pg_engine)
        with pg_engine.connect() as conn:
            found = conn.execute(
                sa_text("SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :name"),
                {"name": index_name},
            ).scalar()
        assert found == 1, f"{index_name} missing from pg_indexes"


@pytest.mark.usefixtures("pg_engine")
class TestIndexUsagePg:
    def test_sales_list_uses_tenant_date_index(self, pg_engine):
        _ensure_migration_indexes(pg_engine)
        with pg_engine.connect() as conn:
            plan = _explain_plan(
                conn,
                "SELECT id FROM sales WHERE tenant_id = :t ORDER BY sale_date DESC LIMIT 20",
                {"t": 1},
            )
        assert "idx_sales_tenant_date" in plan

    def test_product_lower_sku_lookup_uses_functional_index(self, pg_engine):
        _ensure_migration_indexes(pg_engine)
        with pg_engine.connect() as conn:
            plan = _explain_plan(
                conn,
                "SELECT id FROM products WHERE tenant_id = :t AND lower(sku) = :sku",
                {"t": 1, "sku": "sku-000123"},
            )
        assert "idx_products_tenant_lower_sku" in plan

    def test_journal_list_uses_tenant_date_index(self, pg_engine):
        _ensure_migration_indexes(pg_engine)
        with pg_engine.connect() as conn:
            plan = _explain_plan(
                conn,
                "SELECT id FROM gl_journal_entries WHERE tenant_id = :t ORDER BY entry_date DESC LIMIT 50",
                {"t": 1},
            )
        assert "idx_gl_entries_tenant_date" in plan


class TestAuditCliSanity:
    def test_main_exits_zero(self, app, mocker, capsys):
        from scripts import audit_indexes

        mocker.patch("app.factory.create_app", return_value=app)
        rc = audit_indexes.main([])
        assert rc == 0
        captured = capsys.readouterr()
        assert "index audit" in captured.out.lower()
