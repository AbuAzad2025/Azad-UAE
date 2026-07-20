"""
Scoped JSONL restore — tenant / branch / store to a NEW database only.
"""

from __future__ import annotations

import logging
import os
import tarfile
import tempfile
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from services.backup_scope_config import (
    SCOPE_BRANCH,
    SCOPE_TENANT,
    TABLE_EXPORT_ORDER,
    normalize_row_to_target,
    read_data_directory,
)
from utils.safe_sql import delete_where_query, insert_query, select_where_query

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)

RESTORE_CONFIRM = "RESTORE CONFIRM"
REMAP_CONFIRM = "REMAP CONFIRM"


def _required_confirmation(remap: bool) -> str:
    return REMAP_CONFIRM if remap else RESTORE_CONFIRM


def extract_scoped_bundle(archive_path: str, work_dir: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    with tarfile.open(archive_path, "r:gz") as tar:
        names = set(tar.getnames())
        if "manifest.json" not in names:
            raise RuntimeError("missing manifest.json")
        for member in ("manifest.json", "uploads.tar.gz", "checksums.sha256"):
            if member in names:
                tar.extract(member, work_dir, filter="data")
                out[member] = os.path.join(work_dir, member)
        if "data/schema_meta.json" in names or any(n.startswith("data/") for n in names):
            for n in names:
                if n.startswith("data/"):
                    tar.extract(n, work_dir, filter="data")
        elif "tenant_export.json" in names:
            tar.extract("tenant_export.json", work_dir, filter="data")
            out["legacy_tenant_export"] = os.path.join(work_dir, "tenant_export.json")
    manifest_path = os.path.join(work_dir, "manifest.json")
    import json

    with open(manifest_path, "r", encoding="utf-8") as f:
        out["manifest"] = json.load(f)
    data_dir = os.path.join(work_dir, "data")
    if os.path.isdir(data_dir):
        tables, meta = read_data_directory(data_dir)
        out["tables"] = tables
        out["data_meta"] = meta
    elif out.get("legacy_tenant_export"):
        with open(out["legacy_tenant_export"], "r", encoding="utf-8") as f:
            doc = json.load(f)
        out["tables"] = doc.get("tables") or {}
    return out


def _build_id_remap(
    tables: Dict[str, List[Dict[str, Any]]],
    *,
    new_tenant_id: int,
    new_branch_id: Optional[int] = None,
    new_store_id: Optional[int] = None,
) -> Dict[str, Dict[Any, Any]]:
    """Map old PK -> new PK per table when restoring as new tenant/branch/store."""
    id_maps: Dict[str, Dict[Any, Any]] = {}
    tenants = tables.get("tenants") or []
    if tenants:
        tenants[0].get("id")

    for table in TABLE_EXPORT_ORDER:
        rows = tables.get(table) or []
        if not rows:
            continue
        pk_col = "id"
        id_maps[table] = {}
        for row in rows:
            old_id = row.get(pk_col)
            if old_id is None:
                continue
            if table == "tenants":
                id_maps[table][old_id] = new_tenant_id
            elif table == "branches" and new_branch_id is not None:
                id_maps[table][old_id] = new_branch_id
            elif table == "tenant_stores" and new_store_id is not None:
                id_maps[table][old_id] = new_store_id
            else:
                # allocate new synthetic ids above max existing
                id_maps[table][old_id] = old_id  # placeholder, reassigned below

    # Assign new IDs for non-root tables
    for table in TABLE_EXPORT_ORDER:
        rows = tables.get(table) or []
        if not rows or table in ("tenants",):
            continue
        if table == "branches" and new_branch_id is not None:
            for row in rows:
                oid = row.get("id")
                if oid is not None:
                    id_maps.setdefault(table, {})[oid] = new_branch_id
            continue
        if table == "tenant_stores" and new_store_id is not None:
            for row in rows:
                oid = row.get("id")
                if oid is not None:
                    id_maps.setdefault(table, {})[oid] = new_store_id
            continue
        max_existing = max((r.get("id") or 0 for r in rows), default=0)
        base = max(100000, max_existing + 1000)
        for i, row in enumerate(rows):
            oid = row.get("id")
            if oid is None:
                continue
            id_maps.setdefault(table, {})[oid] = base + i + 1

    return id_maps


def _apply_row_remap(
    row: Dict[str, Any],
    table: str,
    id_maps: Dict[str, Dict[Any, Any]],
    *,
    new_tenant_id: int,
    old_tenant_id: Optional[int],
    scope: str,
    remap: bool = False,
    new_branch_id: Optional[int] = None,
    new_store_id: Optional[int] = None,
) -> Dict[str, Any]:
    out = dict(row)
    if "tenant_id" in out and old_tenant_id is not None:
        out["tenant_id"] = new_tenant_id
    if table in id_maps and out.get("id") is not None:
        out["id"] = id_maps[table].get(out["id"], out["id"])
    fk_cols = {
        "role_id": "roles",
        "branch_id": "branches",
        "warehouse_id": "warehouses",
        "customer_id": "customers",
        "merchant_customer_id": "customers",
        "partner_customer_id": "customers",
        "supplier_id": "suppliers",
        "product_id": "products",
        "category_id": "product_categories",
        "sale_id": "sales",
        "purchase_id": "purchases",
        "entry_id": "gl_journal_entries",
        "account_id": "gl_accounts",
        "employee_id": "employees",
        "seller_id": "users",
        "user_id": "users",
    }
    for col, parent in fk_cols.items():
        if col not in out or out[col] is None:
            continue
        parent_map = id_maps.get(parent) or {}
        if out[col] in parent_map:
            out[col] = parent_map[out[col]]
    if scope == SCOPE_BRANCH and new_branch_id is not None and "branch_id" in out:
        out["branch_id"] = new_branch_id
    if table == "tenants" and remap and "slug" in out:
        base = str(out.get("slug") or "tenant")[:80]
        out["slug"] = f"{base}_r{new_tenant_id}"[:100]
    if table == "tenant_stores" and remap and "store_slug" in out:
        base = str(out.get("store_slug") or "store")[:80]
        out["store_slug"] = f"{base}_r{new_store_id or new_tenant_id}"[:100]
    return out


def _delete_tenant_scoped_data(conn: Connection, tenant_id: int, branch_id: Optional[int] = None) -> None:
    from sqlalchemy import text

    from services.backup_scope_config import TABLE_EXPORT_ORDER, table_exists

    reverse = list(reversed(TABLE_EXPORT_ORDER))
    for table in reverse:
        if table == "roles":
            continue
        if not table_exists(conn, table):
            continue
        cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:t"
                ),
                {"t": table},
            )
        }
        try:
            with conn.begin_nested():
                if table == "tenants":
                    conn.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant_id})
                elif branch_id is not None and "branch_id" in cols:
                    conn.execute(delete_where_query(conn, table, "branch_id", branch_id))
                elif "tenant_id" in cols:
                    conn.execute(delete_where_query(conn, table, "tenant_id", tenant_id))
        except Exception as exc:
            logger.debug("delete scoped %s: %s", table, exc)


def _run_import(
    conn: Connection,
    tables: Dict[str, List[Dict[str, Any]]],
    *,
    scope: str,
    source_tenant_id: int,
    target_tenant_id: Optional[int],
    id_maps: Dict[str, Dict[Any, Any]],
    remap: bool,
    new_branch_id: Optional[int],
    new_store_id: Optional[int],
    source_branch_id: Optional[int],
    result: Dict[str, Any],
) -> None:
    """Execute the scoped delete + insert loop against ``conn`` (no commit)."""
    tgt_tid = target_tenant_id if target_tenant_id is not None else source_tenant_id
    order = [t for t in TABLE_EXPORT_ORDER if t in tables]
    for t in tables:
        if t not in order:
            order.append(t)

    if not remap:
        _delete_tenant_scoped_data(
            conn,
            tgt_tid,
            branch_id=source_branch_id if scope == SCOPE_BRANCH else None,
        )

    for table in order:
        rows = tables.get(table) or []
        if not rows:
            continue
        inserted = 0
        table_errors = 0
        for row in rows:
            mapped = _apply_row_remap(
                row,
                table,
                id_maps,
                new_tenant_id=tgt_tid,
                old_tenant_id=source_tenant_id,
                scope=scope,
                remap=remap,
                new_branch_id=new_branch_id,
                new_store_id=new_store_id,
            )
            mapped = normalize_row_to_target(conn, table, mapped)
            try:
                with conn.begin_nested():
                    conn.execute(
                        insert_query(
                            conn,
                            table,
                            mapped,
                            on_conflict_do_nothing=(table == "roles"),
                        )
                    )
                inserted += 1
            except Exception as e:
                table_errors += 1
                if table_errors <= 2:
                    result["errors"].append(f"{table}: {type(e).__name__}")
                logger.debug("insert %s failed: %s", table, e)
        result["inserted"][table] = inserted


def import_scoped_tables(
    target_url: str,
    tables: Dict[str, List[Dict[str, Any]]],
    *,
    scope: str,
    source_tenant_id: int,
    target_tenant_id: Optional[int] = None,
    remap: bool = False,
    new_branch_id: Optional[int] = None,
    new_store_id: Optional[int] = None,
    source_branch_id: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    from sqlalchemy import create_engine

    result: Dict[str, Any] = {"ok": True, "inserted": {}, "errors": []}
    tgt_tid = target_tenant_id if target_tenant_id is not None else source_tenant_id

    id_maps: Dict[str, Dict[Any, Any]] = {}
    if remap:
        id_maps = _build_id_remap(
            tables,
            new_tenant_id=tgt_tid,
            new_branch_id=new_branch_id,
            new_store_id=new_store_id,
        )
        id_maps.setdefault("tenants", {})[(tables.get("tenants") or [{}])[0].get("id", source_tenant_id)] = tgt_tid

    engine = create_engine(target_url)
    if dry_run:
        # Simulate the full restore inside a transaction, then roll back so
        # nothing is persisted. Returns the affected-row summary instead.
        with engine.connect() as conn:
            trans = conn.begin()
            _run_import(
                conn,
                tables,
                scope=scope,
                source_tenant_id=source_tenant_id,
                target_tenant_id=target_tenant_id,
                id_maps=id_maps,
                remap=remap,
                new_branch_id=new_branch_id,
                new_store_id=new_store_id,
                source_branch_id=source_branch_id,
                result=result,
            )
            trans.rollback()
        result["dry_run"] = True
        expected_products = len(tables.get("products") or [])
        result["products_expected"] = expected_products
        result["products_inserted"] = result["inserted"].get("products", 0)
        result["rows_skipped"] = max(0, expected_products - result["products_inserted"])
        if any(result["inserted"].get(t, 0) == 0 and tables.get(t) for t in ("tenants", "roles", "branches")):
            result["ok"] = False
        return result

    with engine.begin() as conn:
        _run_import(
            conn,
            tables,
            scope=scope,
            source_tenant_id=source_tenant_id,
            target_tenant_id=target_tenant_id,
            id_maps=id_maps,
            remap=remap,
            new_branch_id=new_branch_id,
            new_store_id=new_store_id,
            source_branch_id=source_branch_id,
            result=result,
        )

    expected_products = len(tables.get("products") or [])
    inserted_products = result["inserted"].get("products", 0)
    result["products_expected"] = expected_products
    result["products_inserted"] = inserted_products
    result["rows_skipped"] = max(0, expected_products - inserted_products)

    fatal_tables = ("tenants", "roles", "branches")
    if any(result["inserted"].get(t, 0) == 0 and tables.get(t) for t in fatal_tables):
        result["ok"] = False
    if expected_products and inserted_products < expected_products:
        result["ok"] = False
        result["errors"].append(f"products: expected {expected_products} inserted {inserted_products}")
    elif result["errors"]:
        result["ok"] = sum(result["inserted"].values()) > 0
    return result


def _table_has_column(conn, table: str, column: str) -> bool:
    from sqlalchemy import text

    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def verify_scoped_restore(
    target_url: str,
    manifest: Dict[str, Any],
    *,
    expected_tenant_id: int,
    scope: str,
) -> Dict[str, Any]:
    from sqlalchemy import create_engine, text

    from services.backup_scope_config import table_exists

    out: Dict[str, Any] = {"ok": True, "errors": [], "warnings": [], "counts": {}}
    row_counts = manifest.get("row_counts_per_table") or {}
    core_tables = (
        "tenants",
        "branches",
        "customers",
        "products",
        "product_partners",
        "sales",
        "gl_journal_entries",
    )
    optional_low = ("sale_lines", "purchase_lines")
    engine = create_engine(target_url)
    with engine.connect() as conn:
        tid = expected_tenant_id
        for table, expected in row_counts.items():
            if not expected or not table_exists(conn, table):
                continue
            try:
                with conn.begin_nested():
                    if table == "tenants":
                        actual = conn.execute(select_where_query(conn, table, "id", tid)).scalar()
                    elif table_exists(
                        conn,
                        table,
                    ) and _table_has_column(conn, table, "tenant_id"):
                        actual = conn.execute(select_where_query(conn, table, "tenant_id", tid)).scalar()
                    else:
                        continue
                    out["counts"][table] = int(actual or 0)
                    exp_n, act_n = int(expected), int(actual or 0)
                    if table in core_tables and act_n < exp_n:
                        out["ok"] = False
                        out["errors"].append(f"{table}: expected>={exp_n} got {act_n}")
                    elif table not in optional_low and act_n < max(1, int(exp_n * 0.85)):
                        out["warnings"].append(f"{table}: expected>={exp_n} got {act_n}")
            except Exception as exc:
                logger.debug("verify count %s: %s", table, exc)
        try:
            with conn.begin_nested():
                cross = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM sales s WHERE s.tenant_id = :tid "
                        "AND NOT EXISTS (SELECT 1 FROM tenants t WHERE t.id = s.tenant_id)"
                    ),
                    {"tid": tid},
                ).scalar()
                if cross:
                    out["ok"] = False
                    out["errors"].append("orphan tenant FK on sales")
        except Exception as exc:
            logger.debug("verify cross-tenant sales: %s", exc)
        if table_exists(conn, "products"):
            try:
                with conn.begin_nested():
                    orphan_merchant = conn.execute(
                        text("""
                            SELECT COUNT(*) FROM products p
                            WHERE p.tenant_id = :tid
                              AND p.merchant_customer_id IS NOT NULL
                              AND NOT EXISTS (
                                SELECT 1 FROM customers c
                                WHERE c.id = p.merchant_customer_id AND c.tenant_id = :tid
                              )
                            """),
                        {"tid": tid},
                    ).scalar()
                    if int(orphan_merchant or 0) > 0:
                        out["ok"] = False
                        out["errors"].append(f"orphan products.merchant_customer_id count={orphan_merchant}")
            except Exception as exc:
                logger.debug("verify orphan merchant_customer_id: %s", exc)
    return out


def restore_scoped_backup(
    backup_service_cls,
    filename: str,
    target_database_url: str,
    *,
    confirmation: str = "",
    remap: bool = False,
    target_tenant_id: Optional[int] = None,
    new_branch_id: Optional[int] = None,
    new_store_id: Optional[int] = None,
    restore_uploads: bool = False,
    uploads_dest_root: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Restore scoped backup to target DB (never current DATABASE_URL)."""
    outcome: Dict[str, Any] = {"ok": False, "errors": [], "warnings": []}
    required = _required_confirmation(remap)
    if confirmation.strip() != required:
        outcome["errors"].append(f"Typed confirmation {required!r} required")
        return outcome

    current_url = os.environ.get("DATABASE_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI") or ""
    if backup_service_cls._urls_same_database(current_url, target_database_url):
        outcome["errors"].append("Target database is the same as current DATABASE_URL — use a new database")
        return outcome

    verify = backup_service_cls.verify_backup(filename)
    if not verify.get("valid"):
        outcome["errors"].append("backup verification failed")
        outcome["details"] = verify
        return outcome

    manifest = verify.get("manifest") or {}
    scope = manifest.get("backup_scope") or SCOPE_TENANT
    if scope == "system":
        outcome["errors"].append("Use restore_backup_to_target_db for system scope")
        return outcome

    path = backup_service_cls._backup_path(filename)
    if not path:
        outcome["errors"].append("invalid filename")
        return outcome

    from services.backup_scoped_engine import ensure_target_schema

    ok_schema, schema_err = ensure_target_schema(target_database_url)
    if not ok_schema:
        outcome["errors"].append(f"schema upgrade: {schema_err}")
        return outcome

    work = tempfile.mkdtemp(prefix="azad_scoped_restore_")
    try:
        bundle = extract_scoped_bundle(path, work)
        tables = bundle.get("tables") or {}
        src_tid = int(manifest.get("tenant_id") or 0)
        src_bid = manifest.get("branch_id")
        tgt_tid = target_tenant_id if remap else src_tid
        if remap and not target_tenant_id:
            from sqlalchemy import create_engine, text

            with create_engine(target_database_url).connect() as conn:
                max_id = conn.execute(text("SELECT COALESCE(MAX(id),0) FROM tenants")).scalar()
            tgt_tid = int(max_id or 0) + 1

        import_result = import_scoped_tables(
            target_database_url,
            tables,
            scope=scope,
            source_tenant_id=src_tid,
            target_tenant_id=tgt_tid,
            remap=remap,
            new_branch_id=new_branch_id,
            new_store_id=new_store_id,
            source_branch_id=int(src_bid or 0) if src_bid is not None else None,
            dry_run=dry_run,
        )
        outcome["import"] = import_result
        outcome["products_expected"] = import_result.get("products_expected")
        outcome["products_inserted"] = import_result.get("products_inserted")
        outcome["rows_skipped"] = import_result.get("rows_skipped")
        outcome["affected_rows"] = import_result.get("inserted")
        if not import_result.get("ok"):
            outcome["errors"].extend(import_result.get("errors") or ["import failed"])
            return outcome

        if dry_run:
            # No changes were persisted (transaction was rolled back).
            outcome["dry_run"] = True
            outcome["ok"] = not outcome["errors"]
            outcome["target_tenant_id"] = tgt_tid
            outcome["scope"] = scope
            outcome["note"] = (
                "dry-run: restoration simulated and rolled back — no changes persisted to the target database"
            )
            return outcome

        if tgt_tid is not None:
            scoped_verify = verify_scoped_restore(
                target_database_url,
                manifest,
                expected_tenant_id=tgt_tid,
                scope=scope,
            )
            outcome["scoped_verify"] = scoped_verify
            if not scoped_verify.get("ok"):
                outcome["errors"].extend(scoped_verify.get("errors") or [])
            elif scoped_verify.get("warnings"):
                outcome["warnings"].extend(scoped_verify["warnings"])

        if restore_uploads and bundle.get("uploads.tar.gz"):
            dest = uploads_dest_root or backup_service_cls._BASEDIR
            import tarfile as tf

            with tf.open(bundle["uploads.tar.gz"], "r:gz") as utar:
                utar.extractall(dest, filter="data")
            outcome["warnings"].append("uploads extracted")

        outcome["ok"] = not outcome["errors"]
        outcome["target_tenant_id"] = tgt_tid
        outcome["scope"] = scope
        return outcome
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)
