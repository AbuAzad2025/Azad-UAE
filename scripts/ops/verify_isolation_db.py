#!/usr/bin/env python3
"""Fail if a seeded multi-tenant database breaks isolation or financial rules.

Run against the database produced by seed_clean_isolation_db.py::

    $env:DATABASE_URL = "postgresql+psycopg2://postgres@localhost:5433/azad_isolation_test"
    python scripts/ops/verify_isolation_db.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CHECKS = {
    "cross_tenant_gl_entry": """
        SELECT count(*) FROM gl_journal_lines l
        JOIN gl_journal_entries e ON e.id = l.entry_id WHERE l.tenant_id <> e.tenant_id
    """,
    "cross_tenant_gl_account": """
        SELECT count(*) FROM gl_journal_lines l
        JOIN gl_accounts a ON a.id = l.account_id WHERE l.tenant_id <> a.tenant_id
    """,
    "cross_tenant_sale_line": """
        SELECT count(*) FROM sale_lines sl
        JOIN sales s ON s.id = sl.sale_id WHERE sl.tenant_id <> s.tenant_id
    """,
    "cross_tenant_product_category": """
        SELECT count(*) FROM products p
        JOIN product_categories c ON c.id = p.category_id WHERE p.tenant_id <> c.tenant_id
    """,
    "duplicate_product_skus": "SELECT count(*) FROM (SELECT tenant_id, sku FROM products GROUP BY 1,2 HAVING count(*)>1) x",
    "duplicate_sale_numbers": "SELECT count(*) FROM (SELECT tenant_id, sale_number FROM sales GROUP BY 1,2 HAVING count(*)>1) x",
    "unbalanced_gl": """
        SELECT count(*) FROM (
            SELECT e.tenant_id, e.id, SUM(l.debit - l.credit) diff
            FROM gl_journal_entries e JOIN gl_journal_lines l ON l.entry_id = e.id
            GROUP BY 1,2 HAVING abs(SUM(l.debit - l.credit)) > 0.001
        ) x
    """,
    # A negative customer balance is legitimate (a debit/amount owed to us),
    # so it is validated by the document-based reconciler, not by a blanket
    # sign check here. Negative stock, by contrast, is never legitimate.
    "negative_stock": "SELECT count(*) FROM products WHERE current_stock < 0",
    # Every tenant must have its own independent staff; a missing tenant_user
    # means that tenant cannot log in at all.
    "tenants_without_users": """
        SELECT count(*) FROM tenants t
        WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.tenant_id = t.id)
    """,
    # A store-only package must not carry workshop roles, and a workshop must
    # not carry store roles — the package's feature flags are the contract.
    "store_role_in_storeless_tenant": """
        SELECT count(*) FROM users u
        JOIN roles r ON r.id = u.role_id
        JOIN tenants t ON t.id = u.tenant_id
        WHERE t.enable_store = false AND r.slug IN ('cashier', 'inventory')
    """,
    "maintenance_role_in_workshopless_tenant": """
        SELECT count(*) FROM users u
        JOIN roles r ON r.id = u.role_id
        JOIN tenants t ON t.id = u.tenant_id
        WHERE t.enable_maintenance = false AND r.slug LIKE 'maintenance_%'
    """,
}


def main() -> int:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is required")
    engine = create_engine(url, poolclass=NullPool)
    failures: list[str] = []
    try:
        with engine.connect() as conn:
            tenants = conn.execute(text("SELECT id, slug FROM tenants ORDER BY id")).all()
            print(f"tenants: {len(tenants)}")
            for tid, slug in tenants:
                products = conn.execute(text("SELECT count(*) FROM products WHERE tenant_id=:t"), {"t": tid}).scalar()
                accounts = conn.execute(
                    text("SELECT count(*) FROM gl_accounts WHERE tenant_id=:t"), {"t": tid}
                ).scalar()
                print(f"  {tid} {slug}: accounts={accounts} products={products}")
            for name, sql in CHECKS.items():
                value = conn.execute(text(sql)).scalar()
                print(f"  {name}: {value}")
                if value:
                    failures.append(f"{name}={value}")
            report = conn.execute(
                text("""
                SELECT t.slug, t.enable_maintenance,
                       (SELECT count(*) FROM maintenance_orders m WHERE m.tenant_id=t.id),
                       t.enable_partners,
                       (SELECT count(*) FROM partner_transactions p WHERE p.tenant_id=t.id),
                       t.enable_store,
                       (SELECT count(*) FROM store_product_prices p WHERE p.tenant_id=t.id)
                FROM tenants t ORDER BY t.id
            """)
            ).all()
            for slug, maint_on, maint, partners_on, partners, store_on, store in report:
                if (maint_on and not maint) or (not maint_on and maint):
                    failures.append(f"{slug}: maintenance flag/data disagree")
                if (partners_on and not partners) or (not partners_on and partners):
                    failures.append(f"{slug}: partner flag/data disagree")
                if (store_on and not store) or (not store_on and store):
                    failures.append(f"{slug}: store flag/data disagree")
    finally:
        engine.dispose()

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("OK: isolation, package enforcement and financial invariants all pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
