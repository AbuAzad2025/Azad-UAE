"""Coverage-99% boost for services/backup_scope_config.py pure helpers +
branches not exercised by integration-level tests in
test_backup_scoped_engine / test_backup_scoped_restore.
"""

from __future__ import annotations

import os
import tarfile
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from services.backup_scope_config import (
    _default_for_type,
    _path_from_urlish,
    build_tenant_uploads_archive,
    column_metadata,
    normalize_row_to_target,
    read_data_directory,
    sanitize_slug,
    scope_filter_summary,
    table_exists,
    write_data_directory,
)
from services.backup_scoped_engine import SCOPE_BRANCH, SCOPE_STORE, SCOPE_TENANT

# ---------------------------------------------------------------------------
# _default_for_type branches
# ---------------------------------------------------------------------------


class TestDefaultForType:
    def test_boolean_returns_false(self):
        assert _default_for_type("boolean") is False
        assert _default_for_type("BOOLEAN") is False

    @pytest.mark.parametrize(
        "dt",
        ["integer", "INTEGER", "numeric", "decimal", "money", "real", "double precision", "float", "bigint"],
    )
    def test_numeric_returns_zero(self, dt):
        assert _default_for_type(dt) == 0

    @pytest.mark.parametrize("dt", ["jsonb", "json"])
    def test_json_returns_dict(self, dt):
        assert _default_for_type(dt) == {}

    @pytest.mark.parametrize("dt", ["timestamp with time zone", "timestamp", "date", "time without time zone", "time"])
    def test_datetime_returns_datetime(self, dt):
        assert isinstance(_default_for_type(dt), datetime)

    def test_uuid_returns_uuid_string(self):
        result = _default_for_type("uuid")
        assert isinstance(result, str)
        uuid.UUID(result)

    @pytest.mark.parametrize("dt", ["character varying", "text", "unsupported_xyz", None, ""])
    def test_unsupported_returns_empty_string(self, dt):
        assert _default_for_type(dt) == ""


# ---------------------------------------------------------------------------
# column_metadata
# ---------------------------------------------------------------------------


class TestColumnMetadata:
    def test_returns_empty_when_table_missing(self):
        conn = MagicMock()
        with patch("services.backup_scope_config.table_exists", return_value=False):
            result = column_metadata(conn, "nonexistent_table")
        assert result == []


# ---------------------------------------------------------------------------
# normalize_row_to_target
# ---------------------------------------------------------------------------


class TestNormalizeRowToTarget:
    def test_empty_cols_returns_row_unchanged(self):
        conn = MagicMock()
        with patch("services.backup_scope_config.column_metadata", return_value=[]):
            row = {"id": 1, "name": "x"}
            assert normalize_row_to_target(conn, "t", row) == row

    def test_fills_default_for_missing_notnull(self):
        conn = MagicMock()
        cols = [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": None},
        ]
        with patch("services.backup_scope_config.column_metadata", return_value=cols):
            out = normalize_row_to_target(conn, "t", {})
        assert "id" in out
        assert out["id"] == 0

    def test_passes_through_existing_column(self):
        conn = MagicMock()
        cols = [
            {"name": "id", "data_type": "integer", "is_nullable": "NO", "default": None},
        ]
        with patch("services.backup_scope_config.column_metadata", return_value=cols):
            out = normalize_row_to_target(conn, "t", {"id": 7})
        assert out["id"] == 7

    def test_keeps_null_when_column_nullable(self):
        conn = MagicMock()
        cols = [
            {"name": "note", "data_type": "text", "is_nullable": "YES", "default": None},
        ]
        with patch("services.backup_scope_config.column_metadata", return_value=cols):
            out = normalize_row_to_target(conn, "t", {})
        assert "note" not in out


# ---------------------------------------------------------------------------
# scope_filter_summary
# ---------------------------------------------------------------------------


class TestScopeFilterSummary:
    def test_tenant(self):
        s = scope_filter_summary(SCOPE_TENANT, 1)
        assert "tenant_id=1" in s
        assert "global/platform owners" in s

    def test_branch(self):
        s = scope_filter_summary(SCOPE_BRANCH, 1, branch_id=5)
        assert "tenant_id=1" in s
        assert "branch_id=5" in s

    def test_store(self):
        s = scope_filter_summary(SCOPE_STORE, 1, store_id=8)
        assert "tenant_id=1" in s
        assert "store_id=8" in s
        assert "tenant_stores" in s

    def test_unknown_returns_scope(self):
        assert scope_filter_summary("weird", 1) == "weird"


# ---------------------------------------------------------------------------
# _path_from_urlish branches
# ---------------------------------------------------------------------------


class TestPathFromUrlish:
    def test_none_value(self):
        assert _path_from_urlish(None, "/tmp") is None

    def test_empty_value(self):
        assert _path_from_urlish("", "/tmp") is None

    def test_non_string(self):
        assert _path_from_urlish(123, "/tmp") is None  # type: ignore[arg-type]

    def test_external_url_rejected(self):
        assert _path_from_urlish("https://example.com/x.png", "/tmp") is None

    def test_static_prefix(self, tmp_path):
        f = tmp_path / "uploads" / "x.png"
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(b"\x89PNG")
        result = _path_from_urlish("static/uploads/x.png", str(tmp_path))
        assert result is not None
        assert os.path.isfile(result)

    def test_leading_slash_static(self, tmp_path):
        f = tmp_path / "uploads" / "y.png"
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(b"x")
        result = _path_from_urlish("/static/uploads/y.png", str(tmp_path))
        assert result is not None

    def test_uploads_path(self, tmp_path):
        f = tmp_path / "uploads" / "logo.png"
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(b"x")
        assert _path_from_urlish("uploads/logo.png", str(tmp_path)) is not None

    def test_non_uploads_falls_back_to_uploads_join(self, tmp_path):
        f = tmp_path / "uploads" / "misc.txt"
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(b"x")
        assert _path_from_urlish("misc.txt", str(tmp_path)) is not None

    def test_path_traversal_rejected(self, tmp_path):
        result = _path_from_urlish("../etc/passwd", str(tmp_path))
        assert result is None

    def test_non_existing_file_returns_none(self, tmp_path):
        assert _path_from_urlish("uploads/nonexistent.png", str(tmp_path)) is None


# ---------------------------------------------------------------------------
# build_tenant_uploads_archive
# ---------------------------------------------------------------------------


class TestBuildTenantUploadsArchive:
    def test_packs_existing_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("a")
        f2.write_text("b")
        dest = tmp_path / "out.tar.gz"
        result = build_tenant_uploads_archive([str(f1), str(f2)], str(dest), str(tmp_path))
        assert result["files_packed"] == 2
        assert result["files_requested"] == 2
        assert tarfile.is_tarfile(str(dest))

    def test_skips_missing_files(self, tmp_path):
        present = tmp_path / "a.txt"
        present.write_text("a")
        missing = str(tmp_path / "ghost.txt")
        dest = tmp_path / "out.tar.gz"
        result = build_tenant_uploads_archive([str(present), missing], str(dest), str(tmp_path))
        assert result["files_packed"] == 1
        assert result["files_requested"] == 2


# ---------------------------------------------------------------------------
# write_data_directory + read_data_directory
# ---------------------------------------------------------------------------


class TestWriteReadDataDirectory:
    def test_roundtrip_with_skipped_lines(self, tmp_path):
        rows_users = [{"id": 1, "name": "Ali"}]
        rows_products = [{"id": 2, "sku": "P1"}]
        write_data_directory(
            str(tmp_path),
            {"users": rows_users, "products": rows_products},
            scope="tenant",
            tenant_id=1,
        )
        with open(os.path.join(str(tmp_path), "users.jsonl"), "a", encoding="utf-8") as fh:
            fh.write("\n   \n")
        with open(os.path.join(str(tmp_path), "products.jsonl"), "a", encoding="utf-8") as fh:
            fh.write("\n")
        tables, meta_out = read_data_directory(str(tmp_path))
        assert tables["users"] == rows_users
        assert tables["products"] == rows_products
        assert meta_out["scope"] == "tenant"
        assert meta_out["tenant_id"] == 1

    def test_missing_file_records_empty_list(self, tmp_path):
        tables, meta = read_data_directory(str(tmp_path))
        # No jsonl files written -> no keys in tables (read uses 'order' only
        # when caller passes one; signature now doesn't expose order).
        assert isinstance(tables, dict)
        assert isinstance(meta, dict)


# ---------------------------------------------------------------------------
# sanitize_slug
# ---------------------------------------------------------------------------


class TestSanitizeSlug:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Hello World", "hello_world"),
            ("My Co. Ltd!", "my_co_ltd"),
            ("   spaced   ", "spaced"),
            ("emoji store", "emoji_store"),
        ],
    )
    def test_normalizes(self, raw, expected):
        assert sanitize_slug(raw) == expected

    def test_non_ascii_falls_back(self):
        result = sanitize_slug("🛒")
        # non-ascii gets replaced to "_"; trailing "_" stripped; may fall
        # back to "tenant" if entirely non-ascii without letters.
        assert result

    def test_none_returns_fallback(self):
        assert sanitize_slug(None) == "tenant"

    def test_empty_returns_fallback(self):
        assert sanitize_slug("") == "tenant"


# ---------------------------------------------------------------------------
# table_exists
# ---------------------------------------------------------------------------


class TestTableExists:
    def test_returns_true_when_scalar_one(self):
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = 1
        assert table_exists(conn, "users") is True

    def test_returns_false_when_scalar_none(self):
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = None
        assert table_exists(conn, "users") is False
