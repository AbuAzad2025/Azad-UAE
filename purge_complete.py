"""
Complete purge — zero demo/seed/test data remaining.
Handles chained FKs including sale_lines→sales→users.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()


def exec_sql(sql, params=None):
    with db.engine.begin() as conn:
        return conn.execute(text(sql), params or {})


def query_scalar(sql):
    with db.engine.connect() as conn:
        return conn.execute(text(sql)).scalar() or 0


def query_all(sql):
    with db.engine.connect() as conn:
        return conn.execute(text(sql)).fetchall()


with app.app_context():
    print("=" * 70)
    print("COMPLETE PURGE — ZERO DEMO/SEED/TEST REMAINING")
    print("=" * 70)

    # ── 0. Identify all seed/test/demo users (excluding platform owner id=1) ──
    print("\n[0] IDENTIFY SEED/TEST/DEMO USERS")
    print("-" * 40)

    users = query_all("""
        SELECT id, username, email, tenant_id
        FROM users
        WHERE (
            username LIKE '%seed%'
            OR username LIKE '%testuser%'
            OR username LIKE '%test-%'
            OR email LIKE '%@example.com'
        )
        AND id != 1
        ORDER BY id
    """)
    user_ids = [str(u.id) for u in users]
    user_id_str = ','.join(user_ids) if user_ids else 'NULL'

    print(f"  Found {len(users)} seed/test/demo users")
    for u in users[:10]:
        print(f"    id={u.id} {u.username}")
    if len(users) > 10:
        print(f"    ... and {len(users)-10} more")

    if not users:
        print("  No seed/test/demo users found.")

    # ── 1. Delete referencing records in CORRECT dependency order ──
    print("\n[1] DELETE REFERENCING RECORDS (dependency order)")
    print("-" * 40)

    if users:
        # 1a. sale_lines (child of sales)
        try:
            cnt = query_scalar(f"""
                SELECT COUNT(*) FROM sale_lines
                WHERE sale_id IN (SELECT id FROM sales WHERE seller_id IN ({user_id_str}))
            """)
            if cnt > 0:
                exec_sql(f"""
                    DELETE FROM sale_lines
                    WHERE sale_id IN (SELECT id FROM sales WHERE seller_id IN ({user_id_str}))
                """)
                print(f"  sale_lines: deleted {cnt} records")
            else:
                print(f"  sale_lines: 0 records")
        except Exception as e:
            print(f"  sale_lines: {e}")

        # 1b. payments linked to those sales
        try:
            cnt = query_scalar(f"""
                SELECT COUNT(*) FROM payments
                WHERE sale_id IN (SELECT id FROM sales WHERE seller_id IN ({user_id_str}))
            """)
            if cnt > 0:
                exec_sql(f"""
                    DELETE FROM payments
                    WHERE sale_id IN (SELECT id FROM sales WHERE seller_id IN ({user_id_str}))
                """)
                print(f"  payments (via sales): deleted {cnt} records")
            else:
                print(f"  payments (via sales): 0 records")
        except Exception as e:
            print(f"  payments (via sales): {e}")

        # 1c. sales by these sellers
        try:
            cnt = query_scalar(f"SELECT COUNT(*) FROM sales WHERE seller_id IN ({user_id_str})")
            if cnt > 0:
                exec_sql(f"DELETE FROM sales WHERE seller_id IN ({user_id_str})")
                print(f"  sales: deleted {cnt} records")
            else:
                print(f"  sales: 0 records")
        except Exception as e:
            print(f"  sales: {e}")

        # 1d. payments directly linked to these users
        try:
            cnt = query_scalar(f"SELECT COUNT(*) FROM payments WHERE user_id IN ({user_id_str})")
            if cnt > 0:
                exec_sql(f"DELETE FROM payments WHERE user_id IN ({user_id_str})")
                print(f"  payments (direct): deleted {cnt} records")
            else:
                print(f"  payments (direct): 0 records")
        except Exception as e:
            print(f"  payments (direct): {e}")

        # 1e. Other tables
        others = [
            ("error_audit_logs", "user_id"),
            ("audit_logs", "user_id"),
            ("login_history", "user_id"),
            ("security_alerts", "user_id"),
            ("pos_sessions", "user_id"),
        ]
        for tbl, col in others:
            try:
                cnt = query_scalar(f"SELECT COUNT(*) FROM {tbl} WHERE {col} IN ({user_id_str})")
                if cnt > 0:
                    exec_sql(f"DELETE FROM {tbl} WHERE {col} IN ({user_id_str})")
                    print(f"  {tbl}: deleted {cnt} records")
                else:
                    print(f"  {tbl}: 0 records")
            except Exception as e:
                err = str(e).lower()
                if "does not exist" in err or "undefinedcolumn" in err:
                    print(f"  SKIP: {tbl}.{col} not found")
                else:
                    print(f"  {tbl}: {e}")

    # ── 2. Delete all seed/test/demo users ──
    print("\n[2] DELETE SEED/TEST/DEMO USERS")
    print("-" * 40)

    if users:
        success = 0
        for u in users:
            try:
                exec_sql("DELETE FROM users WHERE id = :id", {"id": u.id})
                print(f"    DELETED user id={u.id} {u.username}")
                success += 1
            except Exception as e:
                print(f"    ERROR user {u.id}: {e}")
        print(f"  DONE: Deleted {success}/{len(users)} users.")
    else:
        print("  Nothing to delete.")

    # ── 3. Delete ALL remaining demo/seed/test tenants ──
    print("\n[3] DELETE ALL DEMO/SEED/TEST TENANTS")
    print("-" * 40)

    tenants = query_all("""
        SELECT id, slug FROM tenants
        WHERE slug LIKE '%demo%' OR slug LIKE '%seed%' OR slug LIKE '%test%'
        ORDER BY id
    """)
    print(f"  Found {len(tenants)} remaining demo/seed/test tenants")
    for t in tenants:
        try:
            exec_sql("DELETE FROM tenants WHERE id = :id", {"id": t.id})
            print(f"    DELETED tenant id={t.id} ({t.slug})")
        except Exception as e:
            print(f"    ERROR tenant {t.id}: {e}")
    print(f"  DONE: Deleted {len(tenants)} tenants.")

    # ── 4. Purge orphaned audit/history records (user_id IS NULL) ──
    print("\n[4] PURGE ORPHANED AUDIT/HISTORY (user_id IS NULL)")
    print("-" * 40)

    audit_tables = [
        ("error_audit_logs", "user_id"),
        ("audit_logs", "user_id"),
        ("login_history", "user_id"),
        ("activity_monitor_logs", "user_id"),
    ]

    total_purged = 0
    for tbl, col in audit_tables:
        try:
            cnt_before = query_scalar(f"SELECT COUNT(*) FROM {tbl} WHERE {col} IS NULL")
            if cnt_before > 0:
                exec_sql(f"DELETE FROM {tbl} WHERE {col} IS NULL")
                print(f"  {tbl}: purged {cnt_before} orphaned records")
                total_purged += cnt_before
            else:
                print(f"  {tbl}: 0 orphaned records")
        except Exception as e:
            err = str(e).lower()
            if "does not exist" in err or "undefinedcolumn" in err:
                print(f"  SKIP: {tbl} not found")
            else:
                print(f"  ERROR {tbl}: {e}")

    print(f"  TOTAL purged: {total_purged} orphaned records")

    # ── 5. Final verification ──
    print("\n[5] FINAL VERIFICATION")
    print("-" * 40)

    rem_tenants = query_scalar("""
        SELECT COUNT(*) FROM tenants
        WHERE slug LIKE '%demo%' OR slug LIKE '%seed%' OR slug LIKE '%test%'
    """)

    rem_seed_users = query_scalar("""
        SELECT COUNT(*) FROM users
        WHERE (
            username LIKE '%seed%'
            OR username LIKE '%testuser%'
            OR username LIKE '%test-%'
            OR email LIKE '%@example.com'
        )
        AND id != 1
    """)

    rem_orphan_err = query_scalar("SELECT COUNT(*) FROM error_audit_logs WHERE user_id IS NULL")
    rem_orphan_aud = query_scalar("SELECT COUNT(*) FROM audit_logs WHERE user_id IS NULL")
    rem_orphan_log = query_scalar("SELECT COUNT(*) FROM login_history WHERE user_id IS NULL")
    rem_orphan_total = rem_orphan_err + rem_orphan_aud + rem_orphan_log

    print(f"  Remaining demo/seed/test tenants: {rem_tenants}")
    print(f"  Remaining seed/test/demo users:   {rem_seed_users}")
    print(f"  Remaining orphaned audit records: {rem_orphan_total}")

    print("\n" + "=" * 70)
    if rem_tenants == 0 and rem_seed_users == 0 and rem_orphan_total == 0:
        print("ALL CLEAR — Zero demo/seed/test data remaining.")
    else:
        print("WARNING — Some data remains. Review above.")
    print("=" * 70)
