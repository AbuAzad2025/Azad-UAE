"""Coverage gap tests for routes/owner/database.py — SQL console, browse, truncate,
update-row, convert, export, data cleanup, and audit log API.

Targets missing lines: 73-77, 123-130, 199-214, 229-253, 264-297, 309-318,
475-494, 506-513, 641-651.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch


from routes.owner import owner_bp


def _inspector():
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["exchange_rate_records", "audit_logs"]
    inspector.get_columns.return_value = [{"name": "id"}, {"name": "name"}]
    inspector.get_indexes.return_value = [{"name": "idx_id"}]
    inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
    return inspector


def _execute_result(rows=None, columns=None, scalar=0):
    result = MagicMock()
    result.fetchall.return_value = rows or []
    result.keys.return_value = columns or ["id"]
    result.scalar.return_value = scalar
    return result


def _mock_query_cls(**terminals):
    cls = MagicMock(name="model_class")
    q = MagicMock()
    q.filter.return_value.count.return_value = terminals.get("count", 0)
    q.filter.return_value.delete.return_value = terminals.get("deleted", 0)
    q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = terminals.get("all", [])
    q.filter.return_value.first.return_value = terminals.get("first")
    cls.query = q
    cls.created_at = MagicMock()
    cls.created_at.__lt__ = MagicMock(return_value=MagicMock())
    cls.archived_at = MagicMock()
    cls.archived_at.__lt__ = MagicMock(return_value=MagicMock())
    cls.action = MagicMock()
    cls.action.in_ = MagicMock(return_value=MagicMock())
    return cls


@contextmanager
def _db_route_patches(**overrides):
    """Patches for routes.owner.database — covers table inspection + query execution."""
    mock_db = overrides.get("mock_db") or MagicMock()
    mock_db.engine = MagicMock()
    mock_db.session.execute.return_value = _execute_result()

    atomic_mock = MagicMock()
    atomic_mock.return_value.__enter__ = MagicMock()
    atomic_mock.return_value.__exit__ = MagicMock(return_value=False)

    patches = [
        patch("routes.owner.database.render_template", return_value="ok"),
        patch("routes.owner.database.url_for", return_value="/"),
        patch("routes.owner.database.db", mock_db),
        patch("routes.owner.database.inspect", return_value=_inspector()),
        patch(
            "routes.owner.database._known_tables_map",
            return_value={
                "exchange_rate_records": "exchange_rate_records",
                "audit_logs": "audit_logs",
            },
        ),
        patch(
            "routes.owner.database._resolve_known_table",
            side_effect=lambda t: t if t in ("exchange_rate_records", "audit_logs") else None,
        ),
        patch(
            "routes.owner.database._resolve_browsable_table",
            side_effect=lambda t: t if t in ("exchange_rate_records", "audit_logs") else None,
        ),
        patch(
            "routes.owner.database._resolve_truncatable_table", side_effect=lambda t: t if t == "audit_logs" else None
        ),
        patch("routes.owner.database._is_blocked_table", return_value=False),
        patch("routes.owner.database._is_sensitive_stats_table", return_value=False),
        patch("routes.owner.database._validate_select_only_sql", return_value=(True, None)),
        patch("routes.owner.database._audit_owner_db_action"),
        patch("routes.owner.database._inspector_column_names", return_value={"id", "name"}),
        patch("routes.owner.database._validate_postgresql_uri", return_value=True),
        patch("routes.owner.database._mask_db_uri", return_value="postgresql://user:***@host/db"),
        patch("routes.owner.shared._invalidate_owner_changes"),
        patch("routes.owner.database.AuditLog", _mock_query_cls(all=[])),
        patch("routes.owner.database.ArchivedRecord", _mock_query_cls(all=[])),
        patch("services.logging_core.LoggingCore.log_audit"),
        patch("services.logging_core.LoggingCore.log_error"),
        patch("utils.db_safety.atomic_transaction", atomic_mock),
    ]
    for p in patches:
        p.start()
    try:
        yield mock_db
    finally:
        for p in reversed(patches):
            p.stop()


class TestDatabaseTools:
    """Lines 56-98 — database_tools listing with column/index info."""

    def test_database_tools_renders(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.return_value = _execute_result(scalar=5)
            resp = app.test_client().get("/owner/database-tools")
        assert resp.status_code == 200

    def test_database_tools_with_restricted_tables(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches(), patch("routes.owner.database._is_sensitive_stats_table", return_value=True):
            resp = app.test_client().get("/owner/database-tools")
        assert resp.status_code == 200


class TestExecuteQuery:
    """Lines 101-134 — execute_query: empty, validation fail, success, DB error."""

    def test_empty_query_returns_400(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().post("/owner/execute-query", data={"query": ""})
        assert resp.status_code == 400

    def test_validation_failure_returns_400(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _db_route_patches(),
            patch(
                "routes.owner.database._validate_select_only_sql",
                return_value=(False, "not allowed"),
            ),
        ):
            resp = app.test_client().post("/owner/execute-query", data={"query": "DROP TABLE users"})
        assert resp.status_code == 400

    def test_successful_query_returns_rows(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.return_value = _execute_result(rows=[(1,), (2,)], columns=["id"])
            resp = app.test_client().post(
                "/owner/execute-query",
                data={"query": "SELECT id FROM exchange_rate_records"},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["count"] == 2

    def test_query_db_error_returns_400(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("db error")
            resp = app.test_client().post(
                "/owner/execute-query",
                data={"query": "SELECT 1"},
            )
        assert resp.status_code == 400


class TestTruncateTable:
    """Lines 178-214 — truncate: missing confirm, unknown table, success, failure."""

    def test_missing_confirm_token_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().post(
                "/owner/truncate-table",
                data={"table_name": "audit_logs", "confirm": "WRONG"},
            )
        assert resp.status_code == 302

    def test_unknown_table_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches(), patch("routes.owner.database._resolve_truncatable_table", return_value=None):
            resp = app.test_client().post(
                "/owner/truncate-table",
                data={"table_name": "unknown", "confirm": "YES_DELETE_ALL"},
            )
        assert resp.status_code == 302

    def test_successful_truncate(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().post(
                "/owner/truncate-table",
                data={"table_name": "audit_logs", "confirm": "YES_DELETE_ALL"},
            )
        assert resp.status_code == 302

    def test_truncate_db_error(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("truncate fail")
            resp = app.test_client().post(
                "/owner/truncate-table",
                data={"table_name": "audit_logs", "confirm": "YES_DELETE_ALL"},
            )
        assert resp.status_code == 302


class TestBrowseTable:
    """Lines 217-253 — browse_table: unknown, success, DB error."""

    def test_unknown_table_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches(), patch("routes.owner.database._resolve_browsable_table", return_value=None):
            resp = app.test_client().get("/owner/browse-table/unknown")
        assert resp.status_code == 302

    def test_browse_renders_with_pagination(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.side_effect = [
                MagicMock(scalar=MagicMock(return_value=100)),
                _execute_result(rows=[(1,), (2,)], columns=["id"]),
            ]
            resp = app.test_client().get("/owner/browse-table/audit_logs?page=2")
        assert resp.status_code == 200

    def test_browse_db_error_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("browse fail")
            resp = app.test_client().get("/owner/browse-table/audit_logs")
        assert resp.status_code == 302


class TestUpdateRow:
    """Lines 256-297 — update_row: blocked table, no data, no PK, success, error."""

    def test_blocked_table_returns_403(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches(), patch("routes.owner.database._resolve_browsable_table", return_value=None):
            resp = app.test_client().post(
                "/owner/update-row/customers/1",
                json={"name": "x"},
            )
        assert resp.status_code == 403

    def test_empty_updates_returns_400(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().post(
                "/owner/update-row/audit_logs/1",
                json={},
            )
        assert resp.status_code == 400

    def test_no_pk_returns_400(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        insp = _inspector()
        insp.get_pk_constraint.return_value = {"constrained_columns": []}
        with _db_route_patches(), patch("routes.owner.database.inspect", return_value=insp):
            resp = app.test_client().post(
                "/owner/update-row/audit_logs/1",
                json={"name": "new"},
            )
        assert resp.status_code == 400

    def test_successful_update(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().post(
                "/owner/update-row/audit_logs/1",
                json={"name": "updated"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_update_db_error_returns_500(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("update fail")
            resp = app.test_client().post(
                "/owner/update-row/audit_logs/1",
                json={"name": "updated"},
            )
        assert resp.status_code == 500

    def test_only_pk_column_in_updates_returns_400(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().post(
                "/owner/update-row/audit_logs/1",
                json={"id": 999},
            )
        assert resp.status_code == 400


class TestEditTableData:
    """Lines 300-318 — edit_table_data: unknown, success, error."""

    def test_unknown_table_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches(), patch("routes.owner.database._resolve_browsable_table", return_value=None):
            resp = app.test_client().get("/owner/edit-table-data/unknown")
        assert resp.status_code == 302

    def test_edit_renders(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().get("/owner/edit-table-data/audit_logs")
        assert resp.status_code == 200

    def test_edit_db_error_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("edit fail")
            resp = app.test_client().get("/owner/edit-table-data/audit_logs")
        assert resp.status_code == 302


class TestSqlConsole:
    """Lines 321-354 — sql_console GET + POST (valid, invalid, error)."""

    def test_get_renders(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().get("/owner/sql-console")
        assert resp.status_code == 200

    def test_post_valid_query(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.return_value = _execute_result(rows=[(1,)], columns=["id"])
            resp = app.test_client().post(
                "/owner/sql-console",
                data={"sql_query": "SELECT 1"},
            )
        assert resp.status_code == 200

    def test_post_invalid_query(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _db_route_patches(),
            patch(
                "routes.owner.database._validate_select_only_sql",
                return_value=(False, "not allowed"),
            ),
        ):
            resp = app.test_client().post(
                "/owner/sql-console",
                data={"sql_query": "DROP TABLE users"},
            )
        assert resp.status_code == 200

    def test_post_db_error(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.side_effect = RuntimeError("exec fail")
            resp = app.test_client().post(
                "/owner/sql-console",
                data={"sql_query": "SELECT 1"},
            )
        assert resp.status_code == 200


class TestExportDatabase:
    """Lines 357-433 — export: invalid format, json export, pg_dump unavailable."""

    def test_invalid_format_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().post(
                "/owner/export-database",
                data={"format": "xml"},
            )
        assert resp.status_code == 302

    def test_json_export_success(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.return_value = (
                _execute_result(rows=[(1,)], columns=["id"]),
                _execute_result(rows=[(2,)], columns=["id"]),
            )
            resp = app.test_client().post(
                "/owner/export-database",
                data={"format": "json"},
            )
        assert resp.status_code == 302

    def test_sql_export_pg_dump_unavailable(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _db_route_patches(),
            patch(
                "services.backup_service.BackupService._parse_db_url",
                return_value=None,
            ),
        ):
            resp = app.test_client().post(
                "/owner/export-database",
                data={"format": "sql"},
            )
        assert resp.status_code == 302

    def test_sql_export_success(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stderr = ""
        mock_proc.stdout = ""
        with (
            _db_route_patches(),
            patch(
                "services.backup_service.BackupService._parse_db_url",
                return_value={
                    "host": "localhost",
                    "port": "5432",
                    "username": "user",
                    "password": "pass",
                    "dbname": "test",
                },
            ),
            patch(
                "services.backup_service.BackupService._resolve_pg_tool",
                return_value="/usr/bin/pg_dump",
            ),
            patch(
                "services.backup_exec.run_pg_tool",
                return_value=mock_proc,
            ),
        ):
            resp = app.test_client().post(
                "/owner/export-database",
                data={"format": "sql"},
            )
        assert resp.status_code == 302

    def test_export_exception_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _db_route_patches(),
            patch(
                "os.makedirs",
                side_effect=OSError("disk full"),
            ),
        ):
            resp = app.test_client().post(
                "/owner/export-database",
                data={"format": "json"},
            )
        assert resp.status_code == 302


class TestConvertDatabase:
    """Lines 436-515 — convert: GET, POST empty target, invalid URI, success, error."""

    def test_get_renders(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().get("/owner/convert-database")
        assert resp.status_code == 200

    def test_post_empty_target_db(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().post(
                "/owner/convert-database",
                data={"target_db": ""},
            )
        assert resp.status_code == 200

    def test_post_non_postgresql_target(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().post(
                "/owner/convert-database",
                data={"target_db": "mysql"},
            )
        assert resp.status_code == 200

    def test_post_invalid_uri(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _db_route_patches(),
            patch(
                "routes.owner.database._validate_postgresql_uri",
                return_value=False,
            ),
        ):
            resp = app.test_client().post(
                "/owner/convert-database",
                data={"target_db": "postgresql", "postgresql_uri": "invalid://uri"},
            )
        assert resp.status_code == 200

    def test_post_successful_conversion(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)
        with _db_route_patches() as mock_db:
            mock_db.session.execute.return_value = _execute_result(rows=[(1, "x")], columns=["id", "name"])
            with patch("sqlalchemy.create_engine", return_value=mock_engine):
                resp = app.test_client().post(
                    "/owner/convert-database",
                    data={
                        "target_db": "postgresql",
                        "postgresql_uri": "postgresql://user:pass@host/db",
                    },
                )
        assert resp.status_code == 200

    def test_post_conversion_error(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _db_route_patches(),
            patch(
                "sqlalchemy.create_engine",
                side_effect=RuntimeError("engine fail"),
            ),
        ):
            resp = app.test_client().post(
                "/owner/convert-database",
                data={
                    "target_db": "postgresql",
                    "postgresql_uri": "postgresql://user:pass@host/db",
                },
            )
        assert resp.status_code == 200


class TestClearCache:
    """Lines 137-175 — clear_cache: success, Redis down fallback."""

    def test_cache_clear_success(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches(), patch("extensions.cache") as mock_cache:
            mock_cache.clear.return_value = None
            resp = app.test_client().post("/owner/clear-cache")
        assert resp.status_code == 302

    def test_cache_clear_redis_down_fallback(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches(), patch("extensions.cache") as mock_cache:
            mock_cache.clear.side_effect = RuntimeError("Redis down")
            mock_cache.cache = MagicMock()
            type(mock_cache.cache).__name__ = "RedisCache"
            mock_cache.app = MagicMock()
            resp = app.test_client().post("/owner/clear-cache")
        assert resp.status_code == 302


class TestDatabaseOptimize:
    """Lines 518-534 — database_optimize: success, partial, error."""

    def test_optimize_success(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _db_route_patches(),
            patch(
                "utils.database_optimizer.DatabaseOptimizer.vacuum_postgres",
                return_value={"success": True},
            ),
            patch(
                "utils.database_optimizer.DatabaseOptimizer.analyze_tables",
                return_value={"success": True},
            ),
        ):
            resp = app.test_client().post("/owner/database-optimize")
        assert resp.status_code == 302

    def test_optimize_partial_failure(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _db_route_patches(),
            patch(
                "utils.database_optimizer.DatabaseOptimizer.vacuum_postgres",
                return_value={"success": False, "error": "VACUUM failed"},
            ),
            patch(
                "utils.database_optimizer.DatabaseOptimizer.analyze_tables",
                return_value={"success": True},
            ),
        ):
            resp = app.test_client().post("/owner/database-optimize")
        assert resp.status_code == 302

    def test_optimize_exception(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _db_route_patches(),
            patch(
                "utils.database_optimizer.DatabaseOptimizer.vacuum_postgres",
                side_effect=RuntimeError("optimize boom"),
            ),
        ):
            resp = app.test_client().post("/owner/database-optimize")
        assert resp.status_code == 302


class TestVerifyBackups:
    """Lines 537-564 — verify_backups: success and error."""

    def test_verify_backups_renders(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _db_route_patches(),
            patch(
                "services.backup_service.BackupService.list_backups",
                return_value=[{"filename": "bak.sql", "size_mb": 1.5, "datetime": "2025-01-01"}],
            ),
            patch(
                "services.backup_service.BackupService.verify_backup",
                return_value={"valid": True, "format": "sql", "errors": []},
            ),
        ):
            resp = app.test_client().get("/owner/verify-backups")
        assert resp.status_code == 200

    def test_verify_backups_error_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with (
            _db_route_patches(),
            patch(
                "services.backup_service.BackupService.list_backups",
                side_effect=RuntimeError("list fail"),
            ),
        ):
            resp = app.test_client().get("/owner/verify-backups")
        assert resp.status_code == 302


class TestDataCleanup:
    """Lines 567-611 — data_cleanup: GET, POST no type, logs, archived, error."""

    def test_get_renders(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        audit_cls = _mock_query_cls(count=3)
        arch_cls = _mock_query_cls(count=1)
        with (
            _db_route_patches(),
            patch("routes.owner.database.AuditLog", audit_cls),
            patch("routes.owner.database.ArchivedRecord", arch_cls),
        ):
            resp = app.test_client().get("/owner/data-cleanup")
        assert resp.status_code == 200

    def test_post_no_cleanup_type(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        audit_cls = _mock_query_cls(count=3)
        arch_cls = _mock_query_cls(count=1)
        with (
            _db_route_patches(),
            patch("routes.owner.database.AuditLog", audit_cls),
            patch("routes.owner.database.ArchivedRecord", arch_cls),
        ):
            resp = app.test_client().post(
                "/owner/data-cleanup",
                data={"days": "30", "cleanup_type": ""},
            )
        assert resp.status_code == 200

    def test_post_cleanup_logs(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches(), patch("routes.owner.database.AuditLog") as audit_cls:
            audit_cls.query.filter.return_value.delete.return_value = 5
            resp = app.test_client().post(
                "/owner/data-cleanup",
                data={"days": "30", "cleanup_type": "logs"},
            )
        assert resp.status_code == 302

    def test_post_cleanup_archived(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches(), patch("routes.owner.database.ArchivedRecord") as arch_cls:
            arch_cls.query.filter.return_value.delete.return_value = 2
            resp = app.test_client().post(
                "/owner/data-cleanup",
                data={"days": "180", "cleanup_type": "archived"},
            )
        assert resp.status_code == 302

    def test_post_cleanup_error_redirects(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches(), patch("routes.owner.database.AuditLog") as audit_cls:
            audit_cls.query.filter.return_value.delete.side_effect = RuntimeError("delete fail")
            resp = app.test_client().post(
                "/owner/data-cleanup",
                data={"days": "30", "cleanup_type": "logs"},
            )
        assert resp.status_code == 302


class TestImportExportToolsAndExcel:
    """Lines 614-634 — import_export_tools + export_excel blocked/unblocked."""

    def test_import_export_tools_renders(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().get("/owner/import-export-tools")
        assert resp.status_code == 200

    def test_export_excel_blocked_table(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches(), patch("routes.owner.database._is_blocked_table", return_value=True):
            resp = app.test_client().get("/owner/export-excel/customers")
        assert resp.status_code == 302

    def test_export_excel_unknown_table(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        with _db_route_patches():
            resp = app.test_client().get("/owner/export-excel/nonexistent")
        assert resp.status_code == 302


class TestApiRecentAuditLogs:
    """Lines 637-663 — api_recent_audit_logs JSON endpoint."""

    def test_api_returns_logs(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        log1 = MagicMock()
        log1.created_at = datetime(2025, 1, 15, 10, 30, 0)
        log1.action = "rebuild_gl_tree"
        log1.metadata = {"success": True}
        log1.details = "Rebuilt GL tree"
        audit_cls = MagicMock()
        chain = audit_cls.query.filter.return_value.order_by.return_value.limit.return_value
        chain.all.return_value = [log1]
        with (
            _db_route_patches(),
            patch("models.AuditLog", audit_cls),
            patch("sqlalchemy.desc", return_value=MagicMock()),
        ):
            resp = app.test_client().get("/owner/api/recent-audit-logs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["logs"]) == 1
        assert data["logs"][0]["action"] == "rebuild_gl_tree"

    def test_api_empty_logs(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        audit_cls = MagicMock()
        chain = audit_cls.query.filter.return_value.order_by.return_value.limit.return_value
        chain.all.return_value = []
        with (
            _db_route_patches(),
            patch("models.AuditLog", audit_cls),
            patch("sqlalchemy.desc", return_value=MagicMock()),
        ):
            resp = app.test_client().get("/owner/api/recent-audit-logs")
        assert resp.status_code == 200
        assert resp.get_json()["logs"] == []

    def test_api_log_with_none_metadata(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        log = MagicMock()
        log.created_at = datetime(2025, 1, 15, 10, 30, 0)
        log.action = "fix_cost_centers"
        log.metadata = None
        log.details = None
        audit_cls = MagicMock()
        chain = audit_cls.query.filter.return_value.order_by.return_value.limit.return_value
        chain.all.return_value = [log]
        with (
            _db_route_patches(),
            patch("models.AuditLog", audit_cls),
            patch("sqlalchemy.desc", return_value=MagicMock()),
        ):
            resp = app.test_client().get("/owner/api/recent-audit-logs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["logs"][0]["success"] is True
