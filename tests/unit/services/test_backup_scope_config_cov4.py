"""Coverage-4 for services.backup_scope_config — fallback/except arcs (real paths)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from services.backup_scope_config import (
    _default_for_type,
    _fetch_child_rows,
    _serialize_row,
    export_scoped_database,
    normalize_row_to_target,
    sanitize_slug,
)


class TestSanitizeSlug:
    def test_none_returns_fallback(self):
        assert sanitize_slug(None) == "tenant"
        assert sanitize_slug("") == "tenant"

    def test_custom_fallback_truncated(self):
        assert sanitize_slug(None, fallback="x" * 50) == "x" * 32

    def test_cleans_and_truncates(self):
        assert sanitize_slug("  My Tenant!! ") == "my_tenant"
        assert len(sanitize_slug("a" * 100)) == 48

    def test_underscores_only_falls_back(self):
        assert sanitize_slug("___") == "tenant"


class TestDefaultForType:
    def test_branches(self):
        assert _default_for_type("boolean") is False
        assert _default_for_type("INTEGER") == 0
        assert _default_for_type("numeric(10,2)") == 0
        assert _default_for_type("jsonb") == {}
        assert isinstance(_default_for_type("timestamp with time zone"), datetime)
        assert isinstance(_default_for_type("uuid"), str)
        assert _default_for_type("varchar") == ""
        assert _default_for_type(None) == ""


class TestSerializeRow:
    def test_isoformat_and_bytes(self):
        row = {"ts": datetime(2026, 1, 2, 3, 4, 5), "blob": b"\x00ff", "n": 1}
        out = _serialize_row(dict(row))
        assert out["ts"] == "2026-01-02T03:04:05"
        assert out["blob"] == b"\x00ff".hex()
        assert out["n"] == 1


class TestNormalizeRow:
    def test_no_columns_returns_row(self):
        conn = MagicMock()
        import services.backup_scope_config as cfg

        cfg_conn = conn
        # table_exists False -> column_metadata [] -> passthrough
        from unittest.mock import patch

        with patch.object(cfg, "column_metadata", return_value=[]):
            row = {"a": 1}
            assert normalize_row_to_target(cfg_conn, "missing", row) == {"a": 1}

    def test_drops_unknown_and_fills_not_null(self):
        from unittest.mock import patch

        import services.backup_scope_config as cfg

        cols = [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": None},
            {"name": "name", "data_type": "varchar", "is_nullable": "YES", "default": None},
            {"name": "gone", "data_type": "varchar", "is_nullable": "NO", "default": "NULL"},
        ]
        with patch.object(cfg, "column_metadata", return_value=cols):
            out = normalize_row_to_target(MagicMock(), "t", {"id": 5, "extra": 9})
            assert out["id"] == 5
            assert "extra" not in out
            assert out["gone"] == ""


class TestFetchChildRows:
    def test_empty_parents_short_circuits(self):
        assert _fetch_child_rows(MagicMock(), "sale_lines", "sales", "id", "sale_id", []) == []

    def test_missing_table_short_circuits(self):
        from unittest.mock import patch

        import services.backup_scope_config as cfg

        with patch.object(cfg, "table_exists", return_value=False):
            assert _fetch_child_rows(MagicMock(), "nope", "sales", "id", "sale_id", [1]) == []


class TestExportScoped:
    def test_unknown_scope(self):
        tables, counts, included, skipped, unresolved = export_scoped_database(MagicMock(), "bogus", tenant_id=1)
        assert tables == {}
        assert skipped == ["unknown scope bogus"]

    def test_branch_requires_id(self):
        tables, counts, included, skipped, unresolved = export_scoped_database(
            MagicMock(), "branch", tenant_id=1, branch_id=None
        )
        assert skipped == ["branch_id required"]

    def test_store_requires_id(self):
        tables, counts, included, skipped, unresolved = export_scoped_database(
            MagicMock(), "store", tenant_id=1, store_id=None
        )
        assert skipped == ["store_id required"]
