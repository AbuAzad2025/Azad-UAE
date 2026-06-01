"""
NULL column inventory audit — Development / Staging / pre-deploy QA only.

Read-only database audit (information_schema + COUNT NULLs). SELECT only — no
INSERT/UPDATE/DELETE. Uses DATABASE_URL from .env locally; does not embed or
print credentials or passwords.

Do NOT run against production without a full backup and explicit approval.
Do NOT commit JSON/CSV outputs from this script (gitignored under tools/qa/).

Run: python tools/qa/null_column_audit.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, text

TARGET_COLUMNS = frozenset({
    "tenant_id",
    "branch_id",
    "user_id",
    "created_by",
    "updated_by",
    "account_id",
    "product_id",
    "customer_id",
    "sale_id",
    "purchase_id",
    "warehouse_id",
    "category_id",
    "status",
    "source",
    "reference_type",
    "reference_id",
    "created_at",
    "updated_at",
})

CROSS_TENANT_GL_SQL = """
    SELECT COUNT(*) FROM gl_journal_lines jl
    JOIN gl_journal_entries je ON je.id = jl.entry_id
    JOIN gl_accounts ga ON ga.id = jl.account_id
    WHERE je.tenant_id IS DISTINCT FROM ga.tenant_id
"""

ACTIVE_INVOICE_SETTINGS_NULL_TENANT_SQL = """
    SELECT COUNT(*) FROM invoice_settings WHERE tenant_id IS NULL AND is_active = true
"""


def discover_models_with_tenant_id(models_dir: str) -> list[dict]:
    pattern_tablename = re.compile(r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]")
    pattern_tenant = re.compile(r"tenant_id\s*=\s*db\.Column")
    out: list[dict] = []
    for root, _dirs, files in os.walk(models_dir):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            try:
                src = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if "tenant_id" not in src or "db.Column" not in src:
                continue
            tablename = None
            for line in src.splitlines():
                m = pattern_tablename.search(line)
                if m:
                    tablename = m.group(1)
            if tablename and pattern_tenant.search(src):
                out.append({"model_file": os.path.relpath(path, models_dir), "table": tablename})
    return sorted(out, key=lambda x: x["table"])


def qident(*parts: str) -> str:
    return ".".join(f'"{p}"' for p in parts)


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2

    engine = create_engine(db_url)
    models_dir = os.path.join(os.path.dirname(__file__), "..", "..", "models")
    model_tenant_tables = {m["table"] for m in discover_models_with_tenant_id(models_dir)}

    cols_sql = text(
        """
        SELECT table_schema, table_name, column_name, is_nullable, column_default, data_type
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
          AND column_name = ANY(:cols)
        ORDER BY table_schema, table_name, column_name
        """
    )

    fk_sql = text(
        """
        SELECT
            tc.table_schema,
            tc.table_name,
            kcu.column_name,
            ccu.table_schema AS foreign_table_schema,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name,
            tc.constraint_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND kcu.column_name = ANY(:cols)
        ORDER BY tc.table_schema, tc.table_name, kcu.column_name
        """
    )

    idx_sql = text(
        """
        SELECT
            n.nspname AS table_schema,
            t.relname AS table_name,
            i.relname AS index_name,
            a.attname AS column_name,
            ix.indisunique AS is_unique,
            ix.indisprimary AS is_primary
        FROM pg_class t
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_index ix ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        WHERE a.attname = 'tenant_id'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY n.nspname, t.relname, i.relname
        """
    )

    existing_tables_sql = text(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        """
    )

    with engine.connect() as conn:
        col_rows = conn.execute(cols_sql, {"cols": list(TARGET_COLUMNS)}).mappings().all()
        existing = {
            (r["table_schema"], r["table_name"])
            for r in conn.execute(existing_tables_sql).mappings().all()
        }
        fk_rows = conn.execute(fk_sql, {"cols": list(TARGET_COLUMNS)}).mappings().all()
        idx_rows = conn.execute(idx_sql).mappings().all()

        fk_by_key: dict[tuple, list] = {}
        for r in fk_rows:
            key = (r["table_schema"], r["table_name"], r["column_name"])
            fk_by_key.setdefault(key, []).append(
                {
                    "constraint_name": r["constraint_name"],
                    "references": f'{r["foreign_table_schema"]}.{r["foreign_table_name"]}.{r["foreign_column_name"]}',
                }
            )

        full_inventory: list[dict] = []
        for r in col_rows:
            schema, table, column = r["table_schema"], r["table_name"], r["column_name"]
            null_count = None
            total_rows = None
            if (schema, table) in existing:
                count_sql = (
                    f"SELECT COUNT(*) AS null_count FROM {qident(schema, table)} "
                    f"WHERE {qident(column)} IS NULL"
                )
                null_count = conn.execute(text(count_sql)).scalar()
                total_sql = f"SELECT COUNT(*) FROM {qident(schema, table)}"
                total_rows = conn.execute(text(total_sql)).scalar()

            is_tenant_scoped = "tenant_id" in {
                c["column_name"]
                for c in col_rows
                if c["table_schema"] == schema and c["table_name"] == table
            }

            entry = {
                "table_schema": schema,
                "table": table,
                "column": column,
                "null_count": null_count,
                "total_rows": total_rows,
                "is_nullable": r["is_nullable"],
                "column_default": r["column_default"],
                "data_type": r["data_type"],
                "foreign_keys": fk_by_key.get((schema, table, column), []),
                "is_tenant_scoped_table": is_tenant_scoped,
                "in_sqlalchemy_models_tenant_id": table in model_tenant_tables,
            }
            full_inventory.append(entry)

        full_inventory.sort(
            key=lambda x: (
                -(x["null_count"] or 0),
                x["table_schema"],
                x["table"],
                x["column"],
            )
        )

        filtered = [
            e
            for e in full_inventory
            if (e["null_count"] or 0) > 0
            or (e["column"] == "tenant_id" and e["is_tenant_scoped_table"])
        ]

        tables_with_tenant_col = {
            (r["table_schema"], r["table_name"])
            for r in col_rows
            if r["column_name"] == "tenant_id"
        }

        tenant_id_model_checks: list[dict] = []
        for table in sorted(model_tenant_tables):
            schema = "public"
            if (schema, table) not in existing:
                tenant_id_model_checks.append(
                    {
                        "table": table,
                        "table_exists": False,
                        "tenant_id_column_in_db": False,
                        "null_count": None,
                        "total_rows": None,
                    }
                )
                continue
            if (schema, table) not in tables_with_tenant_col:
                tenant_id_model_checks.append(
                    {
                        "table": table,
                        "table_exists": True,
                        "tenant_id_column_in_db": False,
                        "null_count": None,
                        "total_rows": conn.execute(
                            text(f"SELECT COUNT(*) FROM {qident(schema, table)}")
                        ).scalar(),
                    }
                )
                continue
            nc = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {qident(schema, table)} WHERE {qident('tenant_id')} IS NULL"
                )
            ).scalar()
            tr = conn.execute(text(f"SELECT COUNT(*) FROM {qident(schema, table)}")).scalar()
            tenant_id_model_checks.append(
                {
                    "table": table,
                    "table_exists": True,
                    "tenant_id_column_in_db": True,
                    "null_count": nc,
                    "total_rows": tr,
                }
            )
        tenant_id_model_checks.sort(key=lambda x: (-(x["null_count"] or 0), x["table"]))

        cross_tenant_gl = conn.execute(text(CROSS_TENANT_GL_SQL)).scalar()
        active_invoice_null = conn.execute(text(ACTIVE_INVOICE_SETTINGS_NULL_TENANT_SQL)).scalar()

    tenant_id_indexes = [
        {
            "table_schema": r["table_schema"],
            "table": r["table_name"],
            "index_name": r["index_name"],
            "column": r["column_name"],
            "is_unique": bool(r["is_unique"]),
            "is_primary": bool(r["is_primary"]),
        }
        for r in idx_rows
    ]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_columns": sorted(TARGET_COLUMNS),
        "summary": {
            "column_pairs_scanned": len(full_inventory),
            "filtered_rows": len(filtered),
            "pairs_with_nulls": sum(1 for e in full_inventory if (e["null_count"] or 0) > 0),
            "sqlalchemy_models_with_tenant_id": len(model_tenant_tables),
        },
        "specific_checks": {
            "cross_tenant_gl_lines": cross_tenant_gl,
            "active_invoice_settings_tenant_null_active": active_invoice_null,
            "tenant_id_by_model_table": tenant_id_model_checks,
        },
        "tenant_id_indexes": tenant_id_indexes,
        "inventory_filtered": filtered,
        "full_null_inventory": full_inventory,
        "models_with_tenant_id": discover_models_with_tenant_id(models_dir),
    }

    out_path = os.path.join(
        os.path.dirname(__file__),
        f"null_column_audit_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print(json.dumps(report, indent=2, default=str))
    print(f"\nWrote: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
