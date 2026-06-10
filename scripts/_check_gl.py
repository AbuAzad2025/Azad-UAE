import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SKIP_SYSTEM_INTEGRITY'] = '1'
from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("=" * 60)
    print("GL ACCOUNTS CHECK")
    print("=" * 60)

    for t in ['gl_accounts', 'gl_journal_entries', 'gl_journal_lines',
              'gl_periods', 'gl_account_mappings', 'gl_concept_registry']:
        try:
            r = db.session.execute(text(f"SELECT COUNT(*) FROM {t}"))
            c = r.scalar()
            print(f"  {t:40s} | {c} rows")
            if c > 0 and t == 'gl_accounts':
                sample = db.session.execute(text("SELECT account_number, name_ar FROM gl_accounts LIMIT 5"))
                for row in sample:
                    print(f"      {row.account_number} | {row.name_ar}")
        except Exception as e:
            print(f"  {t:40s} | ERROR: {str(e)[:50]}")

    print("=" * 60)
