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
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from models.tenant import Tenant
from models.branch import Branch
from models.tenant_store import TenantStore
from utils.tenanting import get_active_tenant_id
from utils.auth_helpers import is_global_owner_user

logger = logging.getLogger(__name__)

BACKUP_VERSION = 3
BACKUP_BASENAME_RE = re.compile(
    r"^azad_backup_(?:system|tenant_[a-z0-9_-]+|branch_[a-z0-9_-]+|store_[a-z0-9_-]+)"
    r"_\d{8}_\d{6}_[0-9a-f]+\.tar\.gz$",
    re.IGNORECASE,
)
BACKUP_BASENAME_LEGACY_RE = re.compile(
    r"^azad_backup_\d{8}_\d{6}_[0-9a-f]+\.tar\.gz$",
    re.IGNORECASE,
)
LEGACY_NAME_RE = re.compile(
    r"^(manual_backup_|auto_backup_).+\.(sql\.gz|dump)$",
    re.IGNORECASE,
)


class BackupService:
    """PostgreSQL + uploads backup; safe restore only to a different database URL."""

    _BASEDIR = os.path.abspath(os.path.join(os.path.dirname(str(__file__)), os.pardir))
    BACKUP_DIR = os.path.join(_BASEDIR, "instance", "backups")
    BACKUP_PREFIX = "azad_backup_"
    LEGACY_MANUAL_PREFIX = "manual_backup_"
    LEGACY_AUTO_PREFIX = "auto_backup_"

    @classmethod
    def get_list_backups_context(cls, user) -> Dict[str, Any]:
        is_owner = is_global_owner_user(user)
        if is_owner:
            backups = cls.list_backups()
            tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()
            branches = (
                Branch.query.filter_by(is_active=True).order_by(Branch.name).all()
            )
            stores = TenantStore.query.order_by(TenantStore.store_slug).all()
        else:
            backups = cls.list_backups_for_user(user)
            tenants = []
            active_tid = get_active_tenant_id(user)
            if active_tid:
                branches = (
                    Branch.query.filter_by(tenant_id=active_tid, is_active=True)
                    .order_by(Branch.name)
                    .all()
                )
                stores = TenantStore.query.filter_by(tenant_id=active_tid).all()
            else:
                branches = []
                stores = []

        return {
            "backups": backups,
            "stats": cls.get_backup_stats(),
            "schedule_settings": cls.get_schedule_settings(),
            "schedule_state": cls.get_schedule_state(),
            "backup_dir": cls.BACKUP_DIR,
            "pg_tools": cls.pg_tools_status(),
            "tenants": tenants,
            "branches": branches,
            "stores": stores,
            "is_platform_owner": is_owner,
            "now": datetime.now(),
        }

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
        except Exception as e:
            import sys
            import traceback

            sys.stderr.write(
                f"[BACKUP_WARNING] Failed to load JSON file {file_path}: {e}\n"
            )
            traceback.print_exc()
            try:
                from services.logging_core import LoggingCore

                LoggingCore.log_error(
                    message=str(e),
                    category="BACKUP",
                    source=f"services.backup_service.BackupService._load_json_file[{file_path}]",
                    level="WARNING",
                    exception=e,
                )
            except Exception:
                pass
            return None

    @classmethod
    def _write_json_file(cls, file_path: str, data: Dict) -> bool:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            import sys
            import traceback

            sys.stderr.write(
                f"[BACKUP_WARNING] Failed to write JSON file {file_path}: {e}\n"
            )
            traceback.print_exc()
            try:
                from services.logging_core import LoggingCore

                LoggingCore.log_error(
                    message=str(e),
                    category="BACKUP",
                    source=f"services.backup_service.BackupService._write_json_file[{file_path}]",
                    level="WARNING",
                    exception=e,
                )
            except Exception:
                pass
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
    def list_backups(cls, auto_only: bool = False) -> List[Dict]:
        """Return all backups sorted newest-first."""
        cls.initialize()
        results: List[Dict] = []
        if not os.path.isdir(cls.BACKUP_DIR):
            return results
        for name in os.listdir(cls.BACKUP_DIR):
            path = os.path.join(cls.BACKUP_DIR, name)
            if not os.path.isfile(path):
                continue
            if not (name.startswith(cls.BACKUP_PREFIX) or LEGACY_NAME_RE.match(name)):
                continue
            is_auto = name.startswith(cls.BACKUP_PREFIX) and "auto" in name.lower()
            if auto_only and not is_auto:
                continue
            meta = cls.get_backup_info(name) or {"filename": name}
            meta.setdefault("filename", name)
            meta.setdefault("size", os.path.getsize(path))
            meta.setdefault("modified", os.path.getmtime(path))
            results.append(meta)
        results.sort(key=lambda b: b.get("modified", 0), reverse=True)
        return results

    @classmethod
    def pg_tools_status(cls) -> Dict[str, Any]:
        dump = cls._resolve_pg_tool("pg_dump", "PG_DUMP_PATH")
        restore = cls._resolve_pg_tool("pg_restore", "PG_RESTORE_PATH")
        version = None
        if dump:
            try:
                from services.backup_exec import run_pg_tool

                proc = run_pg_tool([dump, "--version"], timeout=15)
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
            if (
                "postgresql" not in engine_url.drivername
                and "postgres" not in engine_url.drivername
            ):
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
    def _is_windows(cls) -> bool:
        return os.name == "nt"

    @classmethod
    def _which(cls, exe_name: str) -> Optional[str]:
        exe = str(exe_name)
        path_env = os.environ.get("PATH") or ""
        exts = (("",) + tuple(os.environ.get("PATHEXT", "").split(os.pathsep))) if cls._is_windows() else ("",)
        for directory in path_env.split(os.pathsep):
            if not directory:
                continue
            for ext in exts:
                candidate = os.path.join(directory, exe + ext)
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    return candidate
        return None

    @classmethod
    def _resolve_pg_tool(cls, exe_name: str, env_var: str) -> Optional[str]:
        value = (os.environ.get(env_var) or "").strip().strip('"')
        if value and os.path.isfile(value):
            return value
        found = cls._which(exe_name)
        if found:
            return found
        if not cls._is_windows():
            return None
        candidates: List[str] = []
        for pf in filter(
            None, [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
        ):
            candidates.extend(
                glob.glob(os.path.join(pf, "PostgreSQL", "*", "bin", exe_name))
            )
            candidates.extend(
                glob.glob(os.path.join(pf, "PostgreSQL", "*", "bin", exe_name + ".exe"))
            )
        candidates.extend(
            glob.glob(os.path.join("C:\\", "PostgreSQL", "*", "bin", exe_name))
        )
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
            from services.backup_exec import run_git

            proc = run_git(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=cls._BASEDIR,
                timeout=10,
            )
            if proc.returncode == 0:
                return (proc.stdout or "").strip()[:12] or "unknown"
        except Exception as exc:
            logging.getLogger(__name__).debug("git short sha: %s", exc)
        return "unknown"

    @classmethod
    def _git_branch(cls) -> Optional[str]:
        try:
            from services.backup_exec import run_git

            proc = run_git(
                ["git", "branch", "--show-current"],
                cwd=cls._BASEDIR,
                timeout=10,
            )
            if proc.returncode == 0:
                br = (proc.stdout or "").strip()
                return br or None
        except Exception as exc:
            logging.getLogger(__name__).debug("git branch: %s", exc)
        return None

    @classmethod
    def _alembic_info(cls) -> Tuple[Optional[str], Optional[str]]:
        try:
            from sqlalchemy import create_engine, text

            url = os.environ.get("DATABASE_URL") or os.environ.get(
                "SQLALCHEMY_DATABASE_URI"
            )
            if not url:
                return None, None
            with create_engine(url).connect() as conn:
                cur = conn.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                ).scalar()
            return str(cur) if cur else None, str(cur) if cur else None
        except Exception:
            return None, None

    @classmethod
    def _upload_roots(cls) -> List[str]:
        roots = [os.path.join(cls._BASEDIR, "static", "uploads")]
        try:
            from flask import current_app

            folder = str(current_app.config.get("UPLOAD_FOLDER") or "")
            if folder:
                abs_folder = (
                    folder
                    if os.path.isabs(folder)
                    else os.path.join(cls._BASEDIR, folder)
                )
                if abs_folder not in roots and os.path.isdir(abs_folder):
                    roots.append(abs_folder)
        except Exception as exc:
            logging.getLogger(__name__).debug("upload roots: %s", exc)
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

            url = os.environ.get("DATABASE_URL") or os.environ.get(
                "SQLALCHEMY_DATABASE_URI"
            )
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
            summary["checks"].append(
                "basic_integrity: OK" if dual == 0 and unbal == 0 else "WARN"
            )
        except Exception as e:
            summary["checks"].append(f"basic_integrity: error ({type(e).__name__})")
        return summary

    @classmethod
    def _run_pg_dump_custom(
        cls, params: Dict[str, str], dest_file: str
    ) -> Tuple[bool, str]:
        pg_dump = cls._resolve_pg_tool("pg_dump", "PG_DUMP_PATH")
        if not pg_dump:
            return (
                False,
                "pg_dump not found. Set PG_DUMP_PATH to your PostgreSQL bin directory.",
            )
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
        from services.backup_exec import run_pg_tool

        proc = run_pg_tool(cmd, env=env, timeout=3600)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "pg_dump failed").strip()
            return False, err[:800]
        if not os.path.isfile(dest_file) or os.path.getsize(dest_file) == 0:
            return False, "pg_dump produced empty file"
        return True, ""

    @classmethod
    def sanitize_filename(cls, filename: str) -> Optional[str]:
        return cls._safe_filename(filename)

    @classmethod
    def _safe_filename(cls, filename: str) -> Optional[str]:
        if not filename or ".." in filename or "/" in filename or "\\" in filename:
            return None
        base = os.path.basename(filename)
        if (
            BACKUP_BASENAME_RE.match(base)
            or BACKUP_BASENAME_LEGACY_RE.match(base)
            or LEGACY_NAME_RE.match(base)
        ):
            return base
        return None

    @classmethod
    def _archive_basename(
        cls,
        scope: str,
        timestamp: str,
        short_sha: str,
        tenant_slug: Optional[str] = None,
        branch_id: Optional[int] = None,
        store_id: Optional[int] = None,
    ) -> str:
        from services.backup_scope_config import SCOPE_SYSTEM, sanitize_slug

        if scope == SCOPE_SYSTEM:
            label = "system"
        elif scope == "tenant":
            label = f"tenant_{sanitize_slug(tenant_slug, 'tenant')}"
        elif scope == "branch":
            label = f"branch_{branch_id or 'x'}"
        elif scope == "store":
            label = f"store_{store_id or 'x'}"
        else:
            label = scope[:24]
        return f"{cls.BACKUP_PREFIX}{label}_{timestamp}_{short_sha}.tar.gz"

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
    def _build_manifest(
        cls,
        *,
        scope: str,
        short_sha: str,
        alembic_current: Optional[str],
        alembic_heads: Optional[str],
        params: Dict[str, str],
        pre_checks: Dict[str, Any],
        approx_rows: int,
        file_hashes: Dict[str, str],
        tools: Dict[str, Any],
        uploads_meta: Dict[str, Any],
        manual: bool,
        description: str,
        created_by: Optional[Dict[str, Any]],
        tables_included: List[str],
        tables_excluded: List[str],
        row_counts_per_table: Dict[str, int],
        allowed_restore_scope: str,
        tenant_id: Optional[int] = None,
        tenant_slug: Optional[str] = None,
        tenant_name: Optional[str] = None,
        branch_id: Optional[int] = None,
        store_id: Optional[int] = None,
        data_filter_summary: Optional[str] = None,
        uploads_unresolved: Optional[List[str]] = None,
        extra_includes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        includes = list(
            extra_includes or ["manifest", "env.example.redacted", "README_RESTORE.txt"]
        )
        return {
            "app_name": "Azad-UAE",
            "backup_version": BACKUP_VERSION,
            "format": "azad_tar_v1",
            "backup_scope": scope,
            "tenant_id": tenant_id,
            "tenant_slug": tenant_slug,
            "tenant_name": tenant_name,
            "branch_id": branch_id,
            "store_id": store_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by_user_id": (created_by or {}).get("user_id"),
            "created_by_role": (created_by or {}).get("role"),
            "git_commit": short_sha,
            "git_branch": cls._git_branch(),
            "alembic_current": alembic_current,
            "alembic_heads": alembic_heads,
            "database_driver": "postgresql",
            "database_host_masked": cls._mask_db_host(params["host"]),
            "database_name": params["dbname"],
            "tables_count": pre_checks.get("tables_count"),
            "approximate_rows": approx_rows,
            "includes": includes,
            "sha256": file_hashes,
            "command_versions": {
                "pg_dump": tools.get("pg_dump_version"),
                "python": sys.version.split()[0],
            },
            "uploads_meta": uploads_meta,
            "uploads_included_count": uploads_meta.get("files_packed", 0),
            "uploads_unresolved_count": len(uploads_unresolved or []),
            "uploads_unresolved": (uploads_unresolved or [])[:50],
            "pre_backup_checks": pre_checks,
            "manual": bool(manual),
            "description": description or "",
            "allowed_restore_scope": allowed_restore_scope,
            "data_filter_summary": data_filter_summary or "",
            "tables_included": tables_included,
            "tables_excluded": tables_excluded,
            "row_counts_per_table": row_counts_per_table,
        }

    @classmethod
    def _build_sidecar(
        cls,
        archive_name: str,
        archive_path: str,
        manifest: Dict[str, Any],
        timestamp: str,
        size: int,
        short_sha: str,
        alembic_current: Optional[str],
        manual: bool,
        description: str,
    ) -> Dict[str, Any]:
        return {
            "filename": archive_name,
            "path": archive_path,
            "format": "azad_tar_v1",
            "backup_scope": manifest.get("backup_scope"),
            "tenant_id": manifest.get("tenant_id"),
            "tenant_slug": manifest.get("tenant_slug"),
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

    @classmethod
    def _fetch_tenant_row(cls, tenant_id: int) -> Optional[Dict[str, Any]]:
        from sqlalchemy import create_engine, text

        url = os.environ.get("DATABASE_URL") or os.environ.get(
            "SQLALCHEMY_DATABASE_URI"
        )
        if not url:
            return None
        with create_engine(url).connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, slug, name, enable_auto_backup FROM tenants WHERE id = :tid"
                ),
                {"tid": tenant_id},
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "slug": row[1],
                "name": row[2],
                "enable_auto_backup": row[3] is not False,
            }

    @classmethod
    def _write_checksums_file(cls, work_dir: str, members: List[str]) -> str:
        lines: List[str] = []
        for member in members:
            path = os.path.join(work_dir, member)
            if os.path.isfile(path):
                lines.append(f"{cls._sha256_file(path)}  {member}")
            elif member == "data" and os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for fn in sorted(files):
                        rel = os.path.relpath(os.path.join(root, fn), work_dir).replace(
                            "\\", "/"
                        )
                        lines.append(
                            f"{cls._sha256_file(os.path.join(work_dir, rel))}  {rel}"
                        )
        checksums_path = os.path.join(work_dir, "checksums.sha256")
        with open(checksums_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
        return checksums_path

    @classmethod
    def _create_scoped_backup(
        cls,
        scope: str,
        tenant_id: int,
        *,
        branch_id: Optional[int] = None,
        store_id: Optional[int] = None,
        manual: bool = True,
        description: str = "",
        created_by: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        from services.backup_scope_config import (
            SCOPE_BRANCH,
            SCOPE_STORE,
            SCOPE_TENANT,
            build_tenant_uploads_archive,
            collect_scoped_upload_paths,
            export_scoped_database,
            scope_filter_summary,
            write_data_directory,
        )

        cls.initialize()
        tenant = cls._fetch_tenant_row(tenant_id)
        if not tenant:
            cls._set_schedule_state(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_error=f"tenant_id {tenant_id} not found",
                last_action="create_backup",
            )
            return None

        if not tenant.get("enable_auto_backup", True):
            logger.info(
                "Skipping backup for tenant %s (enable_auto_backup=False)", tenant_id
            )
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_sha = cls._git_short_sha()
        archive_name = cls._archive_basename(
            scope,
            timestamp,
            short_sha,
            tenant_slug=tenant.get("slug"),
            branch_id=branch_id,
            store_id=store_id,
        )
        archive_path = os.path.join(cls.BACKUP_DIR, archive_name)
        work_dir = tempfile.mkdtemp(prefix=f"azad_{scope}_backup_")

        try:
            from sqlalchemy import create_engine

            url = os.environ.get("DATABASE_URL") or os.environ.get(
                "SQLALCHEMY_DATABASE_URI"
            )
            params = cls._parse_db_url(url)
            if not params or not url:
                return None

            with create_engine(url).connect() as conn:
                tables_payload, row_counts, included, skipped, unresolved = (
                    export_scoped_database(
                        conn,
                        scope,
                        tenant_id=tenant_id,
                        branch_id=branch_id,
                        store_id=store_id,
                    )
                )
                upload_paths, upload_unresolved = collect_scoped_upload_paths(
                    conn,
                    scope,
                    tenant_id,
                    cls._BASEDIR,
                    branch_id=branch_id,
                    store_id=store_id,
                )
            unresolved = list(unresolved) + upload_unresolved

            data_dir = os.path.join(work_dir, "data")
            write_data_directory(
                data_dir,
                tables_payload,
                scope=scope,
                tenant_id=tenant_id,
                branch_id=branch_id,
                store_id=store_id,
            )

            uploads_path = os.path.join(work_dir, "uploads.tar.gz")
            uploads_meta = build_tenant_uploads_archive(
                upload_paths, uploads_path, cls._BASEDIR
            )

            alembic_current, alembic_heads = cls._alembic_info()
            pre_checks = cls._pre_backup_checks_summary()
            tools = cls.pg_tools_status()

            archive_members = [
                "data",
                "uploads.tar.gz",
                "manifest.json",
                "env.example.redacted",
                "README_RESTORE.txt",
            ]
            cls._write_checksums_file(work_dir, archive_members)

            file_hashes: Dict[str, str] = {}
            for member in archive_members + ["checksums.sha256"]:
                p = os.path.join(work_dir, member)
                if os.path.isfile(p):
                    file_hashes[member] = cls._sha256_file(p)
                elif member == "data" and os.path.isdir(p):
                    for root, _, files in os.walk(p):
                        for fn in files:
                            rel = os.path.relpath(
                                os.path.join(root, fn), work_dir
                            ).replace("\\", "/")
                            file_hashes[rel] = cls._sha256_file(
                                os.path.join(work_dir, rel)
                            )

            restore_scope_map = {
                SCOPE_TENANT: "tenant_same_or_new_with_remap",
                SCOPE_BRANCH: "branch_same_or_new_with_remap",
                SCOPE_STORE: "store_same_or_new_with_remap",
            }
            manifest = cls._build_manifest(
                scope=scope,
                short_sha=short_sha,
                alembic_current=alembic_current,
                alembic_heads=alembic_heads,
                params=params,
                pre_checks=pre_checks,
                approx_rows=sum(row_counts.values()),
                file_hashes=file_hashes,
                tools=tools,
                uploads_meta=uploads_meta,
                manual=manual,
                description=description,
                created_by=created_by,
                tables_included=included,
                tables_excluded=skipped,
                row_counts_per_table=row_counts,
                allowed_restore_scope=restore_scope_map.get(scope, scope),
                tenant_id=tenant_id,
                tenant_slug=tenant.get("slug"),
                tenant_name=tenant.get("name"),
                branch_id=branch_id,
                store_id=store_id,
                data_filter_summary=scope_filter_summary(
                    scope, tenant_id, branch_id=branch_id, store_id=store_id
                ),
                uploads_unresolved=unresolved,
                extra_includes=archive_members + ["checksums.sha256"],
            )
            manifest["unresolved_references"] = unresolved[:100]

            with open(
                os.path.join(work_dir, "manifest.json"), "w", encoding="utf-8"
            ) as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            with open(
                os.path.join(work_dir, "env.example.redacted"), "w", encoding="utf-8"
            ) as f:
                json.dump(cls._build_env_redacted(), f, indent=2)
            cls._write_readme_restore(os.path.join(work_dir, "README_RESTORE.txt"))

            with tarfile.open(archive_path, "w:gz") as tar:
                for member in archive_members + ["checksums.sha256"]:
                    full = os.path.join(work_dir, member)
                    if os.path.isdir(full):
                        for root, _, files in os.walk(full):
                            for fn in files:
                                abs_p = os.path.join(root, fn)
                                arc = os.path.relpath(abs_p, work_dir).replace(
                                    "\\", "/"
                                )
                                tar.add(abs_p, arcname=arc)
                    elif os.path.isfile(full):
                        tar.add(full, arcname=member)

            size = os.path.getsize(archive_path)
            sidecar = cls._build_sidecar(
                archive_name,
                archive_path,
                manifest,
                timestamp,
                size,
                short_sha,
                alembic_current,
                manual,
                description,
            )
            with open(archive_path + ".meta.json", "w", encoding="utf-8") as f:
                json.dump(sidecar, f, indent=2, ensure_ascii=False)

            cls._apply_retention()
            cls._set_schedule_state(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_success_at=datetime.now(timezone.utc).isoformat(),
                last_error=None,
                last_filename=archive_name,
                last_manual=bool(manual),
                last_action=f"{scope}_backup",
            )
            return sidecar
        except Exception as e:
            cls._set_schedule_state(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_error=str(e)[:800],
                last_action=f"{scope}_backup",
            )
            logger.exception("%s backup failed", scope)
            return None
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    @classmethod
    def list_backups_for_user(cls, user) -> List[Dict]:
        """Filter backups by scope permissions."""
        from utils.auth_helpers import is_global_owner_user
        from utils.tenanting import get_active_tenant_id

        backups = cls.list_backups()
        if is_global_owner_user(user):
            return backups
        active_tid = get_active_tenant_id(user)
        user_branch_id = getattr(user, "branch_id", None)
        filtered = []
        for meta in backups:
            scope = meta.get("backup_scope")
            fn = meta.get("filename", "")
            if not scope and fn.startswith("azad_backup_system_"):
                scope = "system"
            if scope == "system":
                continue
            if scope == "tenant" and active_tid and meta.get("tenant_id") == active_tid:
                filtered.append(meta)
            elif (
                scope == "branch" and active_tid and meta.get("tenant_id") == active_tid
            ):
                if user_branch_id and meta.get("branch_id") == user_branch_id:
                    filtered.append(meta)
            elif (
                scope == "store" and active_tid and meta.get("tenant_id") == active_tid
            ):
                filtered.append(meta)
        return filtered

    @classmethod
    def user_may_access_backup(cls, user, filename: str) -> bool:
        from utils.auth_helpers import is_global_owner_user

        safe = cls.sanitize_filename(filename)
        if not safe:
            return False
        if is_global_owner_user(user):
            return True
        info = cls.get_backup_info(safe) or {}
        manifest = info.get("manifest") or {}
        scope = manifest.get("backup_scope")
        if scope == "system":
            return False
        from utils.tenanting import get_active_tenant_id

        active_tid = get_active_tenant_id(user)
        if manifest.get("tenant_id") != active_tid:
            return False
        if scope == "branch":
            return manifest.get("branch_id") == getattr(user, "branch_id", None)
        return True

    @classmethod
    def create_backup(
        cls,
        manual: bool = True,
        description: str = "",
        scope: str = "system",
        tenant_id: Optional[int] = None,
        branch_id: Optional[int] = None,
        store_id: Optional[int] = None,
        created_by: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create scoped backup archive (system full DB or tenant-scoped export)."""
        from services.backup_scope_config import (
            SCOPE_BRANCH,
            SCOPE_STORE,
            SCOPE_SYSTEM,
            SCOPE_TENANT,
        )

        scope_n = (scope or SCOPE_SYSTEM).strip().lower()
        if scope_n == SCOPE_SYSTEM:
            return cls._create_system_backup(manual, description, created_by=created_by)
        if scope_n == SCOPE_TENANT:
            if not tenant_id:
                cls._set_schedule_state(
                    last_run_at=datetime.now(timezone.utc).isoformat(),
                    last_error="tenant_id required for tenant backup",
                    last_action="create_backup",
                )
                return None
            return cls._create_scoped_backup(
                SCOPE_TENANT,
                int(tenant_id),
                manual=manual,
                description=description,
                created_by=created_by,
            )
        if scope_n == SCOPE_BRANCH:
            if not tenant_id or not branch_id:
                cls._set_schedule_state(
                    last_run_at=datetime.now(timezone.utc).isoformat(),
                    last_error="tenant_id and branch_id required for branch backup",
                    last_action="create_backup",
                )
                return None
            return cls._create_scoped_backup(
                SCOPE_BRANCH,
                int(tenant_id),
                branch_id=int(branch_id),
                manual=manual,
                description=description,
                created_by=created_by,
            )
        if scope_n == SCOPE_STORE:
            if not tenant_id or not store_id:
                cls._set_schedule_state(
                    last_run_at=datetime.now(timezone.utc).isoformat(),
                    last_error="tenant_id and store_id required for store backup",
                    last_action="create_backup",
                )
                return None
            return cls._create_scoped_backup(
                SCOPE_STORE,
                int(tenant_id),
                store_id=int(store_id),
                manual=manual,
                description=description,
                created_by=created_by,
            )
        cls._set_schedule_state(
            last_run_at=datetime.now(timezone.utc).isoformat(),
            last_error=f"unknown backup scope: {scope_n}",
            last_action="create_backup",
        )
        return None

    @classmethod
    def _create_system_backup(
        cls,
        manual: bool,
        description: str,
        created_by: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Full PostgreSQL custom dump + all uploads."""
        from services.backup_scope_config import SCOPE_SYSTEM

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
            cls._set_schedule_state(
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_error="pg_dump not found. Set PG_DUMP_PATH.",
                last_action="create_backup",
            )
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_sha = cls._git_short_sha()
        archive_name = cls._archive_basename(SCOPE_SYSTEM, timestamp, short_sha)
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

                url = os.environ.get("DATABASE_URL") or os.environ.get(
                    "SQLALCHEMY_DATABASE_URI"
                )
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
            except Exception as exc:
                logging.getLogger(__name__).debug("approx row count: %s", exc)

            file_hashes = {
                "db.dump": cls._sha256_file(db_dump_path),
                "uploads.tar.gz": cls._sha256_file(uploads_path),
            }

            manifest = cls._build_manifest(
                scope="system",
                short_sha=short_sha,
                alembic_current=alembic_current,
                alembic_heads=alembic_heads,
                params=params,
                pre_checks=pre_checks,
                approx_rows=approx_rows,
                file_hashes=file_hashes,
                tools=tools,
                uploads_meta=uploads_meta,
                manual=manual,
                description=description,
                created_by=created_by,
                tables_included=["full_database"],
                tables_excluded=[],
                row_counts_per_table={},
                allowed_restore_scope="system_new_database_only",
            )

            manifest_path = os.path.join(work_dir, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

            env_path = os.path.join(work_dir, "env.example.redacted")
            with open(env_path, "w", encoding="utf-8") as f:
                json.dump(cls._build_env_redacted(), f, indent=2)

            readme_path = os.path.join(work_dir, "README_RESTORE.txt")
            cls._write_readme_restore(readme_path)

            sys_members = [
                "db.dump",
                "uploads.tar.gz",
                "manifest.json",
                "env.example.redacted",
                "README_RESTORE.txt",
            ]
            cls._write_checksums_file(work_dir, sys_members)
            sys_members.append("checksums.sha256")
            with tarfile.open(archive_path, "w:gz") as tar:
                for member in sys_members:
                    tar.add(os.path.join(work_dir, member), arcname=member)

            size = os.path.getsize(archive_path)
            sidecar = cls._build_sidecar(
                archive_name,
                archive_path,
                manifest,
                timestamp,
                size,
                short_sha,
                alembic_current,
                manual,
                description,
            )
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
        modern = [b for b in cls.list_backups() if b.get("format") == "azad_tar_v1"]
        if len(modern) <= keep:
            return
        for b in sorted(modern, key=lambda x: x.get("timestamp", ""))[
            : len(modern) - keep
        ]:
            cls.delete_backup(b["filename"])

    @classmethod
    def auto_backup_daily(cls) -> Optional[Dict]:
        settings = cls.get_schedule_settings()
        now_iso = datetime.now(timezone.utc).isoformat()
        cls._set_schedule_state(last_run_at=now_iso, last_action="auto_backup")
        if not settings.get("enabled", True):
            return None

        result = cls.create_backup(
            manual=False,
            description=f"Scheduled {settings.get('frequency', 'daily')} system backup",
            scope="system",
        )

        try:
            from sqlalchemy import create_engine, text

            url = os.environ.get("DATABASE_URL") or os.environ.get(
                "SQLALCHEMY_DATABASE_URI"
            )
            if url:
                with create_engine(url).connect() as conn:
                    rows = conn.execute(
                        text(
                            "SELECT id FROM tenants WHERE is_active = TRUE AND enable_auto_backup = TRUE"
                        )
                    ).fetchall()
                for (tid,) in rows:
                    cls.create_backup(
                        manual=False,
                        description=f"Scheduled {settings.get('frequency', 'daily')} tenant backup",
                        scope="tenant",
                        tenant_id=tid,
                    )
        except Exception as exc:
            logger.warning("Per-tenant auto backup loop failed (non-fatal): %s", exc)

        return result

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
            except Exception as exc:
                logging.getLogger(__name__).debug("backup sidecar: %s", exc)
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
            from services.backup_exec import run_pg_tool

            proc = run_pg_tool([pg_restore, "--list", path], timeout=120)
            return proc.returncode == 0
        return False

    @classmethod
    def _verify_modern_archive(
        cls, path: str, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        work = tempfile.mkdtemp(prefix="azad_verify_")
        try:
            with tarfile.open(path, "r:gz") as tar:
                archive_names = set(tar.getnames())
                if "manifest.json" not in archive_names:
                    result["errors"].append("missing manifest.json")
                    return result
                tar.extract("manifest.json", work, filter="data")
            manifest_path = os.path.join(work, "manifest.json")
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            result["manifest"] = manifest
            scope = manifest.get("backup_scope") or "system"
            result["backup_scope"] = scope

            if scope in ("tenant", "branch", "store"):
                has_data = any(n.startswith("data/") for n in archive_names)
                has_legacy = "tenant_export.json" in archive_names
                if not has_data and not has_legacy:
                    result["errors"].append("missing data/ or tenant_export.json")
                    return result
                if has_legacy:
                    with tarfile.open(path, "r:gz") as tar:
                        tar.extract("tenant_export.json", work, filter="data")
                    export_path = os.path.join(work, "tenant_export.json")
                    expected = (manifest.get("sha256") or {}).get("tenant_export.json")
                    if expected and cls._sha256_file(export_path) != expected:
                        result["errors"].append("tenant_export.json checksum mismatch")
                        return result
                    tenant_ok = cls._verify_tenant_export(export_path, manifest)
                else:
                    with tarfile.open(path, "r:gz") as tar:
                        for n in archive_names:
                            if n.startswith("data/"):
                                tar.extract(n, work, filter="data")
                    from services.backup_scope_config import read_data_directory

                    tables, _meta = read_data_directory(os.path.join(work, "data"))
                    export_doc = {
                        "tenant_id": manifest.get("tenant_id"),
                        "tables": tables,
                    }
                    export_path = os.path.join(work, "_verify_export.json")
                    with open(export_path, "w", encoding="utf-8") as f:
                        json.dump(export_doc, f)
                    tenant_ok = cls._verify_tenant_export(export_path, manifest)
                if not tenant_ok.get("ok"):
                    result["errors"].extend(tenant_ok.get("errors", []))
                    return result
                result["scoped_verify"] = tenant_ok
            else:
                required = {"db.dump", "uploads.tar.gz", "manifest.json"}
                missing = required - archive_names
                if missing:
                    result["errors"].append(f"missing members: {sorted(missing)}")
                    return result
                with tarfile.open(path, "r:gz") as tar:
                    tar.extract("db.dump", work, filter="data")
                db_path = os.path.join(work, "db.dump")
                expected = (manifest.get("sha256") or {}).get("db.dump")
                if expected and cls._sha256_file(db_path) != expected:
                    result["errors"].append("db.dump checksum mismatch")
                    return result
                pg_restore = cls._resolve_pg_tool("pg_restore", "PG_RESTORE_PATH")
                if pg_restore:
                    from services.backup_exec import run_pg_tool

                    proc = run_pg_tool([pg_restore, "--list", db_path], timeout=180)
                    if proc.returncode != 0:
                        result["errors"].append("pg_restore --list failed")
                        return result
                else:
                    result["warnings"].append(
                        "pg_restore not available; skipped dump list check"
                    )

            result["valid"] = True
            result["format"] = "azad_tar_v1"
            return result
        except Exception as e:
            result["errors"].append(str(e)[:200])
            return result
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @classmethod
    def _verify_tenant_export(
        cls, export_path: str, manifest: Dict[str, Any]
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {"ok": True, "errors": []}
        try:
            with open(export_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except Exception as e:
            return {"ok": False, "errors": [f"tenant_export unreadable: {e}"]}

        scope = manifest.get("backup_scope") or "tenant"
        tid = manifest.get("tenant_id")
        if doc.get("tenant_id") is not None and int(doc.get("tenant_id") or 0) != int(
            tid or 0
        ):
            out["ok"] = False
            out["errors"].append("export tenant_id mismatch manifest")

        tenants_rows = (doc.get("tables") or {}).get("tenants") or []
        if len(tenants_rows) != 1:
            out["ok"] = False
            out["errors"].append(
                f"tenants row count expected 1 got {len(tenants_rows)}"
            )
        elif (
            tenants_rows
            and tenants_rows[0].get("id") is not None
            and int(tenants_rows[0].get("id") or 0) != int(tid or 0)
        ):
            out["ok"] = False
            out["errors"].append("tenants row id mismatch")

        bid = manifest.get("branch_id")
        sid = manifest.get("store_id")
        for table, rows in (doc.get("tables") or {}).items():
            if table == "tenants":
                continue
            for row in rows:
                row_tid = row.get("tenant_id")
                if row_tid is not None and int(row_tid or 0) != int(tid or 0):
                    out["ok"] = False
                    out["errors"].append(f"cross-tenant row in {table}")
                    break
                if scope == "branch" and bid is not None and table != "branches":
                    rb = row.get("branch_id")
                    if rb is not None and int(rb or 0) != int(bid):
                        out["ok"] = False
                        out["errors"].append(f"cross-branch row in {table}")
                        break
                if scope == "store" and sid is not None and table == "tenant_stores":
                    if int(row.get("id", -1) or 0) != int(sid):
                        out["ok"] = False
                        out["errors"].append("tenant_stores id mismatch")
                        break
            if not out["ok"]:
                break

        if scope == "branch" and bid is not None:
            br_rows = (doc.get("tables") or {}).get("branches") or []
            if len(br_rows) != 1 or int(br_rows[0].get("id", -1) or 0) != int(bid):
                out["ok"] = False
                out["errors"].append("branches isolation failed")

        users_rows = (doc.get("tables") or {}).get("users") or []
        for row in users_rows:
            if row.get("tenant_id") in (None, "") or row.get("is_owner"):
                out["ok"] = False
                out["errors"].append("global/owner user in tenant backup")
                break

        manifest_counts = manifest.get("row_counts_per_table") or {}
        for table, expected in manifest_counts.items():
            actual = len((doc.get("tables") or {}).get(table) or [])
            if actual != expected:
                out["ok"] = False
                out["errors"].append(
                    f"row count mismatch {table}: {actual} vs {expected}"
                )
        return out

    @classmethod
    def prepare_restore(
        cls,
        filename: str,
        target_database_url: Optional[str] = None,
        target_tenant_id: Optional[int] = None,
        remap: bool = False,
    ) -> Dict[str, Any]:
        """Prepare restore plan/commands (system DB restore or tenant verify-only)."""
        return cls.prepare_restore_command(
            filename,
            target_database_url=target_database_url,
            target_tenant_id=target_tenant_id,
            remap=remap,
        )

    @classmethod
    def prepare_restore_command(
        cls,
        filename: str,
        target_database_url: Optional[str] = None,
        target_tenant_id: Optional[int] = None,
        remap: bool = False,
    ) -> Dict[str, Any]:
        """Return safe pg_restore instructions (never restores in-place)."""
        info = cls.get_backup_info(filename)
        if not info:
            return {"ok": False, "error": "backup not found"}
        manifest = info.get("manifest") or {}
        scope = manifest.get("backup_scope") or "system"
        if scope in ("tenant", "branch", "store"):
            src_tid = manifest.get("tenant_id")
            if (
                target_tenant_id
                and int(target_tenant_id) != int(src_tid or -1)
                and not remap
            ):
                return {
                    "ok": False,
                    "error": f"{scope} restore to a different tenant_id requires remap=True",
                }
            confirm = "REMAP CONFIRM" if remap else "RESTORE CONFIRM"
            return {
                "ok": True,
                "mode": f"{scope}_restore_to_new_db",
                "warning": "Never restore over the live DATABASE_URL.",
                "commands": [
                    "tar -xzf BACKUP.tar.gz",
                    "Set TARGET_TEST_DATABASE_URL to a NEW empty PostgreSQL database",
                    "flask db upgrade  # schema on target",
                    f"POST restore with confirmation={confirm!r}",
                    "python tools/qa/backup_restore_check.py --scope "
                    f"{scope} --restore-to-temp-local",
                ],
                "tenant_id": src_tid,
                "target_tenant_id": target_tenant_id,
                "remap": remap,
                "confirmation_required": confirm,
            }
        target = (
            target_database_url or ""
        ).strip() or "postgresql://USER:***@HOST:PORT/NEW_DB_NAME"
        masked_target = "***"
        try:
            p = urlparse(target.replace("postgresql+psycopg2://", "postgresql://", 1))
            if p.hostname:
                masked_target = (
                    f"postgresql://{p.username or 'USER'}:***@"
                    f"{cls._mask_db_host(str(p.hostname or ''))}:{p.port or 5432}/{p.path.lstrip('/')}"
                )
        except Exception as exc:
            logging.getLogger(__name__).debug("mask restore target url: %s", exc)
        pg_restore = (
            cls._resolve_pg_tool("pg_restore", "PG_RESTORE_PATH") or "pg_restore"
        )
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

        current_url = (
            os.environ.get("DATABASE_URL")
            or os.environ.get("SQLALCHEMY_DATABASE_URI")
            or ""
        )
        if cls._urls_same_database(current_url, target_database_url):
            outcome["errors"].append(
                "Target database is the same as current DATABASE_URL. "
                "Use a different TARGET database."
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
            from services.backup_exec import run_pg_tool

            proc = run_pg_tool(cmd, env=env, timeout=3600)
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
    def restore_scoped_backup_to_target_db(
        cls,
        filename: str,
        target_database_url: str,
        *,
        confirmation: str = "",
        remap: bool = False,
        target_tenant_id: Optional[int] = None,
        restore_uploads: bool = False,
        uploads_dest_root: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        import shutil
        import tempfile

        from services.backup_scoped_engine import restore_scoped_to_target

        verify = cls.verify_backup(filename)
        if not verify.get("valid"):
            return {
                "ok": False,
                "errors": ["backup verification failed"],
                "details": verify,
            }
        manifest = verify.get("manifest") or {}
        path = cls._backup_path(filename)
        if not path:
            return {"ok": False, "errors": ["invalid filename"]}

        work = tempfile.mkdtemp(prefix="azad_scoped_restore_")
        try:
            with tarfile.open(path, "r:gz") as tar:
                tar.extractall(work, filter="data")
            outcome = restore_scoped_to_target(
                work,
                manifest,
                target_database_url,
                confirmation=confirmation,
                remap=remap,
                target_tenant_id=target_tenant_id,
                restore_uploads_dir=uploads_dest_root if restore_uploads else None,
                base_dir=cls._BASEDIR,
                dry_run=dry_run,
            )
            if outcome.get("ok") and not dry_run:
                from services.backup_scoped_engine import verify_scoped_isolation
                from services.backup_scoped_restore import verify_scoped_restore

                iso = verify_scoped_isolation(manifest, work)
                outcome["archive_verify"] = iso
                tgt_tid = int(
                    outcome.get("target_tenant_id") or manifest.get("tenant_id") or 0
                )
                db_v = verify_scoped_restore(
                    target_database_url,
                    manifest,
                    expected_tenant_id=tgt_tid,
                    scope=manifest.get("backup_scope") or "tenant",
                )
                outcome["scoped_verify"] = db_v
                if not iso.get("ok"):
                    outcome.setdefault("warnings", []).append(
                        "archive isolation check: "
                        + "; ".join(iso.get("errors") or [])[:200]
                    )
                if not db_v.get("ok"):
                    outcome["ok"] = False
                    outcome.setdefault("errors", []).extend(db_v.get("errors") or [])
            return outcome
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @classmethod
    def write_restore_proof(cls, backup_filename: str, payload: Dict[str, Any]) -> str:
        cls.initialize()
        base = backup_filename.replace(".tar.gz", "")
        path = os.path.join(cls.BACKUP_DIR, f"{base}.restore_proof.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        marker = os.path.join(cls.BACKUP_DIR, ".latest_restore_proof.json")
        with open(marker, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "proof_file": os.path.basename(path),
                    "verified_at": payload.get("verified_at"),
                    "backup_scope": payload.get("backup_scope"),
                },
                f,
            )
        return path

    @classmethod
    def restore_backup(cls, backup_filename: str) -> bool:
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
