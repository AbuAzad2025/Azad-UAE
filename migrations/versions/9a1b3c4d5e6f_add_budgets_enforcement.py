"""add budgets.enforcement column (model/DB drift fix)

The ``Budget`` model defines ``enforcement`` (warn/hard/off) but no
migration ever created the column, so any query touching ``budgets``
— e.g. the ``branch.budgets`` backref loaded during branch delete
guards — crashed with ``UndefinedColumn: budgets.enforcement``.

Revision ID: 9a1b3c4d5e6f
Revises: 7f4c5e2a9011
Create Date: 2026-09-08 22:55:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "9a1b3c4d5e6f"
down_revision = "7f4c5e2a9011"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    try:
        return column in [c["name"] for c in insp.get_columns(table)]
    except Exception:
        return False


def upgrade():
    if not _column_exists("budgets", "enforcement"):
        with op.batch_alter_table("budgets", schema=None) as batch_op:
            batch_op.add_column(sa.Column("enforcement", sa.String(length=20), nullable=True))
        op.execute("UPDATE budgets SET enforcement = 'warn' WHERE enforcement IS NULL")


def downgrade():
    if _column_exists("budgets", "enforcement"):
        with op.batch_alter_table("budgets", schema=None) as batch_op:
            batch_op.drop_column("enforcement")
