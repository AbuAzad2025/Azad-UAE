"""
tests/unit/test_backup_scope_config.py — Pure-logic tests for backup scope
configuration and scoped database export (no Flask, no real DB).
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from services.backup_scope_config import (
    SCOPE_BRANCH,
    SCOPE_STORE,
    SCOPE_TENANT,
    _fetch_child_rows,
    _fetch_rows,
    _merge_product_customer_dependencies,
    _path_from_urlish,
    _serialize_row,
    export_scoped_database,
    export_tenant_database,
    read_data_directory,
    sanitize_slug,
    scope_filter_summary,
    table_exists,
    write_data_directory,
)


# ===========================================================================
# Pure function: sanitize_slug
# ===========================================================================

@pytest.mark.parametrize("slug,expected", [
    ("hello-world", "hello-world"),
    ("", "tenant"),
    (None, "tenant"),
    ("  spaces  ", "spaces"),
    ("UPPER-CASE", "upper-case"),
    ("special!@#chars", "special_chars"),
    ("a" * 100, "a" * 48),
    ("___trim___", "trim"),
])
def test_sanitize_slug(slug, expected):
    assert sanitize_slug(slug) == expected


# ===========================================================================
# Pure function: _serialize_row
# ===========================================================================

@pytest.mark.parametrize("item,expected_key,expected_val", [
    ({"dt": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)}, "dt", "2024-01-01T12:00:00+00:00"),
    ({"b": b"\x00\xff"}, "b", "00ff"),
    ({"n": 42}, "n", 42),
    ({"s": "hello"}, "s", "hello"),
])
def test_serialize_row(item, expected_key, expected_val):
    result = _serialize_row(item)
    assert result[expected_key] == expected_val


# ===========================================================================
# Pure function: _path_from_urlish
# ===========================================================================

@pytest.mark.parametrize("value,base,expected", [
    (None, "/base", None),
    ("", "/base", None),
    (42, "/base", None),
    ("http://example.com/img.jpg", "/base", None),
    ("https://example.com/img.jpg", "/base", None),
])
def test_path_from_urlish_defensive(value, base, expected):
    """Non-string, empty, and URL values must return None."""
    assert _path_from_urlish(value, base) == expected


def test_path_from_urlish_traversal_rejected(tmp_path):
    """Path traversal attempts outside static/uploads/ return None."""
    result = _path_from_urlish("../../etc/passwd", str(tmp_path))
    assert result is None


# ===========================================================================
# Pure function: scope_filter_summary
# ===========================================================================

@pytest.mark.parametrize("scope,tid,bid,sid,expected", [
    (SCOPE_TENANT, 1, None, None, "tenant_id=1 only"),
    (SCOPE_BRANCH, 1, 5, None, "tenant_id=1 branch_id=5"),
    (SCOPE_STORE, 1, None, 3, "tenant_id=1 store_id=3"),
    ("unknown", 0, None, None, "unknown"),
])
def test_scope_filter_summary(scope, tid, bid, sid, expected):
    result = scope_filter_summary(scope, tid, bid, sid)
    assert expected in result


# ===========================================================================
# table_exists via mock connection
# ===========================================================================

def test_table_exists_returns_true_when_table_found(mock_db_connection):
    conn = mock_db_connection(scalar=1)
    assert table_exists(conn, "products") is True
    conn.execute.assert_called_once()


def test_table_exists_returns_false_when_table_missing(mock_db_connection):
    conn = mock_db_connection(scalar=None)
    assert table_exists(conn, "ghost_table") is False


# ===========================================================================
# _fetch_rows via mock connection
# ===========================================================================

def test_fetch_rows_returns_serialized_rows(mock_db_connection):
    conn = mock_db_connection(
        rows=[(1, "widget"), (2, "gadget")],
        keys=["id", "name"],
    )
    result = _fetch_rows(conn, "products", "tenant_id = :tid", {"tid": 1})
    assert len(result) == 2
    assert result[0] == {"id": 1, "name": "widget"}
    assert result[1] == {"id": 2, "name": "gadget"}


def test_fetch_rows_empty(mock_db_connection):
    conn = mock_db_connection(rows=[], keys=["id"])
    result = _fetch_rows(conn, "empty_table", "1=0", {})
    assert result == []


# ===========================================================================
# _fetch_child_rows via mock connection
# ===========================================================================

def test_fetch_child_rows_returns_empty_when_no_parents(mock_db_connection):
    conn = mock_db_connection()
    result = _fetch_child_rows(conn, "sale_lines", "sales", "id", "sale_id", [])
    assert result == []


def test_fetch_child_rows_skips_missing_child_table(mock_db_connection, mocker):
    mocker.patch("services.backup_scope_config.table_exists", return_value=False)
    conn = mock_db_connection()
    result = _fetch_child_rows(conn, "ghost", "parent", "id", "fk", [1, 2])
    assert result == []


def test_fetch_child_rows_returns_rows(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    conn = mock_db_connection(
        rows=[(10, 1, 99.0), (11, 1, 50.0)],
        keys=["id", "sale_id", "amount"],
    )
    result = _fetch_child_rows(conn, "sale_lines", "sales", "id", "sale_id", [1])
    assert len(result) == 2
    assert result[0]["sale_id"] == 1


# ===========================================================================
# _merge_product_customer_dependencies
# ===========================================================================

def _merge_setup(mocker, mock_db_connection, *, customers_table=True, merchant_customer_id=None,
                 partner_customer_id=None, existing_customer_ids=None, fetch_result=None):
    mocker.patch("services.backup_scope_config.table_exists", return_value=customers_table)
    conn = mock_db_connection(rows=fetch_result or [], keys=["id", "name", "tenant_id"])

    tables_out = {"products": [], "product_partners": []}
    if merchant_customer_id is not None:
        tables_out["products"] = [{"id": 1, "merchant_customer_id": merchant_customer_id, "tenant_id": 1}]
    if partner_customer_id is not None:
        tables_out["product_partners"] = [{"id": 1, "partner_customer_id": partner_customer_id, "tenant_id": 1}]
    if existing_customer_ids:
        tables_out["customers"] = [{"id": cid, "name": f"c{cid}", "tenant_id": 1} for cid in existing_customer_ids]

    row_counts = {}
    included = []
    unresolved = []
    return conn, tables_out, row_counts, included, unresolved


def test_merge_skip_no_customers_table(mocker, mock_db_connection):
    conn, tables_out, row_counts, included, unresolved = _merge_setup(
        mocker, mock_db_connection, customers_table=False, merchant_customer_id=5
    )
    _merge_product_customer_dependencies(conn, tables_out, row_counts, included, 1, unresolved)
    assert unresolved == []


def test_merge_no_missing_customers(mocker, mock_db_connection):
    conn, tables_out, row_counts, included, unresolved = _merge_setup(
        mocker, mock_db_connection, merchant_customer_id=5, existing_customer_ids=[5]
    )
    _merge_product_customer_dependencies(conn, tables_out, row_counts, included, 1, unresolved)
    assert unresolved == []


def test_merge_fetches_missing_and_appends(mocker, mock_db_connection):
    conn, tables_out, row_counts, included, unresolved = _merge_setup(
        mocker, mock_db_connection, merchant_customer_id=5, existing_customer_ids=[],
        fetch_result=[(5, "merchant_co", 1)],
    )
    _merge_product_customer_dependencies(conn, tables_out, row_counts, included, 1, unresolved)
    assert len(tables_out.get("customers") or []) == 1
    assert tables_out["customers"][0]["id"] == 5


def test_merge_reports_unresolved_ref(mocker, mock_db_connection):
    conn, tables_out, row_counts, included, unresolved = _merge_setup(
        mocker, mock_db_connection, merchant_customer_id=99, existing_customer_ids=[],
        fetch_result=[],
    )
    _merge_product_customer_dependencies(conn, tables_out, row_counts, included, 1, unresolved)
    assert any("missing_merchant" in u for u in unresolved)


# ===========================================================================
# export_scoped_database  (patched helpers)
# ===========================================================================

@pytest.fixture
def patch_export_helpers(mocker):
    """Patch all DB helpers so export_scoped_database runs without a real connection."""
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    mocker.patch("services.backup_scope_config._fetch_rows",
                 return_value=[{"id": 1, "name": "row", "tenant_id": 1}])
    mocker.patch("services.backup_scope_config._fetch_child_rows",
                 return_value=[{"id": 10, "sale_id": 1, "amount": 100.0}])
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies",
                 return_value=None)
    mocker.patch("services.backup_scope_config.logger")


@pytest.mark.parametrize("scope,tenant_id,kwargs", [
    (SCOPE_TENANT, 1, {}),
    (SCOPE_BRANCH, 1, {"branch_id": 5}),
    (SCOPE_STORE, 1, {"store_id": 3}),
])
def test_export_scoped_database_happy_path(patch_export_helpers, scope, tenant_id, kwargs):
    conn = None
    tables, counts, included, skipped, unresolved = export_scoped_database(
        conn, scope, tenant_id=tenant_id, **kwargs
    )
    assert len(tables) > 0
    assert "tenants" in tables or any("tenants" in t for t in included)
    assert isinstance(counts, dict)
    assert isinstance(unresolved, list)


def test_export_scoped_database_unknown_scope(patch_export_helpers):
    conn = None
    result = export_scoped_database(conn, "unknown_scope", tenant_id=1)
    assert len(result) == 4
    _, _, _, skipped = result
    assert "unknown" in str(skipped)


def test_export_scoped_database_requires_branch_id(patch_export_helpers):
    conn = None
    result = export_scoped_database(conn, SCOPE_BRANCH, tenant_id=1)
    assert len(result) == 4
    _, _, _, skipped = result
    assert "branch_id required" in str(skipped)


def test_export_scoped_database_requires_store_id(patch_export_helpers):
    conn = None
    result = export_scoped_database(conn, SCOPE_STORE, tenant_id=1)
    assert len(result) == 4
    _, _, _, skipped = result
    assert "store_id required" in str(skipped)


# ===========================================================================
# export_tenant_database wrapper
# ===========================================================================

def test_export_tenant_database_returns_4_tuple(patch_export_helpers):
    conn = None
    result = export_tenant_database(conn, 1)
    assert len(result) == 4
    tables, counts, included, skipped = result
    assert isinstance(tables, dict)


# ===========================================================================
# write_data_directory / read_data_directory round-trip
# ===========================================================================

def test_write_read_directory_roundtrip(tmp_path):
    tables = {
        "customers": [{"id": 1, "name": "Acme"}],
        "products": [{"id": 10, "title": "Widget", "price": 9.99}],
    }
    meta = write_data_directory(str(tmp_path), tables, scope=SCOPE_TENANT, tenant_id=1)
    assert meta["backup_version"] >= 3
    assert meta["scope"] == SCOPE_TENANT
    assert meta["tenant_id"] == 1
    assert meta["tables"]["customers"]["row_count"] == 1
    assert meta["tables"]["products"]["row_count"] == 1

    restored_tables, restored_meta = read_data_directory(str(tmp_path))
    assert len(restored_tables["customers"]) == 1
    assert restored_tables["products"][0]["title"] == "Widget"


def test_read_data_directory_missing_meta_falls_back_to_jsonl_files(tmp_path):
    (tmp_path / "customers.jsonl").write_text(
        '{"id":1,"name":"A"}\n{"id":2,"name":"B"}\n', encoding="utf-8"
    )
    tables, meta = read_data_directory(str(tmp_path))
    assert len(tables.get("customers") or []) == 2


def test_read_data_directory_empty_dir(tmp_path):
    tables, meta = read_data_directory(str(tmp_path))
    assert tables == {}
