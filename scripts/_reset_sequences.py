import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from extensions import db
from sqlalchemy import text
app = create_app()
with app.app_context():
    tables = [
        'tenants','products','product_categories','sales','purchases',
        'customers','suppliers','warehouses','branches','users',
        'payments','stock_movements','gl_journal_entries',
        'product_serials','expenses','product_returns'
    ]
    for t in tables:
        try:
            seq = f"{t}_id_seq"
            db.session.execute(text(f"ALTER SEQUENCE IF EXISTS {seq} RESTART WITH 1"))
            db.session.commit()
            print(f'Reset {seq}')
        except Exception as e:
            db.session.rollback()
            print(f'Skip {t}: {str(e)[:60]}')
    print('Sequence reset done')
