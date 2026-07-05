"""
Database Integrity Audit
Checks for corrupt, orphaned, inconsistent, or bad seed data.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()

results = []
warnings = []
critical = []

def log(msg, level='info'):
    print(msg)
    if level == 'warning':
        warnings.append(msg)
    elif level == 'critical':
        critical.append(msg)

with app.app_context():
    # ── 1. Orphaned Records (Foreign Keys to Missing Parents) ──
    log("\n" + "=" * 60)
    log("1. ORPHANED RECORDS (Foreign Keys to Missing Parents)")
    log("=" * 60)

    orphan_checks = [
        ("users", "tenant_id", "tenants", "id"),
        ("users", "role_id", "roles", "id"),
        ("products", "tenant_id", "tenants", "id"),
        ("products", "category_id", "product_categories", "id"),
        ("customers", "tenant_id", "tenants", "id"),
        ("suppliers", "tenant_id", "tenants", "id"),
        ("sales", "tenant_id", "tenants", "id"),
        ("sales", "customer_id", "customers", "id"),
        ("sales", "seller_id", "users", "id"),
        ("sales", "warehouse_id", "warehouses", "id"),
        ("sale_lines", "tenant_id", "tenants", "id"),
        ("sale_lines", "sale_id", "sales", "id"),
        ("sale_lines", "product_id", "products", "id"),
        ("purchases", "tenant_id", "tenants", "id"),
        ("purchases", "supplier_id", "suppliers", "id"),
        ("purchase_lines", "tenant_id", "tenants", "id"),
        ("purchase_lines", "purchase_id", "purchases", "id"),
        ("payments", "tenant_id", "tenants", "id"),
        ("payments", "customer_id", "customers", "id"),
        ("payments", "supplier_id", "suppliers", "id"),
        ("expenses", "tenant_id", "tenants", "id"),
        ("expenses", "category_id", "expense_categories", "id"),
        ("cheques", "tenant_id", "tenants", "id"),
        ("cheques", "customer_id", "customers", "id"),
        ("cheques", "supplier_id", "suppliers", "id"),
        ("warehouses", "tenant_id", "tenants", "id"),
        ("expense_categories", "tenant_id", "tenants", "id"),
        ("product_categories", "tenant_id", "tenants", "id"),
        ("branches", "tenant_id", "tenants", "id"),
        ("gl_accounts", "tenant_id", "tenants", "id"),
        ("pos_sessions", "tenant_id", "tenants", "id"),
        ("pos_sessions", "user_id", "users", "id"),
        ("invoice_settings", "tenant_id", "tenants", "id"),
        ("card_vault", "tenant_id", "tenants", "id"),
        ("card_vault", "customer_id", "customers", "id"),
    ]

    total_orphans = 0
    for table, fk_col, parent_table, parent_col in orphan_checks:
        try:
            sql = text(f"""
                SELECT COUNT(*) FROM {table} t
                LEFT JOIN {parent_table} p ON t.{fk_col} = p.{parent_col}
                WHERE t.{fk_col} IS NOT NULL AND p.{parent_col} IS NULL
            """)
            count = db.session.execute(sql).scalar() or 0
            if count > 0:
                log(f"  CRITICAL: {table}.{fk_col} → {count} orphaned records (missing {parent_table})", 'critical')
                total_orphans += count
        except Exception as e:
            # Table might not exist
            pass

    if total_orphans == 0:
        log("  OK - No orphaned foreign key references found.")
    else:
        log(f"\n  TOTAL ORPHANS: {total_orphans}", 'critical')

    # ── 2. Records with NULL tenant_id ──
    log("\n" + "=" * 60)
    log("2. RECORDS WITH NULL tenant_id")
    log("=" * 60)

    tenant_tables = [
        'users', 'products', 'customers', 'suppliers', 'sales', 'purchases',
        'payments', 'expenses', 'cheques', 'warehouses', 'branches',
        'product_categories', 'expense_categories', 'gl_accounts',
        'pos_sessions', 'invoice_settings', 'card_vault',
    ]

    total_null_tenant = 0
    for table in tenant_tables:
        try:
            sql = text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL")
            count = db.session.execute(sql).scalar() or 0
            if count > 0:
                log(f"  WARNING: {table} has {count} records with NULL tenant_id", 'warning')
                total_null_tenant += count
        except Exception:
            pass

    if total_null_tenant == 0:
        log("  OK - All records have tenant_id.")
    else:
        log(f"\n  TOTAL NULL tenant_id: {total_null_tenant}", 'warning')

    # ── 3. Duplicate Critical Records ──
    log("\n" + "=" * 60)
    log("3. DUPLICATES")
    log("=" * 60)

    dup_checks = [
        ("tenants", "slug"),
        ("users", "username"),
        ("users", "email"),
        ("roles", "slug"),
        ("products", "sku"),
        ("warehouses", ["tenant_id", "name"]),
        ("product_categories", ["tenant_id", "name"]),
        ("expense_categories", ["tenant_id", "slug"]),
        ("gl_accounts", ["tenant_id", "code"]),
    ]

    total_dups = 0
    for table, cols in dup_checks:
        try:
            if isinstance(cols, str):
                col_str = cols
                group_by = cols
            else:
                col_str = ', '.join(cols)
                group_by = col_str

            sql = text(f"""
                SELECT {col_str}, COUNT(*) as cnt
                FROM {table}
                GROUP BY {group_by}
                HAVING COUNT(*) > 1
            """)
            rows = db.session.execute(sql).fetchall()
            if rows:
                log(f"  WARNING: {table} has {len(rows)} duplicate groups on ({col_str})", 'warning')
                for row in rows:
                    log(f"    - {dict(row)}")
                total_dups += len(rows)
        except Exception as e:
            pass

    if total_dups == 0:
        log("  OK - No duplicate critical records found.")
    else:
        log(f"\n  TOTAL DUPLICATE GROUPS: {total_dups}", 'warning')

    # ── 4. Sales with Zero/No Lines ──
    log("\n" + "=" * 60)
    log("4. SALES WITH ZERO OR NO LINES")
    log("=" * 60)

    try:
        sql = text("""
            SELECT s.id, s.sale_number, s.total_amount
            FROM sales s
            LEFT JOIN sale_lines sl ON s.id = sl.sale_id
            WHERE sl.id IS NULL AND s.is_active = 1
        """)
        empty_sales = db.session.execute(sql).fetchall()
        if empty_sales:
            log(f"  WARNING: {len(empty_sales)} active sales have no lines", 'warning')
            for row in empty_sales[:5]:
                log(f"    - Sale #{row.sale_number} (id={row.id}), total={row.total_amount}")
        else:
            log("  OK - All active sales have at least one line.")
    except Exception as e:
        log(f"  SKIP: Could not check sales lines: {e}")

    # ── 5. Sales with Mismatched Totals ──
    log("\n" + "=" * 60)
    log("5. SALES WITH MISMATCHED TOTALS")
    log("=" * 60)

    try:
        sql = text("""
            SELECT s.id, s.sale_number, s.total_amount,
                   SUM(sl.line_total) as calculated_total
            FROM sales s
            JOIN sale_lines sl ON s.id = sl.sale_id
            WHERE s.is_active = 1
            GROUP BY s.id, s.sale_number, s.total_amount
            HAVING ABS(s.total_amount - SUM(sl.line_total)) > 0.01
        """)
        mismatched = db.session.execute(sql).fetchall()
        if mismatched:
            log(f"  WARNING: {len(mismatched)} sales have mismatched totals", 'warning')
            for row in mismatched[:5]:
                log(f"    - Sale #{row.sale_number} (id={row.id}): stored={row.total_amount}, calculated={row.calculated_total}")
        else:
            log("  OK - All sale totals match their line sums.")
    except Exception as e:
        log(f"  SKIP: Could not check sale totals: {e}")

    # ── 6. Purchases with Zero/No Lines ──
    log("\n" + "=" * 60)
    log("6. PURCHASES WITH ZERO OR NO LINES")
    log("=" * 60)

    try:
        sql = text("""
            SELECT p.id, p.purchase_number, p.total_amount
            FROM purchases p
            LEFT JOIN purchase_lines pl ON p.id = pl.purchase_id
            WHERE pl.id IS NULL AND p.is_active = 1
        """)
        empty_purchases = db.session.execute(sql).fetchall()
        if empty_purchases:
            log(f"  WARNING: {len(empty_purchases)} active purchases have no lines", 'warning')
            for row in empty_purchases[:5]:
                log(f"    - Purchase #{row.purchase_number} (id={row.id}), total={row.total_amount}")
        else:
            log("  OK - All active purchases have at least one line.")
    except Exception as e:
        log(f"  SKIP: Could not check purchase lines: {e}")

    # ── 7. Payments with Zero Amount ──
    log("\n" + "=" * 60)
    log("7. PAYMENTS WITH ZERO OR NEGATIVE AMOUNTS")
    log("=" * 60)

    try:
        sql = text("SELECT COUNT(*) FROM payments WHERE amount <= 0 OR amount IS NULL")
        count = db.session.execute(sql).scalar() or 0
        if count > 0:
            log(f"  WARNING: {count} payments have zero or negative amount", 'warning')
        else:
            log("  OK - All payments have positive amounts.")
    except Exception as e:
        log(f"  SKIP: Could not check payments: {e}")

    # ── 8. Expenses with Zero Amount ──
    log("\n" + "=" * 60)
    log("8. EXPENSES WITH ZERO OR NEGATIVE AMOUNTS")
    log("=" * 60)

    try:
        sql = text("SELECT COUNT(*) FROM expenses WHERE amount <= 0 OR amount IS NULL")
        count = db.session.execute(sql).scalar() or 0
        if count > 0:
            log(f"  WARNING: {count} expenses have zero or negative amount", 'warning')
        else:
            log("  OK - All expenses have positive amounts.")
    except Exception as e:
        log(f"  SKIP: Could not check expenses: {e}")

    # ── 9. Users Without Roles ──
    log("\n" + "=" * 60)
    log("9. USERS WITHOUT VALID ROLES")
    log("=" * 60)

    try:
        sql = text("""
            SELECT u.id, u.username, u.email
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            WHERE u.role_id IS NULL OR r.id IS NULL
        """)
        users_no_role = db.session.execute(sql).fetchall()
        if users_no_role:
            log(f"  WARNING: {len(users_no_role)} users have no valid role", 'warning')
            for row in users_no_role[:5]:
                log(f"    - {row.username} ({row.email})")
        else:
            log("  OK - All users have valid roles.")
    except Exception as e:
        log(f"  SKIP: Could not check user roles: {e}")

    # ── 10. Demo/Seed Data Check ──
    log("\n" + "=" * 60)
    log("10. DEMO / SEED DATA IDENTIFICATION")
    log("=" * 60)

    try:
        sql = text("SELECT id, slug, name FROM tenants WHERE slug LIKE '%demo%' OR slug LIKE '%seed%' OR slug LIKE '%test%'")
        demo_tenants = db.session.execute(sql).fetchall()
        if demo_tenants:
            log(f"  INFO: {len(demo_tenants)} demo/seed tenants found:")
            for row in demo_tenants:
                log(f"    - id={row.id}, slug={row.slug}, name={row.name}")

                # Count related records
                counts = []
                for tbl in ['users', 'products', 'customers', 'suppliers', 'sales', 'purchases', 'payments', 'expenses', 'cheques']:
                    try:
                        cnt = db.session.execute(text(f"SELECT COUNT(*) FROM {tbl} WHERE tenant_id = {row.id}")).scalar() or 0
                        if cnt > 0:
                            counts.append(f"{tbl}={cnt}")
                    except:
                        pass
                if counts:
                    log(f"      Related: {', '.join(counts)}")
        else:
            log("  OK - No demo/seed tenants found.")
    except Exception as e:
        log(f"  SKIP: Could not check demo tenants: {e}")

    try:
        sql = text("SELECT COUNT(*) FROM users WHERE username LIKE '%seed%' OR email LIKE '%@example.com'")
        seed_users = db.session.execute(sql).scalar() or 0
        if seed_users > 0:
            log(f"  INFO: {seed_users} seed/demo users found (username LIKE 'seed%' or email LIKE '@example.com')")
        else:
            log("  OK - No seed/demo users found.")
    except Exception as e:
        log(f"  SKIP: Could not check seed users: {e}")

    # ── 11. Inactive but Referenced Records ──
    log("\n" + "=" * 60)
    log("11. INACTIVE RECORDS STILL REFERENCED")
    log("=" * 60)

    try:
        sql = text("""
            SELECT COUNT(*) FROM sales s
            JOIN customers c ON s.customer_id = c.id
            WHERE c.is_active = 0
        """)
        count = db.session.execute(sql).scalar() or 0
        if count > 0:
            log(f"  WARNING: {count} sales reference inactive customers", 'warning')
        else:
            log("  OK - No sales reference inactive customers.")
    except Exception as e:
        log(f"  SKIP: {e}")

    try:
        sql = text("""
            SELECT COUNT(*) FROM sales s
            JOIN products p ON s.id IN (SELECT sale_id FROM sale_lines WHERE product_id = p.id)
            WHERE p.is_active = 0
        """)
        count = db.session.execute(sql).scalar() or 0
        if count > 0:
            log(f"  WARNING: {count} sales reference inactive products", 'warning')
        else:
            log("  OK - No sales reference inactive products.")
    except Exception as e:
        log(f"  SKIP: {e}")

    # ── 12. GL Account Integrity ──
    log("\n" + "=" * 60)
    log("12. GL ACCOUNT INTEGRITY")
    log("=" * 60)

    try:
        sql = text("""
            SELECT COUNT(*) FROM gl_accounts
            WHERE code IS NULL OR name IS NULL OR account_type IS NULL
        """)
        count = db.session.execute(sql).scalar() or 0
        if count > 0:
            log(f"  WARNING: {count} GL accounts have NULL critical fields", 'warning')
        else:
            log("  OK - All GL accounts have required fields.")
    except Exception as e:
        log(f"  SKIP: Could not check GL accounts: {e}")

    # ── SUMMARY ──
    log("\n" + "=" * 60)
    log("SUMMARY")
    log("=" * 60)
    log(f"  Critical issues: {len(critical)}")
    log(f"  Warnings: {len(warnings)}")

    if critical:
        log("\n  CRITICAL ISSUES (require immediate action):")
        for c in critical:
            log(f"    {c}")

    if warnings:
        log("\n  WARNINGS (should be reviewed):")
        for w in warnings:
            log(f"    {w}")

    if not critical and not warnings:
        log("\n  ALL CLEAR - No integrity issues found.")

print("\nAudit complete.")
