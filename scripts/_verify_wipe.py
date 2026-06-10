import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()

TABLES = [
    'tenants','users','roles','permissions','roles_permissions',
    'customers','suppliers','products','product_categories',
    'sales','sale_lines','purchases','purchase_lines',
    'payments','receipts','warehouses','branches',
    'stock_movements','product_serials','expenses',
    'product_returns','product_partners','partner_commission_entries',
    'gl_journal_entries','gl_journal_lines','gl_accounts',
    'audit_logs','login_histories','security_alerts',
    'shop_customer_accounts','shop_wishlists','shop_reviews',
    'store_coupons','tenant_stores','currencies',
    'ai_memories','ai_interactions','ai_expertise',
]

with app.app_context():
    print("=" * 60)
    print("DATABASE WIPE VERIFICATION")
    print("=" * 60)
    total = 0
    for t in TABLES:
        try:
            r = db.session.execute(text(f"SELECT COUNT(*) FROM {t}"))
            c = r.scalar()
            total += c
            status = "EMPTY" if c == 0 else f"HAS {c} ROWS"
            print(f"  {t:40s} | {status}")
        except Exception as e:
            print(f"  {t:40s} | TABLE NOT FOUND")
    print("=" * 60)
    print(f"TOTAL ROWS ACROSS ALL TABLES: {total}")
    print("=" * 60)
