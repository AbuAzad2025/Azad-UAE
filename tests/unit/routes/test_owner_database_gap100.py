"""Gap100 for routes/owner/database.py — covers json export loop 410->437.

Targets: `elif export_format == "json"` branch including blocked skip,
row dict building, json.dump, flash/audit.
"""

from __future__ import annotations

import builtins
from contextlib import ExitStack
from unittest.mock import MagicMock, patch, mock_open

from routes.owner import owner_bp


def _result(rows=None, columns=None):
    r = MagicMock()
    r.fetchall.return_value = rows or []
    r.keys.return_value = columns or ["id", "name"]
    r.scalar.return_value = 0
    return r


def _atomic():
    a = MagicMock()
    a.return_value.__enter__ = MagicMock()
    a.return_value.__exit__ = MagicMock(return_value=False)
    return a


_real_open = builtins.open


def _conditional_open(*args, **kwargs):
    # Only mock the export file, delegate others (e.g. Babel .mo) to real open
    path = str(args[0]) if args else ""
    if "db_export" in path or "instance/backups" in path:
        mo = mock_open()
        return mo(*args, **kwargs)
    return _real_open(*args, **kwargs)


class TestExportDatabaseJsonGap100:
    """Covers 410->437 json export with real loop, blocked table, and file write."""

    def test_json_export_covers_loop_and_blocked(self, app_factory, bypass_owner_auth, tmp_path):
        app = app_factory(owner_bp)
        mock_db = MagicMock()
        mock_db.engine = MagicMock()
        # Two tables: one blocked, two normal
        known = {"a": "table_a", "b": "table_b", "c": "blocked_t"}
        # First call for table_a returns 1 row, table_b returns 2 rows
        # We use side_effect to return different results per table
        r_a = _result(rows=[(1, "foo")], columns=["id", "name"])
        r_b = _result(rows=[(2, "bar"), (3, "baz")], columns=["id", "name"])
        # blocked table won't be queried, so only 2 execute calls
        mock_db.session.execute.side_effect = [r_a, r_b]

        atomic = _atomic()
        m_open = mock_open()
        with ExitStack() as stack:
            stack.enter_context(patch("routes.owner.database.render_template", return_value="ok"))
            stack.enter_context(patch("routes.owner.database.url_for", return_value="/"))
            stack.enter_context(patch("routes.owner.database.db", mock_db))
            stack.enter_context(patch("routes.owner.database.inspect", return_value=MagicMock()))
            stack.enter_context(patch("routes.owner.database._known_tables_map", return_value=known))
            stack.enter_context(patch("routes.owner.database._resolve_known_table", side_effect=lambda t: t))
            stack.enter_context(patch("routes.owner.database._resolve_browsable_table", side_effect=lambda t: t))
            stack.enter_context(patch("routes.owner.database._resolve_truncatable_table", side_effect=lambda t: t))
            stack.enter_context(
                patch("routes.owner.database._is_blocked_table", side_effect=lambda t: t == "blocked_t")
            )
            stack.enter_context(patch("routes.owner.database._is_sensitive_stats_table", return_value=False))
            stack.enter_context(patch("routes.owner.database._validate_select_only_sql", return_value=(True, None)))
            stack.enter_context(patch("routes.owner.database._audit_owner_db_action"))
            stack.enter_context(patch("routes.owner.database._inspector_column_names", return_value={"id", "name"}))
            stack.enter_context(patch("routes.owner.database._validate_postgresql_uri", return_value=True))
            stack.enter_context(patch("routes.owner.database._mask_db_uri", return_value="postgresql://***"))
            stack.enter_context(patch("routes.owner.shared._invalidate_owner_changes"))
            stack.enter_context(patch("routes.owner.database.atomic_transaction", atomic))
            stack.enter_context(patch("utils.db_safety.atomic_transaction", atomic))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_error"))
            stack.enter_context(patch("routes.owner.database.select_all_query", return_value="SELECT 1"))
            m_open = mock_open()
            # conditional open prevents breaking Babel .mo loading
            stack.enter_context(patch.object(builtins, "open", side_effect=_conditional_open))
            dump_mock = stack.enter_context(patch("routes.owner.database.json.dump"))

            resp = app.test_client().post("/owner/export-database", data={"format": "json"})

        assert resp.status_code == 302
        # json.dump should have been called with export_data containing only non-blocked tables
        assert dump_mock.called
        args, _kwargs = dump_mock.call_args
        export_data = args[0]
        assert "table_a" in export_data
        assert "table_b" in export_data
        assert "blocked_t" not in export_data
        # Verify row dict building covered (lines 420-422)
        assert export_data["table_a"] == [{"id": 1, "name": "foo"}]
        assert export_data["table_b"] == [{"id": 2, "name": "bar"}, {"id": 3, "name": "baz"}]

    def test_json_export_empty_tables_still_writes(self, app_factory, bypass_owner_auth, tmp_path):
        app = app_factory(owner_bp)
        mock_db = MagicMock()
        mock_db.engine = MagicMock()
        known = {"x": "table_x"}
        r_empty = _result(rows=[], columns=["id"])
        mock_db.session.execute.return_value = r_empty
        atomic = _atomic()
        with ExitStack() as stack:
            stack.enter_context(patch("routes.owner.database.render_template", return_value="ok"))
            stack.enter_context(patch("routes.owner.database.url_for", return_value="/"))
            stack.enter_context(patch("routes.owner.database.db", mock_db))
            stack.enter_context(patch("routes.owner.database.inspect", return_value=MagicMock()))
            stack.enter_context(patch("routes.owner.database._known_tables_map", return_value=known))
            stack.enter_context(patch("routes.owner.database._is_blocked_table", return_value=False))
            stack.enter_context(patch("routes.owner.database._is_sensitive_stats_table", return_value=False))
            stack.enter_context(patch("routes.owner.database._validate_select_only_sql", return_value=(True, None)))
            stack.enter_context(patch("routes.owner.database._audit_owner_db_action"))
            stack.enter_context(patch("routes.owner.database._inspector_column_names", return_value={"id"}))
            stack.enter_context(patch("routes.owner.database._validate_postgresql_uri", return_value=True))
            stack.enter_context(patch("routes.owner.database._mask_db_uri", return_value="***"))
            stack.enter_context(patch("routes.owner.shared._invalidate_owner_changes"))
            stack.enter_context(patch("routes.owner.database.atomic_transaction", atomic))
            stack.enter_context(patch("utils.db_safety.atomic_transaction", atomic))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_error"))
            stack.enter_context(patch("routes.owner.database.select_all_query", return_value="SELECT 1"))
            stack.enter_context(patch.object(builtins, "open", side_effect=_conditional_open))
            dump_mock = stack.enter_context(patch("routes.owner.database.json.dump"))
            resp = app.test_client().post("/owner/export-database", data={"format": "json"})
        assert resp.status_code == 302
        assert dump_mock.called
        export_data = dump_mock.call_args[0][0]
        assert export_data["table_x"] == []

    def test_json_export_uses_select_all_query(self, app_factory, bypass_owner_auth, tmp_path):
        app = app_factory(owner_bp)
        mock_db = MagicMock()
        mock_db.engine = MagicMock()
        known = {"t1": "my_table"}
        mock_db.session.execute.return_value = _result(rows=[(1,)], columns=["id"])
        atomic = _atomic()
        with ExitStack() as stack:
            stack.enter_context(patch("routes.owner.database.render_template", return_value="ok"))
            stack.enter_context(patch("routes.owner.database.url_for", return_value="/"))
            stack.enter_context(patch("routes.owner.database.db", mock_db))
            stack.enter_context(patch("routes.owner.database.inspect", return_value=MagicMock()))
            stack.enter_context(patch("routes.owner.database._known_tables_map", return_value=known))
            stack.enter_context(patch("routes.owner.database._is_blocked_table", return_value=False))
            stack.enter_context(patch("routes.owner.database._is_sensitive_stats_table", return_value=False))
            stack.enter_context(patch("routes.owner.database._validate_select_only_sql", return_value=(True, None)))
            stack.enter_context(patch("routes.owner.database._audit_owner_db_action"))
            stack.enter_context(patch("routes.owner.database._inspector_column_names", return_value={"id"}))
            stack.enter_context(patch("routes.owner.database._validate_postgresql_uri", return_value=True))
            stack.enter_context(patch("routes.owner.database._mask_db_uri", return_value="***"))
            stack.enter_context(patch("routes.owner.shared._invalidate_owner_changes"))
            stack.enter_context(patch("routes.owner.database.atomic_transaction", atomic))
            stack.enter_context(patch("utils.db_safety.atomic_transaction", atomic))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_audit"))
            stack.enter_context(patch("services.logging_core.LoggingCore.log_error"))
            sel_mock = stack.enter_context(patch("routes.owner.database.select_all_query", return_value="SELECT 1"))
            stack.enter_context(patch.object(builtins, "open", side_effect=_conditional_open))
            stack.enter_context(patch("routes.owner.database.json.dump"))
            resp = app.test_client().post("/owner/export-database", data={"format": "json"})
        assert resp.status_code == 302
        assert sel_mock.called
