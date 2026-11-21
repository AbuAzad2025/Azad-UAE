"""Coverage gaps for ``services/logging_core.py`` and
``services/maintenance_stock_service.py``.

The two services already have happy-path suites; this file drives the arcs they
never reach.  The logging half exercises helpers, setup fallbacks, query filters,
severity mapping and performance/activity paths.  The maintenance-stock half
drives every validation guard, the MWAC fallbacks, the FEFO/serial branches and
the create-a-row paths of both moving-average helpers.

Nothing here changes production code: collaborators are patched at the service
boundary and the few MWAC tests use the real ORM against the isolated test DB.
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from services.gl_posting import GlPostingError
from services.logging_core import LoggingCore, _ensure_utf8_stream
from services.maintenance_stock_service import MaintenanceStockService

# The conftest replaces these with no-ops for the whole session (to keep test
# noise down).  Capture the real classmethod descriptors at import time so the
# specific method whose truncation branch we need can be put back temporarily.
_REAL_LOG_FRONTEND_ERROR = LoggingCore.__dict__["log_frontend_error"]

_DEFAULT = object()


def _comparison_column(mocker):
    """A column stand-in usable in generated SQL expressions."""
    column = mocker.MagicMock()
    column.__ge__.return_value = mocker.MagicMock()
    column.__le__.return_value = mocker.MagicMock()
    column.__eq__.return_value = mocker.MagicMock()
    column.in_.return_value = mocker.MagicMock()
    column.desc.return_value = mocker.MagicMock()
    return column


def _q(mocker):
    """A query stand-in that returns itself from every chaining method."""
    query = mocker.MagicMock()
    for name in ("filter_by", "filter", "order_by", "join", "distinct", "populate_existing", "with_for_update"):
        getattr(query, name).return_value = query
    query.first.return_value = None
    query.all.return_value = []
    query.count.return_value = 0
    query.paginate.return_value = SimpleNamespace(items=[], page=1)
    return query


def _mock_error_model(mocker):
    """Patch the module-local ErrorAuditLog with a queryable MagicMock."""
    model = mocker.patch("models.error_audit_log.ErrorAuditLog")
    query = _q(mocker)
    model.query = query
    for name in (
        "category",
        "level",
        "source",
        "message",
        "exception_type",
        "url",
        "created_at",
        "last_seen_at",
        "is_resolved",
    ):
        setattr(model, name, mocker.MagicMock())
    mocker.patch(
        "extensions.db.session.query"
    ).return_value.distinct.return_value.order_by.return_value.all.return_value = []
    # ``or_`` must accept the MagicMock ``ilike()`` results produced above.
    mocker.patch("extensions.db.or_")
    return model, query


def _fake_log(mocker, *, stack="short", as_dict=None):
    log = mocker.MagicMock()
    log.id = 1
    log.level = "ERROR"
    log.category = "BACKEND"
    log.source = "src"
    log.created_at = datetime.now(UTC)
    log.message = "msg"
    log.stack_trace = stack
    log.to_dict.return_value = {"id": 1, "stack_trace": stack if as_dict is None else as_dict}
    return log


# ── logging_core: helpers and setup fallbacks ──────────────────────────────


class TestLoggingCoreHelperGaps:
    def test_utf8_stream_with_buffer_but_no_reconfigure(self):
        class BufferOnly:
            def __init__(self):
                self.buffer = io.BytesIO()

        wrapped = _ensure_utf8_stream(BufferOnly())
        assert isinstance(wrapped, io.TextIOWrapper)

    def test_utf8_stream_without_reconfigure_or_buffer(self):
        class Plain:
            pass

        stream = Plain()
        assert _ensure_utf8_stream(stream) is stream

    def test_slow_query_listener_skips_duplicate_registration(self, app, mocker):
        info = mocker.patch.object(app.logger, "info")
        LoggingCore._slow_query_listener_registered = True
        try:
            LoggingCore.register_slow_query_listener(app)
        finally:
            LoggingCore._slow_query_listener_registered = False
        assert any("already registered" in str(call) for call in info.call_args_list)

    def test_json_logging_skips_non_stream_handler(self, app):
        root = logging.getLogger()
        null_handler = logging.NullHandler()
        root.addHandler(null_handler)
        try:
            LoggingCore._setup_json_logging(app)
        finally:
            root.removeHandler(null_handler)

    def test_self_diagnostics_handler_path_without_parent(self, app, mocker, tmp_path, monkeypatch):
        from logging.handlers import RotatingFileHandler

        monkeypatch.chdir(tmp_path)
        handler = mocker.MagicMock(spec=RotatingFileHandler)
        handler.baseFilename = "relative.log"
        monkeypatch.setattr(LoggingCore, "_handlers", {"app": handler})
        mocker.patch("os.path.exists", return_value=False)
        mocker.patch("os.access", return_value=True)
        LoggingCore._run_self_diagnostics(app)

    def test_capture_warning_without_request_context(self, app, mocker):
        import warnings as builtin_warnings

        original = builtin_warnings.showwarning
        forwarded = mocker.MagicMock()
        builtin_warnings.showwarning = forwarded
        mocker.patch("services.logging_core.has_request_context", return_value=False)
        warn = mocker.patch("services.logging_core.logger.warning")
        try:
            LoggingCore._capture_warnings(app)
            builtin_warnings.showwarning("dep msg", DeprecationWarning, __file__, 1)
        finally:
            builtin_warnings.showwarning = original
        forwarded.assert_called_once()
        assert any("DeprecationWarning: dep msg" in str(call) for call in warn.call_args_list)


# ── logging_core: error persistence and queries ────────────────────────────


class TestLoggingCoreErrorGaps:
    def test_log_frontend_error_without_stack(self, monkeypatch, mocker):
        monkeypatch.setattr(LoggingCore, "log_frontend_error", _REAL_LOG_FRONTEND_ERROR)
        persist = mocker.patch.object(LoggingCore, "_persist_error", return_value=1)
        LoggingCore.log_frontend_error("frontend message", stack=None)
        persist.assert_called_once()
        assert persist.call_args.kwargs["stack_trace"] is None

    def test_persist_error_without_extra_or_request_context(self, app, mocker):
        mocker.patch("services.logging_core.has_request_context", return_value=False)
        mocker.patch.object(LoggingCore, "_find_duplicate", return_value=None)
        conn = mocker.MagicMock()
        conn.execute.return_value.fetchone.return_value = (31,)
        ctx = mocker.MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch("extensions.db.engine.connect", return_value=ctx)
        assert LoggingCore._persist_error("no context", category="BACKEND", level="ERROR", source="src") == 31

    def test_duplicate_bump_below_escalation_threshold(self, app, mocker):
        mocker.patch.object(LoggingCore, "_find_duplicate", return_value=8)
        mocker.patch.object(LoggingCore, "_bump_duplicate", return_value=3)
        alerts = mocker.patch.object(LoggingCore, "_fire_alert_callbacks")
        assert LoggingCore._persist_error("m", category="BACKEND", level="ERROR", source="s") == 8
        alerts.assert_not_called()

    def test_error_log_filters_and_invalid_dates(self, app, mocker):
        _mock_error_model(mocker)
        LoggingCore.get_error_logs(source="svc", from_date="2024-01-01", to_date="2024-02-01", search="boom")
        LoggingCore.get_error_logs(from_date="bad", to_date="bad")

    def test_export_filters_and_long_stack_json(self, app, mocker):
        _model, query = _mock_error_model(mocker)
        query.order_by.return_value.all.return_value = [_fake_log(mocker, stack="X" * 700)]
        body, mime, name = LoggingCore.export_error_logs(
            source="svc",
            from_date="2024-01-01",
            to_date="2024-02-01",
            search="boom",
            fmt="json",
        )
        assert mime == "application/json"
        assert json.loads(body)[0]["stack_trace"].endswith("... [TRUNCATED]")

    def test_export_invalid_dates_are_ignored(self, app, mocker):
        _model, query = _mock_error_model(mocker)
        query.order_by.return_value.all.return_value = []
        LoggingCore.export_error_logs(from_date="bad", to_date="bad", fmt="json")

    def test_export_text_truncates_long_stack_and_skips_missing(self, app, mocker):
        _model, query = _mock_error_model(mocker)
        query.order_by.return_value.all.return_value = [
            _fake_log(mocker, stack="Y" * 700),
            _fake_log(mocker, stack=None),
        ]
        body, mime, _name = LoggingCore.export_error_logs(fmt="txt")
        assert mime.startswith("text/plain")
        assert "... [TRUNCATED - Full trace available in UI]" in body.decode("utf-8")

    def test_export_nested_stack_helper_is_reachable(self, app, mocker):
        """``_truncate_stack_trace`` is a nested helper with no production caller.

        Grab the function object from the frame at return time so its body can
        still be covered without editing the production module.
        """
        _model, query = _mock_error_model(mocker)
        query.order_by.return_value.all.return_value = []
        captured = {}

        def profiler(frame, event, arg):
            if event == "return" and frame.f_code.co_name == "export_error_logs":
                helper = frame.f_locals.get("_truncate_stack_trace")
                if helper is not None:
                    captured["helper"] = helper
            return profiler

        sys.setprofile(profiler)
        try:
            LoggingCore.export_error_logs(fmt="json")
        finally:
            sys.setprofile(None)

        helper = captured["helper"]
        assert helper(None) == ""
        assert helper("short") == "short"
        assert helper("Z" * 600).endswith("... [TRUNCATED - Full trace available in UI]")

    def test_clear_all_error_logs_failure(self, mocker):
        @contextmanager
        def broken_transaction(*_args, **_kwargs):
            raise RuntimeError("db down")
            yield

        mocker.patch("services.logging_core.atomic_transaction", broken_transaction)
        assert LoggingCore.clear_all_error_logs() == 0

    def test_audit_logs_without_tenant_scope(self, app, mocker):
        _q_and_model(mocker)
        _items, _pagination, stats, _users = LoggingCore.get_audit_logs()
        assert stats["total"] == 0


def _q_and_model(mocker):
    """Patch AuditLog/User/db.func for the unscoped audit-query path."""
    audit = mocker.patch("models.audit.AuditLog")
    audit.query = _q(mocker)
    audit.created_at = mocker.MagicMock()
    user = mocker.patch("models.user.User")
    user.query.filter_by.return_value.all.return_value = []
    mocker.patch("extensions.db.func")
    return audit, audit.query


# ── logging_core: event helpers, performance and activity ──────────────────


class TestLoggingCoreEventAndMetricsGaps:
    def test_financial_database_and_migration_events(self, mocker):
        err = mocker.patch.object(LoggingCore, "log_error")
        LoggingCore.log_financial_event("POST_FAIL", "bad", severity="critical", tenant_id=3)
        assert err.call_args.kwargs["level"] == "CRITICAL"
        assert err.call_args.kwargs["category"] == "FINANCIAL"
        LoggingCore.log_financial_event("POST", "bad", severity="low")
        assert err.call_args.kwargs["level"] == "WARNING"

        LoggingCore.log_database_event("DB_DOWN", "bad", severity="error")
        assert err.call_args.kwargs["level"] == "ERROR"
        assert err.call_args.kwargs["category"] == "DATABASE"

        LoggingCore.log_migration_event("DRIFT", "bad", severity="high")
        assert err.call_args.kwargs["category"] == "DATABASE"
        assert err.call_args.kwargs["message"].startswith("[MIGRATION.DRIFT]")

    def test_slow_query_below_threshold(self, mocker):
        warn = mocker.patch("services.logging_core.logger.warning")
        LoggingCore.log_slow_query("SELECT 1", 0.01)
        warn.assert_not_called()

    def test_performance_metrics_missing_and_non_slow_lines(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert LoggingCore.get_performance_metrics() == {"slow_queries_count": 0, "slow_queries": []}
        os.makedirs("logs", exist_ok=True)
        with open("logs/performance.log", "w", encoding="utf-8") as handle:
            handle.write("plain line\nSLOW QUERY x\n")
        data = LoggingCore.get_performance_metrics()
        assert data["slow_queries_count"] == 1
        assert data["slow_queries"] == ["SLOW QUERY x"]

    def test_performance_metrics_data_missing_file(self, mocker):
        mocker.patch("os.path.exists", return_value=False)
        assert LoggingCore.get_performance_metrics_data() == {"slow_queries_count": 0, "slow_queries": []}

    def test_activity_context_without_branch_filter(self, mocker):
        import models

        col = _comparison_column(mocker)
        audit = mocker.MagicMock()
        audit.created_at = col
        audit.query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
        user = mocker.MagicMock()
        user.last_seen = col
        user.is_active = col
        user.tenant_id = col
        user.query.filter.return_value.all.return_value = []
        sale = mocker.MagicMock()
        sale.created_at = col
        sale.tenant_id = col
        sale.branch_id = col
        sale.query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        original = (models.AuditLog, models.Sale, models.User)
        models.AuditLog, models.Sale, models.User = audit, sale, user
        try:
            context = LoggingCore.get_activity_context(tenant_id=1, branch_id=None)
        finally:
            models.AuditLog, models.Sale, models.User = original
        assert context["stats"]["active_now"] == 0
        assert context["stats"]["today_sales"] == 0

    def test_security_events_with_tenant_and_no_user(self, mocker):
        import models

        col = _comparison_column(mocker)
        audit = mocker.MagicMock()
        audit.created_at = col
        audit.tenant_id = col
        audit.action = col
        query = audit.query.filter.return_value
        query.filter.return_value = query
        query.order_by.return_value.limit.return_value.all.return_value = []
        original = models.AuditLog
        models.AuditLog = audit
        try:
            assert LoggingCore.get_security_events(tenant_id=7) == []
        finally:
            models.AuditLog = original
        assert query.filter.call_count == 2

    def test_track_login_attempt_unknown_user(self, mocker):
        mocker.patch("models.User").query.filter_by.return_value.first.return_value = None
        LoggingCore.track_login_attempt("nobody", success=False, ip_address="1.1.1.1")

    def test_track_login_attempt_below_lockout(self, db_session, mocker):
        user = mocker.MagicMock()
        user.login_attempts = 0
        user.locked_until = None
        mocker.patch("models.User").query.filter_by.return_value.first.return_value = user
        LoggingCore.track_login_attempt("bob", success=False, ip_address="1.1.1.1")
        assert user.login_attempts == 1
        assert user.locked_until is None


# ── maintenance_stock_service: fakes shared by the branch tests ────────────


def _fake_line(*, tid=1, order=None, warehouse_id=10, product_id=20, quantity=2, cost_price=None, line_id=1):
    if order is None:
        order = SimpleNamespace(id=99, warehouse_id=10, order_number="MNT-1")
    return SimpleNamespace(
        tenant_id=tid,
        order=order,
        warehouse_id=warehouse_id,
        product_id=product_id,
        quantity=quantity,
        cost_price=cost_price,
        id=line_id,
        serial_numbers=None,
        movement_id=None,
        cost_aed=None,
    )


def _fake_return_line(*, tid=1, order_line=None, quantity=1, return_id=77):
    if order_line is None:
        order_line = SimpleNamespace(
            order=SimpleNamespace(id=99, warehouse_id=10, order_number="MNT-1"),
            warehouse_id=10,
            product_id=20,
            cost_price=Decimal("10"),
            serial_numbers=None,
        )
    return SimpleNamespace(
        tenant_id=tid,
        order_line=order_line,
        quantity=quantity,
        return_id=return_id,
        unit_cost=None,
        line_total_cost=None,
    )


def _patch_tenant_query(mocker, *, product=_DEFAULT, warehouse=_DEFAULT):
    def lookup(model, *_args, **_kwargs):
        query = _q(mocker)
        name = getattr(model, "__name__", "")
        if name == "Product":
            query.first.return_value = SimpleNamespace(id=20) if product is _DEFAULT else product
        elif name == "Warehouse":
            query.first.return_value = SimpleNamespace(id=10) if warehouse is _DEFAULT else warehouse
        return query

    return mocker.patch("services.maintenance_stock_service.tenant_query", side_effect=lookup)


def _patch_consumer(
    mocker,
    *,
    movement_user_id=None,
    fefo=None,
    serials=None,
    serial_exc=False,
    resolve=(Decimal("10"), "mwac"),
):
    mocker.patch(
        "services.maintenance_stock_service.StockService.create_movement",
        return_value=SimpleNamespace(id=555, user_id=movement_user_id, reference_id=99),
    )
    mocker.patch.object(MaintenanceStockService, "_resolve_unit_cost", return_value=resolve)
    mocker.patch.object(MaintenanceStockService, "_apply_mwac_outflow")
    mocker.patch("services.maintenance_stock_service.StockBatchService.batches_enabled", return_value=fefo is not None)
    if fefo is not None:
        mocker.patch("services.maintenance_stock_service.StockBatchService.consume_fefo", return_value=fefo)
    issue = mocker.patch(
        "services.maintenance_stock_service.SerialTrackingService.issue_serials",
        return_value=list(serials or []),
    )
    if serial_exc:
        issue.side_effect = RuntimeError("serials unavailable")
    mocker.patch("services.maintenance_stock_service.log_financial")
    return issue


# ── maintenance_stock_service: validation guards ───────────────────────────


class TestMaintenanceStockValidation:
    @pytest.mark.parametrize(
        "kind, expected",
        [
            ("no_line", ValueError),
            ("no_order", GlPostingError),
            ("no_warehouse", GlPostingError),
            ("no_product", GlPostingError),
            ("no_warehouse_row", GlPostingError),
            ("bad_qty", GlPostingError),
        ],
    )
    def test_consume_guards(self, mocker, kind, expected):
        line = None
        if kind == "no_order":
            line = _fake_line()
            line.order = None
        elif kind == "no_warehouse":
            line = _fake_line(warehouse_id=None, order=SimpleNamespace(id=99, warehouse_id=None, order_number="M"))
        elif kind == "bad_qty":
            line = _fake_line(quantity=0)
        elif kind in ("no_product", "no_warehouse_row"):
            line = _fake_line()
        _patch_tenant_query(
            mocker,
            product=None if kind == "no_product" else _DEFAULT,
            warehouse=None if kind == "no_warehouse_row" else _DEFAULT,
        )
        with pytest.raises(expected):
            MaintenanceStockService.consume_parts_for_order_line(line, 1)

    @pytest.mark.parametrize(
        "kind, expected",
        [
            ("no_line", ValueError),
            ("no_order_line", GlPostingError),
            ("no_warehouse", GlPostingError),
            ("no_product", GlPostingError),
            ("no_warehouse_row", GlPostingError),
            ("bad_qty", GlPostingError),
        ],
    )
    def test_return_guards(self, mocker, kind, expected):
        return_line = None
        if kind == "no_order_line":
            return_line = _fake_return_line()
            return_line.order_line = None
        elif kind == "no_warehouse":
            order_line = _fake_return_line().order_line
            order_line.warehouse_id = None
            order_line.order.warehouse_id = None
            return_line = _fake_return_line(order_line=order_line)
        elif kind == "bad_qty":
            return_line = _fake_return_line(quantity=0)
        elif kind in ("no_product", "no_warehouse_row"):
            return_line = _fake_return_line()
        _patch_tenant_query(
            mocker,
            product=None if kind == "no_product" else _DEFAULT,
            warehouse=None if kind == "no_warehouse_row" else _DEFAULT,
        )
        with pytest.raises(expected):
            MaintenanceStockService.return_parts_for_return_line(return_line, 1)


# ── maintenance_stock_service: cost resolution fallbacks ───────────────────


class TestMaintenanceStockCostResolution:
    def test_cost_price_fallback(self, db_session, sample_tenant, sample_warehouse, sample_product):
        from models import ProductWarehouseCost

        db_session.add(
            ProductWarehouseCost(
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                warehouse_id=sample_warehouse.id,
                total_quantity=0,
                total_value=0,
                average_cost=0,
            )
        )
        db_session.flush()
        cost, source = MaintenanceStockService._resolve_unit_cost(
            sample_product.id, sample_warehouse.id, sample_tenant.id, line_cost_price=Decimal("7.5")
        )
        assert source == "cost_price"
        assert cost == Decimal("7.5000")

    def test_cost_price_fallback_when_average_is_zero(
        self, db_session, sample_tenant, sample_warehouse, sample_product
    ):
        from models import ProductWarehouseCost

        db_session.add(
            ProductWarehouseCost(
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                warehouse_id=sample_warehouse.id,
                total_quantity=5,
                total_value=0,
                average_cost=0,
            )
        )
        db_session.flush()
        cost, source = MaintenanceStockService._resolve_unit_cost(
            sample_product.id, sample_warehouse.id, sample_tenant.id, line_cost_price=Decimal("3.5")
        )
        assert source == "cost_price"
        assert cost == Decimal("3.5000")

    def test_last_purchase_fallback(self, db_session, sample_tenant, sample_warehouse, sample_product):
        from models import ProductCostHistory

        db_session.add(
            ProductCostHistory(
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                warehouse_id=sample_warehouse.id,
                movement_type="purchase",
                new_average_cost=Decimal("6.25"),
                quantity_change=Decimal("1"),
                new_total_quantity=Decimal("1"),
                new_total_value=Decimal("6.25"),
                movement_unit_cost=Decimal("6.25"),
            )
        )
        db_session.flush()
        cost, source = MaintenanceStockService._resolve_unit_cost(
            sample_product.id, sample_warehouse.id, sample_tenant.id
        )
        assert source == "last_purchase"
        assert cost == Decimal("6.2500")

    def test_no_cost_available_raises(self, db_session, sample_tenant, sample_warehouse, sample_product):
        with pytest.raises(GlPostingError):
            MaintenanceStockService._resolve_unit_cost(sample_product.id, sample_warehouse.id, sample_tenant.id)


# ── maintenance_stock_service: consumption branches ────────────────────────


class TestMaintenanceStockConsumption:
    def test_movement_user_already_set(self, mocker):
        _patch_tenant_query(mocker)
        _patch_consumer(mocker, movement_user_id=99)
        line = _fake_line()
        movement = MaintenanceStockService.consume_parts_for_order_line(line, 1)
        assert movement.id == 555
        assert line.movement_id == 555
        assert line.cost_price == Decimal("10.0000")

    def test_fefo_partial_and_full_consumption(self, mocker):
        _patch_tenant_query(mocker)
        _patch_consumer(mocker, fefo=(Decimal("0.5"), Decimal("3")))
        partial = _fake_line()
        MaintenanceStockService.consume_parts_for_order_line(partial, 1)
        assert partial.cost_price == Decimal("9.0000")

        _patch_consumer(mocker, fefo=(Decimal("2"), Decimal("18")))
        full = _fake_line()
        MaintenanceStockService.consume_parts_for_order_line(full, 1)
        assert full.cost_price == Decimal("9.0000")

    def test_fefo_with_no_consumption_keeps_mwac(self, mocker):
        _patch_tenant_query(mocker)
        _patch_consumer(mocker, fefo=(Decimal("0"), Decimal("0")))
        line = _fake_line()
        MaintenanceStockService.consume_parts_for_order_line(line, 1)
        assert line.cost_price == Decimal("10.0000")

    def test_serial_tracking_failure_and_success(self, mocker):
        _patch_tenant_query(mocker)
        _patch_consumer(mocker, serial_exc=True)
        line = _fake_line()
        MaintenanceStockService.consume_parts_for_order_line(line, 1)
        assert line.serial_numbers is None

        _patch_consumer(mocker, serials=["SER-1"])
        tracked = _fake_line()
        MaintenanceStockService.consume_parts_for_order_line(tracked, 1)
        assert tracked.serial_numbers == ["SER-1"]


# ── maintenance_stock_service: MWAC helpers ────────────────────────────────


class TestMaintenanceStockMwac:
    def _movement(self, db_session, tenant, product, warehouse):
        from models import StockMovement

        movement = StockMovement(
            tenant_id=tenant.id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            movement_type="maintenance",
            quantity=-1,
        )
        db_session.add(movement)
        db_session.flush()
        return movement

    def test_outflow_consuming_all_stock_resets_average(
        self, db_session, sample_tenant, sample_warehouse, sample_product
    ):
        from models import ProductWarehouseCost

        movement = self._movement(db_session, sample_tenant, sample_product, sample_warehouse)
        pwc = ProductWarehouseCost(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            total_quantity=1,
            total_value=10,
            average_cost=10,
        )
        db_session.add(pwc)
        db_session.flush()
        MaintenanceStockService._apply_mwac_outflow(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            quantity=Decimal("2"),
            unit_cost=Decimal("10"),
            movement=movement,
        )
        assert pwc.average_cost == 0
        assert pwc.total_value == 0

    def test_outflow_creates_missing_cost_row(self, db_session, sample_tenant, sample_warehouse, sample_product):
        from models import ProductWarehouseCost

        movement = self._movement(db_session, sample_tenant, sample_product, sample_warehouse)
        MaintenanceStockService._apply_mwac_outflow(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            quantity=Decimal("1"),
            unit_cost=Decimal("10"),
            movement=movement,
        )
        pwc = ProductWarehouseCost.query.filter_by(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
        ).first()
        assert pwc is not None
        assert pwc.average_cost == 0

    def test_inflow_creates_missing_cost_row(self, db_session, sample_tenant, sample_warehouse, sample_product):
        from models import ProductWarehouseCost

        movement = self._movement(db_session, sample_tenant, sample_product, sample_warehouse)
        MaintenanceStockService._apply_mwac_inflow(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
            quantity=Decimal("2"),
            unit_cost=Decimal("10"),
            movement=movement,
        )
        pwc = ProductWarehouseCost.query.filter_by(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            warehouse_id=sample_warehouse.id,
        ).first()
        assert pwc is not None
        assert pwc.total_quantity == 2
        assert pwc.average_cost == Decimal("10.000000")


# ── maintenance_stock_service: return branches ─────────────────────────────


class TestMaintenanceStockReturns:
    def _patch_returner(self, mocker, *, movement_user_id=None, batches=False, serial_exc=False):
        mocker.patch(
            "services.maintenance_stock_service.StockService.create_movement",
            return_value=SimpleNamespace(id=556, user_id=movement_user_id, reference_id=77),
        )
        mocker.patch.object(MaintenanceStockService, "_apply_mwac_inflow")
        mocker.patch("services.maintenance_stock_service.StockBatchService.batches_enabled", return_value=batches)
        restore = mocker.patch("services.maintenance_stock_service.StockBatchService.restore_on_reversal")
        serials = mocker.patch("services.maintenance_stock_service.SerialTrackingService.restore_serials")
        if serial_exc:
            serials.side_effect = RuntimeError("restore unavailable")
        mocker.patch("services.maintenance_stock_service.log_financial")
        return restore, serials

    def test_resolve_cost_when_line_cost_is_zero(self, mocker):
        _patch_tenant_query(mocker)
        self._patch_returner(mocker)
        resolve = mocker.patch.object(
            MaintenanceStockService,
            "_resolve_unit_cost",
            return_value=(Decimal("8"), "mwac"),
        )
        return_line = _fake_return_line()
        return_line.order_line.cost_price = Decimal("0")
        result = MaintenanceStockService.return_parts_for_return_line(return_line, 1)
        assert result.id == 556
        resolve.assert_called_once()

    def test_movement_user_already_set_and_batches(self, mocker):
        _patch_tenant_query(mocker)
        restore, _serials = self._patch_returner(mocker, movement_user_id=88, batches=True)
        MaintenanceStockService.return_parts_for_return_line(_fake_return_line(), 1)
        restore.assert_called_once()

    def test_serial_restore_success_and_failure(self, mocker):
        _patch_tenant_query(mocker)
        _restore, serials = self._patch_returner(mocker)
        line = _fake_return_line()
        line.order_line.serial_numbers = ["SER-2"]
        MaintenanceStockService.return_parts_for_return_line(line, 1)
        serials.assert_called_once()

        _restore2, failing = self._patch_returner(mocker, serial_exc=True)
        other = _fake_return_line()
        other.order_line.serial_numbers = ["SER-3"]
        MaintenanceStockService.return_parts_for_return_line(other, 1)
        failing.assert_called_once()
