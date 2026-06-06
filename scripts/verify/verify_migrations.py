import os
os.environ['FLASK_APP'] = 'app.py'
from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("\n" + "="*70)
    print("MIGRATION CHAIN ANALYSIS")
    print("="*70)

    # جميع الملفات في versions
    import os
    versions_dir = 'migrations/versions'
    migration_files = sorted([f for f in os.listdir(versions_dir) if f.endswith('.py')])

    print("\nAVAILABLE MIGRATION FILES (last 15):")
    for f in migration_files[-15:]:  # آخر 15 ملف
        print(f"  - {f}")

    # الهجرات المطبقة
    print("\n" + "-"*70)
    print("APPLIED MIGRATIONS (in alembic_version table):")
    result = db.session.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
    applied = [row[0] for row in result.fetchall()]
    for m in applied:
        print(f"  ✓ {m}")

    if not applied:
        print("  (NO MIGRATIONS APPLIED)")

    # Check migration revises chains
    print("\n" + "-"*70)
    print("CHECKING MIGRATION REVISION CHAINS (last 10):")

    for mig_file in migration_files[-10:]:
        filepath = os.path.join(versions_dir, mig_file)
        with open(filepath, 'r') as f:
            content = f.read()
            # استخرج revision و revises
            import re
            rev = re.search(r"revision = ['\"]([^'\"]+)['\"]", content)
            revises = re.search(r"down_revision = ['\"]([^'\"]+)['\"]", content)

            rev_id = rev.group(1) if rev else "???"
            revises_id = revises.group(1) if revises else "None"

            applied_mark = "✓" if rev_id in applied else " "
            print(f"\n  [{applied_mark}] {mig_file}")
            print(f"       revision: {rev_id}")
            print(f"       revises:  {revises_id}")
