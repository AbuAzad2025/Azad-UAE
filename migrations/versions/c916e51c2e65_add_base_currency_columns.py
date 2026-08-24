"""add base_currency columns

Revision ID: c916e51c2e65
Revises: f3a9c1e5b2d8
Create Date: 2026-08-24 22:27:14.593895

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c916e51c2e65'
down_revision = 'f3a9c1e5b2d8'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
        return column in cols
    except Exception:
        return False


def upgrade():
    for table in ("expenses", "payments", "product_returns", "purchases", "receipts", "sales"):
        if not _column_exists(table, "base_currency"):
            op.add_column(table, sa.Column("base_currency", sa.String(length=3), nullable=False, server_default="AED"))


def downgrade():
    for table in ("expenses", "payments", "product_returns", "purchases", "receipts", "sales"):
        if _column_exists(table, "base_currency"):
            op.drop_column(table, "base_currency")
