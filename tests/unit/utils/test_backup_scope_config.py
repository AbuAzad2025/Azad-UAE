"""
tests/unit/test_backup_scope_config.py — Pure-logic tests for backup scope
configuration and scoped database export (no Flask, no real DB).
"""

from datetime import datetime, timezone

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


@pytest.mark.parametrize(
    "slug,expected",
    [
        ("hello-world", "hello-world"),
        ("", "tenant"),
        (None, "tenant"),
        ("  spaces  ", "spaces"),
        ("UPPER-CASE", "upper-case"),
        ("special!@#chars", "special_chars"),
        ("a" * 100, "a" * 48),
        ("___trim___", "trim"),
    ],
)
def test_sanitize_slug(slug, expected):
    assert sanitize_slug(slug) == expected


# ===========================================================================
# Pure function: _serialize_row
# ===========================================================================


@pytest.mark.parametrize(
    "item,expected_key,expected_val",
    [
        (
            {"dt": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)},
            "dt",
            "2024-01-01T12:00:00+00:00",
        ),
        ({"b": b"\x00\xff"}, "b", "00ff"),
        ({"n": 42}, "n", 42),
        ({"s": "hello"}, "s", "hello"),
    ],
)
def test_serialize_row(item, expected_key, expected_val):
    result = _serialize_row(item)
    assert result[expected_key] == expected_val


# ===========================================================================
# Pure function: _path_from_urlish
# ===========================================================================


@pytest.mark.parametrize(
    "value,base,expected",
    [
        (None, "/base", None),
        ("", "/base", None),
        (42, "/base", None),
        ("http://example.com/img.jpg", "/base", None),
        ("https://example.com/img.jpg", "/base", None),
    ],
)
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


@pytest.mark.parametrize(
    "scope,tid,bid,sid,expected",
    [
        (SCOPE_TENANT, 1, None, None, "tenant_id=1 only"),
        (SCOPE_BRANCH, 1, 5, None, "tenant_id=1 branch_id=5"),
        (SCOPE_STORE, 1, None, 3, "tenant_id=1 store_id=3"),
        ("unknown", 0, None, None, "unknown"),
    ],
)
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


def _merge_setup(
    mocker,
    mock_db_connection,
    *,
    customers_table=True,
    merchant_customer_id=None,
    partner_customer_id=None,
    existing_customer_ids=None,
    fetch_result=None,
):
    mocker.patch(
        "services.backup_scope_config.table_exists", return_value=customers_table
    )
    conn = mock_db_connection(rows=fetch_result or [], keys=["id", "name", "tenant_id"])

    tables_out = {"products": [], "product_partners": []}
    if merchant_customer_id is not None:
        tables_out["products"] = [
            {"id": 1, "merchant_customer_id": merchant_customer_id, "tenant_id": 1}
        ]
    if partner_customer_id is not None:
        tables_out["product_partners"] = [
            {"id": 1, "partner_customer_id": partner_customer_id, "tenant_id": 1}
        ]
    if existing_customer_ids:
        tables_out["customers"] = [
            {"id": cid, "name": f"c{cid}", "tenant_id": 1}
            for cid in existing_customer_ids
        ]

    row_counts = {}
    included = []
    unresolved = []
    return conn, tables_out, row_counts, included, unresolved


def test_merge_skip_no_customers_table(mocker, mock_db_connection):
    conn, tables_out, row_counts, included, unresolved = _merge_setup(
        mocker, mock_db_connection, customers_table=False, merchant_customer_id=5
    )
    _merge_product_customer_dependencies(
        conn, tables_out, row_counts, included, 1, unresolved
    )
    assert unresolved == []


def test_merge_no_missing_customers(mocker, mock_db_connection):
    conn, tables_out, row_counts, included, unresolved = _merge_setup(
        mocker, mock_db_connection, merchant_customer_id=5, existing_customer_ids=[5]
    )
    _merge_product_customer_dependencies(
        conn, tables_out, row_counts, included, 1, unresolved
    )
    assert unresolved == []


def test_merge_fetches_missing_and_appends(mocker, mock_db_connection):
    conn, tables_out, row_counts, included, unresolved = _merge_setup(
        mocker,
        mock_db_connection,
        merchant_customer_id=5,
        existing_customer_ids=[],
        fetch_result=[(5, "merchant_co", 1)],
    )
    _merge_product_customer_dependencies(
        conn, tables_out, row_counts, included, 1, unresolved
    )
    assert len(tables_out.get("customers") or []) == 1
    assert tables_out["customers"][0]["id"] == 5


def test_merge_reports_unresolved_ref(mocker, mock_db_connection):
    conn, tables_out, row_counts, included, unresolved = _merge_setup(
        mocker,
        mock_db_connection,
        merchant_customer_id=99,
        existing_customer_ids=[],
        fetch_result=[],
    )
    _merge_product_customer_dependencies(
        conn, tables_out, row_counts, included, 1, unresolved
    )
    assert any("missing_merchant" in u for u in unresolved)


# ===========================================================================
# export_scoped_database  (patched helpers)
# ===========================================================================


@pytest.fixture
def patch_export_helpers(mocker):
    """Patch all DB helpers so export_scoped_database runs without a real connection."""
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    mocker.patch(
        "services.backup_scope_config._fetch_rows",
        return_value=[{"id": 1, "name": "row", "tenant_id": 1}],
    )
    mocker.patch(
        "services.backup_scope_config._fetch_child_rows",
        return_value=[{"id": 10, "sale_id": 1, "amount": 100.0}],
    )
    mocker.patch(
        "services.backup_scope_config._merge_product_customer_dependencies",
        return_value=None,
    )
    mocker.patch("services.backup_scope_config.logger")


@pytest.mark.parametrize(
    "scope,tenant_id,kwargs",
    [
        (SCOPE_TENANT, 1, {}),
        (SCOPE_BRANCH, 1, {"branch_id": 5}),
        (SCOPE_STORE, 1, {"store_id": 3}),
    ],
)
def test_export_scoped_database_happy_path(
    patch_export_helpers, scope, tenant_id, kwargs
):
    conn = None
    tables, _counts, _included, _skipped, _unresolved = export_scoped_database(
        conn, scope, tenant_id=tenant_id, **kwargs
    )
    assert len(tables) > 0
    assert "tenants" in tables or any("tenants" in t for t in _included)
    assert isinstance(_counts, dict)
    assert isinstance(_unresolved, list)


def test_export_scoped_database_unknown_scope(patch_export_helpers):
    conn = None
    result = export_scoped_database(conn, "unknown_scope", tenant_id=1)
    assert len(result) == 5
    _, _, _, skipped, _ = result
    assert "unknown" in str(skipped)


def test_export_scoped_database_requires_branch_id(patch_export_helpers):
    conn = None
    result = export_scoped_database(conn, SCOPE_BRANCH, tenant_id=1)
    assert len(result) == 5
    _, _, _, skipped, _ = result
    assert "branch_id required" in str(skipped)


def test_export_scoped_database_requires_store_id(patch_export_helpers):
    conn = None
    result = export_scoped_database(conn, SCOPE_STORE, tenant_id=1)
    assert len(result) == 5
    _, _, _, skipped, _ = result
    assert "store_id required" in str(skipped)


# ===========================================================================
# export_tenant_database wrapper
# ===========================================================================


def test_export_tenant_database_returns_4_tuple(patch_export_helpers):
    conn = None
    result = export_tenant_database(conn, 1)
    assert len(result) == 4
    tables, _counts, _included, _skipped = result
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

    restored_tables, _restored_meta = read_data_directory(str(tmp_path))
    assert len(restored_tables["customers"]) == 1
    assert restored_tables["products"][0]["title"] == "Widget"


def test_read_data_directory_missing_meta_falls_back_to_jsonl_files(tmp_path):
    (tmp_path / "customers.jsonl").write_text(
        '{"id":1,"name":"A"}\n{"id":2,"name":"B"}\n', encoding="utf-8"
    )
    tables, _meta = read_data_directory(str(tmp_path))
    assert len(tables.get("customers") or []) == 2


def test_read_data_directory_empty_dir(tmp_path):
    tables, _meta = read_data_directory(str(tmp_path))
    assert tables == {}


import json  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from services.backup_scope_config import (  # noqa: E402
    build_tenant_uploads_archive,
    collect_scoped_upload_paths,
    collect_tenant_upload_paths,
)


def test_path_from_urlish_static_and_uploads(tmp_path):
    uploads = tmp_path / "static" / "uploads"
    uploads.mkdir(parents=True)
    img = uploads / "logo.png"
    img.write_bytes(b"png")
    base = str(tmp_path / "static")
    assert _path_from_urlish("/static/uploads/logo.png", base) == str(img)
    assert _path_from_urlish("uploads/logo.png", base) == str(img)
    assert _path_from_urlish("logo.png", base) == str(img)


def test_merge_no_refs_needed(mocker, mock_db_connection):
    conn, tables_out, row_counts, included, unresolved = _merge_setup(
        mocker, mock_db_connection, existing_customer_ids=[]
    )
    _merge_product_customer_dependencies(
        conn, tables_out, row_counts, included, 1, unresolved
    )
    assert unresolved == []


def test_merge_partner_customer_ref(mocker, mock_db_connection):
    conn, tables_out, row_counts, included, unresolved = _merge_setup(
        mocker,
        mock_db_connection,
        partner_customer_id=8,
        existing_customer_ids=[],
        fetch_result=[(8, "partner", 1)],
    )
    _merge_product_customer_dependencies(
        conn, tables_out, row_counts, included, 1, unresolved
    )
    assert tables_out["customers"][0]["id"] == 8


def test_merge_exception_records_unresolved(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    conn = mock_db_connection()
    conn.execute.side_effect = RuntimeError("query failed")
    tables_out = {"products": [{"merchant_customer_id": 5}]}
    unresolved = []
    _merge_product_customer_dependencies(conn, tables_out, {}, [], 1, unresolved)
    assert any("merge_refs_error" in u for u in unresolved)


def test_export_skips_missing_tables(mocker, mock_db_connection):
    mocker.patch(
        "services.backup_scope_config.table_exists",
        side_effect=lambda _c, t: t == "tenants",
    )
    mocker.patch("services.backup_scope_config._fetch_rows", return_value=[{"id": 1}])
    mocker.patch("services.backup_scope_config._fetch_child_rows", return_value=[])
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    _, _, _, skipped, _ = export_scoped_database(conn, SCOPE_TENANT, tenant_id=1)
    assert any("missing" in s for s in skipped)


def test_export_branch_and_store_validation(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    mocker.patch("services.backup_scope_config._fetch_rows", return_value=[])
    mocker.patch("services.backup_scope_config._fetch_child_rows", return_value=[])
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    _, _, _, _, un1 = export_scoped_database(
        conn, SCOPE_BRANCH, tenant_id=1, branch_id=2
    )
    _, _, _, _, un2 = export_scoped_database(conn, SCOPE_STORE, tenant_id=1, store_id=3)
    assert any("branches" in u for u in un1)
    assert any("tenant_stores" in u for u in un2)


def test_export_includes_roles_for_users(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)

    def fetch_rows(_db_conn, table, _where, _params):
        if table == "users":
            return [{"id": 1, "role_id": 9, "tenant_id": 1}]
        if table == "tenants":
            return [{"id": 1}]
        return []

    mocker.patch("services.backup_scope_config._fetch_rows", side_effect=fetch_rows)
    mocker.patch("services.backup_scope_config._fetch_child_rows", return_value=[])
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection(rows=[(9, "admin")], keys=["id", "name"])
    tables, _, _, _, _ = export_scoped_database(conn, SCOPE_TENANT, tenant_id=1)
    assert "roles" in tables


def test_export_fetch_error_and_rollback(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    mocker.patch(
        "services.backup_scope_config._fetch_rows", side_effect=RuntimeError("boom")
    )
    mocker.patch("services.backup_scope_config._fetch_child_rows", return_value=[])
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    _, _, _, skipped, _ = export_scoped_database(conn, SCOPE_TENANT, tenant_id=1)
    assert any("error_RuntimeError" in s for s in skipped)


def test_write_data_directory_extra_table(tmp_path):
    tables = {"customers": [{"id": 1}], "extra_table": [{"id": 99}]}
    meta = write_data_directory(str(tmp_path), tables, scope=SCOPE_TENANT, tenant_id=1)
    assert "extra_table" in meta["table_order"]


def test_read_data_directory_skips_missing_jsonl(tmp_path):
    meta = {"table_order": ["customers", "missing_table"]}
    (tmp_path / "schema_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (tmp_path / "customers.jsonl").write_text('{"id":1}\n', encoding="utf-8")
    tables, _ = read_data_directory(str(tmp_path))
    assert "customers" in tables
    assert "missing_table" not in tables


def test_collect_tenant_upload_paths_wrapper(mocker, mock_db_connection, tmp_path):
    mocker.patch(
        "services.backup_scope_config.collect_scoped_upload_paths",
        return_value=(["/a.png"], ["unresolved"]),
    )
    paths, _unresolved = collect_tenant_upload_paths(
        mock_db_connection(), 1, str(tmp_path)
    )
    assert paths == ["/a.png"]


def test_build_archive_skips_missing_file(tmp_path):
    dest = tmp_path / "out.tar.gz"
    info = build_tenant_uploads_archive(
        [str(tmp_path / "missing.txt")], str(dest), str(tmp_path)
    )
    assert info["files_packed"] == 0


def test_collect_scoped_upload_paths_resolves_and_unresolved(
    mocker, mock_db_connection, tmp_path
):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    uploads = tmp_path / "static" / "uploads"
    uploads.mkdir(parents=True)
    logo = uploads / "logo.png"
    logo.write_bytes(b"png")
    base = str(tmp_path / "static")

    def execute_router(stmt, _bind=None):
        sql = str(stmt)
        result = MagicMock()
        if "column_name" in sql:
            result.__iter__ = lambda _self: iter(
                [("image_url",), ("logo_path",), ("watermark_image_path",)]
            )
        else:
            result.__iter__ = lambda _self: iter(
                [
                    ("/static/uploads/logo.png",),
                    ("http://bad.example/x.png",),
                ]
            )
        return result

    conn = mock_db_connection()
    conn.execute.side_effect = execute_router

    paths, unresolved = collect_scoped_upload_paths(
        conn,
        SCOPE_STORE,
        1,
        base,
        store_id=3,
    )
    assert str(logo) in paths
    assert unresolved


def test_path_from_urlish_backslash_and_traversal(tmp_path):
    base = str(tmp_path / "static")
    assert _path_from_urlish("static\\uploads\\x", base) is None
    assert _path_from_urlish("../../etc/passwd", base) is None


def test_export_child_missing_table(mocker, mock_db_connection):
    mocker.patch(
        "services.backup_scope_config.table_exists",
        side_effect=lambda _c, t: t != "sale_lines",
    )
    mocker.patch(
        "services.backup_scope_config._fetch_rows",
        return_value=[{"id": 1, "tenant_id": 1}],
    )
    mocker.patch("services.backup_scope_config._fetch_child_rows", return_value=[])
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    _, _, _, skipped, _ = export_scoped_database(conn, SCOPE_TENANT, tenant_id=1)
    assert any("sale_lines:missing" in s for s in skipped)


def test_export_roles_query_failure(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    mocker.patch(
        "services.backup_scope_config._fetch_rows",
        return_value=[{"id": 1, "role_id": 9, "tenant_id": 1}],
    )
    mocker.patch("services.backup_scope_config._fetch_child_rows", return_value=[])
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    conn.execute.side_effect = RuntimeError("roles query failed")
    export_scoped_database(conn, SCOPE_TENANT, tenant_id=1)


def test_build_archive_packs_existing_file(tmp_path):
    src = tmp_path / "static" / "uploads" / "keep.txt"
    src.parent.mkdir(parents=True)
    src.write_text("data", encoding="utf-8")
    dest = tmp_path / "out.tar.gz"
    info = build_tenant_uploads_archive([str(src)], str(dest), str(tmp_path / "static"))
    assert info["files_packed"] == 1


def test_merge_rollback_failure_logged(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    conn = mock_db_connection()
    conn.execute.side_effect = RuntimeError("query failed")
    conn.rollback.side_effect = RuntimeError("rb fail")
    tables_out = {"products": [{"merchant_customer_id": 5}]}
    unresolved = []
    _merge_product_customer_dependencies(conn, tables_out, {}, [], 1, unresolved)
    assert any("merge_refs_error" in u for u in unresolved)


def test_path_from_urlish_static_prefix(tmp_path):
    uploads = tmp_path / "static" / "uploads"
    uploads.mkdir(parents=True)
    f = uploads / "a.txt"
    f.write_text("x", encoding="utf-8")
    base = str(tmp_path / "static")
    assert _path_from_urlish("/static/uploads/a.txt", base) == str(f)
    assert _path_from_urlish("static/uploads/a.txt", base) == str(f)


def test_export_child_fetch_error(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)

    def fetch_rows(_db_conn, table, _where, _params):
        if table == "gl_journal_entries":
            return [{"id": 3}]
        if table == "branches":
            return [{"id": 2, "tenant_id": 1}]
        if table == "tenants":
            return [{"id": 1}]
        return []

    mocker.patch("services.backup_scope_config._fetch_rows", side_effect=fetch_rows)
    mocker.patch(
        "services.backup_scope_config._fetch_child_rows",
        side_effect=RuntimeError("child boom"),
    )
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    _, _, _, skipped, _ = export_scoped_database(
        conn,
        SCOPE_BRANCH,
        tenant_id=1,
        branch_id=2,
    )
    assert any("error_RuntimeError" in s for s in skipped)


def test_export_skips_excluded_roles_table(mocker, mock_db_connection):
    import services.backup_scope_config as bsc

    mocker.patch.object(
        bsc,
        "TENANT_TABLE_FILTERS",
        (("roles", "id = 1"), ("tenants", "id = :tid")),
    )
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    mocker.patch("services.backup_scope_config._fetch_rows", return_value=[])
    mocker.patch("services.backup_scope_config._fetch_child_rows", return_value=[])
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    _, _, _, skipped, _ = export_scoped_database(conn, SCOPE_TENANT, tenant_id=1)
    assert any("roles:excluded_policy" in s for s in skipped)


def test_export_fetch_rollback_failure_logged(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    mocker.patch(
        "services.backup_scope_config._fetch_rows", side_effect=RuntimeError("boom")
    )
    mocker.patch("services.backup_scope_config._fetch_child_rows", return_value=[])
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    conn.rollback.side_effect = RuntimeError("rb fail")
    _, _, _, skipped, _ = export_scoped_database(conn, SCOPE_TENANT, tenant_id=1)
    assert any("error_RuntimeError" in s for s in skipped)


def test_export_child_rollback_failure(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)

    def fetch_rows(_db_conn, table, _where, _params):
        if table == "sales":
            return [{"id": 1}]
        if table == "tenants":
            return [{"id": 1}]
        return []

    mocker.patch("services.backup_scope_config._fetch_rows", side_effect=fetch_rows)
    mocker.patch(
        "services.backup_scope_config._fetch_child_rows",
        side_effect=RuntimeError("child fail"),
    )
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    conn.rollback.side_effect = RuntimeError("rb fail")
    _, _, _, skipped, _ = export_scoped_database(
        conn,
        SCOPE_BRANCH,
        tenant_id=1,
        branch_id=2,
    )
    assert any("error_RuntimeError" in s for s in skipped)


def test_roles_export_rollback_failure(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    mocker.patch(
        "services.backup_scope_config._fetch_rows",
        return_value=[{"id": 1, "role_id": 9, "tenant_id": 1}],
    )
    mocker.patch("services.backup_scope_config._fetch_child_rows", return_value=[])
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    conn.execute.side_effect = RuntimeError("roles fail")
    conn.rollback.side_effect = RuntimeError("rb fail")
    export_scoped_database(conn, SCOPE_TENANT, tenant_id=1)


def test_path_from_urlish_bare_filename(tmp_path):
    uploads = tmp_path / "static" / "uploads"
    uploads.mkdir(parents=True)
    f = uploads / "bare.jpg"
    f.write_bytes(b"j")
    base = str(tmp_path / "static")
    assert _path_from_urlish("bare.jpg", base) == str(f)


def test_collect_upload_products_table_missing(mocker, mock_db_connection, tmp_path):
    mocker.patch("services.backup_scope_config.table_exists", return_value=False)
    paths, _unresolved = collect_scoped_upload_paths(
        _conn := mock_db_connection(), SCOPE_TENANT, 1, str(tmp_path)
    )
    assert paths == []


def test_export_child_missing_on_branch_scope(mocker, mock_db_connection):
    mocker.patch(
        "services.backup_scope_config.table_exists",
        side_effect=lambda _c, t: t != "sale_lines",
    )
    mocker.patch(
        "services.backup_scope_config._fetch_rows",
        return_value=[{"id": 1, "tenant_id": 1, "branch_id": 2}],
    )
    mocker.patch("services.backup_scope_config._fetch_child_rows", return_value=[])
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    _, _, _, skipped, _ = export_scoped_database(
        conn,
        SCOPE_BRANCH,
        tenant_id=1,
        branch_id=2,
    )
    assert any("sale_lines:missing" in s for s in skipped)


def test_path_from_urlish_slash_uploads_prefix(tmp_path):
    uploads = tmp_path / "static" / "uploads"
    uploads.mkdir(parents=True)
    f = uploads / "doc.pdf"
    f.write_bytes(b"d")
    base = str(tmp_path / "static")
    assert _path_from_urlish("/uploads/doc.pdf", base) == str(f)


def test_export_child_excluded_policy_continue(mocker, mock_db_connection):
    mocker.patch(
        "services.backup_scope_config.CHILD_VIA_PARENT",
        (("audit_logs", "sales", "id", "sale_id"),),
    )
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    mocker.patch(
        "services.backup_scope_config._fetch_rows",
        return_value=[{"id": 1, "tenant_id": 1}],
    )
    child_mock = mocker.patch(
        "services.backup_scope_config._fetch_child_rows", return_value=[]
    )
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    conn = mock_db_connection()
    export_scoped_database(conn, SCOPE_BRANCH, tenant_id=1, branch_id=2)
    child_mock.assert_not_called()


def test_collect_upload_path_error_branch_scope(mocker, mock_db_connection, tmp_path):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)

    def execute_router(stmt, _bind=None):
        sql = str(stmt)
        result = MagicMock()
        if "column_name" in sql:
            result.__iter__ = lambda _self: iter([("image_url",)])
        else:
            raise RuntimeError("path fail")
        return result

    conn = mock_db_connection()
    conn.execute.side_effect = execute_router
    conn.rollback.side_effect = RuntimeError("rb fail")
    paths, _unresolved = collect_scoped_upload_paths(
        conn,
        SCOPE_BRANCH,
        1,
        str(tmp_path),
        branch_id=2,
    )
    assert paths == []


def test_export_via_real_fetch_rows(mocker, mock_db_connection):
    mocker.patch("services.backup_scope_config.table_exists", return_value=True)
    conn = mock_db_connection()

    def execute_router(stmt, _params=None):
        sql = str(stmt)
        result = MagicMock()
        if "information_schema" in sql:
            result.scalar.return_value = 1
            return result
        if "tenants" in sql:
            result.fetchall.return_value = [(1, "T")]
            result.keys.return_value = ["id", "name"]
        elif "sales" in sql and "sale_lines" not in sql:
            result.fetchall.return_value = [(5, 1)]
            result.keys.return_value = ["id", "tenant_id"]
        elif "sale_lines" in sql:
            result.fetchall.return_value = [(50, 5, 100.0)]
            result.keys.return_value = ["id", "sale_id", "amount"]
        else:
            result.fetchall.return_value = []
            result.keys.return_value = ["id"]
        return result

    conn.execute.side_effect = execute_router
    mocker.patch("services.backup_scope_config._merge_product_customer_dependencies")
    tables, _, _included, _skipped, _ = export_scoped_database(
        conn, SCOPE_TENANT, tenant_id=1
    )
    assert "tenants" in tables
    assert tables["tenants"][0]["name"] == "T"
