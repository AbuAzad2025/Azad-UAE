"""platform vault collection evidence (accrued vs collected)

The platform vault (tenant-less) is the treasury for Azad platform money:
donations granted to the platform and store-sale commissions. Accounting
accrues them, but only the platform owner can confirm real-world receipt.

Schema changes:
- ``payment_transactions.tenant_id`` becomes nullable: platform receipts
  (settlement payouts, platform donations) belong to no tenant. Tenant
  receipts keep their tenant_id; ORM scoping already treats NULL as
  platform-only (owners see it, tenant queries filter by their id).
- ``azad_platform_fees`` gains ``collected_at`` + ``confirmed_by`` so the
  accrued (accounting) vs collected (owner-confirmed cash) split is stored
  on the row, next to the existing status paid + vault PaymentTransaction.

Revision ID: c3d4e5f6a7b8
Revises: 9a1b3c4d5e6f
Create Date: 2026-09-08 23:20:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "9a1b3c4d5e6f"
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


def _column_is_nullable(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    for c in insp.get_columns(table):
        if c["name"] == column:
            return bool(c.get("nullable", True))
    return True


def upgrade():
    if not _column_is_nullable("payment_transactions", "tenant_id"):
        with op.batch_alter_table("payment_transactions", schema=None) as batch_op:
            batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=True)
    if not _column_exists("azad_platform_fees", "collected_at"):
        with op.batch_alter_table("azad_platform_fees", schema=None) as batch_op:
            batch_op.add_column(sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True))
    if not _column_exists("azad_platform_fees", "confirmed_by"):
        with op.batch_alter_table("azad_platform_fees", schema=None) as batch_op:
            batch_op.add_column(sa.Column("confirmed_by", sa.Integer(), nullable=True))
            batch_op.create_index("ix_azad_platform_fees_confirmed_by", ["confirmed_by"])


def downgrade():
    if _column_exists("azad_platform_fees", "confirmed_by"):
        with op.batch_alter_table("azad_platform_fees", schema=None) as batch_op:
            batch_op.drop_index("ix_azad_platform_fees_confirmed_by")
            batch_op.drop_column("confirmed_by")
    if _column_exists("azad_platform_fees", "collected_at"):
        with op.batch_alter_table("azad_platform_fees", schema=None) as batch_op:
            batch_op.drop_column("collected_at")
    if _column_is_nullable("payment_transactions", "tenant_id"):
        with op.batch_alter_table("payment_transactions", schema=None) as batch_op:
            batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)
