"""
Production backup/restore for PostgreSQL + uploads (PythonAnywhere-ready).

Artifact: instance/backups/azad_backup_YYYYMMDD_HHMMSS_<shortsha>.tar.gz
  - db.dump          (pg_dump -Fc)
  - uploads.tar.gz
  - manifest.json
  - env.example.redacted
  - README_RESTORE.txt
"""
from __future__ import annotations

import glob
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BACKUP_VERSION = 1
BACKUP_BASENAME_RE = re.compile(
    r"^azad_backup_\d{8}_\d{6}_[0-9a-f]+\.tar\.gz$",
    re.IGNORECASE,
)
LEGACY_NAME_RE = re.compile(
    r"^(manual_backup_|auto_backup_).+\.(sql\.gz|dump)$",
    re.IGNORECASE,
)


class BackupService:
    """PostgreSQL + uploads backup; safe restore only to a different database URL."""

    _BASEDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    BACKUP_DIR = os.path.join(_BASEDIR, "instance", "backups")
    BACKUP_PREFIX = "azad_backup_"
    LEGACY_MANUAL_PREFIX = "manual_backup_"
    LEGACY_AUTO_PREFIX = "auto_backup_"

    @classmethod
    def retention_count(cls) -> int:
        try:
            return max(1, int(os.environ.get("BACKUP_RETENTION_COUNT", "10")))
        except (TypeError, ValueError):
            return 10

    @classmethod
    def _schedule_settings_path(cls) -> str:
        return os.path.join(cls._BASEDIR, "instance", "backup_settings.json")

    @classmethod
    def _schedule_state_path(cls) -> str:
        return os.path.join(cls._BASEDIR, "instance", "backup_state.json")

    @classmethod
    def _load_json_file(cls, file_path: str) -> Optional[Dict]:
        try:
            if not os.path.exists(file_path):
                return None
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    @classmethod
    def _write_json_file(cls, file_path: str, data: Dict) -> bool:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    @classmethod
    def get_schedule_settings(cls) -> Dict:
        settings = cls._load_json_file(cls._schedule_settings_path()) or {}
        return {
            "enabled": bool(settings.get("enabled", True)),
            "frequency": str(settings.get("frequency", "daily")),
            "backup_time": str(settings.get("backup_time", "02:00")),
            "keep_count": int(settings.get("keep_count", cls.retention_count())),
        }

    @classmethod
    def save_schedule_settings(cls, settings: Dict) -> bool:
        normalized = {
            "enabled": bool(settings.get("enabled", True)),
            "frequency": str(settings.get("frequency", "daily")),
            "backup_time": str(settings.get("backup_time", "02:00")),
            "keep_count": int(settings.get("keep_count", cls.retention_count())),
        }
        return cls._write_json_file(cls._schedule_settings_path(), normalized)

    @classmethod
    def get_schedule_state(cls) -> Dict:
        state = cls._load_json_file(cls._schedule_state_path()) or {}
        return {
            "last_run_at": state.get("last_run_at"),
            "last_success_at": state.get("last_success_at"),
            "last_error": state.get("last_error"),
            "last_filename": state.get("last_filename"),
            "last_manual": state.get("last_manual"),
            "last_action": state.get("last_action"),
        }

    @classmethod
    def _set_schedule_state(cls, **kwargs) -> None:
        state = cls._load_json_file(cls._schedule_state_path()) or {}
        state.update(kwargs)
        cls._write_json_file(cls._schedule_state_path(), state)

    @classmethod
    def get_backup_stats(cls) -> Dict:
        try:
            backups = cls.list_backups()
            total_size_bytes = sum(int(b.get("size", 0) or 0) for b in backups)
            latest = backups[0] if backups else None
            modern = sum(1 for b in backups if b.get("format") == "azad_tar_v1")
            manual_count = sum(1 for b in backups if b.get("manual"))
            return {
                "total_count": len(backups),
                "modern_count": modern,
                "legacy_count": len(backups) - modern,
                "manual_count": manual_count,
                "auto_count": max(0, len(backups) - manual_count),
                "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
                "latest_backup": latest,
            }
        except Exception:
            return {
                "total_count": 0,
                "modern_count": 0,
                "legacy_count": 0,
                "total_size_mb": 0,
                "latest_backup": None,
            }

    @classmethod
    def initialize(cls) -> bool:
        try:
            os.makedirs(cls.BACKUP_DIR, exist_ok=True)
            return True
        except Exception as e:
            logger.error("Failed to initialize backup directory: %s", e)
            return False

    @classmethod
    def pg_tools_status(cls) -> Dict[str, Any]:
        dump = cls._resolve_pg_tool("pg_dump", "PG_DUMP_PATH")
        restore = cls._resolve_pg_tool("pg_restore", "PG_RESTORE_PATH")
        version = None
        if dump:
            try:
                proc = subprocess.run(
                    [dump, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                version = (proc.stdout or proc.stderr or "").strip().split("\n")[0]
            except Exception:
                version = None
        return {
            "pg_dump": dump,
            "pg_restore": restore,
            "pg_dump_version": version,
            "available": bool(dump and restore),
        }

    @classmethod
    def _parse_db_url(cls, url: Optional[str] = None) -> Optional[Dict[str, str]]:
        try:
            if url:
                from sqlalchemy.engine.url import make_url

                engine_url = make_url(url)
            else:
                from extensions import db

                engine_url = db.engine.url
            if "postgresql" not in engine_url.drivername and "postgres" not in engine_url.drivername:
                return None
            host = engine_url.host or "127.0.0.1"
            if str(host).lower() in ("localhost", "::1"):
                host = "127.0.0.1"
            return {
                "host": str(host),
                "port": str(engine_url.port or 5432),
                "username": str(engine_url.username or ""),
                "password": str(engine_url.password or ""),
                "dbname": str((engine_url.database or "").lstrip("/")),
            }
        except Exception as e:
            logger.error("Error parsing DB URL: %s", e)
            return None

    @classmethod
    def _mask_db_host(cls, host: str) -> str:
        if not host:
            return "***"
        if host in ("127.0.0.1", "localhost"):
            return host
        parts = host.split(".")
        if len(parts) >= 2:
            return f"{parts[0]}.***.{parts[-1]}"
        return "***"

    @classmethod
    def _normalize_db_identity(cls, params: Dict[str, str]) -> str:
        return "|".join(
            [
                params.get("host", ""),
                params.get("port", ""),
                params.get("username", ""),
                params.get("dbname", ""),
            ]
        )

    @classmethod
    def _resolve_pg_tool(cls, exe_name: str, env_var: str) -> Optional[str]:
        value = (os.environ.get(env_var) or "").strip().strip('"')
        if value and os.path.isfile(value):
            return value
        found = shutil.which(exe_name)
        if found:
            return found
        if os.name != "nt":
            return None
        candidates: List[str] = []
        for pf in filter(
            None, [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
        ):
            candidates.extend(glob.glob(os.path.join(pf, "PostgreSQL", "*", "bin", exe_name)))
            candidates.extend(
                glob.glob(os.path.join(pf, "PostgreSQL", "*", "bin", exe_name + ".exe"))
            )
        candidates.extend(glob.glob(os.path.join("C:\\", "PostgreSQL", "*", "bin", exe_name)))
        candidates.extend(
            glob.glob(os.path.join("C:\\", "PostgreSQL", "*", "bin", exe_name + ".exe"))
        )
        for c in candidates:
            if os.path.isfile(c):
                return c
        return None

    @classmethod
    def _sha256_file(cls, path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @classmethod
    def _git_short_sha(cls) -> str:
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=cls._BASEDIR,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0:
                return (proc.stdout or "").strip()[:12] or "unknown"
        except Exception:
            pass
        return "unknown"

    @classmethod
    def _git_branch(cls) -> Optional[str]:
        try:
            proc = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=cls._BASEDIR,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0:
                br = (proc.stdout or "").strip()
                return br or None
        except Exception:
            pass
        return None

    @classmethod
    def _alembic_info(cls) -> Tuple[Optional[str], Optional[str]]:
        try:
            from flask import current_app
            from flask_migrate import current as alembic_current
            from flask_migrate import heads as alembic_heads

            with current_app.app_context():
                cur = alembic_current()
                hd = alembic_heads()
            return str(cur) if cur else None, str(hd) if hd else None
        except Exception:
            return None, None

    @classmethod
    def _upload_roots(cls) -> List[str]:
        roots = [os.path.join(cls._BASEDIR, "static", "uploads")]
        try:
            from flask import current_app

            folder = current_app.config.get("UPLOAD_FOLDER")
            if folder:
                abs_folder = (
                    folder
                    if os.path.isabs(folder)
                    else os.path.join(cls._BASEDIR, folder)
                )
                if abs_folder not in roots and os.path.isdir(abs_folder):
                    roots.append(abs_folder)
        except Exception:
            pass
        return [r for r in roots if os.path.isdir(r)]

    @classmethod
    def _build_uploads_archive(cls, dest_path: str) -> Dict[str, Any]:
        file_count = 0
        with tarfile.open(dest_path, "w:gz") as tar:
            for root_dir in cls._upload_roots():
                base_name = os.path.relpath(root_dir, cls._BASEDIR).replace("\\", "/")
                for dirpath, dirnames, filenames in os.walk(root_dir):
                    dirnames[:] = [
                        d
                        for d in dirnames
                        if d != "__pycache__" and not d.startswith(".")
                    ]
                    for fn in filenames:
                        if fn.endswith((".pyc", ".log")):
                            continue
                        full = os.path.join(dirpath, fn)
                        arcname = os.path.join(
                            base_name,
                            os.path.relpath(full, root_dir),
                        ).replace("\\", "/")
                        tar.add(full, arcname=arcname)
                        file_count += 1
        return {"upload_roots": cls._upload_roots(), "files_packed": file_count}

    @classmethod
    def _build_env_redacted(cls) -> Dict[str, str]:
        keys = [
            "DATABASE_URL",
            "SQLALCHEMY_DATABASE_URI",
            "SECRET_KEY",
            "BASE_URL",
            "REDIS_URL",
            "FLASK_ENV",
            "BACKUP_RETENTION_COUNT",
            "TARGET_TEST_DATABASE_URL",
        ]
        out: Dict[str, str] = {}
        for key in keys:
            val = os.environ.get(key)
            if val is None:
                continue
            if key in ("DATABASE_URL", "SQLALCHEMY_DATABASE_URI", "REDIS_URL"):
                out[key] = "***masked***"
            elif key == "SECRET_KEY":
                out[key] = "***masked***"
            elif key == "BASE_URL":
                out[key] = val.split("?")[0][:120]
            else:
                out[key] = val[:80] if len(val) <= 80 else val[:40] + "..."
        return out

    @classmethod
    def _pre_backup_checks_summary(cls) -> Dict[str, Any]:
        summary: Dict[str, Any] = {"checks": []}
        params = cls._parse_db_url()
        if not params:
            summary["checks"].append("postgresql_url: FAIL")
            return summary
        try:
            from sqlalchemy import create_engine, text

            url = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI")
            if not url:
                summary["checks"].append("database_url: missing")
                return summary
            engine = create_engine(url)
            with engine.connect() as conn:
                tables = int(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM information_schema.tables "
                            "WHERE table_schema='public' AND table_type='BASE TABLE'"
                        )
                    ).scalar()
                    or 0
                )
                dual = int(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM gl_journal_lines "
                            "WHERE debit > 0 AND credit > 0"
                        )
                    ).scalar()
                    or 0
                )
                unbal = int(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM gl_journal_entries "
                            "WHERE ABS(COALESCE(total_debit,0)-COALESCE(total_credit,0)) > 0.001"
                        )
                    ).scalar()
                    or 0
                )
            summary["tables_count"] = tables
            summary["gl_dual_side"] = dual
            summary["unbalanced_journal_entries"] = unbal
            summary["checks"].append("basic_integrity: OK" if dual == 0 and unbal == 0 else "WARN")
        except Exception as e:
            summary["checks"].append(f"basic_integrity: error ({type(e).__name__})")
        return summary

    @classmethod
    def _run_pg_dump_custom(cls, params: Dict[str, str], dest_file: str) -> Tuple[bool, str]:
        pg_dump = cls._resolve_pg_tool("pg_dump", "PG_DUMP_PATH")
        if not pg_dump:
            return False, "pg_dump not found. Set PG_DUMP_PATH to your PostgreSQL bin directory."
        env = os.environ.copy()
        if params.get("password"):
            env["PGPASSWORD"] = params["password"]
        cmd = [
            pg_dump,
            "--host",
            params["host"],
            "--port",
            params["port"],
            "--username",
            params["username"],
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            dest_file,
            params["dbname"],
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=3600)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "pg_dump failed").strip()
            return False, err[:800]
        if not os.path.isfile(dest_file) or os.path.getsize(dest_file) == 0:
            return False, "pg_dump produced empty file"
        return True, ""

    @classmethod
    def sanitize_filename(cls, filename: str) -> Optional[str]:
        """Public wrapper for path traversal-safe backup names."""
        return cls._safe_filename(filename)

    @classmethod
    def _safe_filename(cls, filename: str) -> Optional[str]:
        if not filename or ".." in filename or "/" in filename or "\\" in filename:
            return None
        base = os.path.basename(filename)
        if BACKUP_BASENAME_RE.match(base) or LEGACY_NAME_RE.match(base):
            return base
        return None

    @classmethod
    def _backup_path(cls, filename: str) -> Optional[str]:
        safe = cls._safe_filename(filename)
        if not safe:
            return None
        path = os.path.join(cls.BACKUP_DIR, safe)
        if not os.path.abspath(path).startswith(os.path.abspath(cls.BACKUP_DIR)):
            return None
        return path

    @classmethod
    def create_backup(
        cls,
        manual: bool = True,
        description: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Create unified tar.gz backup (PostgreSQL custom dump + uploads)."""
        cls.initialize()
        params = cls._parse_db_url()
        if not params:
            cls._set_schedule_state(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_error="PostgreSQL DATABASE_URL required",
                last_action="create_backup",
            )
            return None

        tools = cls.pg_tools_status()
        if not tools.get("pg_dump"):
            msg = tools.get("pg_dump") or "pg_dump not found"
            cls._set_schedule_state(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_error="pg_dump not found. Set PG_DUMP_PATH.",
                last_action="create_backup",
            )
            logger.error(msg)
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_sha = cls._git_short_sha()
        archive_name = f"{cls.BACKUP_PREFIX}{timestamp}_{short_sha}.tar.gz"
        archive_path = os.path.join(cls.BACKUP_DIR, archive_name)
        work_dir = tempfile.mkdtemp(prefix="azad_backup_")

        try:
            db_dump_path = os.path.join(work_dir, "db.dump")
            ok, err = cls._run_pg_dump_custom(params, db_dump_path)
            if not ok:
                cls._set_schedule_state(
                    last_run_at=datetime.now(timezone.utc).isoformat(),
                    last_error=err,
                    last_action="create_backup",
                )
                return None

            uploads_path = os.path.join(work_dir, "uploads.tar.gz")
            uploads_meta = cls._build_uploads_archive(uploads_path)

            alembic_current, alembic_heads = cls._alembic_info()
            pre_checks = cls._pre_backup_checks_summary()
            approx_rows = 0
            try:
                from sqlalchemy import create_engine, text

                url = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI")
                if url:
                    with create_engine(url).connect() as conn:
                        approx_rows = int(
                            conn.execute(
                                text(
                                    "SELECT COALESCE(SUM(n_live_tup),0)::bigint "
                                    "FROM pg_stat_user_tables"
                                )
                            ).scalar()
                            or 0
                        )
            except Exception:
                pass

            file_hashes = {
                "db.dump": cls._sha256_file(db_dump_path),
                "uploads.tar.gz": cls._sha256_file(uploads_path),
            }

            manifest = {
                "app_name": "Azad-UAE",
                "backup_version": BACKUP_VERSION,
                "format": "azad_tar_v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "git_commit": short_sha,
                "git_branch": cls._git_branch(),
                "alembic_current": alembic_current,
                "alembic_heads": alembic_heads,
                "database_driver": "postgresql",
                "database_host_masked": cls._mask_db_host(params["host"]),
                "database_name": params["dbname"],
                "tables_count": pre_checks.get("tables_count"),
                "approximate_rows": approx_rows,
                "includes": ["db_dump", "uploads", "manifest", "env.example.redacted", "README_RESTORE.txt"],
                "sha256": file_hashes,
                "command_versions": {
                    "pg_dump": tools.get("pg_dump_version"),
                    "python": sys.version.split()[0],
                },
                "uploads_meta": uploads_meta,
                "pre_backup_checks": pre_checks,
                "manual": bool(manual),
                "description": description or "",
            }

            manifest_path = os.path.join(work_dir, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

            env_path = os.path.join(work_dir, "env.example.redacted")
            with open(env_path, "w", encoding="utf-8") as f:
                json.dump(cls._build_env_redacted(), f, indent=2)

            readme_path = os.path.join(work_dir, "README_RESTORE.txt")
            cls._write_readme_restore(readme_path)

            with tarfile.open(archive_path, "w:gz") as tar:
                for member in (
                    "db.dump",
                    "uploads.tar.gz",
                    "manifest.json",
                    "env.example.redacted",
                    "README_RESTORE.txt",
                ):
                    tar.add(os.path.join(work_dir, member), arcname=member)

            size = os.path.getsize(archive_path)
            sidecar = {
                "filename": archive_name,
                "path": archive_path,
                "format": "azad_tar_v1",
                "timestamp": timestamp,
                "datetime": manifest["created_at"],
                "size": size,
                "size_mb": round(size / (1024 * 1024), 2),
                "git_commit": short_sha,
                "alembic_current": alembic_current,
                "manual": bool(manual),
                "description": description,
                "checksum": cls._sha256_file(archive_path),
            }
            with open(archive_path + ".meta.json", "w", encoding="utf-8") as f:
                json.dump(sidecar, f, indent=2, ensure_ascii=False)

            cls._apply_retention()
            cls._set_schedule_state(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_success_at=datetime.now(timezone.utc).isoformat(),
                last_error=None,
                last_filename=archive_name,
                last_manual=bool(manual),
                last_action="create_backup",
            )
            logger.info("Backup created: %s", archive_name)
            return sidecar
        except Exception as e:
            cls._set_schedule_state(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_error=str(e)[:800],
                last_action="create_backup",
            )
            logger.exception("Backup failed")
            if os.path.exists(archive_path):
                try:
                    os.remove(archive_path)
                except OSError:
                    pass
            return None
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    @classmethod
    def _write_readme_restore(cls, path: str) -> None:
        text = """Azad-UAE backup restore (PythonAnywhere / PostgreSQL)
============================================================

1. Create a NEW empty PostgreSQL database (do not restore over production in place).
2. Upload the azad_backup_*.tar.gz to instance/backups/ on the server.
3. Extract: tar -xzf azad_backup_YYYYMMDD_HHMMSS_<sha>.tar.gz -C /tmp/azad_restore
4. Restore DB:
   pg_restore --clean --if-exists --no-owner --no-privileges \\
     --dbname=postgresql://USER:***@HOST:PORT/NEW_DB_NAME /tmp/azad_restore/db.dump
5. Restore uploads:
   tar -xzf uploads.tar.gz -C /home/USERNAME/Azad-UAE/static/
6. Configure .env with DATABASE_URL pointing to the NEW database (never commit .env).
7. Verify:
   flask db current
   python tools/qa/predeploy_check.py --profile production-readiness

This archive does NOT include secrets, .env, or AI runtime memory.
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    @classmethod
    def _apply_retention(cls) -> None:
        keep = cls.retention_count()
        modern = [
            b
            for b in cls.list_backups()
            if b.get("format") == "azad_tar_v1"
        ]
        if len(modern) <= keep:
            return
        for b in sorted(modern, key=lambda x: x.get("timestamp", ""))[: len(modern) - keep]:
            cls.delete_backup(b["filename"])

    @classmethod
    def auto_backup_daily(cls) -> Optional[Dict]:
        settings = cls.get_schedule_settings()
        now_iso = datetime.now(timezone.utc).isoformat()
        cls._set_schedule_state(last_run_at=now_iso, last_action="auto_backup")
        if not settings.get("enabled", True):
            return None
        return cls.create_backup(
            manual=False,
            description=f"Scheduled {settings.get('frequency', 'daily')} backup",
        )

    @classmethod
    def list_backups(cls) -> List[Dict]:
        cls.initialize()
        backups: List[Dict] = []
        backup_dir = Path(cls.BACKUP_DIR)
        patterns = ["azad_backup_*.tar.gz", "*.sql.gz", "*.dump"]
        seen = set()
        files: List[Path] = []
        for pat in patterns:
            files.extend(backup_dir.glob(pat))
        for backup_file in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
            if backup_file.name in seen:
                continue
            seen.add(backup_file.name)
            meta_path = str(backup_file) + ".meta.json"
            metadata: Dict[str, Any] = {}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                except Exception:
                    metadata = {}
            if not metadata:
                is_modern = backup_file.name.startswith(cls.BACKUP_PREFIX)
                metadata = {
                    "filename": backup_file.name,
                    "path": str(backup_file),
                    "size": backup_file.stat().st_size,
                    "size_mb": round(backup_file.stat().st_size / (1024 * 1024), 2),
                    "datetime": datetime.fromtimestamp(
                        backup_file.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                    "format": "azad_tar_v1" if is_modern else "legacy",
                    "manual": cls.LEGACY_MANUAL_PREFIX in backup_file.name,
                }
            if backup_file.name.endswith(".tar.gz") and metadata.get("format") != "legacy":
                metadata.setdefault("format", "azad_tar_v1")
            backups.append(metadata)
        return backups

    @classmethod
    def get_backup_info(cls, filename: str) -> Optional[Dict[str, Any]]:
        path = cls._backup_path(filename)
        if not path or not os.path.exists(path):
            return None
        info: Dict[str, Any] = {"filename": os.path.basename(path), "path": path}
        sidecar = path + ".meta.json"
        if os.path.exists(sidecar):
            try:
                with open(sidecar, "r", encoding="utf-8") as f:
                    info["sidecar"] = json.load(f)
            except Exception:
                pass
        if filename.endswith(".tar.gz"):
            try:
                with tarfile.open(path, "r:gz") as tar:
                    if "manifest.json" in tar.getnames():
                        member = tar.extractfile("manifest.json")
                        if member:
                            info["manifest"] = json.loads(member.read().decode("utf-8"))
            except Exception as e:
                info["manifest_error"] = str(e)[:200]
        return info

    @classmethod
    def verify_backup(cls, filename: str) -> Dict[str, Any]:
        """Verify archive integrity; returns structured result."""
        result: Dict[str, Any] = {
            "valid": False,
            "filename": filename,
            "errors": [],
            "warnings": [],
        }
        path = cls._backup_path(filename)
        if not path or not os.path.exists(path):
            result["errors"].append("backup not found")
            return result
        if os.path.getsize(path) == 0:
            result["errors"].append("empty file")
            return result

        sidecar_path = path + ".meta.json"
        if os.path.exists(sidecar_path):
            try:
                with open(sidecar_path, "r", encoding="utf-8") as f:
                    sidecar = json.load(f)
                stored = sidecar.get("checksum")
                if stored and stored != cls._sha256_file(path):
                    result["errors"].append("archive checksum mismatch")
                    return result
            except Exception:
                result["warnings"].append("sidecar unreadable")

        if filename.endswith(".tar.gz") and filename.startswith(cls.BACKUP_PREFIX):
            return cls._verify_modern_archive(path, result)

        if filename.endswith(".gz") or filename.endswith(".dump"):
            if cls._verify_legacy_file(path, filename):
                result["valid"] = True
                result["format"] = "legacy"
            else:
                result["errors"].append("legacy backup corrupt")
            return result

        result["errors"].append("unknown backup format")
        return result

    @classmethod
    def _verify_legacy_file(cls, path: str, filename: str) -> bool:
        if os.path.getsize(path) == 0:
            return False
        if filename.endswith(".gz"):
            import gzip

            try:
                with gzip.open(path, "rb") as f:
                    f.read(1024)
                return True
            except Exception:
                return False
        if filename.endswith(".dump"):
            pg_restore = cls._resolve_pg_tool("pg_restore", "PG_RESTORE_PATH")
            if not pg_restore:
                return os.path.getsize(path) > 0
            proc = subprocess.run(
                [pg_restore, "--list", path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return proc.returncode == 0
        return False

    @classmethod
    def _verify_modern_archive(cls, path: str, result: Dict[str, Any]) -> Dict[str, Any]:
        required = {"db.dump", "uploads.tar.gz", "manifest.json"}
        work = tempfile.mkdtemp(prefix="azad_verify_")
        try:
            with tarfile.open(path, "r:gz") as tar:
                names = set(tar.getnames())
                missing = required - names
                if missing:
                    result["errors"].append(f"missing members: {sorted(missing)}")
                    return result
                tar.extract("manifest.json", work, filter="data")
                tar.extract("db.dump", work, filter="data")
            manifest_path = os.path.join(work, "manifest.json")
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            result["manifest"] = manifest
            db_path = os.path.join(work, "db.dump")
            expected = (manifest.get("sha256") or {}).get("db.dump")
            if expected and cls._sha256_file(db_path) != expected:
                result["errors"].append("db.dump checksum mismatch")
                return result
            pg_restore = cls._resolve_pg_tool("pg_restore", "PG_RESTORE_PATH")
            if pg_restore:
                proc = subprocess.run(
                    [pg_restore, "--list", db_path],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if proc.returncode != 0:
                    result["errors"].append("pg_restore --list failed")
                    return result
            else:
                result["warnings"].append("pg_restore not available; skipped dump list check")
            result["valid"] = True
            result["format"] = "azad_tar_v1"
            return result
        except Exception as e:
            result["errors"].append(str(e)[:200])
            return result
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @classmethod
    def prepare_restore_command(
        cls, filename: str, target_database_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return safe pg_restore instructions (never restores in-place)."""
        info = cls.get_backup_info(filename)
        if not info:
            return {"ok": False, "error": "backup not found"}
        target = (target_database_url or "").strip() or "postgresql://USER:***@HOST:PORT/NEW_DB_NAME"
        masked_target = "***"
        try:
            p = urlparse(target.replace("postgresql+psycopg2://", "postgresql://", 1))
            if p.hostname:
                masked_target = (
                    f"postgresql://{p.username or 'USER'}:***@"
                    f"{cls._mask_db_host(p.hostname)}:{p.port or 5432}/{p.path.lstrip('/')}"
                )
        except Exception:
            pass
        pg_restore = cls._resolve_pg_tool("pg_restore", "PG_RESTORE_PATH") or "pg_restore"
        lines = [
            "# Extract archive first",
            f"tar -xzf {filename} -C /tmp/azad_restore",
            "# Restore database to a NEW database only",
            f"{pg_restore} --clean --if-exists --no-owner --no-privileges "
            f'--dbname="{masked_target}" /tmp/azad_restore/db.dump',
            "# Restore uploads",
            "tar -xzf /tmp/azad_restore/uploads.tar.gz -C /path/to/Azad-UAE/static/",
            "flask db current",
            "python tools/qa/predeploy_check.py --profile production-readiness",
        ]
        return {
            "ok": True,
            "commands": lines,
            "warning": "Never restore over the live DATABASE_URL. Use a new database.",
            "masked_target": masked_target,
        }

    @classmethod
    def _urls_same_database(cls, url_a: str, url_b: str) -> bool:
        pa = cls._parse_db_url(url_a)
        pb = cls._parse_db_url(url_b)
        if not pa or not pb:
            return url_a.strip() == url_b.strip()
        return cls._normalize_db_identity(pa) == cls._normalize_db_identity(pb)

    @classmethod
    def restore_backup_to_target_db(
        cls,
        filename: str,
        target_database_url: str,
        *,
        confirmation: str = "",
        restore_uploads: bool = False,
    ) -> Dict[str, Any]:
        """
        Restore db.dump to target_database_url only if it differs from current DATABASE_URL.
        Requires confirmation text RESTORE CONFIRM unless ALLOW_DESTRUCTIVE_RESTORE=1.
        """
        outcome: Dict[str, Any] = {"ok": False, "errors": [], "warnings": []}
        if confirmation.strip() != "RESTORE CONFIRM":
            if os.environ.get("ALLOW_DESTRUCTIVE_RESTORE") != "1":
                outcome["errors"].append("Typed confirmation RESTORE CONFIRM required")
                return outcome

        path = cls._backup_path(filename)
        if not path:
            outcome["errors"].append("invalid filename")
            return outcome

        verify = cls.verify_backup(filename)
        if not verify.get("valid"):
            outcome["errors"].append("backup verification failed")
            outcome["details"] = verify
            return outcome

        current_url = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI") or ""
        if cls._urls_same_database(current_url, target_database_url):
            outcome["errors"].append(
                "Target database is the same as current DATABASE_URL. "
                "Use a different TARGET database or set ALLOW_DESTRUCTIVE_RESTORE=1 explicitly."
            )
            return outcome

        target_params = cls._parse_db_url(target_database_url)
        if not target_params:
            outcome["errors"].append("Invalid target PostgreSQL URL")
            return outcome

        pg_restore = cls._resolve_pg_tool("pg_restore", "PG_RESTORE_PATH")
        if not pg_restore:
            outcome["errors"].append("pg_restore not found")
            return outcome

        work = tempfile.mkdtemp(prefix="azad_restore_")
        try:
            if filename.endswith(".tar.gz") and filename.startswith(cls.BACKUP_PREFIX):
                with tarfile.open(path, "r:gz") as tar:
                    tar.extract("db.dump", work, filter="data")
                    if restore_uploads and "uploads.tar.gz" in tar.getnames():
                        tar.extract("uploads.tar.gz", work, filter="data")
                dump_path = os.path.join(work, "db.dump")
            elif filename.endswith(".dump"):
                dump_path = os.path.join(work, "legacy.dump")
                shutil.copy2(path, dump_path)
            else:
                outcome["errors"].append(
                    "Legacy .sql.gz restore to target DB: use prepare_restore_command / manual psql"
                )
                return outcome

            env = os.environ.copy()
            if target_params.get("password"):
                env["PGPASSWORD"] = target_params["password"]
            cmd = [
                pg_restore,
                "--host",
                target_params["host"],
                "--port",
                target_params["port"],
                "--username",
                target_params["username"],
                "--dbname",
                target_params["dbname"],
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                dump_path,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=3600)
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "pg_restore failed")[:800]
                outcome["errors"].append(err)
                return outcome

            if restore_uploads:
                uploads_archive = os.path.join(work, "uploads.tar.gz")
                if os.path.exists(uploads_archive):
                    for root in cls._upload_roots():
                        os.makedirs(root, exist_ok=True)
                    with tarfile.open(uploads_archive, "r:gz") as utar:
                        utar.extractall(cls._BASEDIR, filter="data")
                    outcome["warnings"].append("uploads restored to static paths")

            outcome["ok"] = True
            outcome["target_db"] = target_params["dbname"]
            outcome["masked_host"] = cls._mask_db_host(target_params["host"])
            return outcome
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @classmethod
    def restore_backup(cls, backup_filename: str) -> bool:
        """Deprecated: refuses in-place restore on current DATABASE_URL."""
        logger.warning(
            "restore_backup(%s) blocked — use restore_backup_to_target_db with a new database",
            backup_filename,
        )
        return False

    @classmethod
    def restore_custom_tables(cls, backup_filename: str, tables: List[str]) -> bool:
        logger.warning("restore_custom_tables blocked for production safety")
        return False

    @classmethod
    def delete_backup(cls, backup_filename: str) -> bool:
        safe = cls._safe_filename(backup_filename)
        if not safe:
            return False
        backup_path = os.path.join(cls.BACKUP_DIR, safe)
        meta_path = backup_path + ".meta.json"
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
            if os.path.exists(meta_path):
                os.remove(meta_path)
            return True
        except Exception as e:
            logger.error("Failed to delete backup %s: %s", backup_filename, e)
            return False

    @classmethod
    def _calculate_checksum(cls, file_path: str) -> str:
        return cls._sha256_file(file_path)
