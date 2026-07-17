import json
import os
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

import pytest

from services.backup_scope_config import SCOPE_BRANCH, SCOPE_STORE, SCOPE_TENANT
from services.backup_scoped_engine import (
    ExportResult,
    _json_default,
    _new_id,
    _remap_row,
    ensure_target_schema,
    export_scope,
    read_jsonl,
    restore_scoped_to_target,
    verify_scoped_isolation,
    write_checksums_file,
    write_data_bundle,
    write_jsonl,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        (datetime(2024, 6, 15, 10, 30, 0), "2024-06-15T10:30:00"),
        (date(2024, 6, 15), "2024-06-15"),
        (time(10, 30, 0), "10:30:00"),
        (Decimal("19.99"), "19.99"),
        (b"\x00\xff", "00ff"),
        (
            UUID("12345678-1234-5678-1234-567812345678"),
            "12345678-1234-5678-1234-567812345678",
        ),
        (42, "42"),
    ],
)
def test_json_default(value, expected):
    assert _json_default(value) == expected


def test_write_read_jsonl_roundtrip(tmp_path):
    path = os.path.join(str(tmp_path), "nested", "test.jsonl")
    rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    write_jsonl(path, rows)
    assert os.path.isfile(path)
    assert read_jsonl(path) == rows


def test_read_jsonl_missing_file(tmp_path):
    assert read_jsonl(os.path.join(str(tmp_path), "nope.jsonl")) == []


def test_read_jsonl_skips_empty_lines(tmp_path):
    path = tmp_path / "test.jsonl"
    path.write_text('{"a":1}\n\n{"a":2}\n', encoding="utf-8")
    assert read_jsonl(str(path)) == [{"a": 1}, {"a": 2}]


def test_write_checksums_file(tmp_path):
    src = tmp_path / "data.txt"
    src.write_text("hello", encoding="utf-8")
    path = write_checksums_file(str(tmp_path), ["data.txt"])
    content = open(path, encoding="utf-8").read()
    assert "data.txt" in content


def test_write_checksums_file_skips_missing(tmp_path):
    path = write_checksums_file(str(tmp_path), ["ghost.txt"])
    assert open(path, encoding="utf-8").read().strip() == ""


BASE_ROW = {"id": 100, "tenant_id": 1, "name": "test", "branch_id": 5}


@pytest.mark.parametrize(
    "row,id_maps,force_tid,expected",
    [
        (dict(BASE_ROW), {}, None, BASE_ROW),
        (dict(BASE_ROW), {"tenants": {1: 99}}, None, {**BASE_ROW, "tenant_id": 99}),
        (dict(BASE_ROW), {}, 888, {**BASE_ROW, "tenant_id": 888}),
        (dict(BASE_ROW), {"branches": {5: 55}}, None, {**BASE_ROW, "branch_id": 55}),
    ],
)
def test_remap_row(row, id_maps, force_tid, expected):
    assert _remap_row(row, "users", id_maps, force_tenant_id=force_tid) == expected


def test_new_id_with_sequence(mock_db_connection):
    conn = mock_db_connection(scalar=42)
    conn.execute.side_effect = [
        type("R", (), {"scalar": lambda self=0: "public.users_id_seq"})(),
        type("R", (), {"scalar": lambda self=0: 101})(),
    ]
    assert _new_id(conn, "users") == 101


def test_new_id_without_sequence_falls_back_to_max(mock_db_connection):
    conn = mock_db_connection(scalar=99)
    conn.execute.side_effect = [
        type("R", (), {"scalar": lambda self=0: None})(),
        type("R", (), {"scalar": lambda self=0: 99})(),
    ]
    assert _new_id(conn, "users") == 99


def test_export_scope_wraps_scoped_database(mocker):
    mocker.patch(
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
    assert result.scope == SCOPE_TENANT
    assert result.tenant_id == 1
    assert "tenants" in result.included


def test_write_data_bundle_creates_meta_and_jsonl(mocker, tmp_path, mock_db_connection):
    mocker.patch("services.backup_scoped_engine.table_exists", return_value=True)
    mocker.patch("services.backup_scoped_engine.write_jsonl")
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
    assert os.path.isfile(os.path.join(str(tmp_path), "export_meta.json"))
    assert "export_meta_path" in result


def test_write_data_bundle_skips_empty_tables(tmp_path, mock_db_connection, mocker):
    mocker.patch("services.backup_scoped_engine.write_jsonl")
    conn = mock_db_connection()
    export = ExportResult(
        tables={},
        row_counts={},
        included=[],
        skipped=[],
        dependency_order=[],
        scope=SCOPE_TENANT,
        tenant_id=1,
    )
    write_data_bundle(str(tmp_path), export, conn)
    jsonl_files = [f for f in os.listdir(str(tmp_path)) if f.endswith(".jsonl")]
    assert jsonl_files == []


SCOPE_TENANT_MANIFEST = {
    "backup_scope": SCOPE_TENANT,
    "tenant_id": 1,
    "row_counts_per_table": {},
}
SCOPE_BRANCH_MANIFEST = {
    "backup_scope": SCOPE_BRANCH,
    "tenant_id": 1,
    "branch_id": 5,
    "row_counts_per_table": {},
}
SCOPE_STORE_MANIFEST = {
    "backup_scope": SCOPE_STORE,
    "tenant_id": 1,
    "store_id": 3,
    "row_counts_per_table": {},
}


def _write_scope_data(tmp_path, tables):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    meta = {"table_order": list(tables.keys())}
    for table, rows in tables.items():
        p = data_dir / f"{table}.jsonl"
        p.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )
    (data_dir / "schema_meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_verify_tenant_isolation_pass(tmp_path):
    tables = {"tenants": [{"id": 1}], "customers": [{"id": 10, "tenant_id": 1}]}
    _write_scope_data(tmp_path, tables)
    assert verify_scoped_isolation(SCOPE_TENANT_MANIFEST, str(tmp_path))["ok"] is True


def test_verify_tenant_isolation_fail_cross_tenant(tmp_path):
    tables = {"tenants": [{"id": 1}], "customers": [{"id": 10, "tenant_id": 99}]}
    _write_scope_data(tmp_path, tables)
    result = verify_scoped_isolation(SCOPE_TENANT_MANIFEST, str(tmp_path))
    assert result["ok"] is False
    assert any("cross-tenant" in e for e in result["errors"])


def test_verify_tenant_isolation_fail_wrong_count(tmp_path):
    tables = {"tenants": [{"id": 1}, {"id": 2}]}
    _write_scope_data(tmp_path, tables)
    assert verify_scoped_isolation(SCOPE_TENANT_MANIFEST, str(tmp_path))["ok"] is False


def test_verify_branch_isolation_pass(tmp_path):
    tables = {
        "branches": [{"id": 5, "tenant_id": 1}],
        "sales": [{"id": 1, "branch_id": 5, "tenant_id": 1}],
    }
    _write_scope_data(tmp_path, tables)
    assert verify_scoped_isolation(SCOPE_BRANCH_MANIFEST, str(tmp_path))["ok"] is True


def test_verify_branch_isolation_fail_cross_branch(tmp_path):
    tables = {"branches": [{"id": 5}], "sales": [{"id": 1, "branch_id": 99}]}
    _write_scope_data(tmp_path, tables)
    result = verify_scoped_isolation(SCOPE_BRANCH_MANIFEST, str(tmp_path))
    assert result["ok"] is False


def test_verify_store_isolation_pass(tmp_path):
    tables = {"tenant_stores": [{"id": 3, "tenant_id": 1}]}
    _write_scope_data(tmp_path, tables)
    assert verify_scoped_isolation(SCOPE_STORE_MANIFEST, str(tmp_path))["ok"] is True


def test_verify_store_isolation_fail(tmp_path):
    tables = {"tenant_stores": [{"id": 3}, {"id": 4}]}
    _write_scope_data(tmp_path, tables)
    assert verify_scoped_isolation(SCOPE_STORE_MANIFEST, str(tmp_path))["ok"] is False


def test_verify_count_mismatch(tmp_path):
    tables = {"customers": [{"id": 1, "tenant_id": 1}]}
    _write_scope_data(tmp_path, tables)
    manifest = {**SCOPE_TENANT_MANIFEST, "row_counts_per_table": {"customers": "5"}}
    result = verify_scoped_isolation(manifest, str(tmp_path))
    assert result["ok"] is False


def test_verify_legacy_tenant_export(tmp_path):
    legacy = {
        "tables": {
            "tenants": [{"id": 1}],
            "customers": [{"id": 2, "tenant_id": 1}],
        }
    }
    (tmp_path / "tenant_export.json").write_text(json.dumps(legacy), encoding="utf-8")
    assert verify_scoped_isolation(SCOPE_TENANT_MANIFEST, str(tmp_path))["ok"] is True


def test_restore_wrong_scope():
    result = restore_scoped_to_target("/x", {"backup_scope": "full"}, "postgres://t")
    assert result["ok"] is False


def test_restore_missing_confirmation():
    result = restore_scoped_to_target(
        "/x", {"backup_scope": SCOPE_TENANT}, "postgres://t"
    )
    assert result["ok"] is False


def test_restore_remap_confirmation_required():
    result = restore_scoped_to_target(
        "/x",
        {"backup_scope": SCOPE_TENANT},
        "postgres://t",
        confirmation="RESTORE CONFIRM",
        remap=True,
    )
    assert result["ok"] is False
    assert any("REMAP CONFIRM" in e for e in result["errors"])


def test_restore_same_database_url(mocker):
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=True
    )
    result = restore_scoped_to_target(
        "/x",
        {"backup_scope": SCOPE_TENANT},
        "postgres://live",
        confirmation="RESTORE CONFIRM",
    )
    assert result["ok"] is False


def test_restore_no_data_directory(mocker):
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    result = restore_scoped_to_target(
        "/tmp/empty_extract",
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
    )
    assert result["ok"] is False


def test_restore_schema_failure(mocker):
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema",
        return_value=(False, "schema boom"),
    )
    result = restore_scoped_to_target(
        "/tmp/x",
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
    )
    assert "schema boom" in result["errors"][0]


def test_ensure_target_schema_flask_upgrade_success(mocker):
    mocker.patch.dict(
        os.environ,
        {"DATABASE_URL": "postgres://src", "SQLALCHEMY_DATABASE_URI": "postgres://src"},
    )
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=True
    )
    proc = mocker.MagicMock(returncode=0, stderr="", stdout="")
    mocker.patch("services.backup_exec.run_python_module", return_value=proc)
    mocker.patch("app.create_app", side_effect=RuntimeError("skip app init"))
    ok, err = ensure_target_schema("postgres://target")
    assert ok is True
    assert err == ""


def test_ensure_target_schema_flask_upgrade_failure(mocker):
    mocker.patch.dict(os.environ, {}, clear=False)
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=True
    )
    proc = mocker.MagicMock(returncode=1, stderr="upgrade failed", stdout="")
    mocker.patch("services.backup_exec.run_python_module", return_value=proc)
    ok, err = ensure_target_schema("postgres://target")
    assert ok is False
    assert "upgrade failed" in err


def test_ensure_target_schema_pg_dump_restore_success(mocker, tmp_path):
    schema_file = tmp_path / "schema.sql"
    schema_file.write_text("CREATE TABLE x(id int);", encoding="utf-8")
    mocker.patch.dict(
        os.environ,
        {
            "DATABASE_URL": "postgres://src/db",
            "SQLALCHEMY_DATABASE_URI": "postgres://src/db",
        },
    )
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_service.BackupService._parse_db_url",
        side_effect=lambda url: {
            "host": "h",
            "port": "5432",
            "username": "u",
            "password": "p",
            "dbname": "d",
        },
    )
    mocker.patch(
        "services.backup_service.BackupService._resolve_pg_tool",
        side_effect=lambda a, b: a,
    )
    dump_proc = mocker.MagicMock(returncode=0)
    restore_proc = mocker.MagicMock(returncode=0)
    mocker.patch(
        "services.backup_exec.run_pg_tool", side_effect=[dump_proc, restore_proc]
    )
    mocker.patch(
        "tempfile.NamedTemporaryFile",
        return_value=mocker.MagicMock(
            name=str(schema_file), __enter__=lambda s: s, __exit__=lambda *a: None
        ),
    )
    mocker.patch("os.path.isfile", return_value=True)
    ok, err = ensure_target_schema("postgres://tgt/db")
    assert ok is True


def test_ensure_target_schema_pg_restore_alembic_probe(mocker, tmp_path):
    schema_file = tmp_path / "schema.sql"
    mocker.patch.dict(os.environ, {"DATABASE_URL": "postgres://src/db"})
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_service.BackupService._parse_db_url",
        return_value={
            "host": "h",
            "port": "5432",
            "username": "u",
            "password": "",
            "dbname": "d",
        },
    )
    mocker.patch(
        "services.backup_service.BackupService._resolve_pg_tool",
        side_effect=lambda a, b: a,
    )
    dump_proc = mocker.MagicMock(returncode=0)
    restore_proc = mocker.MagicMock(returncode=1, stderr="warn", stdout="")
    mocker.patch(
        "services.backup_exec.run_pg_tool", side_effect=[dump_proc, restore_proc]
    )
    mocker.patch(
        "tempfile.NamedTemporaryFile",
        return_value=mocker.MagicMock(
            name=str(schema_file), __enter__=lambda s: s, __exit__=lambda *a: None
        ),
    )
    mocker.patch("os.path.isfile", return_value=True)
    conn = mocker.MagicMock()
    conn.execute.return_value.scalar.return_value = True
    cm = mocker.MagicMock()
    cm.__enter__.return_value = conn
    cm.__exit__.return_value = None
    engine = mocker.MagicMock()
    engine.connect.return_value = cm
    mocker.patch("sqlalchemy.create_engine", return_value=engine)
    ok, err = ensure_target_schema("postgres://tgt/db")
    assert ok is True


def _mock_restore_engine(
    mocker,
    table_exists=True,
    insert_raises=None,
    replication_role_raises=False,
    column_names=None,
):
    conn = mocker.MagicMock()
    txn = mocker.MagicMock()
    txn.__enter__.return_value = conn
    txn.__exit__.return_value = None
    conn.begin.return_value = txn
    seq_counter = {"n": 500}
    cols = column_names or ["id", "tenant_id", "branch_id"]

    def scalar_side():
        seq_counter["n"] += 1
        return seq_counter["n"]

    result = mocker.MagicMock()
    result.scalar.side_effect = lambda: scalar_side()
    col_result = mocker.MagicMock()
    col_result.__iter__.return_value = iter((c,) for c in cols)

    def execute_side(sql, params=None):
        sql_s = str(sql)
        if replication_role_raises and "session_replication_role" in sql_s:
            raise RuntimeError("role denied")
        if "information_schema.columns" in sql_s:
            return col_result
        if insert_raises and "INSERT INTO" in sql_s:
            raise insert_raises
        return result

    conn.execute.side_effect = execute_side
    engine = mocker.MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = None
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = None
    mocker.patch("sqlalchemy.create_engine", return_value=engine)
    mocker.patch(
        "services.backup_scoped_engine.table_exists", return_value=table_exists
    )
    return conn


def test_restore_tenant_success_non_remap(mocker, tmp_path):
    tables = {
        "tenants": [{"id": 1, "slug": "acme"}],
        "customers": [{"id": 10, "tenant_id": 1, "name": "C"}],
    }
    _write_scope_data(tmp_path, tables)
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker)
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
    )
    assert result["ok"] is True
    assert result["target_tenant_id"] == 1


def test_restore_legacy_export_json(mocker, tmp_path):
    doc = {
        "tables": {
            "tenants": [{"id": 1, "slug": "legacy"}],
            "customers": [{"id": 2, "tenant_id": 1}],
        }
    }
    (tmp_path / "tenant_export.json").write_text(json.dumps(doc), encoding="utf-8")
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker)
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
    )
    assert result["ok"] is True


def test_restore_remap_tenant_branch_store(mocker, tmp_path):
    tables = {
        "tenants": [{"id": 1, "slug": "acme"}],
        "branches": [{"id": 5, "tenant_id": 1, "code": "B1"}],
        "tenant_stores": [{"id": 3, "tenant_id": 1, "store_slug": "shop"}],
        "customers": [{"id": 10, "tenant_id": 1}],
    }
    _write_scope_data(tmp_path, tables)
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker)
    next_id = iter(range(600, 700))
    mocker.patch(
        "services.backup_scoped_engine._new_id",
        side_effect=lambda conn, table: next(next_id),
    )
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_STORE, "tenant_id": 1, "store_id": 3, "branch_id": 5},
        "postgres://target",
        confirmation="REMAP CONFIRM",
        remap=True,
        target_tenant_id=77,
        target_branch_id=88,
        target_store_id=99,
    )
    assert result["ok"] is True
    assert result["target_tenant_id"] == 77


def test_restore_remap_missing_tenants_row(mocker, tmp_path):
    tables = {"customers": [{"id": 1, "tenant_id": 1}]}
    _write_scope_data(tmp_path, tables)
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker)
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="REMAP CONFIRM",
        remap=True,
    )
    assert result["ok"] is False


def test_restore_insert_warning_continues(mocker, tmp_path):
    tables = {
        "tenants": [{"id": 1, "slug": "acme"}],
        "customers": [{"id": 10, "tenant_id": 1}],
    }
    _write_scope_data(tmp_path, tables)
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker, insert_raises=RuntimeError("dup"))
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
    )
    assert result["ok"] is True
    assert result["warnings"]


def test_restore_skips_missing_table(mocker, tmp_path):
    tables = {"tenants": [{"id": 1, "slug": "acme"}], "ghost": [{"id": 1}]}
    _write_scope_data(tmp_path, tables)
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker, table_exists=False)
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
    )
    assert result["ok"] is True
    assert any("skip missing table" in w for w in result["warnings"])


def test_restore_uploads_tar_safe_extract(mocker, tmp_path):
    tables = {"tenants": [{"id": 1, "slug": "acme"}]}
    _write_scope_data(tmp_path, tables)
    uploads_dir = tmp_path / "uploads_restore"
    uploads_dir.mkdir()
    arc_path = tmp_path / "uploads.tar.gz"
    arc_path.write_bytes(b"fake")
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker)
    member_ok = mocker.MagicMock(name="ok.txt")
    member_ok.name = "ok.txt"
    member_bad = mocker.MagicMock(name="../evil.txt")
    member_bad.name = "../evil.txt"
    tar = mocker.MagicMock()
    tar.getmembers.return_value = [member_ok, member_bad]
    tar.__enter__.return_value = tar
    mocker.patch("tarfile.open", return_value=tar)
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
        restore_uploads_dir=str(uploads_dir),
        base_dir=str(tmp_path),
    )
    assert result["ok"] is True
    assert any("unsafe path" in w for w in result["warnings"])
    tar.extractall.assert_called_once()


def test_restore_uploads_tar_interrupted_stream(mocker, tmp_path):
    tables = {"tenants": [{"id": 1, "slug": "acme"}]}
    _write_scope_data(tmp_path, tables)
    uploads_dir = tmp_path / "uploads_restore"
    uploads_dir.mkdir()
    (tmp_path / "uploads.tar.gz").write_bytes(b"fake")
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker)
    mocker.patch("tarfile.open", side_effect=EOFError("truncated gzip"))
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
        restore_uploads_dir=str(uploads_dir),
        base_dir=str(tmp_path),
    )
    assert result["ok"] is False


def test_restore_prep_transaction_failure(mocker, tmp_path):
    tables = {"tenants": [{"id": 1, "slug": "acme"}]}
    _write_scope_data(tmp_path, tables)
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    conn = mocker.MagicMock()
    prep = mocker.MagicMock()
    prep.__enter__.return_value = conn
    prep.__exit__.return_value = None
    conn.begin.return_value = prep
    conn.execute.side_effect = RuntimeError("prep failed")
    engine = mocker.MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = None
    mocker.patch("sqlalchemy.create_engine", return_value=engine)
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="REMAP CONFIRM",
        remap=True,
    )
    assert result["ok"] is False


def test_ensure_target_schema_runs_core_data(mocker):
    mocker.patch.dict(
        os.environ,
        {"DATABASE_URL": "postgres://src", "SQLALCHEMY_DATABASE_URI": "postgres://src"},
    )
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=True
    )
    proc = mocker.MagicMock(returncode=0, stderr="", stdout="")
    mocker.patch("services.backup_exec.run_python_module", return_value=proc)
    app = mocker.MagicMock()
    ctx = mocker.MagicMock()
    ctx.__enter__ = mocker.MagicMock(return_value=None)
    ctx.__exit__ = mocker.MagicMock(return_value=False)
    app.app_context.return_value = ctx
    mocker.patch("app.create_app", return_value=app)
    mock_core = mocker.patch("utils.system_init.ensure_core_data", create=True)
    ok, err = ensure_target_schema("postgres://target")
    assert ok is True
    mock_core.assert_called_once()


def test_ensure_target_schema_pg_restore_alembic_probe_exception(mocker, tmp_path):
    schema_file = tmp_path / "schema.sql"
    mocker.patch.dict(os.environ, {"DATABASE_URL": "postgres://src/db"})
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_service.BackupService._parse_db_url",
        return_value={
            "host": "h",
            "port": "5432",
            "username": "u",
            "password": "",
            "dbname": "d",
        },
    )
    mocker.patch(
        "services.backup_service.BackupService._resolve_pg_tool",
        side_effect=lambda a, b: a,
    )
    dump_proc = mocker.MagicMock(returncode=0)
    restore_proc = mocker.MagicMock(returncode=1, stderr="schema warn", stdout="")
    mocker.patch(
        "services.backup_exec.run_pg_tool", side_effect=[dump_proc, restore_proc]
    )
    mocker.patch(
        "tempfile.NamedTemporaryFile",
        return_value=mocker.MagicMock(
            name=str(schema_file), __enter__=lambda s: s, __exit__=lambda *a: None
        ),
    )
    mocker.patch("os.path.isfile", return_value=True)
    mocker.patch("sqlalchemy.create_engine", side_effect=RuntimeError("probe fail"))
    ok, err = ensure_target_schema("postgres://tgt/db")
    assert ok is False
    assert "schema warn" in err


def test_restore_branch_remap(mocker, tmp_path):
    tables = {
        "tenants": [{"id": 1, "slug": "acme"}],
        "branches": [{"id": 5, "tenant_id": 1, "code": "B1"}],
        "customers": [{"id": 10, "tenant_id": 1, "branch_id": 5}],
    }
    _write_scope_data(tmp_path, tables)
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker)
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_BRANCH, "tenant_id": 1, "branch_id": 5},
        "postgres://target",
        confirmation="REMAP CONFIRM",
        remap=True,
        target_tenant_id=77,
        target_branch_id=88,
    )
    assert result["ok"] is True
    assert result["target_tenant_id"] == 77


def test_restore_branch_scope_delete(mocker, tmp_path):
    tables = {
        "tenants": [{"id": 1, "slug": "acme"}],
        "branches": [{"id": 5, "tenant_id": 1, "code": "B1"}],
        "customers": [{"id": 10, "tenant_id": 1, "branch_id": 5}],
    }
    _write_scope_data(tmp_path, tables)
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker, column_names=["id", "tenant_id", "branch_id"])
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_BRANCH, "tenant_id": 1, "branch_id": 5},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
    )
    assert result["ok"] is True


def test_restore_skips_empty_table_rows(mocker, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "tenants.jsonl").write_text(
        '{"id": 1, "slug": "acme"}\n', encoding="utf-8"
    )
    (data_dir / "customers.jsonl").write_text("", encoding="utf-8")
    (data_dir / "schema_meta.json").write_text(
        json.dumps({"table_order": ["tenants", "customers"]}),
        encoding="utf-8",
    )
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker)
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
    )
    assert result["ok"] is True


def test_restore_replication_role_errors(mocker, tmp_path):
    tables = {
        "tenants": [{"id": 1, "slug": "acme"}],
        "customers": [{"id": 10, "tenant_id": 1}],
    }
    _write_scope_data(tmp_path, tables)
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker, replication_role_raises=True)
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="RESTORE CONFIRM",
    )
    assert result["ok"] is True


def test_restore_remap_reuses_existing_id_map(mocker, tmp_path):
    tables = {
        "tenants": [{"id": 1, "slug": "acme"}],
        "customers": [
            {"id": 10, "tenant_id": 1, "name": "A"},
            {"id": 10, "tenant_id": 1, "name": "B"},
        ],
    }
    _write_scope_data(tmp_path, tables)
    mocker.patch(
        "services.backup_service.BackupService._urls_same_database", return_value=False
    )
    mocker.patch(
        "services.backup_scoped_engine.ensure_target_schema", return_value=(True, "")
    )
    _mock_restore_engine(mocker)
    next_id = iter(range(700, 710))
    mocker.patch(
        "services.backup_scoped_engine._new_id",
        side_effect=lambda conn, table: next(next_id),
    )
    result = restore_scoped_to_target(
        str(tmp_path),
        {"backup_scope": SCOPE_TENANT, "tenant_id": 1},
        "postgres://target",
        confirmation="REMAP CONFIRM",
        remap=True,
        target_tenant_id=77,
    )
    assert result["ok"] is True
