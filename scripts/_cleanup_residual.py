import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app
from extensions import db
from sqlalchemy import text
app = create_app()
with app.app_context():
    tables = ['branches','customers','users','roles','permissions','login_histories']
    for t in tables:
        try:
            db.session.execute(text(f"DELETE FROM {t}"))
            db.session.commit()
            print(f'Wiped {t}')
        except Exception as e:
            db.session.rollback()
            print(f'Skip {t}: {str(e)[:60]}')
    print('Residual cleanup done')
