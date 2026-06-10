import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SKIP_SYSTEM_INTEGRITY'] = '1'
from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()

TABLES = [
    'tenants','users','roles','permissions',
    'customers','suppliers','products','product_categories',
    'sales','purchases','payments','warehouses','branches',
    'stock_movements','product_serials','expenses',
    'gl_journal_entries','gl_accounts',
]

with app.app_context():
    print("=" * 60)
    print("CURRENT DATABASE STATE")
    print("=" * 60)
    for t in TABLES:
        try:
            r = db.session.execute(text(f"SELECT COUNT(*) FROM {t}"))
            c = r.scalar()
            if c > 0:
                print(f"  {t:40s} | {c} rows")
        except Exception:
            pass
    print("=" * 60)
