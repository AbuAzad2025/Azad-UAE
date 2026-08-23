"""Tests for services.restore_drill — scratch-db steps mocked, no real restore runs."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy

from services.restore_drill import KEY_TABLES, RestoreDrillService


@pytest.fixture(autouse=True)
def _drill_log_to_tmp(monkeypatch, tmp_path):
    """Redirect the drill report log into the test temp dir."""
    monkeypatch.setattr("services.restore_drill.DRILL_LOG_PATH", str(tmp_path / "logs" / "restore_drill.log"))
    yield


@pytest.fixture
def scratch_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://postgres:secret@localhost:5432/prod_live")
    monkeypatch.setenv("RESTORE_DRILL_DB", "azad_restore_drill_scratch")
    return None


class TestResolveScratchDatabaseUrl:
    def test_requires_env_var(self, monkeypatch):
        monkeypatch.delenv("RESTORE_DRILL_DB", raising=False)
        url, err = RestoreDrillService.resolve_scratch_database_url()
        assert url is None
        assert "RESTORE_DRILL_DB" in err

    @pytest.mark.parametrize("name", ["azad_uae", "azad_uae_test", "postgres", "template0"])
    def test_refuses_protected_names(self, monkeypatch, name):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/whatever")
        monkeypatch.setenv("RESTORE_DRILL_DB", name)
        url, err = RestoreDrillService.resolve_scratch_database_url()
        assert url is None
        assert "protected" in err

    def test_refuses_live_database_name(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@127.0.0.1:5432/prod_live")
        monkeypatch.setenv("RESTORE_DRILL_DB", "prod_live")
        url, err = RestoreDrillService.resolve_scratch_database_url()
        assert url is None
        assert "matches the live database" in err

    def test_builds_scratch_url_and_normalizes_localhost(self, scratch_env):
        url, err = RestoreDrillService.resolve_scratch_database_url()
        assert err == ""
        assert url.endswith("/azad_restore_drill_scratch")
        assert "@127.0.0.1:" in url
        assert "prod_live" not in url
        assert url.startswith("postgresql")

    def test_missing_base_url_reported(self, monkeypatch):
        monkeypatch.setenv("RESTORE_DRILL_DB", "scratch_ok_name")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("SQLALCHEMY_DATABASE_URI", raising=False)
        url, err = RestoreDrillService.resolve_scratch_database_url()
        assert url is None
        assert "DATABASE_URL" in err


class TestRowCountSanity:
    def test_counts_key_tables(self, monkeypatch, scratch_env):
        responses = iter([3, 7, 2])
        scalar_mock = MagicMock(side_effect=lambda: next(responses))
        engine = MagicMock()
        conn = MagicMock()
        conn.execute.return_value.scalar = scalar_mock
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        engine.connect.return_value = ctx
        with patch.object(sqlalchemy, "create_engine", return_value=engine):
            out = RestoreDrillService.row_count_sanity("postgresql://scratch")
        assert out["ok"] is True
        assert out["counts"] == {"users": 3, "sales": 7, "purchases": 2}
        assert set(out["counts"]) == set(KEY_TABLES)

    def test_empty_users_fails_sanity(self, monkeypatch, scratch_env):
        responses = iter([0, 0, 0])
        engine = MagicMock()
        conn = MagicMock()
        conn.execute.return_value.scalar.side_effect = lambda: next(responses)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        engine.connect.return_value = ctx
        with patch.object(sqlalchemy, "create_engine", return_value=engine), patch("time.sleep"):
            out = RestoreDrillService.row_count_sanity("postgresql://scratch")
        assert out["ok"] is False
        assert any("users" in e for e in out["errors"])

    def test_transient_disconnect_retried_once(self, monkeypatch, scratch_env):
        from sqlalchemy.exc import OperationalError

        transient = OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))
        good_engine = MagicMock()
        conn = MagicMock()
        responses = iter([5, 4, 1])
        conn.execute.return_value.scalar.side_effect = lambda: next(responses)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        good_engine.connect.return_value = ctx

        engines = iter([self._failing_engine(transient), good_engine])
        with (
            patch.object(sqlalchemy, "create_engine", side_effect=lambda url, **kw: next(engines)),
            patch("time.sleep") as sleeper,
        ):
            out = RestoreDrillService.row_count_sanity("postgresql://scratch")
        assert out["ok"] is True
        assert out["counts"]["users"] == 5
        sleeper.assert_called_once()

    def _failing_engine(self, error):
        engine = MagicMock()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(side_effect=error)
        ctx.__exit__ = MagicMock(return_value=False)
        engine.connect.return_value = ctx
        return engine


class TestWriteDrillReport:
    def test_appends_parseable_json_line(self, tmp_path):
        path = RestoreDrillService.write_drill_report({"ok": True, "counts": {"users": 1}})
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["ok"] is True
        assert "timestamp" in payload


class TestRunDrill:
    def test_reports_when_no_artifact_available(self, scratch_env):
        with (
            patch(
                "utils.offsite_backup.download_latest_offsite_artifact",
                return_value={"ok": False, "error": "not configured"},
            ),
            patch("services.backup_service.BackupService.list_backups", return_value=[]),
        ):
            result = RestoreDrillService.run_drill(source="auto")
        assert result["ok"] is False
        assert any("no local backups" in e for e in result["errors"])
        assert os.path.exists(result["report_path"])

    def test_happy_path_offsite_origin(self, scratch_env, tmp_path):
        artifact_file = tmp_path / "azad_backup_system_x.tar.gz"
        artifact_file.write_bytes(b"fake")

        with (
            patch(
                "utils.offsite_backup.download_latest_offsite_artifact",
                return_value={"ok": True, "path": str(artifact_file), "key": "backups/x.tar.gz"},
            ) as dl,
            patch.object(RestoreDrillService, "restore_into_scratch", return_value={"ok": True, "errors": []}),
            patch.object(
                RestoreDrillService,
                "row_count_sanity",
                return_value={"ok": True, "errors": [], "counts": {"users": 2, "sales": 1, "purchases": 0}},
            ),
        ):
            result = RestoreDrillService.run_drill(source="auto")

        assert dl.called
        assert result["ok"] is True
        assert result["artifact_origin"] == "offsite"
        assert result["restore_ok"] is True
        assert result["counts"] == {"users": 2, "sales": 1, "purchases": 0}
        report = json.loads(open(result["report_path"], encoding="utf-8").read().strip())
        assert report["ok"] is True

    def test_failed_restore_skips_sanity_but_reports(self, scratch_env):
        with (
            patch(
                "services.restore_drill.RestoreDrillService.acquire_artifact",
                return_value=({"path": "/tmp/x.tar.gz", "origin": "local"}, ""),
            ),
            patch(
                "services.restore_drill.RestoreDrillService.restore_into_scratch",
                return_value={"ok": False, "errors": ["pg_restore failed"]},
            ) as restore_mock,
            patch.object(RestoreDrillService, "row_count_sanity") as sanity_mock,
        ):
            result = RestoreDrillService.run_drill(source="local")
        assert result["ok"] is False
        assert result["restore_ok"] is False
        assert any("pg_restore failed" in e for e in result["errors"])
        sanity_mock.assert_not_called()
        restore_mock.assert_called_once()

    def test_missing_scratch_env_short_circuits(self, monkeypatch):
        monkeypatch.delenv("RESTORE_DRILL_DB", raising=False)
        result = RestoreDrillService.run_drill()
        assert result["ok"] is False
        assert any("RESTORE_DRILL_DB" in e for e in result["errors"])
        assert os.path.exists(result["report_path"])


class TestBackupServiceOffsiteHook:
    def test_disabled_returns_disabled_status(self, monkeypatch):
        from services.backup_service import BackupService

        monkeypatch.delenv("OFFSITE_BACKUP_ENABLED", raising=False)
        status = BackupService._maybe_upload_offsite("/nonexistent/path.tar.gz")
        assert status == {"offsite_status": "disabled"}

    def test_configured_upload_merged_into_status(self, monkeypatch, tmp_path):
        from services.backup_service import BackupService

        monkeypatch.setenv("OFFSITE_BACKUP_ENABLED", "1")
        monkeypatch.setenv("OFFSITE_BACKUP_BUCKET", "bkt")
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(b"x")
        with patch(
            "utils.offsite_backup.upload_backup_archive",
            return_value={"ok": True, "key": "backups/a.tar.gz", "attempts": 1, "error": None},
        ):
            status = BackupService._maybe_upload_offsite(str(archive))
        assert status["offsite_status"] == "uploaded"
        assert status["offsite_key"] == "backups/a.tar.gz"

    def test_hook_never_raises_on_uploader_crash(self, monkeypatch, tmp_path):
        from services.backup_service import BackupService

        monkeypatch.setenv("OFFSITE_BACKUP_ENABLED", "1")
        monkeypatch.setenv("OFFSITE_BACKUP_BUCKET", "bkt")
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(b"x")
        with patch("utils.offsite_backup.upload_backup_archive", side_effect=RuntimeError("kaboom")):
            status = BackupService._maybe_upload_offsite(str(archive))
        assert status["offsite_status"] == "failed"
        assert "kaboom" in status["offsite_error"]
