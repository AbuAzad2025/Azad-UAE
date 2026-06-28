"""
tests/unit/test_backup_scoped_engine.py — Pure-logic tests for the backup
engine orchestration layer (export, remap, verify, restore validation).

Skips ``ensure_target_schema`` and the full ``restore_scoped_to_target``
insertion loop — those shell out to pg_dump/psql or require a live second
database (E2E territory).
"""
import json
import os
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

import pytest

from services.backup_scoped_engine import (
    SCOPE_BRANCH,
    SCOPE_STORE,
    SCOPE_TENANT,
    ExportResult,
    _json_default,
    _new_id,
    _remap_row,
    export_scope,
    read_jsonl,
    restore_scoped_to_target,
    verify_scoped_isolation,
    write_checksums_file,
    write_data_bundle,
    write_jsonl,
)


# ===========================================================================
# Pure function: _json_default
# ===========================================================================

@pytest.mark.parametrize("value,expected", [
    (datetime(2024, 6, 15, 10, 30, 0), "2024-06-15T10:30:00"),
    (date(2024, 6, 15), "2024-06-15"),
    (time(10, 30, 0), "10:30:00"),
    (Decimal("19.99"), "19.99"),
    (b"\x00\xff", "00ff"),
    (UUID("12345678-1234-5678-1234-567812345678"), "12345678-1234-5678-1234-567812345678"),
    (42, "42"),
])
def test_json_default(value, expected):
    assert _json_default(value) == expected


# ===========================================================================
# File I/O: write_jsonl / read_jsonl round-trip
# ===========================================================================

def test_write_read_jsonl_roundtrip(tmp_path):
    path = os.path.join(str(tmp_path), "test.jsonl")
    rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    write_jsonl(path, rows)
    assert os.path.isfile(path)
    restored = read_jsonl(path)
    assert restored == rows


def test_read_jsonl_missing_file(tmp_path):
    assert read_jsonl(os.path.join(str(tmp_path), "nope.jsonl")) == []


def test_read_jsonl_skips_empty_lines(tmp_path):
    path = os.path.join(str(tmp_path), "test.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"a":1}\n\n{"a":2}\n')
    assert read_jsonl(path) == [{"a": 1}, {"a": 2}]


# ===========================================================================
# File I/O: write_checksums_file
# ===========================================================================

def test_write_checksums_file(tmp_path):
    src = tmp_path / "data.txt"
    src.write_text("hello", encoding="utf-8")
    path = write_checksums_file(str(tmp_path), ["data.txt"])
    assert os.path.isfile(path)
    content = open(path, encoding="utf-8").read()
    assert "data.txt" in content
    assert len(content.splitlines()) == 1


def test_write_checksums_file_skips_missing(tmp_path):
    path = write_checksums_file(str(tmp_path), ["ghost.txt"])
    content = open(path, encoding="utf-8").read().strip()
    assert content == ""


# ===========================================================================
# Pure function: _remap_row
# ===========================================================================

BASE_ROW = {"id": 100, "tenant_id": 1, "name": "test", "branch_id": 5}

@pytest.mark.parametrize("desc,row,id_maps,force_tid,expected", [
    ("no remap", dict(BASE_ROW), {}, None, BASE_ROW),
    ("remap pk", dict(BASE_ROW), {"users": {100: 200}}, None,
     {**BASE_ROW, "id": 200}),
    ("force tenant_id", dict(BASE_ROW), {}, 888,
     {**BASE_ROW, "tenant_id": 888}),
    ("remap pk + force tid", dict(BASE_ROW),
     {"tenants": {1: 99}}, 888,
     {"id": 100, "tenant_id": 888, "name": "test", "branch_id": 5}),
    ("fk remap branch", dict(BASE_ROW),
     {"branches": {5: 55}}, None,
     {**BASE_ROW, "branch_id": 55}),
    ("missing ref map no crash", dict(BASE_ROW), {"products": {1: 2}}, None, BASE_ROW),
])
def test_remap_row(desc, row, id_maps, force_tid, expected):
    result = _remap_row(row, "users", id_maps, force_tenant_id=force_tid)
    assert result == expected


# ===========================================================================
# _new_id via mock connection
# ===========================================================================

def test_new_id_with_sequence(mock_db_connection):
    conn = mock_db_connection(scalar=42)
    # First call: pg_get_serial_sequence returns a seq, second: nextval returns next id
    conn.execute.side_effect = [
        type("R", (), {"scalar": lambda self=0: "public.users_id_seq"})(),
        type("R", (), {"scalar": lambda self=0: 101})(),
    ]
    assert _new_id(conn, "users") == 101


def test_new_id_without_sequence_falls_back_to_max(mock_db_connection):
    conn = mock_db_connection(scalar=99)
    conn.execute.side_effect = [
        type("R", (), {"scalar": lambda self=0: None})(),  # no sequence
        type("R", (), {"scalar": lambda self=0: 99})(),    # MAX(id)+1 = 99
    ]
    assert _new_id(conn, "users") == 99


# ===========================================================================
# export_scope
# ===========================================================================

def test_export_scope_wraps_scoped_database(mocker):
    mock_export = mocker.patch(
        "services.backup_scoped_engine.export_scoped_database",
        return_value=(
            {"tenants": [{"id": 1}], "customers": [{"id": 10}]},
            {"tenants": 1, "customers": 1},
            ["tenants", "customers"],
            [],
            [],
        ),
    )
    result = export_scope(None, SCOPE_TENANT, tenant_id=1)
    assert isinstance(result, ExportResult)
    assert result.scope == SCOPE_TENANT
    assert result.tenant_id == 1
    assert "tenants" in result.included
    assert result.row_counts["tenants"] == 1
    mock_export.assert_called_once_with(None, SCOPE_TENANT, tenant_id=1, branch_id=None, store_id=None)


# ===========================================================================
# write_data_bundle
# ===========================================================================

def test_write_data_bundle_creates_meta_and_jsonl(mocker, tmp_path, mock_db_connection):
    mocker.patch("services.backup_scoped_engine.table_exists", return_value=True)
    conn = mock_db_connection(rows=[("id",), ("name",)], keys=["column_name"])

    export = ExportResult(
        tables={"customers": [{"id": 1, "name": "Acme"}]},
        row_counts={"customers": 1},
        included=["customers"],
        skipped=[],
        dependency_order=["customers"],
        scope=SCOPE_TENANT,
        tenant_id=1,
    )
    result = write_data_bundle(str(tmp_path), export, conn)
    assert "export_meta_path" in result
    assert os.path.isfile(os.path.join(str(tmp_path), "customers.jsonl"))
    assert os.path.isfile(os.path.join(str(tmp_path), "export_meta.json"))


def test_write_data_bundle_skips_empty_row_tables(mocker, tmp_path, mock_db_connection):
    mocker.patch("services.backup_scoped_engine.table_exists", return_value=True)
    conn = mock_db_connection(rows=[("id",)], keys=["column_name"])
    export = ExportResult(
        tables={"customers": [], "tenants": [{"id": 1, "slug": "acme"}]},
        row_counts={"customers": 0, "tenants": 1},
        included=["tenants"],
        skipped=["customers"],
        dependency_order=["customers", "tenants"],
        scope=SCOPE_TENANT,
        tenant_id=1,
    )
    write_data_bundle(str(tmp_path), export, conn)
    assert not os.path.isfile(os.path.join(str(tmp_path), "customers.jsonl"))
    assert os.path.isfile(os.path.join(str(tmp_path), "tenants.jsonl"))


# ===========================================================================
# verify_scoped_isolation
# ===========================================================================

SCOPE_TENANT_MANIFEST = {"backup_scope": SCOPE_TENANT, "tenant_id": 1, "row_counts_per_table": {}}
SCOPE_BRANCH_MANIFEST = {"backup_scope": SCOPE_BRANCH, "tenant_id": 1, "branch_id": 5, "row_counts_per_table": {}}
SCOPE_STORE_MANIFEST = {"backup_scope": SCOPE_STORE, "tenant_id": 1, "store_id": 3, "row_counts_per_table": {}}


def _write_scope_data(tmp_path, tables):
    """Create data/schema_meta.json for verify_scoped_isolation."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    import json as _json
    meta = {"table_order": list(tables.keys())}
    for table, rows in tables.items():
        p = data_dir / f"{table}.jsonl"
        p.write_text("\n".join(_json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    (data_dir / "schema_meta.json").write_text(_json.dumps(meta), encoding="utf-8")


def test_verify_tenant_isolation_pass(tmp_path):
    tables = {"tenants": [{"id": 1}], "customers": [{"id": 10, "tenant_id": 1}]}
    _write_scope_data(tmp_path, tables)
    result = verify_scoped_isolation(SCOPE_TENANT_MANIFEST, str(tmp_path))
    assert result["ok"] is True


def test_verify_tenant_isolation_fail_cross_tenant(tmp_path):
    tables = {"tenants": [{"id": 1}], "customers": [{"id": 10, "tenant_id": 99}]}
    _write_scope_data(tmp_path, tables)
    result = verify_scoped_isolation(SCOPE_TENANT_MANIFEST, str(tmp_path))
    assert result["ok"] is False
    assert any("cross-tenant" in e for e in result["errors"])


def test_verify_tenant_isolation_fail_wrong_count(tmp_path):
    tables = {"tenants": [{"id": 1}, {"id": 2}]}
    _write_scope_data(tmp_path, tables)
    result = verify_scoped_isolation(SCOPE_TENANT_MANIFEST, str(tmp_path))
    assert result["ok"] is False


def test_verify_branch_isolation_pass(tmp_path):
    tables = {"branches": [{"id": 5, "tenant_id": 1}], "sales": [{"id": 1, "branch_id": 5, "tenant_id": 1}]}
    _write_scope_data(tmp_path, tables)
    result = verify_scoped_isolation(SCOPE_BRANCH_MANIFEST, str(tmp_path))
    assert result["ok"] is True


def test_verify_branch_isolation_fail_cross_branch(tmp_path):
    tables = {"branches": [{"id": 5}], "sales": [{"id": 1, "branch_id": 99}]}
    _write_scope_data(tmp_path, tables)
    result = verify_scoped_isolation(SCOPE_BRANCH_MANIFEST, str(tmp_path))
    assert result["ok"] is False
    assert any("cross-branch" in e for e in result["errors"])


def test_verify_store_isolation_pass(tmp_path):
    tables = {"tenant_stores": [{"id": 3, "tenant_id": 1}]}
    _write_scope_data(tmp_path, tables)
    result = verify_scoped_isolation(SCOPE_STORE_MANIFEST, str(tmp_path))
    assert result["ok"] is True


def test_verify_store_isolation_fail(tmp_path):
    tables = {"tenant_stores": [{"id": 3}, {"id": 4}]}
    _write_scope_data(tmp_path, tables)
    result = verify_scoped_isolation(SCOPE_STORE_MANIFEST, str(tmp_path))
    assert result["ok"] is False


def test_verify_count_mismatch(tmp_path):
    tables = {"customers": [{"id": 1, "tenant_id": 1}]}
    _write_scope_data(tmp_path, tables)
    manifest = {**SCOPE_TENANT_MANIFEST, "row_counts_per_table": {"customers": "5"}}
    result = verify_scoped_isolation(manifest, str(tmp_path))
    assert result["ok"] is False
    assert any("count" in e for e in result["errors"])


# ===========================================================================
# restore_scoped_to_target — validation / early-return paths only
# ===========================================================================

def test_restore_wrong_scope():
    result = restore_scoped_to_target("/x", {"backup_scope": "full"}, "postgres://t")
    assert result["ok"] is False
    assert any("restore_scoped only" in e for e in result["errors"])


def test_restore_missing_confirmation():
    result = restore_scoped_to_target("/x", {"backup_scope": SCOPE_TENANT}, "postgres://t")
    assert result["ok"] is False
    assert any("confirmation" in e for e in result["errors"])


def test_restore_same_database_url(mocker):
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database",
        return_value=True,
    )
    result = restore_scoped_to_target(
        "/x",
        {"backup_scope": SCOPE_TENANT},
        "postgres://live",
        confirmation="RESTORE CONFIRM",
    )
    assert result["ok"] is False
    assert any("must differ" in e for e in result["errors"])


def test_restore_no_data_directory(mocker):
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database",
        return_value=False,
    )
    mocker.patch("services.backup_scoped_engine.ensure_target_schema", return_value=(True, ""))
    result = restore_scoped_to_target(
        "/tmp/empty_extract",
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
    )
    assert result["ok"] is False
    assert any("no data" in e for e in result["errors"])
