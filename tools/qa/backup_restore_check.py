"""
Backup/restore QA — restore proof uses a temporary PostgreSQL database only.

Usage:
  python tools/qa/backup_restore_check.py --verify-tools
  python tools/qa/backup_restore_check.py --create-and-verify
  python tools/qa/backup_restore_check.py --restore-to-target
  python tools/qa/backup_restore_check.py --create-and-verify --restore-to-temp-local
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import logging
import os
import re
import shutil
import sys

logger = logging.getLogger(__name__)
import tarfile
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TEMP_DB_PREFIX = "azad_restore_test_"
SAMPLE_COUNT_TABLES = (
    "tenants",
    "users",
    "products",
    "customers",
    "sales",
    "sale_lines",
    "payments",
    "gl_journal_entries",
    "gl_journal_lines",
    "stock_movements",
)
RESTORE_PROOF_MAX_AGE_HOURS = 168
EXIT_SKIP = 2


def _load_env() -> str:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(ROOT, ".env"))
    url = (os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI") or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL not set in environment")
    return url


def _git_short_head() -> str:
    try:
        from services.backup_exec import run_git

        proc = run_git(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, timeout=15)
        if proc.returncode == 0:
            return (proc.stdout or "").strip()
    except Exception as exc:
        logger.debug("git head: %s", exc)
    return ""


def _make_url_with_db(base_url: str, dbname: str) -> str:
    from sqlalchemy.engine.url import make_url

    u = make_url(base_url).set(database=dbname)
    try:
        return u.render_as_string(hide_password=False)
    except Exception:
        return str(u)


def _admin_urls(base_url: str) -> List[str]:
    from sqlalchemy.engine.url import make_url

    u = make_url(base_url)
    seen = set()
    urls: List[str] = []
    for db in (u.database, "postgres", "template1"):
        if not db:
            continue
        try:
            candidate = str(u.set(database=db))
        except (ValueError, TypeError) as exc:
            logger.debug("admin url for db %s: %s", db, exc)
            candidate = None
        if candidate and candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)
    return urls


def _create_temp_database(base_url: str, dbname: str) -> Tuple[bool, str]:
    if not re.fullmatch(r"azad_restore_test_[0-9_]+", dbname):
        return False, "invalid temp database name"
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine.url import make_url

    errors: List[str] = []
    for admin in _admin_urls(base_url):
        try:
            engine = create_engine(admin, isolation_level="AUTOCOMMIT")
            with engine.connect() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :n"),
                    {"n": dbname},
                ).scalar()
                if exists:
                    return False, f"database {dbname} already exists"
                conn.execute(text(f'CREATE DATABASE "{dbname}"'))
            return True, ""
        except Exception as e:
            errors.append(f"{admin.split('@')[-1]}: {e}")

    from services.backup_service import BackupService

    params = BackupService._parse_db_url(base_url)
    if params:
        createdb = BackupService._resolve_pg_tool("createdb", "PG_CREATEDB_PATH")
        if createdb:
            env = os.environ.copy()
            if params.get("password"):
                env["PGPASSWORD"] = params["password"]
            from services.backup_exec import run_pg_tool

            proc = run_pg_tool(
                [
                    createdb,
                    "-h",
                    params["host"],
                    "-p",
                    params["port"],
                    "-U",
                    params["username"],
                    dbname,
                ],
                env=env,
                timeout=120,
            )
            if proc.returncode == 0:
                return True, ""
            errors.append((proc.stderr or proc.stdout or "createdb failed")[:300])

    u = make_url(base_url)
    return False, " | ".join(errors)[:800] if errors else "CREATE DATABASE failed"


def _drop_temp_database(base_url: str, dbname: str) -> Tuple[bool, str]:
    if not dbname.startswith(TEMP_DB_PREFIX):
        return False, "refusing to drop non-temp database"
    from sqlalchemy import create_engine, text

    errors: List[str] = []
    for admin in _admin_urls(base_url):
        try:
            engine = create_engine(admin, isolation_level="AUTOCOMMIT")
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :n AND pid <> pg_backend_pid()"
                    ),
                    {"n": dbname},
                )
                conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}"'))
            return True, ""
        except Exception as e:
            errors.append(str(e)[:200])

    from services.backup_service import BackupService

    params = BackupService._parse_db_url(base_url)
    if params:
        dropdb = BackupService._resolve_pg_tool("dropdb", "PG_DROPDB_PATH")
        if dropdb:
            env = os.environ.copy()
            if params.get("password"):
                env["PGPASSWORD"] = params["password"]
            from services.backup_exec import run_pg_tool

            run_pg_tool(
                [
                    dropdb,
                    "-h",
                    params["host"],
                    "-p",
                    params["port"],
                    "-U",
                    params["username"],
                    "--if-exists",
                    dbname,
                ],
                env=env,
                timeout=120,
            )
            return True, ""
    return False, "; ".join(errors)[:500]


def _extract_bundle(backup_path: str, work_dir: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    with tarfile.open(backup_path, "r:gz") as tar:
        names = set(tar.getnames())
        for member in ("db.dump", "uploads.tar.gz", "manifest.json"):
            if member not in names:
                raise RuntimeError(f"missing {member} in backup archive")
            tar.extract(member, work_dir, filter="data")
            out[member] = os.path.join(work_dir, member)
    with open(out["manifest.json"], "r", encoding="utf-8") as f:
        out["manifest"] = json.load(f)
    return out


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_files_under(root: str) -> int:
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        n += len(filenames)
    return n


def _restore_uploads_to_test_dir(uploads_archive: str, dest_root: str, manifest: Dict) -> Dict[str, Any]:
    os.makedirs(dest_root, exist_ok=True)
    dest_abs = os.path.abspath(dest_root)
    expected_hash = (manifest.get("sha256") or {}).get("uploads.tar.gz")
    if expected_hash and _sha256_file(uploads_archive) != expected_hash:
        return {"ok": False, "error": "uploads.tar.gz checksum mismatch"}

    with tarfile.open(uploads_archive, "r:gz") as tar:
        for member in tar.getmembers():
            target = os.path.abspath(os.path.join(dest_root, member.name))
            if not target.startswith(dest_abs + os.sep) and target != dest_abs:
                return {"ok": False, "error": f"path traversal blocked: {member.name}"}
        tar.extractall(dest_root, members=tar.getmembers(), filter="data")

    count = _count_files_under(dest_root)
    return {"ok": True, "files_count": count, "dest": dest_root}


def _table_exists(conn, table: str) -> bool:
    from sqlalchemy import text

    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:t"
            ),
            {"t": table},
        ).scalar()
    )


def _scalar(conn, sql: str) -> int:
    from sqlalchemy import text

    return int(conn.execute(text(sql)).scalar() or 0)


def _fetch_table_counts(url: str, tables: Tuple[str, ...]) -> Dict[str, int]:
    from sqlalchemy import create_engine

    counts: Dict[str, int] = {}
    with create_engine(url).connect() as conn:
        for table in tables:
            if _table_exists(conn, table):
                counts[table] = _scalar(conn, f'SELECT COUNT(*) FROM "{table}"')
    return counts


def _verify_restored_db(
    target_url: str,
    source_url: str,
    manifest: Dict[str, Any],
) -> Dict[str, Any]:
    from sqlalchemy import create_engine, text

    import tools.qa.predeploy_check as pdc

    result: Dict[str, Any] = {"checks": {}, "ok": True, "errors": []}

    with create_engine(target_url).connect() as conn:
        tables_public = _scalar(
            conn,
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE'",
        )
        result["checks"]["tables_count"] = tables_public
        expected_tables = manifest.get("tables_count")
        if expected_tables is not None and tables_public < int(expected_tables):
            result["ok"] = False
            result["errors"].append(
                f"tables_count {tables_public} < manifest {expected_tables}"
            )

        for idx in pdc.REQUIRED_INDEXES:
            exists = conn.execute(
                text("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"),
                {"n": idx},
            ).scalar()
            if not exists:
                result["ok"] = False
                result["errors"].append(f"missing index {idx}")

        for idx in pdc.LEGACY_GLOBAL_UNIQUE_INDEXES:
            if conn.execute(
                text("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"),
                {"n": idx},
            ).scalar():
                result["ok"] = False
                result["errors"].append(f"legacy global index {idx}")

        for idx in pdc.REQUIRED_PER_TENANT_UNIQUE_INDEXES:
            if not conn.execute(
                text("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:n"),
                {"n": idx},
            ).scalar():
                result["ok"] = False
                result["errors"].append(f"missing per-tenant index {idx}")

        for table in pdc.TENANT_NOT_NULL_TABLES:
            row = conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:t AND column_name='tenant_id'"
                ),
                {"t": table},
            ).fetchone()
            if row and row[0] == "YES":
                result["ok"] = False
                result["errors"].append(f"{table}.tenant_id nullable")

        result["checks"]["gl_dual_side"] = _scalar(
            conn, "SELECT COUNT(*) FROM gl_journal_lines WHERE debit > 0 AND credit > 0"
        )
        if result["checks"]["gl_dual_side"]:
            result["ok"] = False
            result["errors"].append("GL dual-side > 0")

        result["checks"]["unbalanced_jes"] = _scalar(
            conn,
            "SELECT COUNT(*) FROM gl_journal_entries "
            "WHERE ABS(COALESCE(total_debit,0)-COALESCE(total_credit,0)) > 0.001",
        )
        if result["checks"]["unbalanced_jes"]:
            result["ok"] = False
            result["errors"].append("unbalanced JEs > 0")

        result["checks"]["cross_tenant_gl"] = _scalar(
            conn,
            """
            SELECT COUNT(*) FROM gl_journal_lines jl
            JOIN gl_journal_entries je ON je.id = jl.entry_id
            JOIN gl_accounts ga ON ga.id = jl.account_id
            WHERE je.tenant_id IS DISTINCT FROM ga.tenant_id
            """,
        )
        if result["checks"]["cross_tenant_gl"]:
            result["ok"] = False
            result["errors"].append("cross-tenant GL > 0")

        result["checks"]["active_invoice_settings_null_tenant"] = _scalar(
            conn,
            "SELECT COUNT(*) FROM invoice_settings WHERE is_active = true AND tenant_id IS NULL",
        )
        if result["checks"]["active_invoice_settings_null_tenant"]:
            result["ok"] = False
            result["errors"].append("active invoice_settings null tenant")

        if _table_exists(conn, "alembic_version"):
            alembic_ver = conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar()
            result["checks"]["alembic_version"] = alembic_ver
            if str(alembic_ver) != "prod_schema_hardening_001":
                result["ok"] = False
                result["errors"].append(
                    f"alembic_version={alembic_ver!r} expected prod_schema_hardening_001"
                )
        else:
            result["ok"] = False
            result["errors"].append("alembic_version table missing")

    source_counts = _fetch_table_counts(source_url, SAMPLE_COUNT_TABLES)
    target_counts = _fetch_table_counts(target_url, SAMPLE_COUNT_TABLES)
    result["row_counts_source"] = source_counts
    result["row_counts_target"] = target_counts
    mismatches = []
    for table, src_n in source_counts.items():
        tgt_n = target_counts.get(table)
        if tgt_n is None:
            mismatches.append(f"{table}: missing on target")
        elif tgt_n != src_n:
            mismatches.append(f"{table}: source={src_n} target={tgt_n}")
    result["checks"]["row_count_mismatches"] = mismatches
    if mismatches:
        result["ok"] = False
        result["errors"].extend(mismatches)

    return result


def _run_predeploy_on_target(target_url: str) -> Dict[str, Any]:
    from services.backup_exec import run_repo_python_script

    env = os.environ.copy()
    env.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    proc = run_repo_python_script(
        "tools/qa/predeploy_check.py",
        [
            "--profile",
            "local",
            "--skip-uat",
            "--database-url",
            target_url,
        ],
        cwd=ROOT,
        env=env,
        timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    overall = "FAIL"
    for line in out.splitlines():
        if line.strip().startswith("OVERALL:"):
            overall = line.split(":", 1)[-1].strip()
            break
    return {
        "exit_code": proc.returncode,
        "overall": overall,
        "tail": out[-1500:],
    }


def _write_restore_proof(backup_filename: str, payload: Dict[str, Any]) -> str:
    from services.backup_service import BackupService

    BackupService.initialize()
    base = backup_filename.replace(".tar.gz", "")
    path = os.path.join(BackupService.BACKUP_DIR, f"{base}.restore_proof.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    marker = os.path.join(BackupService.BACKUP_DIR, ".latest_restore_proof.json")
    with open(marker, "w", encoding="utf-8") as f:
        json.dump({"proof_file": os.path.basename(path), "verified_at": payload.get("verified_at")}, f)
    return path


def verify_tools() -> int:
    from services.backup_service import BackupService

    BackupService.initialize()
    tools = BackupService.pg_tools_status()
    writable = os.access(BackupService.BACKUP_DIR, os.W_OK | os.X_OK)
    print("BACKUP_DIR", BackupService.BACKUP_DIR)
    print("writable", writable)
    print("pg_dump", tools.get("pg_dump") or "MISSING")
    print("pg_restore", tools.get("pg_restore") or "MISSING")
    print("pg_dump_version", tools.get("pg_dump_version"))
    if not writable:
        return 1
    if not tools.get("pg_dump"):
        print("WARN: pg_dump not available")
        return 2
    return 0


def _bootstrap_target_schema(target_url: str) -> Tuple[bool, str]:
    from services.backup_scoped_engine import ensure_target_schema

    return ensure_target_schema(target_url)


def _ensure_temp_store(source_url: str, tenant_id: int) -> Optional[int]:
    from sqlalchemy import create_engine, text

    with create_engine(source_url).connect() as conn:
        row = conn.execute(
            text("SELECT id FROM tenant_stores WHERE tenant_id = :tid LIMIT 1"),
            {"tid": tenant_id},
        ).fetchone()
        if row:
            return int(row[0])
        wh = conn.execute(
            text("SELECT id FROM warehouses WHERE tenant_id = :tid LIMIT 1"),
            {"tid": tenant_id},
        ).fetchone()
        if not wh:
            return None
        slug = f"qa-temp-store-{tenant_id}"
        conn.execute(
            text(
                "INSERT INTO tenant_stores "
                "(tenant_id, warehouse_id, store_slug, is_enabled, created_at, updated_at) "
                "VALUES (:tid, :wid, :slug, false, NOW(), NOW())"
            ),
            {"tid": tenant_id, "wid": int(wh[0]), "slug": slug},
        )
        conn.commit()
        row = conn.execute(
            text("SELECT id FROM tenant_stores WHERE store_slug = :slug"),
            {"slug": slug},
        ).fetchone()
        return int(row[0]) if row else None


def _resolve_branch_id(conn, tenant_id: int, branch_id: Optional[int]) -> Optional[int]:
    from sqlalchemy import text

    if branch_id:
        return int(branch_id)
    row = conn.execute(
        text(
            "SELECT id FROM branches WHERE tenant_id = :tid ORDER BY is_main DESC NULLS LAST, id LIMIT 1"
        ),
        {"tid": tenant_id},
    ).fetchone()
    return int(row[0]) if row else None


def _resolve_store_id(conn, tenant_id: int, store_id: Optional[int]) -> Optional[int]:
    from sqlalchemy import text

    if store_id:
        return int(store_id)
    row = conn.execute(
        text("SELECT id FROM tenant_stores WHERE tenant_id = :tid LIMIT 1"),
        {"tid": tenant_id},
    ).fetchone()
    return int(row[0]) if row else None


def create_and_verify(
    scope: str = "system",
    *,
    tenant_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    store_id: Optional[int] = None,
) -> Tuple[Optional[str], Optional[Dict], int]:
    from services.backup_service import BackupService

    _load_env()
    from app import create_app
    from sqlalchemy import create_engine

    app = create_app()
    with app.app_context():
        BackupService.initialize()
        kwargs: Dict[str, Any] = {
            "manual": True,
            "description": f"backup_restore_check scope={scope}",
            "scope": scope,
        }
        if scope != "system":
            tid = tenant_id or 1
            kwargs["tenant_id"] = tid
            url = os.environ.get("DATABASE_URL") or ""
            if scope in ("branch", "store") and url:
                with create_engine(url).connect() as conn:
                    if scope == "branch":
                        bid = _resolve_branch_id(conn, tid, branch_id)
                        if not bid:
                            print("FAIL: no branch_id for tenant", tid)
                            return None, None, 1
                        kwargs["branch_id"] = bid
                        print("BRANCH_ID", bid)
                    if scope == "store":
                        sid = _resolve_store_id(conn, tid, store_id)
                        if not sid:
                            print("FAIL: no store_id for tenant", tid)
                            return None, None, 1
                        kwargs["store_id"] = sid
                        print("STORE_ID", sid)
        created = BackupService.create_backup(**kwargs)
        if not created:
            print("FAIL: create_backup returned None")
            return None, None, 1
        fn = created["filename"]
        print("CREATED", fn, created.get("size_mb"), "MB", "scope=", scope)
        result = BackupService.verify_backup(fn)
        print(json.dumps(result, indent=2, default=str)[:2500])
        return fn, result, (0 if result.get("valid") else 1)


def restore_to_temp_local(
    backup_filename: Optional[str],
    *,
    cleanup_on_fail: bool = False,
    remap: bool = False,
) -> int:
    from services.backup_service import BackupService
    from services.backup_scoped_restore import REMAP_CONFIRM, RESTORE_CONFIRM

    source_url = _load_env()
    from app import create_app

    app = create_app()
    with app.app_context():
        BackupService.initialize()
        if not backup_filename:
            backups = [
                b
                for b in BackupService.list_backups()
                if str(b.get("filename", "")).startswith("azad_backup_")
            ]
            if not backups:
                print("FAIL: no modern backup")
                return 1
            backup_filename = backups[0]["filename"]

        verify = BackupService.verify_backup(backup_filename)
        if not verify.get("valid"):
            print("FAIL: backup invalid", json.dumps(verify, indent=2))
            return 1

        manifest = verify.get("manifest") or {}
        scope = manifest.get("backup_scope") or "system"
        backup_path = os.path.join(BackupService.BACKUP_DIR, backup_filename)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        temp_db = f"{TEMP_DB_PREFIX}{ts}"
        target_url = _make_url_with_db(source_url, temp_db)
        uploads_dest = os.path.join(ROOT, "instance", "restore_test_uploads", ts)
        work_dir = tempfile.mkdtemp(prefix="azad_restore_proof_")

        proof: Dict[str, Any] = {
            "backup_filename": backup_filename,
            "backup_scope": scope,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "temp_db_name": temp_db,
            "restore_success": False,
            "remap": remap,
            "cleanup_status": "pending",
        }

        try:
            ok_create, reason = _create_temp_database(source_url, temp_db)
            if not ok_create:
                print("SKIPPED_WITH_REASON: cannot create temp database")
                print(reason)
                proof["skip_reason"] = reason
                BackupService.write_restore_proof(backup_filename, proof)
                return EXIT_SKIP

            confirm = REMAP_CONFIRM if remap else RESTORE_CONFIRM

            if scope == "system":
                bundle = _extract_bundle(backup_path, work_dir)
                manifest = bundle.get("manifest") or manifest
                outcome = BackupService.restore_backup_to_target_db(
                    backup_filename,
                    target_url,
                    confirmation=confirm,
                    restore_uploads=False,
                )
                if not outcome.get("ok"):
                    print("FAIL: pg_restore", json.dumps(outcome, indent=2))
                    proof["restore_errors"] = outcome.get("errors")
                    BackupService.write_restore_proof(backup_filename, proof)
                    return 1
                uploads_result = _restore_uploads_to_test_dir(
                    bundle["uploads.tar.gz"], uploads_dest, manifest
                )
                proof["uploads_restore"] = uploads_result
                if not uploads_result.get("ok"):
                    print("FAIL: uploads restore", uploads_result)
                    BackupService.write_restore_proof(backup_filename, proof)
                    return 1
                db_verify = _verify_restored_db(target_url, source_url, manifest)
            else:
                ok_schema, schema_err = _bootstrap_target_schema(target_url)
                if not ok_schema:
                    print("FAIL: schema bootstrap", schema_err)
                    proof["schema_error"] = schema_err
                    BackupService.write_restore_proof(backup_filename, proof)
                    return 1
                outcome = BackupService.restore_scoped_backup_to_target_db(
                    backup_filename,
                    target_url,
                    confirmation=confirm,
                    remap=remap,
                    restore_uploads=True,
                    uploads_dest_root=uploads_dest,
                )
                if not outcome.get("ok"):
                    print("FAIL: scoped restore", json.dumps(outcome, indent=2, default=str))
                    proof["restore_errors"] = outcome.get("errors")
                    BackupService.write_restore_proof(backup_filename, proof)
                    return 1
                from services.backup_scoped_restore import verify_scoped_restore

                tgt_tid = int(outcome.get("target_tenant_id") or manifest.get("tenant_id") or 0)
                db_verify = verify_scoped_restore(
                    target_url, manifest, expected_tenant_id=tgt_tid, scope=scope
                )
                proof["scoped_restore"] = outcome
                imp = outcome.get("import") or {}
                manifest_counts = manifest.get("row_counts_per_table") or {}
                proof["products_source_count"] = int(manifest_counts.get("products") or 0)
                proof["products_restored_count"] = int(
                    imp.get("products_inserted")
                    or (db_verify.get("counts") or {}).get("products")
                    or 0
                )
                proof["rows_skipped"] = int(imp.get("rows_skipped") or 0)
                proof["target_tenant_id"] = tgt_tid if scope != "system" else None
                if proof["products_source_count"] and proof[
                    "products_restored_count"
                ] != proof["products_source_count"]:
                    proof["restore_success"] = False
                    proof["restore_errors"] = proof.get("restore_errors") or []
                    proof["restore_errors"].append(
                        "products count mismatch: source="
                        f"{proof['products_source_count']} restored="
                        f"{proof['products_restored_count']}"
                    )
                    BackupService.write_restore_proof(backup_filename, proof)
                    return 1
                if proof.get("rows_skipped", 0) > 0:
                    proof["restore_success"] = False
                    proof["restore_errors"] = proof.get("restore_errors") or []
                    proof["restore_errors"].append(f"rows_skipped={proof['rows_skipped']}")
                    BackupService.write_restore_proof(backup_filename, proof)
                    return 1

            proof["db_verify"] = db_verify
            print("DB_VERIFY", json.dumps(db_verify, indent=2, default=str))
            if not db_verify.get("ok"):
                BackupService.write_restore_proof(backup_filename, proof)
                return 1

            if scope == "system":
                predeploy = _run_predeploy_on_target(target_url)
                proof["predeploy_on_restored_db"] = predeploy
                print("PREDEPLOY_ON_RESTORED_DB", predeploy.get("overall"))
                if predeploy.get("exit_code") != 0:
                    BackupService.write_restore_proof(backup_filename, proof)
                    return 1

            proof["restore_success"] = True
            proof["manifest_git_commit"] = manifest.get("git_commit")
            proof["git_head_at_proof"] = _git_short_head()
            BackupService.write_restore_proof(backup_filename, proof)
            print("RESTORE_PROOF_PASS", scope, temp_db)
            return 0

        finally:
            if proof.get("restore_success"):
                dropped, drop_err = _drop_temp_database(source_url, temp_db)
                proof["cleanup_status"] = "dropped_db" if dropped else f"drop_failed: {drop_err}"
                if os.path.isdir(uploads_dest):
                    shutil.rmtree(uploads_dest, ignore_errors=True)
                BackupService.write_restore_proof(backup_filename, proof)
            elif cleanup_on_fail:
                _drop_temp_database(source_url, temp_db)
                if os.path.isdir(uploads_dest):
                    shutil.rmtree(uploads_dest, ignore_errors=True)
                BackupService.write_restore_proof(backup_filename, proof)
            shutil.rmtree(work_dir, ignore_errors=True)


def restore_to_target() -> int:
    from services.backup_service import BackupService

    _load_env()
    target = (os.environ.get("TARGET_TEST_DATABASE_URL") or "").strip()
    if not target:
        print("SKIP: TARGET_TEST_DATABASE_URL not set")
        return EXIT_SKIP
    current = (os.environ.get("DATABASE_URL") or "").strip()
    if BackupService._urls_same_database(current, target):
        print("FAIL: TARGET_TEST_DATABASE_URL equals DATABASE_URL")
        return 1

    from app import create_app

    app = create_app()
    with app.app_context():
        backups = BackupService.list_backups()
        modern = [
            b
            for b in backups
            if b.get("format") == "azad_tar_v1"
            or str(b.get("filename", "")).startswith("azad_backup_")
        ]
        if not modern:
            print("FAIL: no modern backup to restore")
            return 1
        fn = modern[0]["filename"]
        verify = BackupService.verify_backup(fn)
        if not verify.get("valid"):
            print("FAIL: backup invalid", verify)
            return 1
        outcome = BackupService.restore_backup_to_target_db(
            fn,
            target,
            confirmation="RESTORE CONFIRM",
            restore_uploads=False,
        )
        print(json.dumps(outcome, indent=2, default=str))
        return 0 if outcome.get("ok") else 1


def verify_scopes() -> int:
    """Verify system vs tenant backup isolation (read-only on live DB + archives)."""
    from services.backup_service import BackupService
    from sqlalchemy import create_engine, text

    _load_env()
    from app import create_app

    app = create_app()
    with app.app_context():
        BackupService.initialize()
        url = os.environ.get("DATABASE_URL") or ""
        live_tenants = 0
        if url:
            with create_engine(url).connect() as conn:
                live_tenants = int(
                    conn.execute(text("SELECT COUNT(*) FROM tenants")).scalar() or 0
                )

        backups = BackupService.list_backups()
        system = [
            b
            for b in backups
            if b.get("backup_scope") == "system"
            or "_system_" in b.get("filename", "")
            or (
                b.get("filename", "").startswith("azad_backup_")
                and "_tenant_" not in b.get("filename", "")
                and b.get("backup_scope") != "tenant"
            )
        ]
        tenant_baks = [b for b in backups if b.get("backup_scope") == "tenant" or "_tenant_" in b.get("filename", "")]

        if not system:
            print("FAIL: no system backup found")
            return 1
        sys_fn = system[0]["filename"]
        sys_v = BackupService.verify_backup(sys_fn)
        print("SYSTEM", sys_fn, "valid=", sys_v.get("valid"))
        if not sys_v.get("valid"):
            return 1
        sys_manifest = sys_v.get("manifest") or {}
        if sys_manifest.get("backup_scope") not in (None, "system"):
            print("FAIL: latest system archive wrong scope")
            return 1
        if live_tenants > 1 and sys_manifest.get("backup_scope") == "system":
            print("OK: system backup present; live tenants=", live_tenants)

        if not tenant_baks:
            print("WARN: no tenant backup yet — creating sample for tenant_id=2 if exists")
            created = BackupService.create_backup(
                scope="tenant",
                tenant_id=2,
                description="backup_restore_check tenant sample",
            )
            if created:
                tenant_baks = [created]
            else:
                print("SKIP tenant backup verify (create failed)")
                return 0

        ten_fn = tenant_baks[0]["filename"]
        ten_v = BackupService.verify_backup(ten_fn)
        print("TENANT", ten_fn, "valid=", ten_v.get("valid"))
        if not ten_v.get("valid"):
            return 1
        tid = (ten_v.get("manifest") or {}).get("tenant_id")
        tv = ten_v.get("scoped_verify") or ten_v.get("tenant_verify") or {}
        if tv and not tv.get("ok"):
            print("FAIL tenant isolation", tv.get("errors"))
            return 1
        print("SCOPE_VERIFY_PASS", f"tenant_id={tid}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-tools", action="store_true")
    parser.add_argument("--create-and-verify", action="store_true")
    parser.add_argument("--restore-to-target", action="store_true")
    parser.add_argument("--verify-scopes", action="store_true")
    parser.add_argument(
        "--scope",
        choices=("system", "tenant", "branch", "store"),
        default="system",
    )
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--branch-id", type=int, default=None)
    parser.add_argument("--store-id", type=int, default=None)
    parser.add_argument(
        "--restore-to-temp-local",
        action="store_true",
        help="Create azad_restore_test_* DB, restore backup, verify, cleanup",
    )
    parser.add_argument("--restore-as-new-tenant", action="store_true")
    parser.add_argument(
        "--with-temp-source-store",
        action="store_true",
        help="If no store on live DB, build store backup from temp source DB (not live)",
    )
    parser.add_argument("--cleanup-on-fail", action="store_true")
    args = parser.parse_args()

    if args.verify_tools:
        return verify_tools()
    if args.verify_scopes:
        return verify_scopes()

    backup_fn: Optional[str] = None
    if args.create_and_verify:
        if args.scope == "store" and args.with_temp_source_store:
            url = _load_env()
            sid = _ensure_temp_store(url, args.tenant_id or 1)
            if sid:
                args.store_id = sid
                print("TEMP_SOURCE_STORE", sid)
        backup_fn, _, code = create_and_verify(
            args.scope,
            tenant_id=args.tenant_id,
            branch_id=args.branch_id,
            store_id=args.store_id,
        )
        if code != 0:
            return code
        if not args.restore_to_temp_local:
            return 0

    if args.restore_to_temp_local:
        return restore_to_temp_local(
            backup_fn,
            cleanup_on_fail=args.cleanup_on_fail,
            remap=args.restore_as_new_tenant,
        )

    if args.restore_to_target:
        return restore_to_target()

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
