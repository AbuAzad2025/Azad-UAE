from __future__ import annotations

from unittest.mock import MagicMock, patch

from utils.backup_optimizer import BackupOptimizer


class TestCompressBackup:
    def test_compresses_backup_and_returns_ratio(self, tmp_path):
        backup = tmp_path / "backup.sql"
        backup.write_bytes(b"x" * 100)

        with (
            patch("utils.backup_optimizer.os.path.getsize", side_effect=[100, 40]),
            patch("utils.backup_optimizer.os.remove") as remove,
            patch("utils.backup_optimizer.logger"),
        ):
            result = BackupOptimizer.compress_backup(str(backup))

        assert result["success"] is True
        assert result["compression_ratio"] == 60.0
        assert result["compressed_path"] == f"{backup}.gz"
        remove.assert_called_once_with(str(backup))

    def test_compression_failure_returns_error(self):
        with (
            patch("builtins.open", side_effect=OSError("read fail")),
            patch("utils.backup_optimizer.logger"),
        ):
            result = BackupOptimizer.compress_backup("/missing.sql")
        assert result["success"] is False


class TestCleanupOldBackups:
    def test_deletes_backups_beyond_keep_count(self, tmp_path):
        files = []
        for idx in range(3):
            path = tmp_path / f"backup-{idx}.sql"
            path.write_text("sql")
            files.append(path)

        with (
            patch("utils.backup_optimizer.os.path.getmtime", side_effect=[3, 2, 1]),
            patch("utils.backup_optimizer.os.remove") as remove,
            patch("utils.backup_optimizer.logger"),
        ):
            result = BackupOptimizer.cleanup_old_backups(str(tmp_path), keep_count=1)

        assert result["success"] is True
        assert result["deleted_count"] == 2
        assert result["kept_count"] == 1
        assert remove.call_count == 2

    def test_cleanup_failure_returns_error(self):
        with (
            patch(
                "utils.backup_optimizer.Path.glob",
                side_effect=RuntimeError("glob fail"),
            ),
            patch("utils.backup_optimizer.logger"),
        ):
            result = BackupOptimizer.cleanup_old_backups("/backups")
        assert result["success"] is False


class TestVerifyBackup:
    def test_accepts_plain_sql_dump(self, tmp_path):
        backup = tmp_path / "dump.sql"
        backup.write_text("PostgreSQL database dump\nCREATE TABLE users", encoding="utf-8")
        assert BackupOptimizer.verify_backup(str(backup)) is True

    def test_accepts_gzip_sql_dump(self, tmp_path):
        import gzip

        backup = tmp_path / "dump.sql.gz"
        with gzip.open(backup, "wb") as handle:
            handle.write(b"INSERT INTO users VALUES (1);")
        assert BackupOptimizer.verify_backup(str(backup)) is True

    def test_rejects_invalid_backup(self, tmp_path):
        backup = tmp_path / "bad.sql"
        backup.write_text("not a database dump", encoding="utf-8")
        assert BackupOptimizer.verify_backup(str(backup)) is False

    def test_verification_failure_returns_false(self):
        with (
            patch("builtins.open", side_effect=OSError("missing")),
            patch("utils.backup_optimizer.logger"),
        ):
            assert BackupOptimizer.verify_backup("/missing.sql") is False


class TestGetBackupInfo:
    def test_returns_sorted_backup_metadata(self, tmp_path):
        first = tmp_path / "a.sql.gz"
        second = tmp_path / "b.sql"
        stat_first = MagicMock(st_size=1024, st_mtime=1000.0)
        stat_second = MagicMock(st_size=2048, st_mtime=2000.0)

        with (
            patch("utils.backup_optimizer.Path.glob", return_value=[first, second]),
            patch("utils.backup_optimizer.os.stat", side_effect=[stat_first, stat_second]),
        ):
            result = BackupOptimizer.get_backup_info(str(tmp_path))

        assert result["success"] is True
        assert result["total_backups"] == 2
        assert result["backups"][0]["filename"] == "b.sql"
        assert result["backups"][0]["compressed"] is False
        assert result["backups"][1]["compressed"] is True

    def test_get_backup_info_failure(self):
        with patch("utils.backup_optimizer.Path.glob", side_effect=RuntimeError("fail")):
            result = BackupOptimizer.get_backup_info("/backups")
        assert result["success"] is False
