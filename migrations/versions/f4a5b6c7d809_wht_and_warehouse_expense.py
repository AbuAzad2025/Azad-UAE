"""Tenant WHT rate + warehouse attribution for expenses.

* tenants.wht_services_rate — the percentage of non-resident *service*
  payments withheld at source (NULL=disabled). The rate stays tenant-chosen
  because statutory WHT rates vary by country, service type and treaty; the
  box posts to WITHHOLDING_TAX_PAYABLE (2149) like every other payable.
* expenses.warehouse_id — optional warehouse attribution so a warehouse
  partner's P&L can carry the expenses physically settled at that
  warehouse instead of seeing zero.

Revision ID: f4a5b6c7d809
Revises: e2f3a4b5c6d8
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f4a5b6c7d809"
down_revision = "e2f3a4b5c6d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tenant_cols = {c["name"] for c in inspector.get_columns("tenants")}
    if "wht_services_rate" not in tenant_cols:
        with op.batch_alter_table("tenants") as batch_op:
            batch_op.add_column(sa.Column("wht_services_rate", sa.Numeric(5, 2), nullable=True))

    expense_cols = {c["name"] for c in inspector.get_columns("expenses")}
    if "warehouse_id" not in expense_cols:
        with op.batch_alter_table("expenses") as batch_op:
            batch_op.add_column(sa.Column("warehouse_id", sa.Integer(), nullable=True))
            batch_op.create_index("ix_expenses_warehouse_id", ["warehouse_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_expenses_warehouse_id",
                "warehouses",
                ["warehouse_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    expense_cols = {c["name"] for c in inspector.get_columns("expenses")}
    if "warehouse_id" in expense_cols:
        with op.batch_alter_table("expenses") as batch_op:
            batch_op.drop_constraint("fk_expenses_warehouse_id", type_="foreignkey")
            batch_op.drop_index("ix_expenses_warehouse_id")
            batch_op.drop_column("warehouse_id")

    tenant_cols = {c["name"] for c in inspector.get_columns("tenants")}
    if "wht_services_rate" in tenant_cols:
        with op.batch_alter_table("tenants") as batch_op:
            batch_op.drop_column("wht_services_rate")
