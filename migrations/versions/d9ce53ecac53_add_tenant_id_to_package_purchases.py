"""add tenant_id to package_purchases F-07 fix

Revision ID: d9ce53ecac53
Revises: 17fca8d581b2
Create Date: 2026-08-31

Ensure package_purchases.tenant_id exists for multi-tenant isolation.
Column is nullable for backward compat, indexed, FK to tenants with RESTRICT.
Works for both PostgreSQL and SQLite via batch mode.
"""

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "d9ce53ecac53"
down_revision = "17fca8d581b2"
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
    if not _column_exists("package_purchases", "tenant_id"):
        with op.batch_alter_table("package_purchases", schema=None) as batch_op:
            batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f("ix_package_purchases_tenant_id"), ["tenant_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_package_purchases_tenant_id_tenants",
                "tenants",
                ["tenant_id"],
                ["id"],
                ondelete="RESTRICT",
            )
        # Backfill from packages -> tenants? package has no tenant, so leave NULL
        # For existing rows, try to infer from customer? Not reliable, keep NULL
        pass


def downgrade():
    if _column_exists("package_purchases", "tenant_id"):
        with op.batch_alter_table("package_purchases", schema=None) as batch_op:
            with contextlib.suppress(Exception):
                batch_op.drop_constraint("fk_package_purchases_tenant_id_tenants", type_="foreignkey")
            with contextlib.suppress(Exception):
                batch_op.drop_index(batch_op.f("ix_package_purchases_tenant_id"))
            batch_op.drop_column("tenant_id")
