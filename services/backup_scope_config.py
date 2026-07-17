"""
Backup scope definitions — system / tenant / branch / store.

Scoped exports use SQL filters only (no cross-tenant rows).
"""

from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger(__name__)
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

SCOPE_SYSTEM = "system"
SCOPE_TENANT = "tenant"
SCOPE_BRANCH = "branch"
SCOPE_STORE = "store"

BACKUP_VERSION = 3

SCOPED_BACKUP_EXCLUDED_TABLES = frozenset(
    {
        "alembic_version",
        "roles",
        "permissions",
        "role_permissions",
        "user_permissions",
        "system_settings",
        "integration_settings",
        "audit_logs",
        "login_history",
        "webhook_logs",
    }
)

# Dependency-safe export order (parents before children).
TABLE_EXPORT_ORDER: Tuple[str, ...] = (
    "tenants",
    "roles",
    "branches",
    "users",
    "product_categories",
    "customers",
    "suppliers",
    "products",
    "product_partners",
    "warehouses",
    "gl_accounts",
    "invoice_settings",
    "tenant_stores",
    "shop_customer_accounts",
    "store_coupons",
    "employees",
    "sales",
    "sale_lines",
    "purchases",
    "purchase_lines",
    "payments",
    "expenses",
    "cheques",
    "stock_movements",
    "gl_journal_entries",
    "gl_journal_lines",
    "salary_advances",
    "payroll_transactions",
    "partner_commission_entries",
    "azad_platform_fees",
    "fixed_assets",
)

# (table, WHERE with bind params)
TENANT_TABLE_FILTERS: Tuple[Tuple[str, str], ...] = tuple(
    (t, "tenant_id = :tid") if t != "tenants" else (t, "id = :tid")
    for t in TABLE_EXPORT_ORDER
    if t not in SCOPED_BACKUP_EXCLUDED_TABLES
)
# users: exclude platform owners
TENANT_TABLE_FILTERS = tuple(
    (
        (t, w)
        if t != "users"
        else (
            "users",
            "tenant_id = :tid AND COALESCE(is_owner, false) = false",
        )
    )
    for t, w in TENANT_TABLE_FILTERS
)

# Child rows filtered via parent IDs (table, parent_table, parent_pk_col, child_fk_col)
CHILD_VIA_PARENT: Tuple[Tuple[str, str, str, str], ...] = (
    ("sale_lines", "sales", "id", "sale_id"),
    ("azad_platform_fees", "sales", "id", "sale_id"),
    ("purchase_lines", "purchases", "id", "purchase_id"),
    ("gl_journal_lines", "gl_journal_entries", "id", "entry_id"),
)

BRANCH_DIRECT_FILTERS: Tuple[Tuple[str, str], ...] = (
    ("tenants", "id = :tid"),
    ("branches", "id = :bid AND tenant_id = :tid"),
    (
        "users",
        "tenant_id = :tid AND branch_id = :bid AND COALESCE(is_owner, false) = false",
    ),
    ("warehouses", "tenant_id = :tid AND branch_id = :bid"),
    ("sales", "tenant_id = :tid AND branch_id = :bid"),
    ("purchases", "tenant_id = :tid AND branch_id = :bid"),
    ("payments", "tenant_id = :tid AND branch_id = :bid"),
    ("expenses", "tenant_id = :tid AND branch_id = :bid"),
    ("cheques", "tenant_id = :tid AND branch_id = :bid"),
    ("gl_journal_entries", "tenant_id = :tid AND branch_id = :bid"),
    ("stock_movements", "tenant_id = :tid AND branch_id = :bid"),
    ("employees", "tenant_id = :tid AND branch_id = :bid"),
    ("salary_advances", "tenant_id = :tid AND branch_id = :bid"),
    ("payroll_transactions", "tenant_id = :tid AND branch_id = :bid"),
    ("partner_commission_entries", "tenant_id = :tid AND branch_id = :bid"),
    ("fixed_assets", "tenant_id = :tid AND branch_id = :bid"),
)

BRANCH_TENANT_MASTERS: Tuple[Tuple[str, str], ...] = (
    ("product_categories", "tenant_id = :tid"),
    ("products", "tenant_id = :tid"),
    ("product_partners", "tenant_id = :tid"),
    ("customers", "tenant_id = :tid"),
    ("suppliers", "tenant_id = :tid"),
    ("gl_accounts", "tenant_id = :tid"),
    ("invoice_settings", "tenant_id = :tid"),
)

STORE_TABLE_FILTERS: Tuple[Tuple[str, str], ...] = (
    ("tenants", "id = :tid"),
    (
        "tenant_stores",
        "id = :sid AND tenant_id = :tid",
    ),
    (
        "warehouses",
        "id IN (SELECT warehouse_id FROM tenant_stores WHERE id = :sid AND tenant_id = :tid)",
    ),
    ("shop_customer_accounts", "tenant_id = :tid"),
    ("store_coupons", "tenant_id = :tid"),
    ("products", "tenant_id = :tid"),
    ("product_categories", "tenant_id = :tid"),
    ("customers", "tenant_id = :tid"),
    ("invoice_settings", "tenant_id = :tid"),
)

SLUG_SAFE_RE = re.compile(r"[^a-z0-9_-]+", re.IGNORECASE)


def sanitize_slug(slug: Optional[str], fallback: str = "tenant") -> str:
    if not slug:
        return fallback[:32]
    cleaned = SLUG_SAFE_RE.sub("_", str(slug).strip().lower()).strip("_")
    return (cleaned or fallback)[:48]


def table_exists(conn: Connection, table: str) -> bool:
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


def column_metadata(conn: Connection, table: str) -> List[Dict[str, Any]]:
    """Return [{name, data_type, is_nullable, default}] for a target table."""
    from sqlalchemy import text

    if not table_exists(conn, table):
        return []
    rows = conn.execute(
        text(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t "
            "ORDER BY ordinal_position"
        ),
        {"t": table},
    ).fetchall()
    return [
        {"name": r[0], "data_type": r[1], "is_nullable": r[2], "default": r[3]}
        for r in rows
    ]


def _default_for_type(data_type: Optional[str]) -> Any:
    """Typed fallback for a NOT NULL column that has no DB default."""
    dt = (data_type or "").lower()
    if "boolean" in dt:
        return False
    if any(
        k in dt
        for k in ("int", "numeric", "decimal", "money", "real", "double", "float")
    ):
        return 0
    if "json" in dt:
        return {}
    if any(k in dt for k in ("timestamp", "date", "time")):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
    if "uuid" in dt:
        import uuid

        return str(uuid.uuid4())
    return ""


def normalize_row_to_target(
    conn: Connection, table: str, row: Dict[str, Any]
) -> Dict[str, Any]:
    """Make a backup row safe to INSERT into the *current* target schema.

    Handles schema drift in both directions:
      * drops keys that no longer exist in the target table (avoids
        ProgrammingError on unknown columns), and
      * fills NOT NULL target columns that have no DB default and are absent
        from the row with a typed default (avoids NotNullViolation).
    Columns already present in the row are passed through untouched.
    """
    cols = column_metadata(conn, table)
    if not cols:
        return row
    names = {c["name"] for c in cols}
    out = {k: v for k, v in row.items() if k in names}
    for c in cols:
        if c["name"] in out:
            continue
        if c["is_nullable"] == "NO" and (
            c["default"] is None or str(c["default"]).upper() == "NULL"
        ):
            out[c["name"]] = _default_for_type(c["data_type"])
    return out


def _serialize_row(item: Dict[str, Any]) -> Dict[str, Any]:
    for key, val in list(item.items()):
        if hasattr(val, "isoformat"):
            item[key] = val.isoformat()
        elif isinstance(val, (bytes, bytearray)):
            item[key] = val.hex()
    return item


def _fetch_rows(
    conn, table: str, where_sql: str, params: Dict[str, Any]
) -> List[Dict[str, Any]]:
    from sqlalchemy import text

    result = conn.execute(text(f'SELECT * FROM "{table}" WHERE {where_sql}'), params)
    rows = []
    for row in result.fetchall():
        rows.append(_serialize_row(dict(zip(result.keys(), row))))
    return rows


def _fetch_child_rows(
    conn,
    child_table: str,
    parent_table: str,
    parent_pk: str,
    child_fk: str,
    parent_ids: List[Any],
) -> List[Dict[str, Any]]:
    if not parent_ids:
        return []
    from sqlalchemy import text

    if not table_exists(conn, child_table):
        return []
    placeholders = ", ".join(f":p{i}" for i in range(len(parent_ids)))
    params = {f"p{i}": pid for i, pid in enumerate(parent_ids)}
    sql = f'SELECT * FROM "{child_table}" WHERE "{child_fk}" IN ({placeholders})'
    result = conn.execute(text(sql), params)
    return [_serialize_row(dict(zip(result.keys(), row))) for row in result.fetchall()]


def _merge_product_customer_dependencies(
    conn,
    tables_out: Dict[str, List[Dict[str, Any]]],
    row_counts: Dict[str, int],
    included: List[str],
    tenant_id: int,
    unresolved: List[str],
) -> None:
    """Ensure customers referenced by products/product_partners are in the export."""
    from sqlalchemy import text

    if not table_exists(conn, "customers"):
        return
    needed: Set[int] = set()
    for product in tables_out.get("products") or []:
        mid = product.get("merchant_customer_id")
        if mid is not None:
            needed.add(int(mid or 0))
    for partner in tables_out.get("product_partners") or []:
        pid = partner.get("partner_customer_id")
        if pid is not None:
            needed.add(int(pid or 0))
    if not needed:
        return
    existing = {
        int(row["id"])
        for row in (tables_out.get("customers") or [])
        if row.get("id") is not None
    }
    missing = sorted(needed - existing)
    if not missing:
        return
    placeholders = ", ".join(f":c{i}" for i in range(len(missing)))
    params: Dict[str, Any] = {"tid": tenant_id}
    params.update({f"c{i}": cid for i, cid in enumerate(missing)})
    try:
        result = conn.execute(
            text(
                f"SELECT * FROM customers WHERE tenant_id = :tid AND id IN ({placeholders})"
            ),
            params,
        )
        extra = [
            _serialize_row(dict(zip(result.keys(), row))) for row in result.fetchall()
        ]
        found_ids = {int(r["id"]) for r in extra if r.get("id") is not None}
        if extra:
            tables_out.setdefault("customers", []).extend(extra)
            row_counts["customers"] = len(tables_out["customers"])
            if "customers" not in included:
                included.append("customers")
        for mid in missing:
            if mid not in found_ids:
                unresolved.append(f"customers:missing_merchant_ref_id={mid}")
    except Exception as exc:
        unresolved.append(f"customers:merge_refs_error_{type(exc).__name__}")
        try:
            conn.rollback()
        except Exception as rb_exc:
            logger.debug("rollback after merge_refs: %s", rb_exc)


def export_scoped_database(
    conn,
    scope: str,
    *,
    tenant_id: int,
    branch_id: Optional[int] = None,
    store_id: Optional[int] = None,
) -> Tuple[
    Dict[str, List[Dict[str, Any]]], Dict[str, int], List[str], List[str], List[str]
]:
    """
    Export scoped rows.
    Returns tables, row_counts, included, skipped, unresolved_references.
    """
    included: List[str] = []
    skipped: List[str] = []
    tables_out: Dict[str, List[Dict[str, Any]]] = {}
    row_counts: Dict[str, int] = {}
    unresolved: List[str] = []

    params: Dict[str, Any] = {"tid": tenant_id}
    if branch_id is not None:
        params["bid"] = branch_id
    if store_id is not None:
        params["sid"] = store_id

    if scope == SCOPE_TENANT:
        specs = list(TENANT_TABLE_FILTERS)
        child_specs = CHILD_VIA_PARENT
    elif scope == SCOPE_BRANCH:
        if not branch_id:
            return tables_out, row_counts, included, ["branch_id required"], []
        specs = list(BRANCH_DIRECT_FILTERS) + list(BRANCH_TENANT_MASTERS)
        child_specs = CHILD_VIA_PARENT
    elif scope == SCOPE_STORE:
        if not store_id:
            return tables_out, row_counts, included, ["store_id required"], []
        specs = list(STORE_TABLE_FILTERS) + [
            (
                "sales",
                "tenant_id = :tid AND warehouse_id IN "
                "(SELECT warehouse_id FROM tenant_stores WHERE id = :sid AND tenant_id = :tid)",
            ),
            (
                "stock_movements",
                "tenant_id = :tid AND warehouse_id IN "
                "(SELECT warehouse_id FROM tenant_stores WHERE id = :sid AND tenant_id = :tid)",
            ),
        ]
        child_specs = CHILD_VIA_PARENT
    else:
        return tables_out, row_counts, included, [f"unknown scope {scope}"], []

    direct_tables = {t for t, _ in specs}
    for table, where_sql in specs:
        if table in SCOPED_BACKUP_EXCLUDED_TABLES:
            skipped.append(f"{table}:excluded_policy")
            continue
        if not table_exists(conn, table):
            skipped.append(f"{table}:missing")
            continue
        try:
            rows = _fetch_rows(conn, table, where_sql, params)
            tables_out[table] = rows
            row_counts[table] = len(rows)
            included.append(table)
        except Exception as exc:
            skipped.append(f"{table}:error_{type(exc).__name__}")
            try:
                conn.rollback()
            except Exception as rb_exc:
                logger.debug("rollback after export %s: %s", table, rb_exc)

    for child_table, parent_table, parent_pk, child_fk in child_specs:
        if child_table in direct_tables:
            continue
        if child_table in SCOPED_BACKUP_EXCLUDED_TABLES:
            continue
        if not table_exists(conn, child_table):
            skipped.append(f"{child_table}:missing")
            continue
        parent_rows = tables_out.get(parent_table) or []
        parent_ids = [
            r.get(parent_pk) for r in parent_rows if r.get(parent_pk) is not None
        ]
        try:
            rows = _fetch_child_rows(
                conn, child_table, parent_table, parent_pk, child_fk, parent_ids
            )
            tables_out[child_table] = rows
            row_counts[child_table] = len(rows)
            if rows:
                included.append(child_table)
            else:
                skipped.append(f"{child_table}:empty")
        except Exception as exc:
            skipped.append(f"{child_table}:error_{type(exc).__name__}")
            try:
                conn.rollback()
            except Exception as rb_exc:
                logger.debug("rollback after child %s: %s", child_table, rb_exc)

    # Branch/store validation
    if scope == SCOPE_BRANCH:
        br = tables_out.get("branches") or []
        if len(br) != 1:
            unresolved.append(f"branches:expected_1_got_{len(br)}")
    if scope == SCOPE_STORE:
        st = tables_out.get("tenant_stores") or []
        if len(st) != 1:
            unresolved.append(f"tenant_stores:expected_1_got_{len(st)}")

    if scope in (SCOPE_TENANT, SCOPE_BRANCH, SCOPE_STORE):
        _merge_product_customer_dependencies(
            conn, tables_out, row_counts, included, tenant_id, unresolved
        )

    if scope in (SCOPE_TENANT, SCOPE_BRANCH, SCOPE_STORE) and table_exists(
        conn, "roles"
    ):
        role_ids = {
            u.get("role_id")
            for u in (tables_out.get("users") or [])
            if u.get("role_id") is not None
        }
        if role_ids:
            from sqlalchemy import text

            placeholders = ", ".join(f":r{i}" for i in range(len(role_ids)))
            params = {f"r{i}": rid for i, rid in enumerate(role_ids)}
            try:
                result = conn.execute(
                    text(f"SELECT * FROM roles WHERE id IN ({placeholders})"),
                    params,
                )
                rows = [
                    _serialize_row(dict(zip(result.keys(), row)))
                    for row in result.fetchall()
                ]
                if rows:
                    tables_out["roles"] = rows
                    row_counts["roles"] = len(rows)
                    if "roles" not in included:
                        included.append("roles")
            except Exception as role_exc:
                logger.debug("roles export: %s", role_exc)
                try:
                    conn.rollback()
                except Exception as rb_exc:
                    logger.debug("rollback after roles: %s", rb_exc)

    return tables_out, row_counts, included, skipped, unresolved


def export_tenant_database(
    conn,
    tenant_id: int,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, int], List[str], List[str]]:
    """Backward-compatible tenant export (no unresolved list)."""
    tables, counts, included, skipped, _ = export_scoped_database(
        conn, SCOPE_TENANT, tenant_id=tenant_id
    )
    return tables, counts, included, skipped


def write_data_directory(
    data_dir: str,
    tables: Dict[str, List[Dict[str, Any]]],
    *,
    scope: str,
    tenant_id: int,
    branch_id: Optional[int] = None,
    store_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Write data/*.jsonl + schema_meta.json; return metadata."""
    os.makedirs(data_dir, exist_ok=True)
    order = [t for t in TABLE_EXPORT_ORDER if t in tables]
    for t in tables:
        if t not in order:
            order.append(t)

    meta: Dict[str, Any] = {
        "backup_version": BACKUP_VERSION,
        "scope": scope,
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "store_id": store_id,
        "table_order": order,
        "tables": {},
    }
    for table in order:
        rows = tables.get(table) or []
        path = os.path.join(data_dir, f"{table}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        meta["tables"][table] = {"row_count": len(rows), "file": f"{table}.jsonl"}
    meta_path = os.path.join(data_dir, "schema_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return meta


def read_data_directory(
    data_dir: str,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    meta_path = os.path.join(data_dir, "schema_meta.json")
    meta: Dict[str, Any] = {}
    if os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    order = meta.get("table_order") or []
    tables: Dict[str, List[Dict[str, Any]]] = {}
    if not order:
        for fn in sorted(os.listdir(data_dir)):
            if fn.endswith(".jsonl"):
                order.append(fn[:-6])
    for table in order:
        path = os.path.join(data_dir, f"{table}.jsonl")
        if not os.path.isfile(path):
            continue
        rows: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        tables[table] = rows
    return tables, meta


def _path_from_urlish(value: str, base_dir: str) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    v = value.strip().replace("\\", "/")
    if v.startswith("http://") or v.startswith("https://"):
        return None
    if v.startswith("/static/"):
        v = v[len("/static/") :]
    if v.startswith("static/"):
        v = v[len("static/") :]
    if v.startswith("uploads/"):
        rel = v
    elif v.startswith("/uploads/"):
        rel = v.lstrip("/")
    else:
        rel = os.path.join("uploads", v.lstrip("/"))
    full = os.path.normpath(os.path.join(base_dir, rel))
    uploads_root = os.path.normpath(os.path.join(base_dir, "uploads"))
    if not full.startswith(uploads_root + os.sep) and full != uploads_root:
        return None
    if os.path.isfile(full):
        return full
    return None


def collect_scoped_upload_paths(
    conn,
    scope: str,
    tenant_id: int,
    base_dir: str,
    *,
    branch_id: Optional[int] = None,
    store_id: Optional[int] = None,
) -> Tuple[List[str], List[str]]:
    """Resolve upload files for scoped backup."""
    from sqlalchemy import text as sa_text

    resolved: Set[str] = set()
    unresolved: List[str] = []

    def add_column(table: str, column: str, where: str, bind: Dict[str, Any]) -> None:
        if not table_exists(conn, table):
            return
        cols = {
            r[0]
            for r in conn.execute(
                sa_text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:t"
                ),
                {"t": table},
            )
        }
        if column not in cols:
            return
        try:
            q = sa_text(
                f'SELECT "{column}" AS p FROM "{table}" WHERE {where} '
                f'AND "{column}" IS NOT NULL AND TRIM("{column}"::text) <> \'\''
            )
            for row in conn.execute(q, bind):
                p = _path_from_urlish(row[0], base_dir)
                if p:
                    resolved.add(p)
                elif row[0]:
                    unresolved.append(f"{table}.{column}:{str(row[0])[:120]}")
        except Exception as path_exc:
            logger.debug("collect upload path %s.%s: %s", table, column, path_exc)
            try:
                conn.rollback()
            except Exception as rb_exc:
                logger.debug("rollback after upload path: %s", rb_exc)

    bind: Dict[str, Any] = {"tid": tenant_id}
    if branch_id is not None:
        bind["bid"] = branch_id
    if store_id is not None:
        bind["sid"] = store_id

    if scope in (SCOPE_TENANT, SCOPE_BRANCH, SCOPE_STORE):
        add_column("products", "image_url", "tenant_id = :tid", bind)
        if table_exists(conn, "invoice_settings"):
            add_column("invoice_settings", "logo_path", "tenant_id = :tid", bind)
            add_column(
                "invoice_settings", "watermark_image_path", "tenant_id = :tid", bind
            )
        if table_exists(conn, "tenant_stores"):
            w = "tenant_id = :tid"
            if store_id:
                w = "id = :sid AND tenant_id = :tid"
            add_column("tenant_stores", "logo_path", w, bind)

    return sorted(resolved), unresolved


def collect_tenant_upload_paths(
    conn,
    tenant_id: int,
    base_dir: str,
) -> Tuple[List[str], List[str]]:
    return collect_scoped_upload_paths(conn, SCOPE_TENANT, tenant_id, base_dir)


def build_tenant_uploads_archive(
    file_paths: List[str], dest_path: str, base_dir: str
) -> Dict[str, Any]:
    import tarfile

    packed = 0
    with tarfile.open(dest_path, "w:gz") as tar:
        for full in file_paths:
            if not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, base_dir).replace("\\", "/")
            tar.add(full, arcname=rel)
            packed += 1
    return {"files_packed": packed, "files_requested": len(file_paths)}


def scope_filter_summary(
    scope: str,
    tenant_id: int,
    branch_id: Optional[int] = None,
    store_id: Optional[int] = None,
) -> str:
    if scope == SCOPE_TENANT:
        return f"tenant_id={tenant_id} only; users exclude global/platform owners"
    if scope == SCOPE_BRANCH:
        return f"tenant_id={tenant_id} branch_id={branch_id}; masters tenant-wide"
    if scope == SCOPE_STORE:
        return f"tenant_id={tenant_id} store_id={store_id} (tenant_stores)"
    return scope
