"""Check alembic_version table."""
from sqlalchemy import text
from app import create_app
app = create_app()
with app.app_context():
    from extensions import db
    rows = db.session.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    print("DB heads:", [r[0] for r in rows])
