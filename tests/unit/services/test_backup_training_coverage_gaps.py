"""Coverage gaps for backup_service, training_progress and training_importer.

Targets the statements and branch arcs that the CI-combined coverage report
still marks as missed. Every patch is applied at the service boundary; no
production code (and no other test) is modified.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from models.ai import AiMemory
from models.ai_training_advanced import AiKnowledgeGraph, AiTrainingBatch, AiTrainingProgress
from services import training_progress as progress_mod
from services.backup_service import BackupService
from services.training_importer import TrainingImporter
from utils.backup_crypto import BackupCrypto

# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _clean_crypto_cache():
    BackupService._crypto_instance = None
    yield
    BackupService._crypto_instance = None


@pytest.fixture
def work_dir():
    """A temp tree outside pytest's basetemp (which the repo conftest wipes)."""
    path = Path(tempfile.mkdtemp(prefix="azad_backtrain_"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def backup_root(work_dir, monkeypatch):
    root = work_dir / "proj"
    root.mkdir()
    backups = root / "instance" / "backups"
    backups.mkdir(parents=True)
    monkeypatch.setattr(BackupService, "_BASEDIR", str(root))
    monkeypatch.setattr(BackupService, "BACKUP_DIR", str(backups))
    return backups


def _minimal_tar_gz(path, member_name="x.txt", content=b"x"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=member_name)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    Path(path).write_bytes(buf.getvalue())


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _mock_conn(mocker):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.scalar.return_value = 42
    engine = MagicMock()
    engine.connect.return_value = conn
    mocker.patch("sqlalchemy.create_engine", return_value=engine)
    return conn


def _mock_scoped_flow(mocker, monkeypatch, *, create_uploads=True, encrypt=False):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
    mocker.patch.object(
        BackupService,
        "_fetch_tenant_row",
        return_value={"id": 42, "slug": "acme", "name": "Acme", "enable_auto_backup": True},
    )
    mocker.patch.object(BackupService, "_git_short_sha", return_value="sha1")
    mocker.patch.object(BackupService, "_alembic_info", return_value=(None, None))
    mocker.patch.object(BackupService, "_pre_backup_checks_summary", return_value={})
    mocker.patch.object(BackupService, "pg_tools_status", return_value={})
    mocker.patch.object(BackupService, "_apply_retention")
    tables = {"tenants": [{"id": 42, "slug": "acme", "name": "Acme"}]}
    mocker.patch(
        "services.backup_scope_config.export_scoped_database",
        return_value=(tables, {"tenants": 1}, ["tenants"], [], []),
    )
    mocker.patch("services.backup_scope_config.collect_scoped_upload_paths", return_value=([], []))

    def fake_uploads(_paths, dest, _base):
        if create_uploads:
            _minimal_tar_gz(dest)
        return {"files_packed": 0}

    mocker.patch("services.backup_scope_config.build_tenant_uploads_archive", side_effect=fake_uploads)
    _mock_conn(mocker)
    if encrypt:
        BackupService._crypto_instance = BackupCrypto("unit-passphrase")


def _mock_system_flow(mocker, monkeypatch, *, no_url=False, encrypt=False):
    mocker.patch.object(
        BackupService,
        "_parse_db_url",
        return_value={"host": "127.0.0.1", "port": "5432", "username": "u", "password": "p", "dbname": "db"},
    )
    mocker.patch.object(BackupService, "_resolve_pg_tool", return_value="/usr/bin/pg_dump")
    mocker.patch.object(BackupService, "_git_short_sha", return_value="abc")
    mocker.patch.object(BackupService, "_alembic_info", return_value=("r1", "r1"))
    mocker.patch.object(BackupService, "_pre_backup_checks_summary", return_value={"checks": []})
    mocker.patch.object(BackupService, "_apply_retention")
    mocker.patch(
        "services.backup_exec.run_pg_tool",
        return_value=subprocess.CompletedProcess([], 0, stdout="pg_dump 16.1", stderr=""),
    )

    def fake_dump(_params, dest):
        Path(dest).write_bytes(b"PGDMP")
        return True, ""

    mocker.patch.object(BackupService, "_run_pg_dump_custom", side_effect=fake_dump)

    def fake_uploads(dest):
        _minimal_tar_gz(dest)
        return {"files_packed": 0}

    mocker.patch.object(BackupService, "_build_uploads_archive", side_effect=fake_uploads)
    _mock_conn(mocker)
    if no_url:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
    if encrypt:
        BackupService._crypto_instance = BackupCrypto("unit-passphrase")


# --------------------------------------------------------------------------- #
# backup_service.py gaps
# --------------------------------------------------------------------------- #


class TestBackupCryptoGaps:
    def test_get_crypto_falls_back_to_environment(self, monkeypatch):
        class NoApp:
            @property
            def config(self):
                raise RuntimeError("no application context")

        monkeypatch.setattr("flask.current_app", NoApp(), raising=False)
        monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", "unit-passphrase")
        crypto = BackupService._get_crypto()
        assert crypto.enabled is True

    def test_encrypt_archive_encrypts_and_removes_original(self, backup_root):
        BackupService._crypto_instance = BackupCrypto("unit-passphrase")
        archive = backup_root / "azad_backup_system_20260101_000000_aa.tar.gz"
        archive.write_bytes(b"archive payload" * 4)
        final_path, encrypted = BackupService._maybe_encrypt_archive(str(archive))
        assert encrypted is True
        assert final_path.endswith(".enc")
        assert not archive.exists()
        assert Path(final_path).is_file()

    def test_encrypt_failure_removes_partial_file(self, backup_root, mocker):
        class FailingCrypto:
            enabled = True

            def encrypt_file(self, _src, dest):
                Path(dest).write_bytes(b"partial")
                raise RuntimeError("encryption failed")

        mocker.patch.object(BackupService, "_get_crypto", return_value=FailingCrypto())
        archive = backup_root / "azad_backup_system_20260101_000000_ab.tar.gz"
        archive.write_bytes(b"archive payload")
        path, encrypted = BackupService._maybe_encrypt_archive(str(archive))
        assert path == str(archive)
        assert encrypted is False
        assert not (backup_root / "azad_backup_system_20260101_000000_ab.tar.gz.enc").exists()

    def test_encrypt_failure_without_partial_file(self, backup_root, mocker):
        class FailingCrypto:
            enabled = True

            def encrypt_file(self, _src, _dest):
                raise RuntimeError("nothing written")

        mocker.patch.object(BackupService, "_get_crypto", return_value=FailingCrypto())
        archive = backup_root / "azad_backup_system_20260101_000000_b4.tar.gz"
        archive.write_bytes(b"archive payload")
        path, encrypted = BackupService._maybe_encrypt_archive(str(archive))
        assert path == str(archive)
        assert encrypted is False
        assert not (backup_root / "azad_backup_system_20260101_000000_b4.tar.gz.enc").exists()

    def test_decrypt_encrypted_archive_without_key_raises(self, backup_root, mocker, monkeypatch):
        from utils.backup_crypto import BackupCryptoError

        monkeypatch.delenv("BACKUP_ENCRYPTION_KEY", raising=False)
        mocker.patch.object(BackupService, "_get_crypto", return_value=BackupCrypto(None))
        encrypted = backup_root / "azad_backup_system_20260101_000000_b5.tar.gz.enc"
        encrypted.write_bytes(b"opaque")
        with pytest.raises(BackupCryptoError):
            BackupService._maybe_decrypt_archive(str(encrypted))

    def test_decrypt_and_cleanup_temp_directory(self, backup_root):
        BackupService._crypto_instance = BackupCrypto("unit-passphrase")
        archive = backup_root / "azad_backup_system_20260101_000000_ac.tar.gz"
        _minimal_tar_gz(archive, "manifest.json", b"{}")
        encrypted_path, encrypted = BackupService._maybe_encrypt_archive(str(archive))
        assert encrypted is True

        with BackupService._open_archive_for_read(encrypted_path) as readable:
            decrypted = Path(readable)
            assert decrypted.is_file()
            with tarfile.open(readable, "r:gz") as tar:
                assert "manifest.json" in tar.getnames()
        assert not decrypted.exists()


class TestBackupToolDiscoveryGaps:
    def test_pg_tools_status_without_dump(self, mocker):
        mocker.patch.object(BackupService, "_resolve_pg_tool", return_value=None)
        status = BackupService.pg_tools_status()
        assert status["pg_dump"] is None
        assert status["pg_dump_version"] is None
        assert status["available"] is False

    def test_which_skips_empty_path_entry_and_returns_none(self, monkeypatch, work_dir):
        monkeypatch.setenv("PATH", os.pathsep.join(["", str(work_dir)]))
        monkeypatch.delenv("PATHEXT", raising=False)
        monkeypatch.setattr(BackupService, "_is_windows", classmethod(lambda cls: False))
        assert BackupService._which("missing_executable_xyz") is None

    def test_resolve_pg_tool_skips_non_file_candidate(self, monkeypatch, mocker, work_dir):
        monkeypatch.setenv("PG_DUMP_PATH", "")
        monkeypatch.setenv("ProgramFiles", str(work_dir))
        monkeypatch.delenv("ProgramFiles(x86)", raising=False)
        mocker.patch.object(BackupService, "_which", classmethod(lambda cls, name: None))
        mocker.patch.object(BackupService, "_is_windows", classmethod(lambda cls: True))
        mocker.patch(
            "services.backup_service.glob.glob",
            side_effect=[["/fake/pg_dump"], ["/fake/pg_dump.exe"], [], []],
        )
        assert BackupService._resolve_pg_tool("pg_dump", "PG_DUMP_PATH") is None

    def test_git_branch_non_zero_exit(self, mocker):
        mocker.patch(
            "services.backup_exec.run_git",
            return_value=subprocess.CompletedProcess([], 1, stdout="", stderr=""),
        )
        assert BackupService._git_branch() is None

    def test_alembic_info_without_database_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)
        assert BackupService._alembic_info() == (None, None)


class TestBackupFlowGaps:
    def test_scoped_backup_skipped_when_auto_backup_disabled(self, backup_root, mocker, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mocker.patch.object(
            BackupService,
            "_fetch_tenant_row",
            return_value={"id": 1, "slug": "acme", "name": "Acme", "enable_auto_backup": False},
        )
        assert BackupService.create_backup(scope="tenant", tenant_id=1) is None

    def test_scoped_backup_tolerates_missing_uploads_member(self, backup_root, mocker, monkeypatch):
        _mock_scoped_flow(mocker, monkeypatch, create_uploads=False)
        sidecar = BackupService.create_backup(scope="tenant", tenant_id=42)
        assert sidecar is not None
        assert sidecar["format"] == "azad_tar_v1"
        assert not any(name.endswith("uploads.tar.gz.enc") for name in os.listdir(backup_root))

    def test_scoped_backup_marks_encrypted_sidecar(self, backup_root, mocker, monkeypatch):
        _mock_scoped_flow(mocker, monkeypatch, encrypt=True)
        sidecar = BackupService.create_backup(scope="tenant", tenant_id=42)
        assert sidecar is not None
        assert sidecar["encrypted"] is True
        assert sidecar["encryption"] == "aes-256-gcm"
        assert sidecar["filename"].endswith(".enc")

    def test_system_backup_without_url_skips_row_probe(self, backup_root, mocker, monkeypatch):
        _mock_system_flow(mocker, monkeypatch, no_url=True)
        sidecar = BackupService.create_backup(scope="system")
        assert sidecar is not None
        assert sidecar["format"] == "azad_tar_v1"

    def test_system_backup_marks_encrypted_sidecar(self, backup_root, mocker, monkeypatch):
        _mock_system_flow(mocker, monkeypatch, encrypt=True)
        sidecar = BackupService.create_backup(scope="system")
        assert sidecar is not None
        assert sidecar["encrypted"] is True
        assert sidecar["encryption"] == "aes-256-gcm"
        assert sidecar["filename"].endswith(".enc")

    def test_offsite_upload_error_is_recorded(self, mocker):
        mocker.patch("utils.offsite_backup.is_configured", return_value=True)
        mocker.patch(
            "utils.offsite_backup.upload_backup_archive",
            return_value={"ok": False, "error": "upload failed", "attempts": 2},
        )
        status = BackupService._maybe_upload_offsite("/tmp/f.tar.gz")
        assert status["offsite_status"] == "failed"
        assert status["offsite_error"] == "upload failed"

    def test_auto_backup_daily_without_url_skips_tenant_loop(self, mocker, monkeypatch):
        mocker.patch.object(
            BackupService,
            "get_schedule_settings",
            return_value={"enabled": True, "frequency": "daily"},
        )
        mocker.patch.object(BackupService, "_set_schedule_state")
        mocker.patch.object(BackupService, "create_backup", return_value={"filename": "sys.tar.gz"})
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)
        assert BackupService.auto_backup_daily() == {"filename": "sys.tar.gz"}

    def test_auto_backup_daily_tenant_loop_error_is_non_fatal(self, mocker, monkeypatch):
        mocker.patch.object(
            BackupService,
            "get_schedule_settings",
            return_value={"enabled": True, "frequency": "daily"},
        )
        mocker.patch.object(BackupService, "_set_schedule_state")
        mocker.patch.object(BackupService, "create_backup", return_value={"filename": "sys.tar.gz"})
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
        mocker.patch("sqlalchemy.create_engine", side_effect=RuntimeError("db down"))
        assert BackupService.auto_backup_daily() == {"filename": "sys.tar.gz"}

    def test_tenant_manual_backup_after_rate_window(self, db_session, sample_tenant, mocker):
        user = MagicMock()
        user.id = 9
        user.username = "tenant-user"
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=sample_tenant.id)
        old = (datetime.now(UTC) - timedelta(hours=2)).timestamp()
        mocker.patch.object(BackupService, "_tenant_manual_backups", return_value=[{"modified": old}])
        mocker.patch.object(
            BackupService,
            "create_backup",
            return_value={"filename": "azad_backup_tenant_acme_20260101_000000_a.tar.gz", "size_mb": 1.0},
        )
        mocker.patch.object(BackupService, "_prune_tenant_manual_backups", return_value=0)
        out = BackupService.create_tenant_manual_backup(user)
        assert out["ok"] is True
        assert out["size_mb"] == 1.0


class TestBackupInfoAndRestoreGaps:
    def test_get_backup_info_legacy_sidecar_without_manifest(self, backup_root):
        name = "manual_backup_legacy.dump"
        (backup_root / name).write_bytes(b"data")
        (backup_root / f"{name}.meta.json").write_text('{"format": "legacy"}', encoding="utf-8")
        info = BackupService.get_backup_info(name)
        assert info["filename"] == name
        assert "manifest" not in info

    def test_get_backup_info_archive_without_manifest_member(self, backup_root):
        name = "azad_backup_system_20260101_000000_ad.tar.gz"
        _minimal_tar_gz(backup_root / name, "notes.txt", b"x")
        info = BackupService.get_backup_info(name)
        assert info["filename"] == name
        assert "manifest" not in info

    def test_get_backup_info_manifest_member_is_directory(self, backup_root):
        name = "azad_backup_system_20260101_000000_ae.tar.gz"
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            entry = tarfile.TarInfo(name="manifest.json")
            entry.type = tarfile.DIRTYPE
            tar.addfile(entry)
        (backup_root / name).write_bytes(buf.getvalue())
        info = BackupService.get_backup_info(name)
        assert info["filename"] == name
        assert "manifest" not in info

    def test_verify_tenant_export_store_scope_with_matching_rows(self, work_dir):
        export = work_dir / "export.json"
        _write_json(
            export,
            {
                "tenant_id": 7,
                "tables": {
                    "tenants": [{"id": 7}],
                    "tenant_stores": [
                        {"id": 9, "tenant_id": 7},
                        {"id": 9, "tenant_id": 7},
                    ],
                    "users": [
                        {"tenant_id": 7, "is_owner": False},
                        {"tenant_id": 7, "is_owner": False},
                    ],
                },
            },
        )
        manifest = {"backup_scope": "store", "tenant_id": 7, "store_id": 9, "row_counts_per_table": {}}
        out = BackupService._verify_tenant_export(str(export), manifest)
        assert out["ok"] is True

    def test_prepare_restore_command_target_without_hostname(self, mocker):
        mocker.patch.object(
            BackupService,
            "get_backup_info",
            return_value={"manifest": {"backup_scope": "system"}},
        )
        plan = BackupService.prepare_restore_command("azad_backup_system_20260101_000000_af.tar.gz", "not-a-url")
        assert plan["ok"] is True
        assert plan["masked_target"] == "***"

    def test_restore_target_without_password(self, backup_root, mocker, monkeypatch):
        current = "postgresql://u:p@127.0.0.1:5432/live"
        target = "postgresql://u@127.0.0.1:5432/newdb"
        monkeypatch.setenv("DATABASE_URL", current)
        name = "azad_backup_system_20260101_000000_b0.tar.gz"
        archive = backup_root / name
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for member, payload in (("db.dump", b"PGDMP"), ("manifest.json", b"{}")):
                info = tarfile.TarInfo(name=member)
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
        archive.write_bytes(buf.getvalue())
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": True})
        mocker.patch.object(BackupService, "_resolve_pg_tool", return_value="/usr/bin/pg_restore")
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="restore refused"),
        )
        out = BackupService.restore_backup_to_target_db(name, target, confirmation="RESTORE CONFIRM")
        assert out["ok"] is False
        assert "restore refused" in out["errors"][0]

    def test_restore_with_uploads_but_no_uploads_member(self, backup_root, mocker, monkeypatch):
        current = "postgresql://u:p@127.0.0.1:5432/live"
        target = "postgresql://u:p@127.0.0.1:5432/newdb"
        monkeypatch.setenv("DATABASE_URL", current)
        name = "azad_backup_system_20260101_000000_b1.tar.gz"
        archive = backup_root / name
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="db.dump")
            info.size = 5
            tar.addfile(info, io.BytesIO(b"PGDMP"))
        archive.write_bytes(buf.getvalue())
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": True})
        mocker.patch.object(BackupService, "_resolve_pg_tool", return_value="/usr/bin/pg_restore")
        mocker.patch(
            "services.backup_exec.run_pg_tool",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        out = BackupService.restore_backup_to_target_db(
            name,
            target,
            confirmation="RESTORE CONFIRM",
            restore_uploads=True,
        )
        assert out["ok"] is True
        assert not any("uploads restored" in warning for warning in out["warnings"])

    def test_restore_scoped_dry_run_skips_verification(self, backup_root, mocker):
        name = "azad_backup_tenant_acme_20260101_000000_b2.tar.gz"
        manifest = {"backup_scope": "tenant", "tenant_id": 7, "row_counts_per_table": {}}
        _minimal_tar_gz(backup_root / name, "manifest.json", json.dumps(manifest).encode("utf-8"))
        mocker.patch.object(BackupService, "verify_backup", return_value={"valid": True, "manifest": manifest})
        mocker.patch(
            "services.backup_scoped_engine.restore_scoped_to_target",
            return_value={"ok": True, "target_tenant_id": 7},
        )
        out = BackupService.restore_scoped_backup_to_target_db(
            name,
            "postgresql://u:p@127.0.0.1:5432/newdb",
            dry_run=True,
        )
        assert out["ok"] is True
        assert "archive_verify" not in out

    def test_delete_backup_with_no_files_present(self, backup_root):
        name = "azad_backup_system_20260101_000000_b3.tar.gz"
        assert BackupService.delete_backup(name) is True
        assert not (backup_root / name).exists()


# --------------------------------------------------------------------------- #
# training_progress.py gaps
# --------------------------------------------------------------------------- #


def _add_progress(
    db_session,
    tenant_id,
    *,
    domain="sales",
    concept="vat",
    covered=True,
    mastery=50,
    confidence=0.5,
    velocity=1.0,
    updated_at=None,
):
    record = AiTrainingProgress(
        tenant_id=tenant_id,
        domain=domain,
        topic="topic",
        concept_name=concept,
        covered=covered,
        usage_count=3,
        confidence=confidence,
        mastery_score=mastery,
        learning_velocity=velocity,
        updated_at=updated_at or datetime.now(UTC),
    )
    db_session.add(record)
    db_session.flush()
    return record


def _add_graph(db_session, tenant_id, source, target):
    edge = AiKnowledgeGraph(
        tenant_id=tenant_id,
        source_concept=source,
        target_concept=target,
        relationship_type="related_to",
    )
    db_session.add(edge)
    db_session.flush()
    return edge


def _add_memory(db_session, tenant_id, *, key="vat", value="5 percent", created_at=None, category="tax"):
    memory = AiMemory(
        tenant_id=tenant_id,
        key=key,
        value=value,
        category=category,
        confidence=0.9,
        source="unit-test",
        is_active=True,
        created_at=created_at or datetime.now(UTC),
    )
    db_session.add(memory)
    db_session.flush()
    return memory


class TestTrainingProgressGaps:
    @pytest.mark.parametrize(
        "mastery,expected",
        [
            (90, "expert"),
            (70, "advanced"),
            (50, "intermediate"),
            (30, "beginner"),
            (5, "novice"),
        ],
    )
    def test_progress_levels(self, db_session, sample_tenant, mastery, expected):
        _add_progress(db_session, sample_tenant.id, mastery=mastery)
        out = progress_mod.get_training_progress(sample_tenant.id)
        assert out["level"] == expected

    def test_progress_with_domain_filter(self, db_session, sample_tenant):
        _add_progress(db_session, sample_tenant.id, domain="tax", concept="vat")
        _add_progress(db_session, sample_tenant.id, domain="sales", concept="discount")
        out = progress_mod.get_training_progress(sample_tenant.id, domain="tax")
        assert out["total_concepts"] == 1
        assert "tax" in out["by_domain"]

    def test_progress_counts_uncovered_domain_records(self, db_session, sample_tenant):
        _add_progress(db_session, sample_tenant.id, domain="tax", concept="vat", covered=False, mastery=10)
        out = progress_mod.get_training_progress(sample_tenant.id)
        assert out["covered_concepts"] == 0
        assert out["by_domain"]["tax"]["covered"] == 0
        assert out["by_domain"]["tax"]["coverage"] == 0.0

    def test_metrics_include_graph_concepts_and_memories(self, db_session, sample_tenant):
        now = datetime.now(UTC)
        _add_graph(db_session, sample_tenant.id, "vat", "rate")
        _add_memory(db_session, sample_tenant.id, key="vat rate", created_at=now - timedelta(days=5))
        _add_memory(db_session, sample_tenant.id, key="old note", created_at=now - timedelta(days=40))
        out = progress_mod.get_training_metrics(sample_tenant.id)
        assert out["knowledge_graph_edges"] == 1
        assert out["total_concepts"] >= 2
        assert out["total_memories"] >= 2
        assert out["velocity_trend"] in ("improving", "declining", "stable")

    def test_concept_details_with_graph_edges_and_memories(self, db_session, sample_tenant):
        _add_progress(db_session, sample_tenant.id, concept="vat", mastery=80, covered=True)
        _add_graph(db_session, sample_tenant.id, "vat", "rate")
        _add_memory(db_session, sample_tenant.id, key="vat registration", value="required")
        out = progress_mod.get_concept_details(sample_tenant.id, "vat")
        assert out["found"] is True
        assert out["total_records"] == 1
        assert out["average_mastery_score"] == 80.0
        assert any(edge["source_concept"] == "vat" for edge in out["knowledge_graph_edges"])
        assert any(memory["key"] == "vat registration" for memory in out["related_memories"])

    @pytest.mark.parametrize(
        "counts,expected",
        [
            ((1, 2, 2), "improving"),
            ((4, 1, 1), "declining"),
            ((2, 2, 2), "stable"),
        ],
    )
    def test_learning_velocity_trends(self, db_session, sample_tenant, counts, expected):
        weeks = [datetime(2026, 1, 7, tzinfo=UTC), datetime(2026, 1, 14, tzinfo=UTC), datetime(2026, 1, 21, tzinfo=UTC)]
        for week_index, count in enumerate(counts):
            for item in range(count):
                _add_progress(
                    db_session,
                    sample_tenant.id,
                    concept=f"w{week_index}-{item}",
                    updated_at=weeks[week_index],
                )
        out = progress_mod.get_learning_velocity(sample_tenant.id)
        assert out["weeks_with_data"] == 3
        assert out["trend"] == expected

    def test_learning_velocity_single_week_is_stable(self, db_session, sample_tenant):
        week = datetime(2026, 1, 7, tzinfo=UTC)
        _add_progress(db_session, sample_tenant.id, concept="only", updated_at=week)
        out = progress_mod.get_learning_velocity(sample_tenant.id)
        assert out["weeks_with_data"] == 1
        assert out["trend"] == "stable"

    def test_learning_velocity_ignores_records_without_timestamp(self, mocker):
        record = MagicMock()
        record.updated_at = None
        query = MagicMock()
        query.filter.return_value.all.return_value = [record]
        mocker.patch.object(progress_mod, "tenant_query", return_value=query)
        out = progress_mod.get_learning_velocity(1)
        assert out["weeks_with_data"] == 0
        assert out["total_concepts"] == 0
        assert out["velocity"] == 0.0

    def test_knowledge_graph_relationships_filtered_by_concept(self, db_session, sample_tenant):
        _add_graph(db_session, sample_tenant.id, "vat", "rate")
        _add_graph(db_session, sample_tenant.id, "sales", "discount")
        out = progress_mod.get_knowledge_graph_relationships(sample_tenant.id, concept="vat")
        assert len(out) == 1
        assert out[0]["source_concept"] == "vat"

    @pytest.mark.parametrize(
        "coverage,mastery,velocity,expected",
        [
            (100, 100, 10.0, "excellent"),
            (95, 95, 3.0, "good"),
            (60, 60, 1.0, "fair"),
        ],
    )
    def test_health_report_without_recommendations(self, mocker, coverage, mastery, velocity, expected):
        mocker.patch.object(
            progress_mod,
            "get_training_progress",
            return_value={
                "coverage_percentage": coverage,
                "average_mastery_score": mastery,
                "total_concepts": 10,
            },
        )
        mocker.patch.object(
            progress_mod,
            "get_training_metrics",
            return_value={"learning_velocity": velocity, "total_memories": 20},
        )
        out = progress_mod.get_training_health_report(1)
        assert out["health_status"] == expected
        assert out["recommendations"] == []


# --------------------------------------------------------------------------- #
# training_importer.py gaps
# --------------------------------------------------------------------------- #


@pytest.fixture
def importer(work_dir):
    return TrainingImporter(upload_folder=str(work_dir))


class TestTrainingImporterGaps:
    def test_ensure_upload_folder_uses_app_config(self, app, work_dir):
        app.config["UPLOAD_FOLDER"] = str(work_dir)
        imp = TrainingImporter()
        folder = imp._ensure_upload_folder()
        assert folder == os.path.join(str(work_dir), "training")
        assert os.path.isdir(folder)

    def test_ensure_upload_folder_without_app_config(self, mocker, work_dir):
        class NoConfigApp:
            @property
            def config(self):
                raise RuntimeError("no application config")

        mocker.patch("flask.current_app", NoConfigApp())
        fallback = str(work_dir / "fallback")
        imp = TrainingImporter(upload_folder=fallback)
        assert imp._ensure_upload_folder() == fallback
        assert os.path.isdir(fallback)

    def test_ensure_upload_folder_without_app_context(self, mocker, work_dir):
        mocker.patch("flask.has_app_context", return_value=False)
        fallback = str(work_dir / "nocontext")
        imp = TrainingImporter(upload_folder=fallback)
        assert imp._ensure_upload_folder() == fallback
        assert os.path.isdir(fallback)

    def test_ensure_upload_folder_with_empty_config(self, app, work_dir):
        app.config["UPLOAD_FOLDER"] = ""
        fallback = str(work_dir / "emptycfg")
        imp = TrainingImporter(upload_folder=fallback)
        assert imp._ensure_upload_folder() == fallback

    def test_json_plain_dict_is_single_record(self, db_session, sample_tenant, importer, work_dir):
        fp = _write_json(work_dir / "plain.json", {"foo": "bar"})
        result = importer.import_from_json(fp, sample_tenant.id)
        assert result["success"] is True
        assert result["total"] == 1
        assert result["processed"] == 0

    def test_json_generic_error_is_reported(self, db_session, sample_tenant, importer, work_dir, mocker):
        fp = _write_json(work_dir / "generic.json", [{"question": "Q", "answer": "A"}])
        mocker.patch.object(importer, "_process_training_records", side_effect=RuntimeError("processing boom"))
        result = importer.import_from_json(fp, sample_tenant.id)
        assert result["success"] is False
        assert "processing boom" in result["error"]

    def test_json_decode_error_without_batch(self, work_dir, mocker):
        mocker.patch(
            "services.training_importer.AiTrainingBatch",
            side_effect=json.JSONDecodeError("bad", "bad", 0),
        )
        bad = work_dir / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        result = TrainingImporter().import_from_json(str(bad), 1)
        assert result["success"] is False
        assert result["batch_id"] is None

    def test_json_generic_error_without_batch(self, work_dir, mocker):
        mocker.patch("services.training_importer.AiTrainingBatch", side_effect=RuntimeError("no batch"))
        fp = _write_json(work_dir / "broken.json", {"question": "Q", "answer": "A"})
        result = TrainingImporter().import_from_json(fp, 1)
        assert result["success"] is False
        assert result["batch_id"] is None

    def test_excel_confidence_is_clamped_and_defaulted(self, db_session, sample_tenant, importer, work_dir):
        fp = str(work_dir / "confidence.xlsx")
        pd.DataFrame(
            [
                {"question": "Q1", "answer": "A1", "confidence": 1.5},
                {"question": "Q2", "answer": "A2", "confidence": -0.5},
                {"question": "Q3", "answer": "A3", "confidence": "not-a-number"},
                {"question": "Q4", "answer": "A4", "confidence": None},
                {"question": "Q5", "answer": "A5", "confidence": 0.7},
            ]
        ).to_excel(fp, index=False)
        result = importer.import_from_excel(fp, sample_tenant.id)
        assert result["success"] is True
        assert result["processed"] == 5
        memories = db_session.query(AiMemory).filter(AiMemory.tenant_id == sample_tenant.id).all()
        by_key = {m.key: float(m.confidence) for m in memories}
        assert by_key["q1"] == 1.0
        assert by_key["q2"] == 0.0
        assert by_key["q3"] == 1.0
        assert by_key["q4"] == 1.0
        assert by_key["q5"] == 0.7

    def test_excel_without_confidence_column_defaults(self, db_session, sample_tenant, importer, work_dir):
        fp = str(work_dir / "defaults.xlsx")
        pd.DataFrame([{"question": "Q", "answer": "A"}]).to_excel(fp, index=False)
        result = importer.import_from_excel(fp, sample_tenant.id)
        assert result["processed"] == 1
        memory = db_session.query(AiMemory).filter(AiMemory.tenant_id == sample_tenant.id).one()
        assert memory.category == "general"
        assert float(memory.confidence) == 1.0

    def test_excel_success_clears_batch_error(self, db_session, sample_tenant, importer, work_dir):
        fp = str(work_dir / "clean.xlsx")
        pd.DataFrame([{"question": "Q1", "answer": "A1"}]).to_excel(fp, index=False)
        result = importer.import_from_excel(fp, sample_tenant.id)
        assert result["errors"] == 0
        batch = db_session.get(AiTrainingBatch, result["batch_id"])
        assert batch.error_message is None

    def test_excel_generic_error_without_batch(self, work_dir, mocker):
        mocker.patch("services.training_importer.AiTrainingBatch", side_effect=RuntimeError("no batch"))
        fp = str(work_dir / "broken.xlsx")
        pd.DataFrame([{"question": "Q", "answer": "A"}]).to_excel(fp, index=False)
        result = TrainingImporter().import_from_excel(fp, 1)
        assert result["success"] is False
        assert result["batch_id"] is None

    def test_process_records_flush_and_error(self, db_session, sample_tenant, importer):
        records = [{"question": f"Q{i}", "answer": f"A{i}", "confidence": 1.0} for i in range(100)]
        records.append({"question": "bad", "answer": "bad", "confidence": "not-a-float"})
        processed, errors = importer._process_training_records(records, sample_tenant.id)
        assert processed == 100
        assert errors == 1
