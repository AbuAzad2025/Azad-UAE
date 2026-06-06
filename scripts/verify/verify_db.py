import sys
import os
sys.path.insert(0, os.getcwd())

# تجنب مشاكل Flask app context
os.environ['FLASK_APP'] = 'app.py'

from app import create_app
from extensions import db
from sqlalchemy import inspect, text

app = create_app()

with app.app_context():
    print("="*60)
    print("DATABASE VERIFICATION")
    print("="*60)

    # 1. جدول profit_centers
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    print("\n1. PROFIT_CENTERS TABLE EXISTS?", 'profit_centers' in tables)

    if 'profit_centers' in tables:
        profit_center_cols = [col['name'] for col in inspector.get_columns('profit_centers')]
        print("   Columns:", profit_center_cols)

    # 2. أعمدة GLJournalLine الجديدة
    print("\n2. GL_JOURNAL_LINES NEW COLUMNS?")
    if 'gl_journal_lines' in tables:
        gl_cols = [col['name'] for col in inspector.get_columns('gl_journal_lines')]
        new_cols = ['branch_id', 'warehouse_id', 'profit_center_id', 'partner_id']
        for col in new_cols:
            exists = col in gl_cols
            print(f"   {col}: {exists}")
    else:
        print("   ERROR: gl_journal_lines table not found!")

    # 3. الهجرة الحالية
    print("\n3. CURRENT MIGRATION VERSION:")
    try:
        result = db.session.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"))
        current_version = result.fetchone()
        if current_version:
            print(f"   {current_version[0]}")
        else:
            print("   NO MIGRATIONS APPLIED")
    except Exception as e:
        print(f"   ERROR: {str(e)}")

    # 4. كل الهجرات المطبقة
    print("\n4. ALL APPLIED MIGRATIONS:")
    try:
        result = db.session.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
        migrations = [row[0] for row in result.fetchall()]
        for m in migrations:
            print(f"   {m}")
        if not migrations:
            print("   (no migrations in table)")
    except Exception as e:
        print(f"   ERROR: {str(e)}")

    # 5. عدد الصفوف في profit_centers
    print("\n5. PROFIT_CENTERS ROW COUNT:")
    if 'profit_centers' in tables:
        try:
            result = db.session.execute(text("SELECT COUNT(*) FROM profit_centers"))
            count = result.fetchone()[0]
            print(f"   {count} rows")
        except Exception as e:
            print(f"   ERROR: {str(e)}")

    # 6. أعمدة GLJournalLine الكاملة
    print("\n6. COMPLETE GL_JOURNAL_LINES COLUMNS:")
    if 'gl_journal_lines' in tables:
        gl_cols = [col['name'] for col in inspector.get_columns('gl_journal_lines')]
        for col in sorted(gl_cols):
            print(f"   - {col}")
