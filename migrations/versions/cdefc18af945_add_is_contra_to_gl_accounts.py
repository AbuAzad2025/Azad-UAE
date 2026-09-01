"""add is_contra to gl_accounts

Revision ID: cdefc18af945
Revises: d9ce53ecac53
Create Date: 2026-09-01

F-08 (audit fix): add is_contra BOOLEAN default false to gl_accounts.
Required for proper accounting of Accumulated Depreciation (1190),
Owner Drawings (3300), Inventory Gain (5201).
"""
import sqlalchemy as sa
from alembic import op

revision = "cdefc18af945"
down_revision = "d9ce53ecac53"
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
    if not _column_exists("gl_accounts", "is_contra"):
        with op.batch_alter_table("gl_accounts", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("is_contra", sa.Boolean(), nullable=False, server_default=sa.text("false"))
            )


def downgrade():
    if _column_exists("gl_accounts", "is_contra"):
        with op.batch_alter_table("gl_accounts", schema=None) as batch_op:
            batch_op.drop_column("is_contra")
