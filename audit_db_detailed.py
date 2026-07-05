"""
Detailed DB audit focusing on the issues found.
Uses separate transactions to avoid abort cascades.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()

def run_query(sql_str, desc):
    print(f"\n{'='*60}")
    print(desc)
    print('='*60)
    try:
        with db.engine.connect() as conn:
            result = conn.execute(text(sql_str))
            rows = result.fetchall()
            if rows:
                print(f"  Found {len(rows)} records:")
                for row in rows[:10]:
                    print(f"    {dict(row)}")
                if len(rows) > 10:
                    print(f"    ... and {len(rows)-10} more")
            else:
                print("  OK - No issues found.")
            return rows
    except Exception as e:
        print(f"  ERROR: {e}")
        return []

with app.app_context():
    # 1. Users with NULL tenant_id — investigate
    run_query("""
        SELECT id, username, email, full_name, is_owner, is_active, role_id,
               created_at::text as created
        FROM users
        WHERE tenant_id IS NULL
        ORDER BY id
    """, "1. USERS WITH NULL tenant_id")

    # 2. Products with duplicate SKU
    run_query("""
        SELECT sku, tenant_id, COUNT(*) as cnt,
               string_agg(id::text, ', ') as ids
        FROM products
        GROUP BY sku, tenant_id
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
    """, "2. PRODUCTS WITH DUPLICATE SKU (per tenant)")

    # 3. Check if any of those duplicate SKUs belong to demo/seed data
    run_query("""
        SELECT p.id, p.sku, p.name, p.tenant_id, t.slug as tenant_slug
        FROM products p
        JOIN tenants t ON p.tenant_id = t.id
        WHERE p.sku IN (
            SELECT sku FROM products
            GROUP BY sku, tenant_id
            HAVING COUNT(*) > 1
        )
        ORDER BY p.sku, p.tenant_id
    """, "3. DUPLICATE SKU PRODUCT DETAILS")

    # 4. Demo/seed tenants
    run_query("""
        SELECT id, slug, name, is_active
        FROM tenants
        WHERE slug LIKE '%demo%' OR slug LIKE '%seed%' OR slug LIKE '%test%'
    """, "4. DEMO/SEED TENANTS")

    # 5. Demo/seed users
    run_query("""
        SELECT id, username, email, full_name, tenant_id, is_owner
        FROM users
        WHERE username LIKE '%seed%' OR email LIKE '%@example.com'
    """, "5. DEMO/SEED USERS")

    # 6. Check sales with no lines
    run_query("""
        SELECT s.id, s.sale_number, s.tenant_id, s.total_amount, s.status
        FROM sales s
        LEFT JOIN sale_lines sl ON s.id = sl.sale_id
        WHERE sl.id IS NULL
        ORDER BY s.id DESC
        LIMIT 20
    """, "6. SALES WITH NO LINES")

    # 7. Check purchases with no lines
    run_query("""
        SELECT p.id, p.purchase_number, p.tenant_id, p.total_amount, p.status
        FROM purchases p
        LEFT JOIN purchase_lines pl ON p.id = pl.purchase_id
        WHERE pl.id IS NULL
        ORDER BY p.id DESC
        LIMIT 20
    """, "7. PURCHASES WITH NO LINES")

    # 8. Check for negative/zero amounts
    run_query("""
        SELECT 'payments' as tbl, COUNT(*) as cnt FROM payments WHERE amount <= 0
        UNION ALL
        SELECT 'expenses', COUNT(*) FROM expenses WHERE amount <= 0
        UNION ALL
        SELECT 'sales', COUNT(*) FROM sales WHERE total_amount <= 0
        UNION ALL
        SELECT 'purchases', COUNT(*) FROM purchases WHERE total_amount <= 0
    """, "8. NEGATIVE/ZERO AMOUNTS")

    # 9. Check GL accounts for missing critical fields
    run_query("""
        SELECT id, code, name, account_type, tenant_id
        FROM gl_accounts
        WHERE code IS NULL OR name IS NULL OR account_type IS NULL
    """, "9. GL ACCOUNTS WITH NULL FIELDS")

    # 10. Inactive customers still referenced by active sales
    run_query("""
        SELECT s.id, s.sale_number, c.id as customer_id, c.name, c.is_active
        FROM sales s
        JOIN customers c ON s.customer_id = c.id
        WHERE c.is_active = 0 AND s.is_active = 1
        LIMIT 20
    """, "10. ACTIVE SALES REFERENCING INACTIVE CUSTOMERS")

print("\nDetailed audit complete.")
