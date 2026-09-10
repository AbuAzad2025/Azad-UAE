"""Coverage tests for routes/owner/database.py — arcs and lines missed previously.

Targets: arcs 159->163, 161->163, 389->391, 410->437 and lines
420-422, 481, 486, 491. Uses test client + DB/external boundary mocks only.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from routes.owner import owner_bp


def _result(rows=None, columns=None):
    res = MagicMock()
    res.fetchall.return_value = rows or []
    res.keys.return_value = columns or ["id"]
    res.scalar.return_value = 0
    return res


@contextmanager
def _patches(**overrides):
    mock_db = overrides.get("mock_db") or MagicMock()
    mock_db.engine = MagicMock()
    mock_db.session.execute.return_value = _result()
    atomic = MagicMock()
    atomic.return_value.__enter__ = MagicMock()
    atomic.return_value.__exit__ = MagicMock(return_value=False)
    patches = [
        patch("routes.owner.database.render_template", return_value="ok"),
        patch("routes.owner.database.url_for", return_value="/"),
        patch("routes.owner.database.db", mock_db),
        patch("routes.owner.database.inspect", return_value=MagicMock()),
        patch(
            "routes.owner.database._known_tables_map",
            return_value={"t1": "t1"},
        ),
        patch(
            "routes.owner.database._resolve_known_table",
            side_effect=lambda t: t,
        ),
        patch(
            "routes.owner.database._resolve_browsable_table",
            side_effect=lambda t: t,
        ),
        patch(
            "routes.owner.database._resolve_truncatable_table",
            side_effect=lambda t: t,
        ),
        patch("routes.owner.database._is_blocked_table", return_value=False),
        patch("routes.owner.database._is_sensitive_stats_table", return_value=False),
        patch("routes.owner.database._validate_select_only_sql", return_value=(True, None)),
        patch("routes.owner.database._audit_owner_db_action"),
        patch("routes.owner.database._inspector_column_names", return_value={"id", "name"}),
        patch("routes.owner.database._validate_postgresql_uri", return_value=True),
        patch("routes.owner.database._mask_db_uri", return_value="postgresql://***"),
        patch("routes.owner.shared._invalidate_owner_changes"),
        patch("services.logging_core.LoggingCore.log_audit"),
        patch("services.logging_core.LoggingCore.log_error"),
        patch("utils.db_safety.atomic_transaction", atomic),
    ]
    for p in patches:
        p.start()
    try:
        yield mock_db
    finally:
        for p in reversed(patches):
            p.stop()


class TestClearCacheArcs:
    """Arcs 159->163 (NullCache skips re-init) and 161->163 (no app)."""

    def test_nullcache_skips_reinit(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)

        class NullCache:
            pass

        NullCache.__name__ = "NullCache"
        fake_cache = MagicMock()
        fake_cache.clear.side_effect = RuntimeError("redis down")
        fake_cache.cache = NullCache()
        with _patches(), patch("extensions.cache", fake_cache):
            resp = app.test_client().post("/owner/clear-cache")
        assert resp.status_code == 302

    def test_no_app_skips_reinit(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)

        class RedisCache:
            pass

        fake_cache = MagicMock()
        fake_cache.clear.side_effect = RuntimeError("redis down")
        fake_cache.cache = RedisCache()
        fake_cache.app = None
        with _patches(), patch("extensions.cache", fake_cache):
            resp = app.test_client().post("/owner/clear-cache")
        assert resp.status_code == 302


class TestExportArcsAndLines:
    """Arcs 389->391 (no password), 410->437 (sql failure) + lines 420-422."""

    def test_sql_export_without_password(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        with (
            _patches(),
            patch(
                "services.backup_service.BackupService._parse_db_url",
                return_value={"host": "h", "port": "5432", "username": "u", "dbname": "d"},
            ),
            patch(
                "services.backup_service.BackupService._resolve_pg_tool",
                return_value="/usr/bin/pg_dump",
            ),
            patch("services.backup_exec.run_pg_tool", return_value=proc),
        ):
            resp = app.test_client().post("/owner/export-database", data={"format": "sql"})
        assert resp.status_code == 302

    def test_sql_export_pg_failure_goes_to_redirect(self, app_factory, bypass_owner_auth):
        app = app_factory(owner_bp)
        proc = MagicMock()
        proc.returncode = 1
        proc.stderr = "boom"
        proc.stdout = ""
        with (
            _patches(),
            patch(
                "services.backup_service.BackupService._parse_db_url",
                return_value={
                    "host": "h",
                    "port": "5432",
                    "username": "u",
                    "password": "p",
                    "dbname": "d",
                },
            ),
            patch(
                "services.backup_service.BackupService._resolve_pg_tool",
                return_value="/usr/bin/pg_dump",
            ),
            patch("services.backup_exec.run_pg_tool", return_value=proc),
        ):
            resp = app.test_client().post("/owner/export-database", data={"format": "sql"})
        assert resp.status_code == 302

    def test_json_export_iterates_rows(self, app_factory, bypass_owner_auth):
        import builtins
        from unittest.mock import mock_open

        app = app_factory(owner_bp)
        with (
            _patches() as mock_db,
            patch("routes.owner.database.select_all_query", return_value="SELECT 1"),
            patch("os.makedirs"),
            patch.object(builtins, "open", mock_open()),
            patch("routes.owner.database.json.dump") as dump_mock,
        ):
            mock_db.session.execute.return_value = _result(rows=[(1,)], columns=["id"])
            resp = app.test_client().post("/owner/export-database", data={"format": "json"})
        assert resp.status_code == 302
        assert dump_mock.called


class TestConvertContinues:
    """Lines 481 (no columns), 486 (no rows), 491 (no matching columns)."""

    def _engine(self):
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
        engine.begin.return_value.__exit__ = MagicMock(return_value=False)
        return engine

    def _post(self, app_factory, extra=()):
        from routes.owner import owner_bp as bp

        app = app_factory(bp)
        return app

    def test_skip_when_no_allowed_columns(self, app_factory, bypass_owner_auth):
        app = self._post(app_factory)
        with (
            _patches(),
            patch("routes.owner.database._inspector_column_names", return_value=set()),
            patch("sqlalchemy.create_engine", return_value=self._engine()),
        ):
            resp = app.test_client().post(
                "/owner/convert-database",
                data={"target_db": "postgresql", "postgresql_uri": "postgresql://u:p@h/db"},
            )
        assert resp.status_code == 200

    def test_skip_when_no_rows(self, app_factory, bypass_owner_auth):
        app = self._post(app_factory)
        with (
            _patches() as mock_db,
            patch("sqlalchemy.create_engine", return_value=self._engine()),
        ):
            mock_db.session.execute.return_value = _result(rows=[], columns=["id", "name"])
            resp = app.test_client().post(
                "/owner/convert-database",
                data={"target_db": "postgresql", "postgresql_uri": "postgresql://u:p@h/db"},
            )
        assert resp.status_code == 200

    def test_skip_when_no_matching_columns(self, app_factory, bypass_owner_auth):
        app = self._post(app_factory)
        with (
            _patches() as mock_db,
            patch("routes.owner.database._inspector_column_names", return_value={"id"}),
            patch("sqlalchemy.create_engine", return_value=self._engine()),
        ):
            mock_db.session.execute.return_value = _result(rows=[("x",)], columns=["other"])
            resp = app.test_client().post(
                "/owner/convert-database",
                data={"target_db": "postgresql", "postgresql_uri": "postgresql://u:p@h/db"},
            )
        assert resp.status_code == 200
