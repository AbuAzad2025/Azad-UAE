"""
Database Cleanup Script
Fixes corrupt/bad seed data identified by audit.
Uses separate connections per operation to avoid transaction aborts.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()

def exec_sql(sql, params=None):
    """Execute SQL in a fresh connection."""
    with db.engine.begin() as conn:
        return conn.execute(text(sql), params or {})

with app.app_context():
    print("=" * 60)
    print("DATABASE CLEANUP")
    print("=" * 60)

    # ── 1. Fix NULL tenant_id users ──
    print("\n[1] Users with NULL tenant_id")
    print("-" * 40)

    result = exec_sql("""
        SELECT id, username, email, is_owner
        FROM users WHERE tenant_id IS NULL
        ORDER BY id
    """)
    rows = result.fetchall()

    legitimate = [r for r in rows if r.is_owner]
    bad = [r for r in rows if not r.is_owner]

    print(f"  Platform owners (legitimate): {len(legitimate)}")
    for r in legitimate:
        print(f"    KEEP: id={r.id}, username={r.username}")

    print(f"  Bad test users: {len(bad)}")
    for r in bad[:5]:
        print(f"    id={r.id}, username={r.username}")
    if len(bad) > 5:
        print(f"    ... and {len(bad)-5} more")

    if bad:
        bad_ids = [str(r.id) for r in bad]
        bad_id_str = ','.join(bad_ids)

        # Nullify user_id in referencing tables (only if column exists)
        nullify_attempts = [
            ("error_audit_logs", "user_id"),
            ("audit_logs", "user_id"),
            ("login_history", "user_id"),
        ]

        for tbl, col in nullify_attempts:
            try:
                exec_sql(f"UPDATE {tbl} SET {col} = NULL WHERE {col} IN ({bad_id_str})")
                print(f"  Nulled {col} in {tbl}")
            except Exception as e:
                # Column doesn't exist or other issue — check if it's a real error
                err = str(e).lower()
                if "does not exist" in err or "undefinedcolumn" in err:
                    print(f"  SKIP: {tbl}.{col} does not exist")
                else:
                    print(f"  ERROR nullifying {tbl}.{col}: {e}")

        # Try delete
        try:
            exec_sql(f"DELETE FROM users WHERE id IN ({bad_id_str})")
            print(f"  DONE: Deleted {len(bad)} bad users.")
        except Exception as e:
            err = str(e).lower()
            if "foreign key" in err:
                # Find which table still references them
                print(f"  DELETE BLOCKED by foreign key: {e}")
                print(f"  FALLBACK: Marking bad users as inactive...")
                exec_sql(f"""
                    UPDATE users
                    SET is_active = false,
                        username = username || '-INACTIVE-' || id::text
                    WHERE id IN ({bad_id_str})
                """)
                print(f"  DONE: Marked {len(bad)} bad users as inactive.")
            else:
                print(f"  ERROR: {e}")
    else:
        print("  OK - No bad users to clean.")

    # ── 2. Fix NULL SKU products ──
    print("\n[2] Products with NULL SKU")
    print("-" * 40)

    result = exec_sql("SELECT id, tenant_id, name FROM products WHERE sku IS NULL ORDER BY id")
    null_skus = result.fetchall()

    if null_skus:
        print(f"  Found {len(null_skus)} products with NULL SKU")
        fixed = 0
        for row in null_skus:
            new_sku = f"SKU-AUTO-{row.tenant_id}-{row.id:06d}"
            exec_sql("UPDATE products SET sku = :sku WHERE id = :id",
                     {"sku": new_sku, "id": row.id})
            fixed += 1
        print(f"  DONE: Assigned unique SKUs to {fixed} products.")
    else:
        print("  OK - No NULL SKUs found.")

    # ── 3. Deduplicate real duplicate SKUs ──
    print("\n[3] Real duplicate SKUs (non-NULL)")
    print("-" * 40)

    result = exec_sql("""
        SELECT sku, tenant_id, COUNT(*) as cnt
        FROM products WHERE sku IS NOT NULL
        GROUP BY sku, tenant_id HAVING COUNT(*) > 1
    """)
    dups = result.fetchall()

    if dups:
        print(f"  WARNING: {len(dups)} duplicate SKU groups found")
        for row in dups:
            ids_result = exec_sql("""
                SELECT id FROM products
                WHERE sku = :sku AND tenant_id = :tid
                ORDER BY id
            """, {"sku": row.sku, "tid": row.tenant_id})
            prod_ids = [r.id for r in ids_result.fetchall()]
            for pid in prod_ids[1:]:
                exec_sql("""
                    UPDATE products SET sku = sku || '-' || :pid::text
                    WHERE id = :pid
                """, {"pid": pid})
        print(f"  DONE: Deduplicated {sum(r.cnt for r in dups)} products.")
    else:
        print("  OK - No real duplicate SKUs found.")

    # ── 4. Sales with no lines ──
    print("\n[4] Sales with no lines")
    print("-" * 40)

    result = exec_sql("""
        SELECT s.id, s.sale_number, s.status, s.tenant_id
        FROM sales s
        LEFT JOIN sale_lines sl ON s.id = sl.sale_id
        WHERE sl.id IS NULL
    """)
    empty_sales = result.fetchall()

    if empty_sales:
        print(f"  Found {len(empty_sales)} sales with no lines:")
        for row in empty_sales:
            print(f"    - {row.sale_number} (id={row.id}, status={row.status})")
        print(f"  NOTE: Review these manually. Cancelled sales may be intentional.")
    else:
        print("  OK - No empty sales found.")

    # ── 5. Demo/seed data summary ──
    print("\n[5] Demo / Seed Data Summary")
    print("-" * 40)

    result = exec_sql("""
        SELECT COUNT(*) FROM tenants
        WHERE slug LIKE '%demo%' OR slug LIKE '%seed%' OR slug LIKE '%test%'
    """)
    demo_tenants = result.scalar() or 0

    result = exec_sql("""
        SELECT COUNT(*) FROM users
        WHERE username LIKE '%seed%' OR email LIKE '%@example.com'
    """)
    demo_users = result.scalar() or 0

    print(f"  Demo/seed tenants: {demo_tenants}")
    print(f"  Demo/seed users: {demo_users}")
    print(f"  (These remain in DB for user decision on purging)")

    print("\n" + "=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)
