"""
Restore drill -- prove a backup artifact actually restores.

Orchestrates: artifact acquisition (offsite with local fallback) -> restore
(pg_restore or scoped import) into a SCRATCH database -> row-count sanity
checks on key tables -> JSON report line appended to ``logs/restore_drill.log``.

Invoked via the ``flask restore-drill`` CLI command
(see cli_commands.register_restore_drill_command).

Scheduling (documentation only -- no OS scheduler changes are made here).
Cron example, daily drill at 03:15 server time:

    15 3 * * * cd /home/USER/Azad-UAE && flask restore-drill >> logs/restore_drill.log 2>&1

Safety rules enforced here:

* The scratch database name comes from ``RESTORE_DRILL_DB`` and is refused if
  it matches the live ``DATABASE_URL`` database or any protected/test name.
* All sanity checks are read-only ``SELECT COUNT(*)`` queries.
* A transient PostgreSQL "server closed the connection" error during the
  row-count phase is retried exactly once.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

DRILL_LOG_PATH = os.path.join("logs", "restore_drill.log")

# Never allow these as scratch targets (live dev DB, shared pytest DB, system DBs).
PROTECTED_DB_NAMES = frozenset({"postgres", "template0", "template1", "azad_uae", "azad_uae_test"})

# Key tables sanity-checked after restore ("invoices" equivalent = sales).
KEY_TABLES: tuple[str, ...] = ("users", "sales", "purchases")
MIN_USERS = 1

_TRANSIENT_MARKER = "server closed the connection"


class RestoreDrillService:
    """Run one end-to-end restore drill against a scratch database."""

    @classmethod
    def resolve_scratch_database_url(cls) -> tuple[str | None, str]:
        """Return ``(url, error)`` for the RESTORE_DRILL_DB scratch target."""
        name = (os.environ.get("RESTORE_DRILL_DB") or "").strip()
        if not name:
            return None, "RESTORE_DRILL_DB env var is required (target scratch database name)"
        if name.lower() in PROTECTED_DB_NAMES:
            return None, f"refusing protected database name {name!r}"
        base = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI") or ""
        if not base:
            return None, "DATABASE_URL is not configured"
        try:
            from sqlalchemy.engine.url import make_url

            url = make_url(base)
            if "postgres" not in url.drivername:
                return None, "restore drill requires a PostgreSQL DATABASE_URL"
            current_db = (url.database or "").lstrip("/")
            if name == current_db:
                return None, f"RESTORE_DRILL_DB {name!r} matches the live database; use a dedicated scratch name"
            scratch = url.set(database=name)
            host = str(scratch.host or "")
            if host.lower() in ("localhost", "::1"):
                scratch = scratch.set(host="127.0.0.1")
            return str(scratch), ""
        except Exception as exc:
            return None, f"invalid DATABASE_URL: {type(exc).__name__}: {exc}"[:200]

    @classmethod
    def acquire_artifact(
        cls, *, source: str = "auto", filename: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        """Locate + fetch the backup artifact to drill.

        Returns ``({"path": ..., "origin": "offsite"|"local", ...}, error)``.
        """
        from services.backup_service import BackupService

        if source in ("auto", "offsite"):
            workdir = tempfile.mkdtemp(prefix="azad_drill_dl_")
            try:
                from utils.offsite_backup import download_latest_offsite_artifact

                result = download_latest_offsite_artifact(workdir)
                if result.get("ok") and result.get("path"):
                    return {"path": result["path"], "origin": "offsite", "workdir": workdir}, ""
                if source == "offsite":
                    shutil.rmtree(workdir, ignore_errors=True)
                    return None, f"offsite download failed: {result.get('error')}"
                logger.warning("Offsite download failed (%s); falling back to local backups", result.get("error"))
                shutil.rmtree(workdir, ignore_errors=True)
            except Exception as exc:
                logger.warning("Offsite download error (%s); falling back to local backups", exc)
                shutil.rmtree(workdir, ignore_errors=True)

        if filename:
            path = BackupService._backup_path(filename)
            if not path or not os.path.exists(path):
                return None, f"local backup not found: {filename}"
            return {"path": path, "origin": "local", "filename": filename}, ""

        backups = BackupService.list_backups()
        if not backups:
            return None, "no local backups available and offsite unavailable/unconfigured"
        newest = backups[0]
        return {
            "path": newest.get("path") or os.path.join(BackupService.BACKUP_DIR, newest["filename"]),
            "origin": "local",
            "filename": newest.get("filename"),
        }, ""

    @classmethod
    def restore_into_scratch(cls, artifact_path: str, scratch_url: str) -> dict[str, Any]:
        """Restore the archive into the scratch DB using existing safe paths."""
        from services.backup_service import BackupService

        filename = os.path.basename(artifact_path)
        verify = BackupService.verify_backup(filename)
        scope = ((verify.get("manifest") or {}).get("backup_scope")) or "system"

        # Copy into a stable-named temp dir so BackupService's filename guard
        # accepts downloads that live outside instance/backups.
        staged_dir = tempfile.mkdtemp(prefix="azad_drill_stage_")
        staged_path = os.path.join(staged_dir, filename)
        shutil.copy2(artifact_path, staged_path)
        try:
            if verify.get("valid") and scope in ("tenant", "branch", "store"):
                outcome = BackupService.restore_scoped_backup_to_target_db(
                    filename,
                    scratch_url,
                    confirmation="RESTORE CONFIRM",
                    dry_run=False,
                )
            else:
                outcome = BackupService.restore_backup_to_target_db(
                    filename,
                    scratch_url,
                    confirmation="RESTORE CONFIRM",
                )
            if verify.get("valid") is False and not outcome.get("ok"):
                outcome.setdefault("errors", []).append(
                    "backup verification failed: " + "; ".join(verify.get("errors") or [])[:200]
                )
            return outcome
        finally:
            shutil.rmtree(staged_dir, ignore_errors=True)

    @classmethod
    def _count_table(cls, conn, table: str) -> int:
        from sqlalchemy import MetaData, Table, func, select

        metadata = MetaData()
        reflected = Table(table, metadata, autoload_with=conn)
        return int(conn.execute(select(func.count()).select_from(reflected)).scalar() or 0)

    @classmethod
    def row_count_sanity(cls, scratch_url: str) -> dict[str, Any]:
        """Read-only row-count checks on key tables; retries transient errors once."""
        from sqlalchemy import create_engine
        from sqlalchemy.exc import OperationalError

        out: dict[str, Any] = {"ok": True, "errors": [], "counts": {}}
        for attempt in (1, 2):
            out["errors"] = []
            out["counts"] = {}
            engine = create_engine(scratch_url, pool_pre_ping=True)
            try:
                try:
                    with engine.connect() as conn:
                        for table in KEY_TABLES:
                            try:
                                out["counts"][table] = cls._count_table(conn, table)
                            except Exception as exc:
                                out["errors"].append(f"{table}: count failed ({type(exc).__name__})")
                    break
                except OperationalError as exc:
                    if _TRANSIENT_MARKER in str(exc) and attempt == 1:
                        logger.warning("Transient PostgreSQL disconnect during drill counts; retrying once")
                        time.sleep(0.5)
                        continue
                    out["errors"].append(f"row-count query failed: {type(exc).__name__}: {exc}"[:300])
                    break
            finally:
                engine.dispose()
        users = int(out["counts"].get("users") or 0)
        if users < MIN_USERS and not any(e.startswith("users:") for e in out["errors"]):
            out["errors"].append(f"users table has {users} rows (expected >= {MIN_USERS})")
        out["ok"] = not out["errors"]
        return out

    @classmethod
    def write_drill_report(cls, payload: dict[str, Any]) -> str:
        """Append one JSON report line to the drill log and mirror it to app logging."""
        line = json.dumps({"timestamp": datetime.now(UTC).isoformat(), **payload}, ensure_ascii=False, default=str)
        try:
            os.makedirs(os.path.dirname(DRILL_LOG_PATH), exist_ok=True)
            with open(DRILL_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            logger.error("Could not write drill report to %s: %s", DRILL_LOG_PATH, exc)
        logger.info("RESTORE DRILL REPORT %s", line)
        return DRILL_LOG_PATH

    @classmethod
    def run_drill(cls, *, source: str = "auto", filename: str | None = None) -> dict[str, Any]:
        """Full drill pipeline. Always writes a report; never raises."""
        started = time.monotonic()
        result: dict[str, Any] = {
            "ok": False,
            "source": source,
            "requested_filename": filename,
            "artifact_origin": None,
            "artifact_filename": None,
            "scratch_db": os.environ.get("RESTORE_DRILL_DB"),
            "restore_ok": False,
            "counts": {},
            "errors": [],
            "report_path": None,
            "duration_seconds": 0,
        }
        scratch_url, err = cls.resolve_scratch_database_url()
        if err:
            result["errors"].append(err)
            result["report_path"] = cls.write_drill_report(result)
            return result

        artifact, err = cls.acquire_artifact(source=source, filename=filename)
        if not artifact:
            result["errors"].append(err)
            result["report_path"] = cls.write_drill_report(result)
            return result

        result["artifact_origin"] = artifact.get("origin")
        result["artifact_filename"] = artifact.get("filename") or os.path.basename(artifact.get("path") or "")
        workdir = artifact.get("workdir")
        try:
            restore_outcome = cls.restore_into_scratch(artifact["path"], scratch_url)
            result["restore_ok"] = bool(restore_outcome.get("ok"))
            for e in restore_outcome.get("errors") or []:
                result["errors"].append(f"restore: {str(e)[:200]}")

            if result["restore_ok"]:
                sanity = cls.row_count_sanity(scratch_url)
                result["counts"] = sanity.get("counts") or {}
                for e in sanity.get("errors") or []:
                    result["errors"].append(f"sanity: {e}")

            result["ok"] = result["restore_ok"] and not result["errors"]
        except Exception as exc:
            logger.exception("Restore drill crashed")
            result["errors"].append(f"drill crashed: {type(exc).__name__}: {exc}"[:250])
        finally:
            result["duration_seconds"] = round(time.monotonic() - started, 2)
            if workdir and os.path.isdir(workdir):
                shutil.rmtree(workdir, ignore_errors=True)
            result["report_path"] = cls.write_drill_report(result)
        return result
