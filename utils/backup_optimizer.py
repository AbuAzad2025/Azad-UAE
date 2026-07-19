import os
import shutil
import gzip
from datetime import datetime
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger(__name__)


class BackupOptimizer:
    @staticmethod
    def compress_backup(backup_path: str) -> dict:
        try:
            with open(backup_path, "rb") as f_in:
                f_out: Any = gzip.open(f"{backup_path}.gz", "wb")
                with f_out:
                    shutil.copyfileobj(f_in, f_out)

            original_size = os.path.getsize(backup_path)
            compressed_size = os.path.getsize(f"{backup_path}.gz")
            compression_ratio = (1 - compressed_size / original_size) * 100

            os.remove(backup_path)

            logger.info(f"✅ Backup compressed: {compression_ratio:.1f}% smaller")

            return {
                "success": True,
                "original_size": original_size,
                "compressed_size": compressed_size,
                "compression_ratio": round(compression_ratio, 1),
                "compressed_path": f"{backup_path}.gz",
            }

        except Exception as e:
            logger.error(f"❌ Compression failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def cleanup_old_backups(backup_dir: str, keep_count: int = 10):
        try:
            backup_files = sorted(
                list(Path(backup_dir).glob("*.sql*"))
                + list(Path(backup_dir).glob("*.dump*")),
                key=os.path.getmtime,
                reverse=True,
            )

            deleted = 0
            for backup_file in backup_files[keep_count:]:
                os.remove(backup_file)
                deleted += 1
                logger.info(f"🗑️ Deleted old backup: {backup_file.name}")

            return {
                "success": True,
                "deleted_count": deleted,
                "kept_count": min(len(backup_files), keep_count),
            }

        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def verify_backup(backup_path: str) -> bool:
        try:
            import gzip

            def check_sql_dump(content: bytes) -> bool:
                text = content.decode("utf-8", errors="ignore")
                markers = ["PostgreSQL", "SET ", "CREATE TABLE", "COPY ", "INSERT INTO"]
                return any(m in text for m in markers)

            if backup_path.endswith(".gz"):
                with gzip.open(backup_path, "rb") as gz:
                    data = gz.read()
                return check_sql_dump(data)
            else:
                with open(backup_path, "rb") as fh:
                    data = fh.read()
                return check_sql_dump(data)
        except Exception as e:
            logger.error(f"❌ Verification failed: {e}")
            return False

    @staticmethod
    def get_backup_info(backup_dir: str) -> dict:
        try:
            backups: list[dict[str, Any]] = []
            for backup_file in Path(backup_dir).glob("*.sql*"):
                stat = os.stat(backup_file)
                backups.append(
                    {
                        "filename": backup_file.name,
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "compressed": backup_file.suffix == ".gz",
                    }
                )

            backups.sort(key=lambda x: x["created"], reverse=True)

            return {
                "success": True,
                "total_backups": len(backups),
                "total_size_mb": sum(b["size_mb"] for b in backups),
                "backups": backups,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
