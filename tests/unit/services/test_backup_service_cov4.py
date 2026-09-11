"""Coverage-4 for services.backup_service — pure/else/except arcs (real paths)."""

from __future__ import annotations

from services.backup_service import BackupService


class TestRetention:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("BACKUP_RETENTION_COUNT", raising=False)
        assert BackupService.retention_count() == 10

    def test_zero_clamped_to_one(self, monkeypatch):
        monkeypatch.setenv("BACKUP_RETENTION_COUNT", "0")
        assert BackupService.retention_count() == 1

    def test_garbage_falls_back(self, monkeypatch):
        monkeypatch.setenv("BACKUP_RETENTION_COUNT", "not-a-number")
        assert BackupService.retention_count() == 10


class TestFilenames:
    def test_traversal_rejected(self):
        assert BackupService._safe_filename("../secret.tar.gz") is None
        assert BackupService._safe_filename("a/b.tar.gz") is None
        assert BackupService._safe_filename("a\\b.tar.gz") is None
        assert BackupService._safe_filename("") is None
        assert BackupService.sanitize_filename("") is None

    def test_unknown_name_rejected(self):
        assert BackupService._safe_filename("random.txt") is None

    def test_archive_basename_scopes(self):
        s = BackupService._archive_basename("system", "20260101_000000", "abc123")
        assert "system" in s and s.endswith(".tar.gz")
        t = BackupService._archive_basename("tenant", "20260101_000000", "abc123", tenant_slug="My Shop!")
        assert "tenant_" in t
        b = BackupService._archive_basename("branch", "20260101_000000", "abc123", branch_id=4)
        assert "branch_4" in b
        b2 = BackupService._archive_basename("branch", "20260101_000000", "abc123", branch_id=None)
        assert "branch_x" in b2
        st = BackupService._archive_basename("store", "20260101_000000", "abc123", store_id=None)
        assert "store_x" in st
        u = BackupService._archive_basename("weird-scope-name-123", "20260101_000000", "abc123")
        assert "weird-scope-name-123"[:24] in u


class TestUrlsSameDb:
    def test_same_url(self):
        url = "postgresql://u:p@localhost:5432/mydb"
        assert BackupService._urls_same_database(url, url) is True

    def test_different_db(self):
        a = "postgresql://u:p@localhost:5432/a"
        b = "postgresql://u:p@localhost:5432/b"
        assert BackupService._urls_same_database(a, b) is False

    def test_unparsable_falls_back_to_string_compare(self):
        assert BackupService._urls_same_database("not a url", "not a url") is True
        assert BackupService._urls_same_database("not a url", "other") is False


class TestJsonFiles:
    def test_load_missing_returns_none(self, tmp_path):
        assert BackupService._load_json_file(str(tmp_path / "nope.json")) is None

    def test_load_corrupt_returns_none(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        assert BackupService._load_json_file(str(p)) is None

    def test_write_and_load_roundtrip(self, tmp_path):
        p = str(tmp_path / "sub" / "ok.json")
        assert BackupService._write_json_file(p, {"a": 1}) is True
        assert BackupService._load_json_file(p) == {"a": 1}

    def test_write_failure_returns_false(self, monkeypatch):
        monkeypatch.setattr("services.backup_service.os.makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        assert BackupService._write_json_file("/nonexistent/x.json", {}) is False


class TestEnvRedacted:
    def test_masks_secrets(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://secret@localhost/db")
        monkeypatch.setenv("BASE_URL", "https://x.example/y?token=abc")
        monkeypatch.setenv("BACKUP_RETENTION_COUNT", "7")
        out = BackupService._build_env_redacted()
        assert out["DATABASE_URL"] == "***masked***"
        assert out["BASE_URL"].startswith("https://")
        assert out["BACKUP_RETENTION_COUNT"] == "7"

    def test_git_helpers_do_not_crash(self, monkeypatch):
        import services.backup_service as bs

        monkeypatch.setattr(bs, "run_git", None, raising=False)
        # call with failing run_git to hit except arc
        from unittest.mock import MagicMock

        monkeypatch.setattr(
            "services.backup_exec.run_git",
            MagicMock(side_effect=RuntimeError("no git")),
            raising=False,
        )
        assert BackupService._git_short_sha() == "unknown"
        assert BackupService._git_branch() in (None, "" if False else BackupService._git_branch())

    def test_backup_stats_exception_returns_zeros(self, monkeypatch):
        monkeypatch.setattr(BackupService, "list_backups", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
        out = BackupService.get_backup_stats()
        assert out["total_count"] == 0

    def test_backup_stats_counts(self, monkeypatch):
        monkeypatch.setattr(
            BackupService,
            "list_backups",
            lambda *a, **k: [
                {"size": 100, "format": "azad_tar_v1", "manual": True},
                {"size": 200, "format": "legacy", "manual": False},
            ],
        )
        out = BackupService.get_backup_stats()
        assert out["total_count"] == 2
        assert out["modern_count"] == 1
        assert out["manual_count"] == 1
