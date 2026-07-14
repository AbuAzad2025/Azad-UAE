"""Unit tests for BackupService — listing, verify, scoped/system backup, restore guards."""
from __future__ import annotations

import gzip
import io
import json
import os
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.backup_service import BACKUP_VERSION, BackupService
from services.backup_scope_config import SCOPE_BRANCH, SCOPE_STORE, SCOPE_SYSTEM, SCOPE_TENANT


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture
def backup_root(tmp_path, monkeypatch):
    """Redirect BACKUP_DIR and instance JSON paths to a temp tree."""
    root = tmp_path / "proj"
    root.mkdir()
    backups = root / "instance" / "backups"
    backups.mkdir(parents=True)
    monkeypatch.setattr(BackupService, "_BASEDIR", str(root))
    monkeypatch.setattr(BackupService, "BACKUP_DIR", str(backups))
    return backups


@pytest.fixture
def pg_tools(monkeypatch):
    monkeypatch.setenv("PG_DUMP_PATH", "")
    monkeypatch.setenv("PG_RESTORE_PATH", "")

    def _fake_resolve(_cls, exe_name, _env_var):
        return f"/usr/bin/{exe_name}"

    monkeypatch.setattr(BackupService, "_resolve_pg_tool", classmethod(_fake_resolve))


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _minimal_tar_gz(path: os.PathLike | str, member_name: str = "x.txt", content: bytes = b"x"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=member_name)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    Path(path).write_bytes(buf.getvalue())


def _make_system_archive(
    archive_path,
    *,
    db_content: bytes = b"PGDMP",
    manifest: dict | None = None,
    uploads_content: bytes | None = None,
):
    """Build a minimal azad system tar.gz for verify tests."""
    work = archive_path.parent / "_work"
    work.mkdir(exist_ok=True)
    db_path = work / "db.dump"
    db_path.write_bytes(db_content)
    uploads_path = work / "uploads.tar.gz"
    if uploads_content is not None:
        uploads_path.write_bytes(uploads_content)
    else:
        _minimal_tar_gz(uploads_path, "uploads/logo.png", b"PNG")

    if manifest is None:
        manifest = {
            "backup_version": BACKUP_VERSION,
            "format": "azad_tar_v1",
            "backup_scope": "system",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sha256": {},
        }
    manifest.setdefault("sha256", {})
    manifest["sha256"]["db.dump"] = BackupService._sha256_file(str(db_path))

    manifest_path = work / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(db_path, arcname="db.dump")
        tar.add(uploads_path, arcname="uploads.tar.gz")
        tar.add(manifest_path, arcname="manifest.json")
    return manifest


def _make_tenant_archive(archive_path, tenant_id=7, branch_id=None, store_id=None):
    scope = SCOPE_TENANT
    if branch_id is not None:
        scope = SCOPE_BRANCH
    elif store_id is not None:
        scope = SCOPE_STORE

    tables = {
        "tenants": [{"id": tenant_id, "slug": "acme", "name": "Acme"}],
        "products": [{"id": 1, "tenant_id": tenant_id, "name": "P1"}],
    }
    if branch_id is not None:
        tables["branches"] = [{"id": branch_id, "tenant_id": tenant_id, "name": "Main"}]
    if store_id is not None:
        tables["tenant_stores"] = [{"id": store_id, "tenant_id": tenant_id, "store_slug": "s1"}]

    manifest = {
        "backup_version": BACKUP_VERSION,
        "format": "azad_tar_v1",
        "backup_scope": scope,
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "store_id": store_id,
        "row_counts_per_table": {k: len(v) for k, v in tables.items()},
        "sha256": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    work = archive_path.parent / "_twork"
    data_dir = work / "data"
    data_dir.mkdir(parents=True)
    for table, rows in tables.items():
        lines = "\n".join(json.dumps(r) for r in rows)
        (data_dir / f"{table}.jsonl").write_text(lines, encoding="utf-8")
    (data_dir / "schema_meta.json").write_text("{}", encoding="utf-8")

    manifest_path = work / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(data_dir, arcname="data")
        tar.add(manifest_path, arcname="manifest.json")
    return manifest


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestRetentionAndInit:
    def test_retention_count_default(self, monkeypatch):
        monkeypatch.delenv("BACKUP_RETENTION_COUNT", raising=False)
        assert BackupService.retention_count() == 10

    def test_retention_count_env_override(self, monkeypatch):
        monkeypatch.setenv("BACKUP_RETENTION_COUNT", "5")
        assert BackupService.retention_count() == 5

    def test_retention_count_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("BACKUP_RETENTION_COUNT", "bad")
        assert BackupService.retention_count() == 10

    def test_initialize_creates_directory(self, backup_root):
        assert BackupService.initialize() is True
        assert backup_root.is_dir()


class TestJsonSchedule:
    def test_schedule_settings_defaults(self, backup_root):
        s = BackupService.get_schedule_settings()
        assert s["enabled"] is True
        assert s["frequency"] == "daily"
        assert s["backup_time"] == "02:00"

    def test_save_and_load_schedule_settings(self, backup_root):
        assert BackupService.save_schedule_settings({
            "enabled": False,
            "frequency": "weekly",
            "backup_time": "03:30",
            "keep_count": 7,
        })
        loaded = BackupService.get_schedule_settings()
        assert loaded["enabled"] is False
        assert loaded["frequency"] == "weekly"
        assert loaded["keep_count"] == 7

    def test_schedule_state_roundtrip(self, backup_root):
        BackupService._set_schedule_state(
            last_run_at="2026-01-01T00:00:00+00:00",
            last_error="none",
            last_filename="azad_backup_system_20260101_000000_abc.tar.gz",
        )
        state = BackupService.get_schedule_state()
        assert state["last_run_at"] == "2026-01-01T00:00:00+00:00"
        assert state["last_filename"].startswith("azad_backup_system")

    def test_load_json_missing_returns_none(self, backup_root):
        assert BackupService._load_json_file(str(backup_root / "missing.json")) is None

    def test_load_json_corrupt_logs_warning(self, backup_root, mocker):
        bad = backup_root / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        mocker.patch("services.logging_core.LoggingCore.log_error")
        assert BackupService._load_json_file(str(bad)) is None

    def test_write_json_failure_returns_false(self, mocker):
        mocker.patch("builtins.open", side_effect=OSError("denied"))
        mocker.patch("services.logging_core.LoggingCore.log_error")
        assert BackupService._write_json_file("/no/such/path/x.json", {"a": 1}) is False


class TestFilenameAndPaths:
    @pytest.mark.parametrize("name,ok", [
        ("azad_backup_system_20260101_120000_abc123.tar.gz", True),
        ("azad_backup_tenant_acme_20260101_120000_abc.tar.gz", True),
        ("azad_backup_20260101_120000_abc.tar.gz", True),
        ("manual_backup_old.sql.gz", True),
        ("../evil.tar.gz", False),
        ("not_a_backup.txt", False),
    ])
    def test_sanitize_filename(self, name, ok):
        result = BackupService.sanitize_filename(name)
        assert (result is not None) is ok

    def test_archive_basename_scopes(self):
        ts = "20260101_120000"
        sha = "deadbeef"
        assert "system" in BackupService._archive_basename(SCOPE_SYSTEM, ts, sha)
        assert "tenant_acme" in BackupService._archive_basename(
            SCOPE_TENANT, ts, sha, tenant_slug="acme"
        )
        assert "branch_5" in BackupService._archive_basename(
            SCOPE_BRANCH, ts, sha, branch_id=5
        )
        assert "store_9" in BackupService._archive_basename(
            SCOPE_STORE, ts, sha, store_id=9
        )

    def test_mask_db_host(self):
        assert BackupService._mask_db_host("127.0.0.1") == "127.0.0.1"
        assert BackupService._mask_db_host("db.example.com") == "db.***.com"
        assert BackupService._mask_db_host("") == "***"

    def test_urls_same_database(self):
        a = "postgresql://user:pass@127.0.0.1:5432/mydb"
        b = "postgresql://user:pass@localhost:5432/mydb"
        assert BackupService._urls_same_database(a, b) is True
        c = "postgresql://user:pass@127.0.0.1:5432/otherdb"
        assert BackupService._urls_same_database(a, c) is False

    def test_parse_db_url_postgres(self):
        params = BackupService._parse_db_url(
            "postgresql://u:p@db.host.example:5432/proddb",
        )
        assert params["host"] == "db.host.example"
        assert params["dbname"] == "proddb"
        assert params["port"] == "5432"

    def test_parse_db_url_non_postgres_returns_none(self):
        assert BackupService._parse_db_url("sqlite:///tmp.db") is None


class TestEnvRedacted:
    def test_masks_secrets(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:secret@host/db")
        monkeypatch.setenv("SECRET_KEY", "supersecret")
        monkeypatch.setenv("BASE_URL", "https://app.example.com/path?q=1")
        monkeypatch.setenv("BACKUP_RETENTION_COUNT", "12")
        out = BackupService._build_env_redacted()
        assert out["DATABASE_URL"] == "***masked***"
        assert out["SECRET_KEY"] == "***masked***"
        assert "example.com" in out["BASE_URL"]
        assert out["BACKUP_RETENTION_COUNT"] == "12"


class TestListAndStats:
    def test_list_backups_newest_first(self, backup_root):
        older = backup_root / "azad_backup_system_20260101_000000_aaaa.tar.gz"
        newer = backup_root / "azad_backup_system_20260201_000000_bbbb.tar.gz"
        older.write_bytes(b"x")
        newer.write_bytes(b"xy")
        os.utime(older, (1_700_000_000, 1_700_000_000))
        os.utime(newer, (1_800_000_000, 1_800_000_000))

        listed = BackupService.list_backups()
        assert len(listed) == 2
        assert listed[0]["filename"] == newer.name

    def test_list_backups_auto_only_filter(self, backup_root):
        (backup_root / "azad_backup_system_auto_20260101_000000_aa.tar.gz").write_bytes(b"a")
        (backup_root / "azad_backup_system_20260102_000000_bb.tar.gz").write_bytes(b"b")
        auto = BackupService.list_backups(auto_only=True)
        assert len(auto) == 1
        assert "auto" in auto[0]["filename"].lower()

    def test_get_backup_stats(self, backup_root, mocker):
        mocker.patch.object(BackupService, "list_backups", return_value=[
            {"size": 1024 * 1024, "format": "azad_tar_v1", "manual": True},
            {"size": 0, "format": "legacy", "manual": False},
        ])
        stats = BackupService.get_backup_stats()
        assert stats["total_count"] == 2
        assert stats["modern_count"] == 1
        assert stats["manual_count"] == 1
        assert stats["total_size_mb"] == 1.0

    def test_get_backup_stats_on_error(self, mocker):
        mocker.patch.object(BackupService, "list_backups", side_effect=RuntimeError("boom"))
        stats = BackupService.get_backup_stats()
        assert stats["total_count"] == 0


class TestCryptoAndUploads:
    def test_sha256_file(self, tmp_path):
        p = tmp_path / "f.bin"
        p.write_bytes(b"hello backup")
        digest = BackupService._sha256_file(str(p))
        assert len(digest) == 64

    def test_write_checksums_file(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("data", encoding="utf-8")
        out = BackupService._write_checksums_file(str(tmp_path), ["a.txt"])
        assert os.path.isfile(out)
        assert "a.txt" in open(out, encoding="utf-8").read()

    def test_build_uploads_archive(self, backup_root, monkeypatch):
        uploads = backup_root.parent.parent / "static" / "uploads"
        uploads.mkdir(parents=True)
        (uploads / "logo.png").write_bytes(b"\x89PNG")
        monkeypatch.setattr(BackupService, "_BASEDIR", str(backup_root.parent.parent))
        dest = backup_root / "uploads.tar.gz"
        meta = BackupService._build_uploads_archive(str(dest))
        assert dest.is_file()
        assert meta["files_packed"] >= 1

    def test_write_readme_restore(self, tmp_path):
        path = tmp_path / "README_RESTORE.txt"
        BackupService._write_readme_restore(str(path))
        text = path.read_text(encoding="utf-8")
        assert "pg_restore" in text


class TestManifestSidecar:
    def test_build_manifest_and_sidecar(self, backup_root, mocker):
        mocker.patch.object(BackupService, "_git_branch", return_value="main")
        params = {"host": "127.0.0.1", "port": "5432", "username": "u", "dbname": "db"}
        manifest = BackupService._build_manifest(
            scope="system",
            short_sha="abc",
            alembic_current="rev1",
            alembic_heads="rev1",
            params=params,
            pre_checks={"tables_count": 10},
            approx_rows=100,
            file_hashes={"db.dump": "hash"},
            tools={"pg_dump_version": "16"},
            uploads_meta={"files_packed": 2},
            manual=True,
            description="test",
            created_by={"user_id": 1, "role": "owner"},
            tables_included=["full_database"],
            tables_excluded=[],
            row_counts_per_table={},
            allowed_restore_scope="system_new_database_only",
        )
        assert manifest["backup_scope"] == "system"
        assert manifest["backup_version"] == BACKUP_VERSION

        archive = backup_root / "x.tar.gz"
        archive.write_bytes(b"data")
        sidecar = BackupService._build_sidecar(
            archive.name, str(archive), manifest, "20260101_120000",
            archive.stat().st_size, "abc", "rev1", True, "test",
        )
        assert sidecar["format"] == "azad_tar_v1"
        assert sidecar["checksum"] == BackupService._sha256_file(str(archive))


class TestAccessControl:
    def test_list_backups_for_owner_sees_all(self, mocker):
        user = MagicMock()
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=True)
        mocker.patch.object(BackupService, "list_backups", return_value=[{"filename": "a"}])
        assert BackupService.list_backups_for_user(user) == [{"filename": "a"}]

    def test_list_backups_for_tenant_user_filters_system(self, mocker):
        user = MagicMock(branch_id=3)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=7)
        backups = [
            {"filename": "sys", "backup_scope": "system"},
            {"filename": "ten", "backup_scope": "tenant", "tenant_id": 7},
            {"filename": "other", "backup_scope": "tenant", "tenant_id": 99},
            {"filename": "br", "backup_scope": "branch", "tenant_id": 7, "branch_id": 3},
            {"filename": "br2", "backup_scope": "branch", "tenant_id": 7, "branch_id": 99},
        ]
        mocker.patch.object(BackupService, "list_backups", return_value=backups)
        filtered = BackupService.list_backups_for_user(user)
        names = {b["filename"] for b in filtered}
        assert "sys" not in names
        assert "ten" in names
        assert "other" not in names
        assert "br" in names
        assert "br2" not in names

    def test_user_may_access_backup(self, mocker):
        user = MagicMock(branch_id=2)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=5)
        mocker.patch.object(BackupService, "get_backup_info", return_value={
            "manifest": {"backup_scope": "branch", "tenant_id": 5, "branch_id": 2},
        })
        assert BackupService.user_may_access_backup(user, "azad_backup_branch_2_20260101_000000_ab.tar.gz")

    def test_get_list_backups_context_tenant_user(self, mocker, sample_tenant, sample_branch, sample_user):
        user = MagicMock()
        user.branch_id = sample_branch.id
        mocker.patch("services.backup_service.is_global_owner_user", return_value=False)
        mocker.patch("services.backup_service.get_active_tenant_id", return_value=sample_tenant.id)
        mocker.patch.object(BackupService, "list_backups_for_user", return_value=[])
        mocker.patch.object(BackupService, "get_backup_stats", return_value={})
        mocker.patch.object(BackupService, "get_schedule_settings", return_value={})
        mocker.patch.object(BackupService, "get_schedule_state", return_value={})
        mocker.patch.object(BackupService, "pg_tools_status", return_value={})
        ctx = BackupService.get_list_backups_context(user)
        assert ctx["is_platform_owner"] is False
        assert len(ctx["branches"]) >= 1

    def test_user_may_access_owner_always(self, mocker):
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=True)
        assert BackupService.user_may_access_backup(MagicMock(), "any/../x") is False
        assert BackupService.user_may_access_backup(
            MagicMock(), "azad_backup_system_20260101_000000_abcd.tar.gz",
        ) is True

    def test_user_may_access_denies_system_scope(self, mocker):
        user = MagicMock()
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        mocker.patch.object(BackupService, "get_backup_info", return_value={
            "manifest": {"backup_scope": "system", "tenant_id": 1},
        })
        name = "azad_backup_system_20260101_000000_abcd.tar.gz"
        assert BackupService.user_may_access_backup(user, name) is False

    def test_get_list_backups_context_owner(self, mocker, sample_tenant):
        user = MagicMock()
        mocker.patch("services.backup_service.is_global_owner_user", return_value=True)
        mocker.patch.object(BackupService, "list_backups", return_value=[])
        mocker.patch.object(BackupService, "get_backup_stats", return_value={})
        mocker.patch.object(BackupService, "get_schedule_settings", return_value={})
        mocker.patch.object(BackupService, "get_schedule_state", return_value={})
        mocker.patch.object(BackupService, "pg_tools_status", return_value={})
        ctx = BackupService.get_list_backups_context(user)
        assert ctx["is_platform_owner"] is True
        assert len(ctx["tenants"]) >= 1


class TestVerifyBackup:
    def test_verify_missing_backup(self, backup_root):
        result = BackupService.verify_backup("azad_backup_system_20260101_000000_aa.tar.gz")
        assert result["valid"] is False
        assert "not found" in result["errors"][0]

    def test_verify_system_archive_valid(self, backup_root, mocker, pg_tools):
        name = "azad_backup_system_20260101_120000_cafe.tar.gz"
        path = backup_root / name
        _make_system_archive(path)
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        result = BackupService.verify_backup(name)
        assert result["valid"] is True
        assert result["format"] == "azad_tar_v1"

    def test_verify_checksum_mismatch(self, backup_root):
        name = "azad_backup_system_20260101_120000_dead.tar.gz"
        path = backup_root / name
        _make_system_archive(path)
        sidecar = {
            "checksum": "0" * 64,
            "format": "azad_tar_v1",
        }
        (backup_root / f"{name}.meta.json").write_text(json.dumps(sidecar), encoding="utf-8")
        result = BackupService.verify_backup(name)
        assert result["valid"] is False
        assert "checksum mismatch" in result["errors"][0]

    def test_verify_tenant_archive(self, backup_root, mocker, pg_tools):
        name = "azad_backup_tenant_acme_20260101_120000_beef.tar.gz"
        path = backup_root / name
        _make_tenant_archive(path, tenant_id=7)
        result = BackupService.verify_backup(name)
        assert result["valid"] is True
        assert result["backup_scope"] == SCOPE_TENANT

    def test_verify_legacy_gzip(self, backup_root):
        name = "manual_backup_legacy.sql.gz"
        path = backup_root / name
        with gzip.open(path, "wb") as gz:
            gz.write(b"-- sql")
        result = BackupService.verify_backup(name)
        assert result["valid"] is True
        assert result["format"] == "legacy"

    def test_verify_tenant_export_mismatch(self, backup_root):
        export = backup_root / "export.json"
        export.write_text(json.dumps({
            "tenant_id": 99,
            "tables": {"tenants": [{"id": 99}]},
        }), encoding="utf-8")
        manifest = {"backup_scope": "tenant", "tenant_id": 7, "row_counts_per_table": {}}
        out = BackupService._verify_tenant_export(str(export), manifest)
        assert out["ok"] is False
        assert any("tenant_id mismatch" in e for e in out["errors"])

    def test_verify_legacy_dump_with_pg_restore(self, backup_root, mocker, pg_tools):
        name = "manual_backup_data.dump"
        path = backup_root / name
        path.write_bytes(b"PGDMP")
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 0),
        )
        result = BackupService.verify_backup(name)
        assert result["valid"] is True

    def test_verify_branch_archive(self, backup_root):
        name = "azad_backup_branch_3_20260101_120000_beef.tar.gz"
        path = backup_root / name
        _make_tenant_archive(path, tenant_id=7, branch_id=3)
        result = BackupService.verify_backup(name)
        assert result["valid"] is True
        assert result["backup_scope"] == SCOPE_BRANCH

    def test_verify_empty_file(self, backup_root):
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        (backup_root / name).write_bytes(b"")
        result = BackupService.verify_backup(name)
        assert "empty file" in result["errors"][0]


class TestCreateBackupGuards:
    def test_create_backup_unknown_scope(self, backup_root):
        assert BackupService.create_backup(scope="invalid") is None

    def test_create_backup_tenant_requires_id(self, backup_root):
        assert BackupService.create_backup(scope=SCOPE_TENANT) is None

    def test_create_backup_branch_requires_ids(self, backup_root):
        assert BackupService.create_backup(scope=SCOPE_BRANCH, tenant_id=1) is None

    def test_create_backup_store_requires_ids(self, backup_root):
        assert BackupService.create_backup(scope=SCOPE_STORE, tenant_id=1) is None


class TestSystemBackupFlow:
    def test_create_system_backup_success(self, backup_root, mocker, monkeypatch, pg_tools):
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://u:p@127.0.0.1:5432/testdb",
        )
        mocker.patch.object(BackupService, "_git_short_sha", return_value="abc123")
        mocker.patch.object(BackupService, "_alembic_info", return_value=("r1", "r1"))
        mocker.patch.object(BackupService, "_pre_backup_checks_summary", return_value={"checks": []})
        mocker.patch.object(BackupService, "_apply_retention")

        def fake_uploads(dest_path):
            _minimal_tar_gz(dest_path)
            return {"files_packed": 0}

        mocker.patch.object(BackupService, "_build_uploads_archive", side_effect=fake_uploads)

        def fake_dump(params, dest):
            with open(dest, "wb") as f:
                f.write(b"PGDMP")
            return True, ""

        mocker.patch.object(BackupService, "_run_pg_dump_custom", side_effect=fake_dump)
        mocker.patch(
            "sqlalchemy.create_engine",
        )
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.scalar.return_value = 42
        mock_engine.connect.return_value = mock_conn
        mocker.patch("sqlalchemy.create_engine", return_value=mock_engine)

        sidecar = BackupService.create_backup(
            manual=True, description="unit test", scope=SCOPE_SYSTEM,
        )
        assert sidecar is not None
        assert sidecar["format"] == "azad_tar_v1"
        assert (backup_root / sidecar["filename"]).is_file()
        assert (backup_root / f"{sidecar['filename']}.meta.json").is_file()

    def test_create_system_backup_no_pg_dump(self, backup_root, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mocker.patch.object(BackupService, "pg_tools_status", return_value={"pg_dump": None})
        assert BackupService.create_backup(scope=SCOPE_SYSTEM) is None

    def test_run_pg_dump_custom_failure(self, backup_root, mocker):
        mocker.patch.object(BackupService, "_resolve_pg_tool", return_value="/usr/bin/pg_dump")
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="fail"),
        )
        ok, err = BackupService._run_pg_dump_custom(
            {"host": "127.0.0.1", "port": "5432", "username": "u", "password": "p", "dbname": "d"},
            str(backup_root / "out.dump"),
        )
        assert ok is False
        assert "fail" in err


class TestScopedBackupFlow:
    def test_create_tenant_backup_success(self, backup_root, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        tid = 42
        mocker.patch.object(BackupService, "_fetch_tenant_row", return_value={
            "id": tid, "slug": "acme", "name": "Acme",
        })
        mocker.patch.object(BackupService, "_git_short_sha", return_value="sha1")
        mocker.patch.object(BackupService, "_alembic_info", return_value=(None, None))
        mocker.patch.object(BackupService, "_pre_backup_checks_summary", return_value={})
        mocker.patch.object(BackupService, "pg_tools_status", return_value={})
        mocker.patch.object(BackupService, "_apply_retention")

        tables = {"tenants": [{"id": tid, "slug": "acme", "name": "Acme"}]}
        mocker.patch(
            "services.backup_scope_config.export_scoped_database",
            return_value=(tables, {"tenants": 1}, ["tenants"], [], []),
        )
        mocker.patch(
            "services.backup_scope_config.collect_scoped_upload_paths",
            return_value=([], []),
        )

        def fake_uploads_archive(paths, dest, base):
            _minimal_tar_gz(dest)
            return {"files_packed": 0}

        mocker.patch(
            "services.backup_scope_config.build_tenant_uploads_archive",
            side_effect=fake_uploads_archive,
        )

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn
        mocker.patch("sqlalchemy.create_engine", return_value=mock_engine)

        sidecar = BackupService.create_backup(
            scope=SCOPE_TENANT, tenant_id=tid, description="tenant backup",
        )
        assert sidecar is not None
        assert "tenant_acme" in sidecar["filename"]

    def test_scoped_backup_missing_tenant(self, backup_root, mocker):
        mocker.patch.object(BackupService, "_fetch_tenant_row", return_value=None)
        assert BackupService.create_backup(scope=SCOPE_TENANT, tenant_id=999) is None

    def test_create_branch_backup_success(self, backup_root, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        tid, bid = 42, 3
        mocker.patch.object(BackupService, "_fetch_tenant_row", return_value={
            "id": tid, "slug": "acme", "name": "Acme",
        })
        mocker.patch.object(BackupService, "_git_short_sha", return_value="sha1")
        mocker.patch.object(BackupService, "_alembic_info", return_value=(None, None))
        mocker.patch.object(BackupService, "_pre_backup_checks_summary", return_value={})
        mocker.patch.object(BackupService, "pg_tools_status", return_value={})
        mocker.patch.object(BackupService, "_apply_retention")
        mocker.patch(
            "services.backup_scope_config.export_scoped_database",
            return_value=({
                "tenants": [{"id": tid, "slug": "acme", "name": "Acme"}],
                "branches": [{"id": bid, "tenant_id": tid, "name": "Main"}],
            }, {"tenants": 1, "branches": 1}, ["tenants", "branches"], [], []),
        )
        mocker.patch(
            "services.backup_scope_config.collect_scoped_upload_paths",
            return_value=([], []),
        )

        def fake_uploads_archive(paths, dest, base):
            _minimal_tar_gz(dest)
            return {"files_packed": 0}

        mocker.patch(
            "services.backup_scope_config.build_tenant_uploads_archive",
            side_effect=fake_uploads_archive,
        )
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn
        mocker.patch("sqlalchemy.create_engine", return_value=mock_engine)
        sidecar = BackupService.create_backup(
            scope=SCOPE_BRANCH, tenant_id=tid, branch_id=bid,
        )
        assert sidecar is not None
        assert "branch_3" in sidecar["filename"]

    def test_create_store_backup_success(self, backup_root, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        tid, sid = 42, 9
        mocker.patch.object(BackupService, "_fetch_tenant_row", return_value={
            "id": tid, "slug": "acme", "name": "Acme",
        })
        mocker.patch.object(BackupService, "_git_short_sha", return_value="sha1")
        mocker.patch.object(BackupService, "_alembic_info", return_value=(None, None))
        mocker.patch.object(BackupService, "_pre_backup_checks_summary", return_value={})
        mocker.patch.object(BackupService, "pg_tools_status", return_value={})
        mocker.patch.object(BackupService, "_apply_retention")
        mocker.patch(
            "services.backup_scope_config.export_scoped_database",
            return_value=({
                "tenants": [{"id": tid, "slug": "acme", "name": "Acme"}],
                "tenant_stores": [{"id": sid, "tenant_id": tid, "store_slug": "s1"}],
            }, {"tenants": 1, "tenant_stores": 1}, ["tenants", "tenant_stores"], [], []),
        )
        mocker.patch(
            "services.backup_scope_config.collect_scoped_upload_paths",
            return_value=([], []),
        )

        def fake_uploads_archive(paths, dest, base):
            _minimal_tar_gz(dest)
            return {"files_packed": 0}

        mocker.patch(
            "services.backup_scope_config.build_tenant_uploads_archive",
            side_effect=fake_uploads_archive,
        )
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn
        mocker.patch("sqlalchemy.create_engine", return_value=mock_engine)
        sidecar = BackupService.create_backup(
            scope=SCOPE_STORE, tenant_id=tid, store_id=sid,
        )
        assert sidecar is not None
        assert "store_9" in sidecar["filename"]


class TestRetentionAndDelete:
    def test_apply_retention_deletes_oldest(self, backup_root, mocker):
        mocker.patch.object(BackupService, "retention_count", return_value=1)
        backups = [
            {"filename": "old.tar.gz", "format": "azad_tar_v1", "timestamp": "20260101"},
            {"filename": "new.tar.gz", "format": "azad_tar_v1", "timestamp": "20260201"},
        ]
        mocker.patch.object(BackupService, "list_backups", return_value=backups)
        deleted = []
        mocker.patch.object(BackupService, "delete_backup", side_effect=lambda f: deleted.append(f) or True)
        BackupService._apply_retention()
        assert "old.tar.gz" in deleted

    def test_delete_backup(self, backup_root):
        name = "azad_backup_system_20260101_000000_dead.tar.gz"
        path = backup_root / name
        path.write_bytes(b"x")
        (backup_root / f"{name}.meta.json").write_text("{}", encoding="utf-8")
        assert BackupService.delete_backup(name) is True
        assert not path.exists()

    def test_auto_backup_disabled(self, backup_root, mocker):
        mocker.patch.object(BackupService, "get_schedule_settings", return_value={"enabled": False})
        assert BackupService.auto_backup_daily() is None

    def test_auto_backup_enabled(self, backup_root, mocker):
        mocker.patch.object(
            BackupService, "get_schedule_settings",
            return_value={"enabled": True, "frequency": "daily"},
        )
        mocker.patch.object(BackupService, "create_backup", return_value={"filename": "x.tar.gz"})
        assert BackupService.auto_backup_daily()["filename"] == "x.tar.gz"


class TestPrepareRestore:
    def test_prepare_restore_system(self, backup_root, mocker, pg_tools):
        name = "azad_backup_system_20260101_120000_ab.tar.gz"
        mocker.patch.object(BackupService, "get_backup_info", return_value={
            "manifest": {"backup_scope": "system"},
        })
        plan = BackupService.prepare_restore_command(name)
        assert plan["ok"] is True
        assert any("pg_restore" in cmd for cmd in plan["commands"])

    def test_prepare_restore_tenant_remap_guard(self, mocker):
        mocker.patch.object(BackupService, "get_backup_info", return_value={
            "manifest": {"backup_scope": "tenant", "tenant_id": 7},
        })
        plan = BackupService.prepare_restore_command(
            "azad_backup_tenant_x_20260101_000000_ab.tar.gz",
            target_tenant_id=99,
            remap=False,
        )
        assert plan["ok"] is False

    def test_prepare_restore_wrapper(self, mocker):
        mocker.patch.object(
            BackupService, "prepare_restore_command",
            return_value={"ok": True},
        )
        assert BackupService.prepare_restore("f.tar.gz")["ok"] is True


class TestRestoreToTarget:
    def test_restore_requires_confirmation(self, backup_root):
        out = BackupService.restore_backup_to_target_db(
            "azad_backup_system_20260101_000000_ab.tar.gz",
            "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="WRONG",
        )
        assert out["ok"] is False

    def test_restore_blocks_same_database(self, backup_root, mocker, monkeypatch):
        url = "postgresql://u:p@127.0.0.1:5432/samedb"
        monkeypatch.setenv("DATABASE_URL", url)
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": True})
        name = "azad_backup_system_20260101_120000_ab.tar.gz"
        path = backup_root / name
        _make_system_archive(path)
        out = BackupService.restore_backup_to_target_db(
            name, url, confirmation="RESTORE CONFIRM",
        )
        assert out["ok"] is False
        assert "same as current" in out["errors"][0]

    def test_restore_success(self, backup_root, mocker, monkeypatch, pg_tools):
        current = "postgresql://u:p@127.0.0.1:5432/live"
        target = "postgresql://u:p@127.0.0.1:5432/restore_db"
        monkeypatch.setenv("DATABASE_URL", current)
        name = "azad_backup_system_20260101_120000_ab.tar.gz"
        path = backup_root / name
        _make_system_archive(path)
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": True})
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        out = BackupService.restore_backup_to_target_db(
            name, target, confirmation="RESTORE CONFIRM",
        )
        assert out["ok"] is True
        assert out["target_db"] == "restore_db"

    def test_restore_with_uploads(self, backup_root, mocker, monkeypatch, pg_tools):
        current = "postgresql://u:p@127.0.0.1:5432/live"
        target = "postgresql://u:p@127.0.0.1:5432/restore_db"
        monkeypatch.setenv("DATABASE_URL", current)
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        _make_system_archive(path)
        uploads_root = backup_root.parent.parent / "static" / "uploads"
        uploads_root.mkdir(parents=True, exist_ok=True)
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": True})
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        out = BackupService.restore_backup_to_target_db(
            name, target, confirmation="RESTORE CONFIRM", restore_uploads=True,
        )
        assert out["ok"] is True
        assert any("uploads restored" in w for w in out.get("warnings", []))


class TestRestoreScoped:
    def test_restore_scoped_delegates(self, backup_root, mocker, monkeypatch, pg_tools):
        name = "azad_backup_tenant_acme_20260101_120000_ab.tar.gz"
        path = backup_root / name
        manifest = _make_tenant_archive(path, tenant_id=7)
        mocker.patch.object(BackupService, "verify_backup", return_value={
            "valid": True, "manifest": manifest,
        })
        mocker.patch(
            "services.backup_scoped_engine.restore_scoped_to_target",
            return_value={"ok": True, "target_tenant_id": 7},
        )
        mocker.patch(
            "services.backup_scoped_engine.verify_scoped_isolation",
            return_value={"ok": True},
        )
        mocker.patch(
            "services.backup_scoped_restore.verify_scoped_restore",
            return_value={"ok": True},
        )
        out = BackupService.restore_scoped_backup_to_target_db(
            name,
            "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="RESTORE CONFIRM",
        )
        assert out["ok"] is True

    def test_restore_scoped_verify_failure(self, backup_root, mocker, pg_tools):
        name = "azad_backup_tenant_acme_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        manifest = _make_tenant_archive(path, tenant_id=7)
        mocker.patch.object(BackupService, "verify_backup", return_value={
            "valid": True, "manifest": manifest,
        })
        mocker.patch(
            "services.backup_scoped_engine.restore_scoped_to_target",
            return_value={"ok": True, "target_tenant_id": 7},
        )
        mocker.patch(
            "services.backup_scoped_engine.verify_scoped_isolation",
            return_value={"ok": True},
        )
        mocker.patch(
            "services.backup_scoped_restore.verify_scoped_restore",
            return_value={"ok": False, "errors": ["row mismatch"]},
        )
        out = BackupService.restore_scoped_backup_to_target_db(
            name, "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="RESTORE CONFIRM",
        )
        assert out["ok"] is False


class TestMisc:
    def test_write_restore_proof(self, backup_root):
        name = "azad_backup_system_20260101_120000_ab.tar.gz"
        path = BackupService.write_restore_proof(name, {
            "verified_at": "2026-01-01",
            "backup_scope": "system",
        })
        assert os.path.isfile(path)
        assert (backup_root / ".latest_restore_proof.json").is_file()

    def test_deprecated_restore_blocked(self):
        assert BackupService.restore_backup("any.tar.gz") is False
        assert BackupService.restore_custom_tables("any.tar.gz", ["users"]) is False

    def test_get_backup_info_with_sidecar(self, backup_root):
        name = "azad_backup_system_20260101_120000_ab.tar.gz"
        path = backup_root / name
        _make_system_archive(path)
        sidecar = {"filename": name, "format": "azad_tar_v1"}
        (backup_root / f"{name}.meta.json").write_text(json.dumps(sidecar), encoding="utf-8")
        info = BackupService.get_backup_info(name)
        assert info["sidecar"]["format"] == "azad_tar_v1"
        assert info["manifest"]["backup_scope"] == "system"

    def test_pg_tools_status(self, mocker, pg_tools):
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 0, stdout="pg_dump 16.1\n", stderr=""),
        )
        status = BackupService.pg_tools_status()
        assert status["available"] is True
        assert "16" in status["pg_dump_version"]

    def test_git_short_sha_fallback(self, mocker):
        mocker.patch(
            "services.backup_exec.run_git",
            side_effect=RuntimeError("no git"),
        )
        assert BackupService._git_short_sha() == "unknown"

    def test_pre_backup_checks_no_postgres(self, mocker):
        mocker.patch.object(BackupService, "_parse_db_url", return_value=None)
        summary = BackupService._pre_backup_checks_summary()
        assert "postgresql_url: FAIL" in summary["checks"][0]


class TestExtendedHelpers:
    def test_fetch_tenant_row(self, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = (7, "acme", "Acme", True)
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn
        mocker.patch("sqlalchemy.create_engine", return_value=mock_engine)
        row = BackupService._fetch_tenant_row(7)
        assert row == {"id": 7, "slug": "acme", "name": "Acme", "enable_auto_backup": True}

    def test_pre_backup_checks_integrity_ok(self, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mocker.patch.object(BackupService, "_parse_db_url", return_value={
            "host": "127.0.0.1", "port": "5432", "username": "u", "dbname": "db",
        })
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.scalar.side_effect = [10, 0, 0]
        mocker.patch("sqlalchemy.create_engine", return_value=MagicMock(
            connect=MagicMock(return_value=mock_conn),
        ))
        summary = BackupService._pre_backup_checks_summary()
        assert summary["tables_count"] == 10
        assert summary["checks"][-1] == "basic_integrity: OK"

    def test_alembic_info(self, mocker):
        mocker.patch("flask_migrate.current", return_value="rev_a")
        mocker.patch("flask_migrate.heads", return_value="rev_b")
        cur, heads = BackupService._alembic_info()
        assert cur == "rev_a"
        assert heads == "rev_b"

    def test_upload_roots_extra_folder(self, backup_root, app):
        extra = Path(BackupService._BASEDIR) / "custom_uploads"
        extra.mkdir()
        app.config["UPLOAD_FOLDER"] = "custom_uploads"
        with app.app_context():
            roots = BackupService._upload_roots()
        assert any("custom_uploads" in r for r in roots)

    def test_git_branch_success(self, mocker):
        mocker.patch(
            "services.backup_exec.run_git",
            return_value=subprocess.CompletedProcess([], 0, stdout="main\n", stderr=""),
        )
        assert BackupService._git_branch() == "main"

    def test_run_pg_dump_no_tool(self, mocker):
        mocker.patch.object(BackupService, "_resolve_pg_tool", return_value=None)
        ok, err = BackupService._run_pg_dump_custom(
            {"host": "127.0.0.1", "port": "5432", "username": "u", "dbname": "d"},
            "out.dump",
        )
        assert ok is False
        assert "pg_dump not found" in err

    def test_run_pg_dump_empty_output(self, backup_root, mocker, pg_tools):
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        dest = backup_root / "empty.dump"
        dest.write_bytes(b"")
        ok, err = BackupService._run_pg_dump_custom(
            {"host": "127.0.0.1", "port": "5432", "username": "u", "dbname": "d"},
            str(dest),
        )
        assert ok is False
        assert "empty file" in err

    def test_initialize_failure(self, mocker):
        mocker.patch("os.makedirs", side_effect=OSError("denied"))
        assert BackupService.initialize() is False

    def test_list_backups_skips_non_files(self, backup_root):
        (backup_root / "subdir").mkdir()
        (backup_root / "junk.txt").write_text("x", encoding="utf-8")
        assert BackupService.list_backups() == []

    def test_list_backups_infers_system_scope(self, mocker):
        user = MagicMock(branch_id=1)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        backups = [{"filename": "azad_backup_system_20260101_000000_abcd.tar.gz"}]
        mocker.patch.object(BackupService, "list_backups", return_value=backups)
        assert BackupService.list_backups_for_user(user) == []

    def test_store_scope_listed_for_tenant_user(self, mocker):
        user = MagicMock(branch_id=1)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=5)
        item = {"filename": "s", "backup_scope": "store", "tenant_id": 5}
        mocker.patch.object(BackupService, "list_backups", return_value=[item])
        assert BackupService.list_backups_for_user(user) == [item]

    def test_delete_backup_failure(self, backup_root, mocker):
        name = "azad_backup_system_20260101_000000_abcd.tar.gz"
        (backup_root / name).write_bytes(b"x")
        mocker.patch("os.remove", side_effect=OSError("locked"))
        assert BackupService.delete_backup(name) is False

    def test_parse_db_url_localhost_normalized(self):
        params = BackupService._parse_db_url("postgresql://u:p@localhost:5432/db")
        assert params["host"] == "127.0.0.1"

    def test_write_checksums_data_directory(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir()
        (data / "t.jsonl").write_text('{"a":1}', encoding="utf-8")
        out = BackupService._write_checksums_file(str(tmp_path), ["data"])
        content = open(out, encoding="utf-8").read()
        assert "data/t.jsonl" in content

    def test_get_list_backups_context_no_active_tenant(self, mocker):
        user = MagicMock()
        mocker.patch("services.backup_service.is_global_owner_user", return_value=False)
        mocker.patch("services.backup_service.get_active_tenant_id", return_value=None)
        mocker.patch.object(BackupService, "list_backups_for_user", return_value=[])
        mocker.patch.object(BackupService, "get_backup_stats", return_value={})
        mocker.patch.object(BackupService, "get_schedule_settings", return_value={})
        mocker.patch.object(BackupService, "get_schedule_state", return_value={})
        mocker.patch.object(BackupService, "pg_tools_status", return_value={})
        ctx = BackupService.get_list_backups_context(user)
        assert ctx["branches"] == []
        assert ctx["stores"] == []

    def test_pre_backup_checks_missing_database_url(self, mocker):
        mocker.patch.object(BackupService, "_parse_db_url", return_value={
            "host": "127.0.0.1", "port": "5432", "username": "u", "dbname": "db",
        })
        mocker.patch.dict(os.environ, {}, clear=True)
        summary = BackupService._pre_backup_checks_summary()
        assert "database_url: missing" in summary["checks"][0]

    def test_apply_retention_keeps_when_under_limit(self, mocker):
        mocker.patch.object(BackupService, "retention_count", return_value=5)
        mocker.patch.object(BackupService, "list_backups", return_value=[
            {"filename": "a.tar.gz", "format": "azad_tar_v1", "timestamp": "1"},
        ])
        mocker.patch.object(BackupService, "delete_backup")
        BackupService._apply_retention()
        BackupService.delete_backup.assert_not_called()

    def test_verify_tenant_export_rejects_owner_user(self, backup_root):
        export = backup_root / "export.json"
        export.write_text(json.dumps({
            "tenant_id": 7,
            "tables": {
                "tenants": [{"id": 7}],
                "users": [{"id": 1, "tenant_id": 7, "is_owner": True}],
            },
        }), encoding="utf-8")
        out = BackupService._verify_tenant_export(str(export), {
            "backup_scope": "tenant", "tenant_id": 7, "row_counts_per_table": {},
        })
        assert out["ok"] is False

    def test_verify_legacy_gzip_corrupt(self, backup_root):
        name = "manual_backup_bad.sql.gz"
        (backup_root / name).write_bytes(b"not-gzip")
        assert BackupService._verify_legacy_file(str(backup_root / name), name) is False

    def test_system_backup_missing_postgres_url(self, backup_root, mocker):
        mocker.patch.object(BackupService, "_parse_db_url", return_value=None)
        assert BackupService.create_backup(scope=SCOPE_SYSTEM) is None

    def test_system_backup_pg_dump_failure(self, backup_root, mocker, monkeypatch, pg_tools):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mocker.patch.object(BackupService, "_run_pg_dump_custom", return_value=(False, "dump failed"))
        assert BackupService.create_backup(scope=SCOPE_SYSTEM) is None

    def test_prepare_restore_tenant_ok(self, mocker):
        mocker.patch.object(BackupService, "get_backup_info", return_value={
            "manifest": {"backup_scope": "tenant", "tenant_id": 7},
        })
        plan = BackupService.prepare_restore_command(
            "azad_backup_tenant_x_20260101_000000_abcd.tar.gz",
            target_tenant_id=7,
        )
        assert plan["ok"] is True
        assert plan["confirmation_required"] == "RESTORE CONFIRM"

    def test_verify_system_without_pg_restore_warns(self, backup_root, mocker):
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        _make_system_archive(path)
        mocker.patch.object(BackupService, "_resolve_pg_tool", return_value=None)
        result = BackupService.verify_backup(name)
        assert result["valid"] is True
        assert any("pg_restore not available" in w for w in result.get("warnings", []))

    def test_user_may_access_wrong_tenant(self, mocker):
        user = MagicMock(branch_id=1)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=5)
        mocker.patch.object(BackupService, "get_backup_info", return_value={
            "manifest": {"backup_scope": "tenant", "tenant_id": 99},
        })
        name = "azad_backup_tenant_x_20260101_000000_abcd.tar.gz"
        assert BackupService.user_may_access_backup(user, name) is False

    def test_scoped_backup_handles_exception(self, backup_root, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mocker.patch.object(BackupService, "_fetch_tenant_row", return_value={
            "id": 1, "slug": "x", "name": "X",
        })
        mocker.patch.object(BackupService, "_git_short_sha", return_value="ab")
        mocker.patch(
            "services.backup_scope_config.export_scoped_database",
            side_effect=RuntimeError("export boom"),
        )
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_engine.connect.return_value = mock_conn
        mocker.patch("sqlalchemy.create_engine", return_value=mock_engine)
        assert BackupService.create_backup(scope=SCOPE_TENANT, tenant_id=1) is None


def _make_legacy_tenant_export_archive(archive_path, tenant_id=7):
    work = archive_path.parent / "_legacy_work"
    work.mkdir(exist_ok=True)
    export_doc = {
        "tenant_id": tenant_id,
        "tables": {"tenants": [{"id": tenant_id, "slug": "acme", "name": "Acme"}]},
    }
    export_path = work / "tenant_export.json"
    export_path.write_text(json.dumps(export_doc), encoding="utf-8")
    manifest = {
        "backup_version": BACKUP_VERSION,
        "format": "azad_tar_v1",
        "backup_scope": "tenant",
        "tenant_id": tenant_id,
        "row_counts_per_table": {"tenants": 1},
        "sha256": {"tenant_export.json": BackupService._sha256_file(str(export_path))},
    }
    manifest_path = work / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(export_path, arcname="tenant_export.json")
        tar.add(manifest_path, arcname="manifest.json")
    return manifest


class TestFullCoverage:
    def test_load_json_logging_core_also_fails(self, backup_root, mocker):
        bad = backup_root / "bad.json"
        bad.write_text("{bad", encoding="utf-8")
        mocker.patch(
            "services.logging_core.LoggingCore.log_error",
            side_effect=RuntimeError("log unavailable"),
        )
        assert BackupService._load_json_file(str(bad)) is None

    def test_write_json_logging_core_also_fails(self, mocker):
        mocker.patch("builtins.open", side_effect=OSError("denied"))
        mocker.patch(
            "services.logging_core.LoggingCore.log_error",
            side_effect=RuntimeError("log unavailable"),
        )
        assert BackupService._write_json_file("/x/y.json", {"a": 1}) is False

    def test_list_backups_when_backup_dir_not_directory(self, backup_root, monkeypatch):
        not_dir = backup_root / "file_not_dir"
        not_dir.write_text("x", encoding="utf-8")
        monkeypatch.setattr(BackupService, "BACKUP_DIR", str(not_dir))
        assert BackupService.list_backups() == []

    def test_parse_db_url_exception(self, mocker):
        mocker.patch(
            "sqlalchemy.engine.url.make_url",
            side_effect=ValueError("bad url"),
        )
        assert BackupService._parse_db_url("postgresql://bad") is None

    def test_resolve_pg_tool_from_env_path(self, backup_root, monkeypatch):
        tool = backup_root / "pg_dump.exe"
        tool.write_bytes(b"")
        monkeypatch.setenv("PG_DUMP_PATH", str(tool))
        assert BackupService._resolve_pg_tool("pg_dump", "PG_DUMP_PATH") == str(tool)

    def test_resolve_pg_tool_windows_glob(self, mocker, monkeypatch):
        monkeypatch.setattr(os, "name", "nt")
        monkeypatch.delenv("PG_DUMP_PATH", raising=False)
        mocker.patch("shutil.which", return_value=None)
        win_path = r"C:\PostgreSQL\16\bin\pg_dump.exe"
        mocker.patch("glob.glob", return_value=[win_path])
        mocker.patch("os.path.isfile", return_value=True)
        assert BackupService._resolve_pg_tool("pg_dump", "PG_DUMP_PATH") == win_path

    def test_git_short_sha_nonzero_exit(self, mocker):
        mocker.patch(
            "services.backup_exec.run_git",
            return_value=subprocess.CompletedProcess([], 1, stdout="abc"),
        )
        assert BackupService._git_short_sha() == "unknown"

    def test_alembic_info_failure(self, mocker):
        mocker.patch("flask_migrate.current", side_effect=RuntimeError("no alembic"))
        assert BackupService._alembic_info() == (None, None)

    def test_upload_roots_exception(self, mocker, app, backup_root):
        broken = MagicMock()
        broken.configure_mock(**{"config.get.side_effect": RuntimeError("boom")})
        mocker.patch("flask.current_app", broken)
        with app.app_context():
            roots = BackupService._upload_roots()
        assert isinstance(roots, list)

    def test_build_uploads_skips_log_and_pyc(self, backup_root, monkeypatch):
        uploads = Path(BackupService._BASEDIR) / "static" / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        (uploads / "keep.txt").write_text("ok", encoding="utf-8")
        (uploads / "skip.pyc").write_bytes(b"\x00")
        (uploads / "skip.log").write_text("log", encoding="utf-8")
        dest = backup_root / "out.tar.gz"
        meta = BackupService._build_uploads_archive(str(dest))
        assert meta["files_packed"] == 1

    def test_pre_backup_integrity_warn(self, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mocker.patch.object(BackupService, "_parse_db_url", return_value={
            "host": "127.0.0.1", "port": "5432", "username": "u", "dbname": "db",
        })
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.scalar.side_effect = [5, 2, 0]
        mocker.patch("sqlalchemy.create_engine", return_value=MagicMock(
            connect=MagicMock(return_value=mock_conn),
        ))
        summary = BackupService._pre_backup_checks_summary()
        assert summary["checks"][-1] == "WARN"

    def test_pre_backup_integrity_db_error(self, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mocker.patch.object(BackupService, "_parse_db_url", return_value={
            "host": "127.0.0.1", "port": "5432", "username": "u", "dbname": "db",
        })
        mocker.patch("sqlalchemy.create_engine", side_effect=RuntimeError("db down"))
        summary = BackupService._pre_backup_checks_summary()
        assert "basic_integrity: error" in summary["checks"][-1]

    def test_run_pg_dump_success(self, backup_root, mocker, pg_tools):
        dest = backup_root / "ok.dump"

        def write_dump(cmd, env=None, timeout=None):
            out = cmd[cmd.index("--file") + 1]
            Path(out).write_bytes(b"PGDMP")
            return subprocess.CompletedProcess(cmd, 0)

        mocker.patch("services.backup_exec.run_pg_tool", side_effect=write_dump)
        ok, err = BackupService._run_pg_dump_custom(
            {
                "host": "127.0.0.1", "port": "5432", "username": "u",
                "password": "secret", "dbname": "d",
            },
            str(dest),
        )
        assert ok is True
        assert err == ""

    def test_archive_basename_unknown_scope(self):
        name = BackupService._archive_basename("custom_scope", "20260101_000000", "ab")
        assert name.startswith("azad_backup_custom_scope_")

    def test_backup_path_rejects_outside_dir(self, mocker):
        mocker.patch.object(BackupService, "_safe_filename", return_value="ok.tar.gz")
        real_abspath = os.path.abspath

        def fake_abspath(path):
            ap = real_abspath(path)
            if ap.endswith("ok.tar.gz"):
                return os.path.join(os.path.abspath("/outside"), "ok.tar.gz")
            return ap

        mocker.patch("os.path.abspath", side_effect=fake_abspath)
        assert BackupService._backup_path("ok.tar.gz") is None

    def test_fetch_tenant_row_no_database_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)
        assert BackupService._fetch_tenant_row(1) is None

    def test_fetch_tenant_row_missing(self, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = None
        mocker.patch("sqlalchemy.create_engine", return_value=MagicMock(
            connect=MagicMock(return_value=mock_conn),
        ))
        assert BackupService._fetch_tenant_row(999) is None

    def test_scoped_backup_unparseable_db_url(self, backup_root, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mocker.patch.object(BackupService, "_fetch_tenant_row", return_value={
            "id": 1, "slug": "x", "name": "X",
        })
        mocker.patch.object(BackupService, "_git_short_sha", return_value="ab")
        mocker.patch.object(BackupService, "_parse_db_url", return_value=None)
        assert BackupService.create_backup(scope=SCOPE_TENANT, tenant_id=1) is None

    def test_user_may_access_tenant_scope(self, mocker):
        user = MagicMock(branch_id=1)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=7)
        mocker.patch.object(BackupService, "get_backup_info", return_value={
            "manifest": {"backup_scope": "tenant", "tenant_id": 7},
        })
        name = "azad_backup_tenant_x_20260101_000000_abcd.tar.gz"
        assert BackupService.user_may_access_backup(user, name) is True

    def test_system_backup_exception_removes_partial_archive(
        self, backup_root, mocker, monkeypatch, pg_tools,
    ):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mocker.patch.object(BackupService, "_git_short_sha", return_value="abc")
        mocker.patch.object(BackupService, "_run_pg_dump_custom", return_value=(True, ""))

        def boom(dest):
            _minimal_tar_gz(dest)
            raise RuntimeError("archive failed")

        mocker.patch.object(BackupService, "_build_uploads_archive", side_effect=boom)
        assert BackupService.create_backup(scope=SCOPE_SYSTEM) is None

    def test_system_backup_approx_rows_query_fails(
        self, backup_root, mocker, monkeypatch, pg_tools,
    ):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mocker.patch.object(BackupService, "_git_short_sha", return_value="abc123")
        mocker.patch.object(BackupService, "_alembic_info", return_value=(None, None))
        mocker.patch.object(BackupService, "_pre_backup_checks_summary", return_value={"checks": []})
        mocker.patch.object(BackupService, "_apply_retention")

        def fake_dump(params, dest):
            Path(dest).write_bytes(b"PGDMP")
            return True, ""

        mocker.patch.object(BackupService, "_run_pg_dump_custom", side_effect=fake_dump)
        def fake_up(dest):
            _minimal_tar_gz(dest)
            return {"files_packed": 0}

        mocker.patch.object(BackupService, "_build_uploads_archive", side_effect=fake_up)
        mocker.patch("sqlalchemy.create_engine", side_effect=RuntimeError("stats unavailable"))
        sidecar = BackupService.create_backup(scope=SCOPE_SYSTEM)
        assert sidecar is not None

    def test_get_backup_info_corrupt_sidecar(self, backup_root):
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        _make_system_archive(path)
        (backup_root / f"{name}.meta.json").write_text("not-json", encoding="utf-8")
        info = BackupService.get_backup_info(name)
        assert "manifest" in info
        assert "sidecar" not in info

    def test_verify_sidecar_unreadable(self, backup_root):
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        _make_system_archive(path)
        (backup_root / f"{name}.meta.json").write_text("{bad", encoding="utf-8")
        result = BackupService.verify_backup(name)
        assert any("sidecar unreadable" in w for w in result.get("warnings", []))

    def test_verify_unknown_format(self, backup_root, mocker):
        path = backup_root / "manual_backup_weird.bin"
        path.write_bytes(b"data")
        mocker.patch.object(BackupService, "_backup_path", return_value=str(path))
        result = BackupService.verify_backup("manual_backup_weird.bin")
        assert "unknown backup format" in result["errors"][0]

    def test_verify_legacy_corrupt_via_verify_backup(self, backup_root):
        name = "manual_backup_bad.sql.gz"
        (backup_root / name).write_bytes(b"bad")
        result = BackupService.verify_backup(name)
        assert "legacy backup corrupt" in result["errors"][0]

    def test_verify_legacy_empty_dump(self, backup_root):
        name = "manual_backup_empty.dump"
        (backup_root / name).write_bytes(b"")
        assert BackupService._verify_legacy_file(str(backup_root / name), name) is False

    def test_verify_legacy_dump_without_pg_restore(self, backup_root, mocker):
        name = "manual_backup_x.dump"
        path = backup_root / name
        path.write_bytes(b"PGDMP")
        mocker.patch.object(BackupService, "_resolve_pg_tool", return_value=None)
        assert BackupService._verify_legacy_file(str(path), name) is True

    def test_verify_missing_manifest(self, backup_root):
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        with tarfile.open(path, "w:gz") as tar:
            data = b"x"
            info = tarfile.TarInfo(name="db.dump")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        result = BackupService.verify_backup(name)
        assert "missing manifest.json" in result["errors"][0]

    def test_verify_scoped_missing_data(self, backup_root):
        name = "azad_backup_tenant_x_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        manifest = {"backup_scope": "tenant", "tenant_id": 7}
        work = path.parent / "_nodata"
        work.mkdir()
        mp = work / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with tarfile.open(path, "w:gz") as tar:
            tar.add(mp, arcname="manifest.json")
        result = BackupService.verify_backup(name)
        assert "missing data/" in result["errors"][0]

    def test_verify_legacy_tenant_export_archive(self, backup_root):
        name = "azad_backup_tenant_x_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        _make_legacy_tenant_export_archive(path, tenant_id=7)
        result = BackupService.verify_backup(name)
        assert result["valid"] is True

    def test_verify_legacy_tenant_export_checksum_mismatch(self, backup_root):
        name = "azad_backup_tenant_x_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        manifest = _make_legacy_tenant_export_archive(path, tenant_id=7)
        manifest["sha256"]["tenant_export.json"] = "0" * 64
        work = path.parent / "_legacy_work"
        (work / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with tarfile.open(path, "w:gz") as tar:
            tar.add(work / "tenant_export.json", arcname="tenant_export.json")
            tar.add(work / "manifest.json", arcname="manifest.json")
        result = BackupService.verify_backup(name)
        assert "tenant_export.json checksum mismatch" in result["errors"][0]

    def test_verify_db_dump_checksum_mismatch(self, backup_root, mocker, pg_tools):
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        work = path.parent / "chk_work"
        work.mkdir(exist_ok=True)
        db_path = work / "db.dump"
        db_path.write_bytes(b"PGDMP")
        uploads_path = work / "uploads.tar.gz"
        _minimal_tar_gz(uploads_path)
        manifest = {
            "backup_scope": "system",
            "sha256": {"db.dump": "0" * 64},
        }
        manifest_path = work / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with tarfile.open(path, "w:gz") as tar:
            tar.add(db_path, arcname="db.dump")
            tar.add(uploads_path, arcname="uploads.tar.gz")
            tar.add(manifest_path, arcname="manifest.json")
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 0),
        )
        result = BackupService.verify_backup(name)
        assert "db.dump checksum mismatch" in result["errors"][0]

    def test_verify_pg_restore_list_fails(self, backup_root, mocker, pg_tools):
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        _make_system_archive(path)
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 1, stderr="bad dump"),
        )
        result = BackupService.verify_backup(name)
        assert "pg_restore --list failed" in result["errors"][0]

    def test_verify_modern_archive_raises(self, backup_root, mocker):
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        (backup_root / name).write_bytes(b"not a tar")
        result = BackupService.verify_backup(name)
        assert result["errors"]

    def test_verify_tenant_export_unreadable(self, backup_root):
        bad = backup_root / "bad.json"
        bad.write_text("{", encoding="utf-8")
        out = BackupService._verify_tenant_export(str(bad), {"tenant_id": 1})
        assert "tenant_export unreadable" in out["errors"][0]

    def test_verify_tenant_export_row_count_mismatch(self, backup_root):
        export = backup_root / "export.json"
        export.write_text(json.dumps({
            "tenant_id": 7,
            "tables": {"tenants": [{"id": 7}], "products": [{"id": 1, "tenant_id": 7}]},
        }), encoding="utf-8")
        out = BackupService._verify_tenant_export(str(export), {
            "tenant_id": 7,
            "row_counts_per_table": {"tenants": 1, "products": 2},
        })
        assert any("row count mismatch" in e for e in out["errors"])

    def test_verify_tenant_export_cross_branch(self, backup_root):
        export = backup_root / "export.json"
        export.write_text(json.dumps({
            "tenant_id": 7,
            "tables": {
                "tenants": [{"id": 7}],
                "branches": [{"id": 3, "tenant_id": 7}],
                "products": [{"id": 1, "tenant_id": 7, "branch_id": 99}],
            },
        }), encoding="utf-8")
        out = BackupService._verify_tenant_export(str(export), {
            "backup_scope": "branch", "tenant_id": 7, "branch_id": 3,
            "row_counts_per_table": {},
        })
        assert any("cross-branch" in e for e in out["errors"])

    def test_verify_tenant_export_store_id_mismatch(self, backup_root):
        export = backup_root / "export.json"
        export.write_text(json.dumps({
            "tenant_id": 7,
            "tables": {
                "tenants": [{"id": 7}],
                "tenant_stores": [{"id": 9, "tenant_id": 7}],
            },
        }), encoding="utf-8")
        out = BackupService._verify_tenant_export(str(export), {
            "backup_scope": "store", "tenant_id": 7, "store_id": 5,
            "row_counts_per_table": {},
        })
        assert any("tenant_stores id mismatch" in e for e in out["errors"])

    def test_verify_tenant_export_branch_isolation_failed(self, backup_root):
        export = backup_root / "export.json"
        export.write_text(json.dumps({
            "tenant_id": 7,
            "tables": {"tenants": [{"id": 7}], "branches": []},
        }), encoding="utf-8")
        out = BackupService._verify_tenant_export(str(export), {
            "backup_scope": "branch", "tenant_id": 7, "branch_id": 3,
            "row_counts_per_table": {},
        })
        assert any("branches isolation failed" in e for e in out["errors"])

    def test_prepare_restore_not_found(self):
        assert BackupService.prepare_restore_command("missing.tar.gz")["ok"] is False

    def test_prepare_restore_remap_tenant(self, mocker):
        mocker.patch.object(BackupService, "get_backup_info", return_value={
            "manifest": {"backup_scope": "tenant", "tenant_id": 7},
        })
        plan = BackupService.prepare_restore_command(
            "azad_backup_tenant_x_20260101_000000_abcd.tar.gz",
            target_tenant_id=99,
            remap=True,
        )
        assert plan["ok"] is True
        assert plan["confirmation_required"] == "REMAP CONFIRM"

    def test_urls_same_database_unparseable(self):
        assert BackupService._urls_same_database("same", "same") is True
        assert BackupService._urls_same_database("a", "b") is False

    def test_restore_invalid_filename(self, backup_root):
        out = BackupService.restore_backup_to_target_db(
            "../bad.tar.gz", "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="RESTORE CONFIRM",
        )
        assert "invalid filename" in out["errors"][0]

    def test_restore_verify_fails(self, backup_root, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/live")
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": False})
        out = BackupService.restore_backup_to_target_db(
            "azad_backup_system_20260101_120000_abcd.tar.gz",
            "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="RESTORE CONFIRM",
        )
        assert "verification failed" in out["errors"][0]

    def test_restore_invalid_target_url(self, backup_root, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/live")
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        _make_system_archive(backup_root / name)
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": True})
        mocker.patch.object(BackupService, "_parse_db_url", return_value=None)
        out = BackupService.restore_backup_to_target_db(
            name, "not-postgres", confirmation="RESTORE CONFIRM",
        )
        assert "Invalid target PostgreSQL URL" in out["errors"][0]

    def test_restore_no_pg_restore_tool(self, backup_root, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/live")
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        _make_system_archive(backup_root / name)
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": True})
        mocker.patch.object(BackupService, "_resolve_pg_tool", return_value=None)
        out = BackupService.restore_backup_to_target_db(
            name, "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="RESTORE CONFIRM",
        )
        assert "pg_restore not found" in out["errors"][0]

    def test_restore_legacy_dump_file(self, backup_root, mocker, monkeypatch, pg_tools):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/live")
        name = "manual_backup_data.dump"
        (backup_root / name).write_bytes(b"PGDMP")
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": True})
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 0),
        )
        out = BackupService.restore_backup_to_target_db(
            name, "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="RESTORE CONFIRM",
        )
        assert out["ok"] is True

    def test_restore_pg_restore_command_fails(self, backup_root, mocker, monkeypatch, pg_tools):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/live")
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        _make_system_archive(backup_root / name)
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": True})
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 1, stderr="restore failed"),
        )
        out = BackupService.restore_backup_to_target_db(
            name, "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="RESTORE CONFIRM",
        )
        assert "restore failed" in out["errors"][0]

    def test_restore_legacy_sql_gz_rejected(self, backup_root, mocker, monkeypatch, pg_tools):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/live")
        name = "manual_backup_data.sql.gz"
        path = backup_root / name
        with gzip.open(path, "wb") as gz:
            gz.write(b"-- sql")
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": True})
        out = BackupService.restore_backup_to_target_db(
            name, "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="RESTORE CONFIRM",
        )
        assert "Legacy .sql.gz restore" in out["errors"][0]

    def test_restore_scoped_invalid_backup(self, mocker):
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": False})
        out = BackupService.restore_scoped_backup_to_target_db(
            "azad_backup_tenant_x_20260101_000000_abcd.tar.gz",
            "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="RESTORE CONFIRM",
        )
        assert out["ok"] is False

    def test_restore_scoped_invalid_path_after_verify(self, backup_root, mocker):
        mocker.patch.object(BackupService, "verify_backup", return_value={
            "valid": True, "manifest": {"backup_scope": "tenant", "tenant_id": 7},
        })
        mocker.patch.object(BackupService, "_backup_path", return_value=None)
        out = BackupService.restore_scoped_backup_to_target_db(
            "azad_backup_tenant_x_20260101_120000_abcd.tar.gz",
            "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="RESTORE CONFIRM",
        )
        assert "invalid filename" in out["errors"][0]

    def test_restore_scoped_isolation_warning(self, backup_root, mocker, pg_tools):
        name = "azad_backup_tenant_acme_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        manifest = _make_tenant_archive(path, tenant_id=7)
        mocker.patch.object(BackupService, "verify_backup", return_value={
            "valid": True, "manifest": manifest,
        })
        mocker.patch(
            "services.backup_scoped_engine.restore_scoped_to_target",
            return_value={"ok": True, "target_tenant_id": 7},
        )
        mocker.patch(
            "services.backup_scoped_engine.verify_scoped_isolation",
            return_value={"ok": False, "errors": ["leak"]},
        )
        mocker.patch(
            "services.backup_scoped_restore.verify_scoped_restore",
            return_value={"ok": True},
        )
        out = BackupService.restore_scoped_backup_to_target_db(
            name, "postgresql://u:p@127.0.0.1:5432/newdb",
            confirmation="RESTORE CONFIRM",
        )
        assert out["ok"] is True
        assert any("archive isolation" in w for w in out.get("warnings", []))

    def test_delete_invalid_filename(self):
        assert BackupService.delete_backup("../../../etc/passwd") is False

    def test_pg_tools_version_query_fails(self, mocker, pg_tools):
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            side_effect=RuntimeError("version failed"),
        )
        status = BackupService.pg_tools_status()
        assert status["pg_dump_version"] is None

    def test_mask_db_host_single_label(self):
        assert BackupService._mask_db_host("internal") == "***"

    def test_build_env_redacted_truncates_long_values(self, monkeypatch):
        monkeypatch.setenv("FLASK_ENV", "x" * 100)
        out = BackupService._build_env_redacted()
        assert out["FLASK_ENV"].endswith("...")
        assert len(out["FLASK_ENV"]) < 100

    def test_get_backup_info_manifest_read_error(self, backup_root):
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        (backup_root / name).write_bytes(b"corrupt tar")
        info = BackupService.get_backup_info(name)
        assert "manifest_error" in info

    def test_verify_tenant_export_wrong_tenant_row_count(self, backup_root):
        export = backup_root / "export.json"
        export.write_text(json.dumps({
            "tenant_id": 7,
            "tables": {"tenants": [{"id": 7}, {"id": 8}]},
        }), encoding="utf-8")
        out = BackupService._verify_tenant_export(str(export), {"tenant_id": 7})
        assert any("tenants row count" in e for e in out["errors"])

    def test_verify_tenant_export_cross_tenant_row(self, backup_root):
        export = backup_root / "export.json"
        export.write_text(json.dumps({
            "tenant_id": 7,
            "tables": {
                "tenants": [{"id": 7}],
                "products": [{"id": 1, "tenant_id": 99}],
            },
        }), encoding="utf-8")
        out = BackupService._verify_tenant_export(str(export), {"tenant_id": 7})
        assert any("cross-tenant" in e for e in out["errors"])

    def test_prepare_restore_mask_target_url_failure(self, mocker):
        mocker.patch.object(BackupService, "get_backup_info", return_value={
            "manifest": {"backup_scope": "system"},
        })
        mocker.patch("services.backup_service.urlparse", side_effect=ValueError("bad"))
        plan = BackupService.prepare_restore_command(
            "azad_backup_system_20260101_120000_abcd.tar.gz",
            target_database_url="postgresql://u:p@host/db",
        )
        assert plan["ok"] is True
        assert plan["masked_target"] == "***"

    def test_resolve_pg_tool_via_which(self, mocker, monkeypatch):
        monkeypatch.delenv("PG_DUMP_PATH", raising=False)
        mocker.patch("shutil.which", return_value="/usr/bin/pg_dump")
        assert BackupService._resolve_pg_tool("pg_dump", "PG_DUMP_PATH") == "/usr/bin/pg_dump"

    def test_resolve_pg_tool_non_windows_no_candidate(self, mocker, monkeypatch):
        monkeypatch.setattr(os, "name", "posix")
        monkeypatch.delenv("PG_DUMP_PATH", raising=False)
        mocker.patch("shutil.which", return_value=None)
        assert BackupService._resolve_pg_tool("pg_dump", "PG_DUMP_PATH") is None

    def test_resolve_pg_tool_windows_no_install(self, mocker, monkeypatch):
        monkeypatch.setattr(os, "name", "nt")
        monkeypatch.delenv("PG_DUMP_PATH", raising=False)
        mocker.patch("shutil.which", return_value=None)
        mocker.patch("glob.glob", return_value=[])
        assert BackupService._resolve_pg_tool("pg_dump", "PG_DUMP_PATH") is None

    def test_git_branch_exception(self, mocker):
        mocker.patch("services.backup_exec.run_git", side_effect=RuntimeError("git"))
        assert BackupService._git_branch() is None

    def test_system_backup_remove_archive_oserror(
        self, backup_root, mocker, monkeypatch, pg_tools,
    ):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        fixed = "azad_backup_system_20260101_120000_abcd.tar.gz"
        mocker.patch.object(BackupService, "_archive_basename", return_value=fixed)
        (backup_root / fixed).write_bytes(b"partial")
        mocker.patch.object(BackupService, "_git_short_sha", return_value="ab")
        mocker.patch.object(BackupService, "_run_pg_dump_custom", return_value=(True, ""))
        mocker.patch.object(
            BackupService, "_build_uploads_archive",
            side_effect=RuntimeError("tar failed"),
        )
        mocker.patch("os.remove", side_effect=OSError("locked"))
        assert BackupService.create_backup(scope=SCOPE_SYSTEM) is None

    def test_verify_legacy_file_unsupported_extension(self, backup_root):
        path = backup_root / "manual_backup_x.backup"
        path.write_bytes(b"x")
        assert BackupService._verify_legacy_file(str(path), path.name) is False

    def test_verify_legacy_dump_pg_restore_fails(self, backup_root, mocker, pg_tools):
        name = "manual_backup_x.dump"
        path = backup_root / name
        path.write_bytes(b"PGDMP")
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 1),
        )
        assert BackupService._verify_legacy_file(str(path), name) is False

    def test_verify_scoped_export_validation_fails(self, backup_root):
        name = "azad_backup_tenant_x_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        work = path.parent / "bad_tenant"
        work.mkdir(exist_ok=True)
        data_dir = work / "data"
        data_dir.mkdir()
        (data_dir / "tenants.jsonl").write_text(
            json.dumps({"id": 7, "slug": "a"}), encoding="utf-8",
        )
        manifest = {
            "backup_scope": "tenant",
            "tenant_id": 7,
            "row_counts_per_table": {"tenants": 2},
        }
        mp = work / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with tarfile.open(path, "w:gz") as tar:
            tar.add(data_dir, arcname="data")
            tar.add(mp, arcname="manifest.json")
        result = BackupService.verify_backup(name)
        assert result["valid"] is False
        assert result["errors"]

    def test_verify_system_missing_uploads_member(self, backup_root):
        name = "azad_backup_system_20260101_120000_abcd.tar.gz"
        path = backup_root / name
        work = path.parent / "missing_up"
        work.mkdir(exist_ok=True)
        db_path = work / "db.dump"
        db_path.write_bytes(b"PGDMP")
        manifest = {"backup_scope": "system", "sha256": {}}
        mp = work / "manifest.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with tarfile.open(path, "w:gz") as tar:
            tar.add(db_path, arcname="db.dump")
            tar.add(mp, arcname="manifest.json")
        result = BackupService.verify_backup(name)
        assert "missing members" in result["errors"][0]
