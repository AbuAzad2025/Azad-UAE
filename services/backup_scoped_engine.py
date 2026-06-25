"""
Scoped backup export (JSONL) and restore with optional ID remap.

Used for tenant / branch / store backups — never mixes scopes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tarfile
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import text

from services.backup_scope_config import (
    SCOPE_BRANCH,
    SCOPE_STORE,
    SCOPE_TENANT,
    TABLE_EXPORT_ORDER,
    build_tenant_uploads_archive,
    collect_scoped_upload_paths,
    export_scoped_database,
    read_data_directory,
    table_exists,
    write_data_directory,
)

logger = logging.getLogger(__name__)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

# FK columns to remap per table (column -> referenced table for id_map lookup)
TABLE_FK_REMAP: Dict[str, Dict[str, str]] = {
    "tenants": {},
    "branches": {"tenant_id": "tenants"},
    "users": {"tenant_id": "tenants", "branch_id": "branches"},
    "products": {"tenant_id": "tenants", "category_id": "product_categories"},
    "product_categories": {"tenant_id": "tenants", "parent_id": "product_categories"},
    "product_partners": {"tenant_id": "tenants", "product_id": "products", "partner_id": "customers"},
    "customers": {"tenant_id": "tenants"},
    "suppliers": {"tenant_id": "tenants"},
    "warehouses": {"tenant_id": "tenants", "branch_id": "branches"},
    "sales": {
        "tenant_id": "tenants",
        "branch_id": "branches",
        "customer_id": "customers",
        "warehouse_id": "warehouses",
        "user_id": "users",
    },
    "sale_lines": {
        "tenant_id": "tenants",
        "sale_id": "sales",
        "product_id": "products",
    },
    "purchases": {
        "tenant_id": "tenants",
        "branch_id": "branches",
        "supplier_id": "suppliers",
        "warehouse_id": "warehouses",
    },
    "purchase_lines": {
        "tenant_id": "tenants",
        "purchase_id": "purchases",
        "product_id": "products",
    },
    "payments": {
        "tenant_id": "tenants",
        "branch_id": "branches",
        "customer_id": "customers",
        "supplier_id": "suppliers",
        "sale_id": "sales",
        "purchase_id": "purchases",
    },
    "expenses": {"tenant_id": "tenants", "branch_id": "branches"},
    "cheques": {"tenant_id": "tenants", "branch_id": "branches"},
    "stock_movements": {
        "tenant_id": "tenants",
        "warehouse_id": "warehouses",
        "product_id": "products",
    },
    "gl_accounts": {"tenant_id": "tenants"},
    "gl_journal_entries": {
        "tenant_id": "tenants",
        "branch_id": "branches",
    },
    "gl_journal_lines": {
        "tenant_id": "tenants",
        "entry_id": "gl_journal_entries",
        "account_id": "gl_accounts",
    },
    "invoice_settings": {"tenant_id": "tenants"},
    "tenant_stores": {"tenant_id": "tenants", "warehouse_id": "warehouses"},
    "shop_customer_accounts": {"tenant_id": "tenants"},
    "store_coupons": {"tenant_id": "tenants"},
    "store_payment_methods": {"tenant_id": "tenants"},
    "employees": {"tenant_id": "tenants", "branch_id": "branches"},
    "salary_advances": {"tenant_id": "tenants", "employee_id": "employees"},
    "payroll_transactions": {"tenant_id": "tenants", "employee_id": "employees"},
    "partner_commission_entries": {
        "tenant_id": "tenants",
        "branch_id": "branches",
        "product_id": "products",
    },
    "azad_platform_fees": {
        "tenant_id": "tenants",
        "sale_id": "sales",
        "payment_id": "payments",
    },
    "fixed_assets": {"tenant_id": "tenants", "branch_id": "branches"},
}


@dataclass
class ExportResult:
    tables: Dict[str, List[Dict[str, Any]]]
    row_counts: Dict[str, int]
    included: List[str]
    skipped: List[str]
    dependency_order: List[str]
    unresolved: List[str] = field(default_factory=list)
    scope: str = ""
    tenant_id: Optional[int] = None
    branch_id: Optional[int] = None
    store_id: Optional[int] = None


def _json_default(val: Any) -> Any:
    if isinstance(val, (datetime, date, time)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, (bytes, bytearray)):
        return val.hex()
    if isinstance(val, UUID):
        return str(val)
    return str(val)


def write_jsonl(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_data_bundle(
    data_dir: str,
    export: ExportResult,
    conn,
) -> Dict[str, Any]:
    """Write data/*.jsonl + schema_meta.json; return metadata for manifest."""
    os.makedirs(data_dir, exist_ok=True)
    schema_meta: Dict[str, Any] = {}
    for table in export.dependency_order:
        rows = export.tables.get(table) or []
        if not rows:
            continue
        write_jsonl(os.path.join(data_dir, f"{table}.jsonl"), rows)
        cols = []
        if table_exists(conn, table):
            cols = [
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"
                    ),
                    {"t": table},
                )
            ]
        schema_meta[table] = {"columns": cols, "row_count": len(rows)}
    meta_path = os.path.join(data_dir, "export_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "dependency_order": export.dependency_order,
                "schema_meta": schema_meta,
                "scope": export.scope,
                "tenant_id": export.tenant_id,
                "branch_id": export.branch_id,
                "store_id": export.store_id,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    return {"export_meta_path": meta_path, "schema_meta": schema_meta}


def write_checksums_file(work_dir: str, rel_paths: List[str]) -> str:
    lines: List[str] = []
    for rel in sorted(rel_paths):
        full = os.path.join(work_dir, rel)
        if os.path.isfile(full):
            h = hashlib.sha256()
            with open(full, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            lines.append(f"{h.hexdigest()}  {rel}")
    path = os.path.join(work_dir, "checksums.sha256")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    return path


def export_scope(
    conn,
    scope: str,
    *,
    tenant_id: int,
    branch_id: Optional[int] = None,
    store_id: Optional[int] = None,
) -> ExportResult:
    tables, counts, included, skipped, unresolved = export_scoped_database(
        conn,
        scope,
        tenant_id=tenant_id,
        branch_id=branch_id,
        store_id=store_id,
    )
    order = [t for t in TABLE_EXPORT_ORDER if t in tables] + [
        t for t in tables if t not in TABLE_EXPORT_ORDER
    ]
    return ExportResult(
        tables=tables,
        row_counts=counts,
        included=included,
        skipped=skipped,
        dependency_order=order,
        unresolved=unresolved,
        scope=scope,
        tenant_id=tenant_id,
        branch_id=branch_id,
        store_id=store_id,
    )


def _new_id(conn, table: str) -> int:
    seq = conn.execute(
        text("SELECT pg_get_serial_sequence(:t, 'id')"),
        {"t": table},
    ).scalar()
    if seq:
        return int(conn.execute(text(f"SELECT nextval('{seq}')")).scalar())
    return int(
        conn.execute(text(f'SELECT COALESCE(MAX(id), 0) + 1 FROM "{table}"')).scalar()
    )


def _remap_row(
    row: Dict[str, Any],
    table: str,
    id_maps: Dict[str, Dict[int, int]],
    *,
    force_tenant_id: Optional[int] = None,
) -> Dict[str, Any]:
    out = dict(row)
    pk = out.get("id")
    if pk is not None and table in id_maps and int(pk) in id_maps[table]:
        out["id"] = id_maps[table][int(pk)]

    if force_tenant_id is not None and "tenant_id" in out:
        out["tenant_id"] = force_tenant_id

    for col, ref_table in TABLE_FK_REMAP.get(table, {}).items():
        if col not in out or out[col] is None:
            continue
        ref_map = id_maps.get(ref_table) or {}
        old = int(out[col])
        if old in ref_map:
            out[col] = ref_map[old]
    return out


def ensure_target_schema(target_database_url: str) -> Tuple[bool, str]:
    """Apply schema to empty target DB via schema-only pg_dump from source (preferred) or flask db upgrade."""
    from services.backup_service import BackupService

    source_url = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI") or ""
    if source_url and not BackupService._urls_same_database(source_url, target_database_url):
        src = BackupService._parse_db_url(source_url)
        tgt = BackupService._parse_db_url(target_database_url)
        pg_dump = BackupService._resolve_pg_tool("pg_dump", "PG_DUMP_PATH")
        pg_restore = BackupService._resolve_pg_tool("pg_restore", "PG_RESTORE_PATH")
        if src and tgt and pg_dump and pg_restore:
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sql", delete=False, encoding="utf-8"
            ) as schema_tmp:
                schema_file = schema_tmp.name
            env = os.environ.copy()
            if src.get("password"):
                env["PGPASSWORD"] = src["password"]
            dump_cmd = [
                pg_dump,
                "--host",
                src["host"],
                "--port",
                src["port"],
                "--username",
                src["username"],
                "--dbname",
                src["dbname"],
                "--schema-only",
                "--no-owner",
                "--no-privileges",
                "-f",
                schema_file,
            ]
            from services.backup_exec import run_pg_tool

            proc = run_pg_tool(dump_cmd, env=env, timeout=600)
            if proc.returncode == 0 and os.path.isfile(schema_file):
                env2 = os.environ.copy()
                if tgt.get("password"):
                    env2["PGPASSWORD"] = tgt["password"]
                psql = BackupService._resolve_pg_tool("psql", "PSQL_PATH") or "psql"
                restore_cmd = [
                    psql,
                    "--host",
                    tgt["host"],
                    "--port",
                    tgt["port"],
                    "--username",
                    tgt["username"],
                    "--dbname",
                    tgt["dbname"],
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-f",
                    schema_file,
                ]
                proc2 = run_pg_tool(restore_cmd, env=env2, timeout=600)
                try:
                    os.remove(schema_file)
                except OSError:
                    pass
                if proc2.returncode == 0:
                    return True, ""
                # pg_restore may warn on existing objects; check alembic table
                from sqlalchemy import create_engine, text

                try:
                    with create_engine(target_database_url).connect() as conn:
                        if conn.execute(
                            text(
                                "SELECT 1 FROM information_schema.tables "
                                "WHERE table_schema='public' AND table_name='alembic_version'"
                            )
                        ).scalar():
                            return True, ""
                except Exception as exc:
                    logger.debug("alembic_version probe after pg_restore: %s", exc)
                err = (proc2.stderr or proc2.stdout or "pg_restore schema failed")[:800]
                return False, err

    env = os.environ.copy()
    env["DATABASE_URL"] = target_database_url
    env["SQLALCHEMY_DATABASE_URI"] = target_database_url
    env.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    from services.backup_exec import run_python_module

    proc = run_python_module("flask", ["db", "upgrade"], cwd=ROOT, env=env, timeout=600)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "flask db upgrade failed")[:800]
        return False, err
    try:
        prev = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = target_database_url
        os.environ["SQLALCHEMY_DATABASE_URI"] = target_database_url
        from app import create_app

        app = create_app()
        with app.app_context():
            from utils.system_init import ensure_core_data

            ensure_core_data()
        if prev:
            os.environ["DATABASE_URL"] = prev
    except Exception as exc:
        logger.warning("ensure_core_data on target: %s", exc)
    return True, ""


def restore_scoped_to_target(
    extract_dir: str,
    manifest: Dict[str, Any],
    target_database_url: str,
    *,
    confirmation: str = "",
    remap: bool = False,
    target_tenant_id: Optional[int] = None,
    target_branch_id: Optional[int] = None,
    target_store_id: Optional[int] = None,
    restore_uploads_dir: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Restore tenant/branch/store JSONL bundle into target DB (must differ from live URL)."""
    outcome: Dict[str, Any] = {"ok": False, "errors": [], "warnings": [], "id_maps": {}}
    scope = manifest.get("backup_scope")
    if scope not in (SCOPE_TENANT, SCOPE_BRANCH, SCOPE_STORE):
        outcome["errors"].append(f"restore_scoped only for scoped backups, got {scope}")
        return outcome

    need_confirm = "REMAP CONFIRM" if remap else "RESTORE CONFIRM"
    if confirmation.strip() != need_confirm:
        outcome["errors"].append(f"Typed confirmation {need_confirm!r} required")
        return outcome

    data_dir = os.path.join(extract_dir, "data")
    legacy_export = os.path.join(extract_dir, "tenant_export.json")

    from services.backup_service import BackupService

    current_url = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI") or ""
    if BackupService._urls_same_database(current_url, target_database_url):
        outcome["errors"].append("Target database must differ from current DATABASE_URL")
        return outcome

    ok_schema, schema_err = ensure_target_schema(target_database_url)
    if not ok_schema:
        outcome["errors"].append(f"schema upgrade failed: {schema_err}")
        return outcome

    from sqlalchemy import create_engine

    src_tid = int(manifest.get("tenant_id") or manifest.get("source_tenant_id") or 0)

    if os.path.isdir(data_dir) and os.path.isfile(os.path.join(data_dir, "schema_meta.json")):
        tables_data, export_meta = read_data_directory(data_dir)
        dependency_order = export_meta.get("table_order") or list(tables_data.keys())
    elif os.path.isfile(legacy_export):
        with open(legacy_export, "r", encoding="utf-8") as f:
            doc = json.load(f)
        tables_data = doc.get("tables") or {}
        dependency_order = [t for t in TABLE_EXPORT_ORDER if t in tables_data] + [
            t for t in tables_data if t not in TABLE_EXPORT_ORDER
        ]
    else:
        outcome["errors"].append("no data/schema_meta.json or tenant_export.json")
        return outcome

    id_maps: Dict[str, Dict[int, int]] = {}
    force_tid: Optional[int] = None

    engine = create_engine(target_database_url)
    with engine.connect() as conn:
        prep = conn.begin()
        try:
            if remap:
                tenant_rows = tables_data.get("tenants") or []
                if not tenant_rows:
                    outcome["errors"].append("remap requires tenants row in export")
                    return outcome
                old_tid = int(tenant_rows[0]["id"])
                if target_tenant_id:
                    new_tid = int(target_tenant_id)
                else:
                    new_tid = _new_id(conn, "tenants")
                id_maps.setdefault("tenants", {})[old_tid] = new_tid
                force_tid = new_tid
                # slug must be unique — suffix
                tr = dict(tenant_rows[0])
                tr["id"] = new_tid
                base_slug = str(tr.get("slug") or f"restored_{new_tid}")
                tr["slug"] = f"{base_slug}_r{new_tid}"[:100]
                tables_data["tenants"] = [tr]
            else:
                force_tid = src_tid
                if scope == SCOPE_TENANT:
                    # clear existing tenant rows on target for same id
                    if table_exists(conn, "tenants"):
                        conn.execute(
                            text("DELETE FROM tenants WHERE id = :tid"),
                            {"tid": src_tid},
                        )

            if scope == SCOPE_BRANCH and remap:
                branch_rows = tables_data.get("branches") or []
                if branch_rows:
                    old_bid = int(branch_rows[0]["id"])
                    new_bid = int(target_branch_id) if target_branch_id else _new_id(conn, "branches")
                    id_maps.setdefault("branches", {})[old_bid] = new_bid
                    br = dict(branch_rows[0])
                    br["id"] = new_bid
                    if force_tid:
                        br["tenant_id"] = force_tid
                    tables_data["branches"] = [br]

            if scope == SCOPE_STORE and remap:
                store_rows = tables_data.get("tenant_stores") or []
                if store_rows:
                    old_sid = int(store_rows[0]["id"])
                    new_sid = int(target_store_id) if target_store_id else _new_id(conn, "tenant_stores")
                    id_maps.setdefault("tenant_stores", {})[old_sid] = new_sid
                    sr = dict(store_rows[0])
                    sr["id"] = new_sid
                    if force_tid:
                        sr["tenant_id"] = force_tid
                    base_slug = str(sr.get("store_slug") or f"store_{new_sid}")
                    sr["store_slug"] = f"{base_slug}_r{new_sid}"[:100]
                    tables_data["tenant_stores"] = [sr]

            prep.commit()
        except Exception as exc:
            prep.rollback()
            outcome["errors"].append(str(exc)[:500])
            return outcome

    for table in dependency_order:
        rows = tables_data.get(table) or []
        if not rows:
            continue
        with engine.begin() as conn:
            try:
                conn.execute(text("SET session_replication_role = replica"))
            except Exception as exc:
                logger.debug("session_replication_role replica: %s", exc)
            if not table_exists(conn, table):
                outcome["warnings"].append(f"skip missing table {table}")
                continue

            if not remap and scope == SCOPE_TENANT and table != "tenants":
                table_cols = {
                    r[0]
                    for r in conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema='public' AND table_name=:t"
                        ),
                        {"t": table},
                    )
                }
                if "tenant_id" in table_cols:
                    conn.execute(
                        text(f'DELETE FROM "{table}" WHERE tenant_id = :tid'),
                        {"tid": src_tid},
                    )
            elif not remap and scope == SCOPE_BRANCH and table not in ("tenants", "branches"):
                bid = int(manifest.get("branch_id") or manifest.get("source_branch_id") or 0)
                branch_cols = {
                    r[0]
                    for r in conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema='public' AND table_name=:t"
                        ),
                        {"t": table},
                    )
                }
                if "branch_id" in branch_cols:
                    conn.execute(
                        text(f'DELETE FROM "{table}" WHERE branch_id = :bid'),
                        {"bid": bid},
                    )

            for row in rows:
                old_pk = row.get("id")
                new_row = _remap_row(row, table, id_maps, force_tenant_id=force_tid)
                if remap and old_pk is not None:
                    if table not in id_maps:
                        id_maps[table] = {}
                    if int(old_pk) not in id_maps.get(table, {}):
                        if table == "tenants" and new_row.get("id"):
                            id_maps.setdefault(table, {})[int(old_pk)] = int(new_row["id"])
                        else:
                            nid = _new_id(conn, table)
                            id_maps.setdefault(table, {})[int(old_pk)] = nid
                            new_row["id"] = nid
                    else:
                        new_row["id"] = id_maps[table][int(old_pk)]

                cols = list(new_row.keys())
                placeholders = ", ".join(f":{c}" for c in cols)
                col_sql = ", ".join(f'"{c}"' for c in cols)
                try:
                    conn.execute(
                        text(
                            f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders})'
                        ),
                        new_row,
                    )
                except Exception as exc:
                    outcome["warnings"].append(
                        f"{table} insert: {type(exc).__name__}"
                    )
            try:
                conn.execute(text("SET session_replication_role = DEFAULT"))
            except Exception as exc:
                logger.debug("session_replication_role default: %s", exc)

    outcome["id_maps"] = {k: len(v) for k, v in id_maps.items()}
    outcome["ok"] = True

    if restore_uploads_dir and base_dir:
        uploads_arc = os.path.join(extract_dir, "uploads.tar.gz")
        if os.path.isfile(uploads_arc):
            dest_abs = os.path.abspath(restore_uploads_dir)
            try:
                with tarfile.open(uploads_arc, "r:gz") as tar:
                    for member in tar.getmembers():
                        target = os.path.abspath(os.path.join(restore_uploads_dir, member.name))
                        if not target.startswith(dest_abs + os.sep) and target != dest_abs:
                            outcome["warnings"].append(f"skipped unsafe path {member.name}")
                            continue
                    tar.extractall(restore_uploads_dir, filter="data")
                outcome["uploads_restored_to"] = restore_uploads_dir
            except (tarfile.TarError, EOFError, OSError) as exc:
                outcome["ok"] = False
                outcome["errors"].append(f"uploads restore failed: {type(exc).__name__}")
                return outcome

    outcome["target_tenant_id"] = force_tid
    return outcome


def verify_scoped_isolation(manifest: Dict[str, Any], extract_dir: str) -> Dict[str, Any]:
    """Post-restore or pre-restore archive checks for scope boundaries."""
    out: Dict[str, Any] = {"ok": True, "errors": []}
    scope = manifest.get("backup_scope")
    tid = manifest.get("tenant_id")
    bid = manifest.get("branch_id")
    sid = manifest.get("store_id")

    data_dir = os.path.join(extract_dir, "data")
    legacy = os.path.join(extract_dir, "tenant_export.json")
    tables: Dict[str, List[Dict[str, Any]]] = {}
    if os.path.isdir(data_dir):
        tables, _meta = read_data_directory(data_dir)
    elif os.path.isfile(legacy):
        with open(legacy, "r", encoding="utf-8") as f:
            tables = json.load(f).get("tables") or {}

    if scope == SCOPE_TENANT and tid is not None:
        for table, rows in tables.items():
            if table == "tenants":
                if len(rows) != 1 or int(rows[0].get("id", -1)) != int(tid):
                    out["ok"] = False
                    out["errors"].append("tenants row isolation failed")
                continue
            for row in rows:
                rt = row.get("tenant_id")
                if rt is not None and int(rt) != int(tid):
                    out["ok"] = False
                    out["errors"].append(f"cross-tenant in {table}")
                    return out

    if scope == SCOPE_BRANCH and bid is not None:
        for table, rows in tables.items():
            if table == "branches":
                if len(rows) != 1 or int(rows[0].get("id", -1)) != int(bid):
                    out["ok"] = False
                    out["errors"].append("branch row isolation failed")
            for row in rows:
                rb = row.get("branch_id")
                if rb is not None and int(rb) != int(bid):
                    out["ok"] = False
                    out["errors"].append(f"cross-branch in {table}")
                    return out

    if scope == SCOPE_STORE and sid is not None:
        ts_rows = tables.get("tenant_stores") or []
        if len(ts_rows) != 1 or int(ts_rows[0].get("id", -1)) != int(sid):
            out["ok"] = False
            out["errors"].append("store row isolation failed")

    counts = manifest.get("row_counts_per_table") or {}
    for table, expected in counts.items():
        if not expected:
            continue
        jsonl_path = os.path.join(data_dir, f"{table}.jsonl") if os.path.isdir(data_dir) else ""
        if jsonl_path and not os.path.isfile(jsonl_path):
            continue
        actual = len(tables.get(table) or [])
        if actual != int(expected):
            out["ok"] = False
            out["errors"].append(f"count {table}: {actual} vs {expected}")
    return out
