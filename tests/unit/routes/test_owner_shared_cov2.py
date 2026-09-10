"""Coverage boost for routes/owner/shared.py.

Targets: lines 187, 193, 257 + arc 147->149.
Helpers are pure functions: real function under test, DB/external faked only.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestResolveTruncatableTable:
    """Line 187: known, non-blocked table returns its canonical name."""

    def test_safe_table_returns_canonical_name(self):
        from routes.owner.shared import _resolve_truncatable_table

        with patch(
            "routes.owner.shared._known_tables_map",
            return_value={"my_table": "my_table"},
        ):
            assert _resolve_truncatable_table("my_table") == "my_table"


class TestSqlReferencesBlockedTable:
    """Line 193: empty query returns None without scanning tokens."""

    def test_empty_query_returns_none(self):
        from routes.owner.shared import _sql_references_blocked_table

        assert _sql_references_blocked_table("") is None
        assert _sql_references_blocked_table(None) is None


class TestInspectorColumnNames:
    """Line 257: known table returns its inspected column names."""

    def test_known_table_returns_columns(self):
        from routes.owner.shared import _inspector_column_names

        inspector = MagicMock()
        inspector.get_columns.return_value = [{"name": "id"}, {"name": "name"}]
        with (
            patch(
                "routes.owner.shared._known_tables_map",
                return_value={"mytable": "mytable"},
            ),
            patch("routes.owner.shared.inspect", return_value=inspector),
        ):
            assert _inspector_column_names("mytable") == {"id", "name"}


class TestBackupCreatedByPayload:
    """Arc 147->149: user without role skips role-slug lookup."""

    def test_no_role_keeps_none(self):
        from routes.owner.shared import _backup_created_by_payload

        user = MagicMock(id=7, username="owner1")
        user.role = None
        with patch("routes.owner.shared.current_user", user):
            payload = _backup_created_by_payload()
        assert payload == {"user_id": 7, "role": None, "username": "owner1"}
