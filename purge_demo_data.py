"""
Purge demo/seed data, keeping only 5 tenants and 5 seed users.
DRY RUN MODE — set DRY_RUN = False to execute.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from sqlalchemy import text

DRY_RUN = False  # LIVE DELETE

app = create_app()


def query_all(sql):
    with db.engine.connect() as conn:
        return conn.execute(text(sql)).fetchall()


def exec_sql(sql, params=None):
    with db.engine.begin() as conn:
        return conn.execute(text(sql), params or {})


with app.app_context():
    mode = "DRY RUN (preview only)" if DRY_RUN else "LIVE DELETE"
    print("=" * 70)
    print(f"DEMO/SEED DATA PURGE — {mode}")
    print("=" * 70)

    # ── 1. Identify demo/seed tenants ──
    print("\n[1] DEMO/SEED TENANTS")
    print("-" * 40)

    tenants = query_all("""
        SELECT id, slug, name, is_active, created_at::text
        FROM tenants
        WHERE slug LIKE '%demo%' OR slug LIKE '%seed%' OR slug LIKE '%test%'
        ORDER BY id ASC
    """)

    print(f"  Total demo/seed tenants: {len(tenants)}")
    for t in tenants:
        print(f"    id={t.id:>6}  slug={t.slug:35s}  active={t.is_active}")

    keep_tenants = tenants[:5]
    delete_tenants = tenants[5:]

    print(f"\n  KEEP (5 oldest):  ids = {', '.join([str(t.id) for t in keep_tenants])}")
    print(f"  DELETE ({len(delete_tenants)}): ids = {', '.join([str(t.id) for t in delete_tenants])}")

    # ── 2. Identify seed/demo users ──
    print("\n[2] DEMO/SEED USERS")
    print("-" * 40)

    users = query_all("""
        SELECT id, username, email, full_name, tenant_id, is_owner, created_at::text
        FROM users
        WHERE username LIKE '%seed%' OR email LIKE '%@example.com'
        ORDER BY id ASC
    """)

    print(f"  Total seed/demo users: {len(users)}")
    for u in users:
        print(f"    id={u.id:>6}  username={u.username:25s}  tenant={u.tenant_id}")

    keep_users = users[:5]
    delete_users = users[5:]

    print(f"\n  KEEP (5 oldest):  ids = {', '.join([str(u.id) for u in keep_users])}")
    print(f"  DELETE ({len(delete_users)}): ids = {', '.join([str(u.id) for u in delete_users])}")

    # ── 3. Cascade impact ──
    print("\n[3] CASCADE IMPACT (records linked to deleted tenants)")
    print("-" * 40)

    if delete_tenants:
        delete_ids = [str(t.id) for t in delete_tenants]
        id_str = ','.join(delete_ids)

        tables = [
            'users', 'products', 'product_categories', 'customers', 'suppliers',
            'sales', 'sale_lines', 'purchases', 'purchase_lines',
            'payments', 'expenses', 'expense_categories', 'cheques',
            'warehouses', 'branches', 'pos_sessions', 'invoice_settings',
            'gl_accounts', 'card_vault',
        ]

        total_related = 0
        for tbl in tables:
            try:
                with db.engine.connect() as conn:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {tbl} WHERE tenant_id IN ({id_str})"))
                    cnt = result.scalar() or 0
                    if cnt > 0:
                        print(f"    {tbl}: {cnt} records")
                        total_related += cnt
            except Exception:
                pass

        print(f"\n  TOTAL business records linked to deleted tenants: ~{total_related}")
    else:
        print("  No tenants to delete.")

    # ── 4. Execute or skip ──
    if DRY_RUN:
        print("\n" + "=" * 70)
        print("DRY RUN COMPLETE — No records were deleted.")
        print("=" * 70)
        print("\nTo execute deletions, set DRY_RUN = False in the script.")
    else:
        print("\n[4] EXECUTING DELETIONS")
        print("-" * 40)

        for t in delete_tenants:
            try:
                exec_sql("DELETE FROM tenants WHERE id = :id", {"id": t.id})
                print(f"  DELETED tenant id={t.id} ({t.slug})")
            except Exception as e:
                print(f"  ERROR: {e}")

        for u in delete_users:
            try:
                exec_sql("DELETE FROM users WHERE id = :id", {"id": u.id})
                print(f"  DELETED user id={u.id} ({u.username})")
            except Exception as e:
                print(f"  ERROR: {e}")

        # Verify
        print("\n[5] POST-PURGE VERIFICATION")
        print("-" * 40)

        remaining_tenants = query_all("""
            SELECT COUNT(*) as cnt FROM tenants
            WHERE slug LIKE '%demo%' OR slug LIKE '%seed%' OR slug LIKE '%test%'
        """)[0].cnt

        remaining_users = query_all("""
            SELECT COUNT(*) as cnt FROM users
            WHERE username LIKE '%seed%' OR email LIKE '%@example.com'
        """)[0].cnt

        print(f"  Remaining demo/seed tenants: {remaining_tenants}")
        print(f"  Remaining demo/seed users: {remaining_users}")

        print("\n" + "=" * 70)
        print("PURGE COMPLETE")
        print("=" * 70)
