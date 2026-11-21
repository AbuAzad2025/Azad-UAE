"""Keep statutory e-invoices, align payroll and vault money precision.

- e_invoices are statutory tax evidence: deleting the linked sale/return must
  null the link, not cascade-delete the XML/QR/hash.
- payroll_transactions money columns were 2dp while the GL posts 3dp, so the
  payslip and the cash line disagreed by up to half a cent.
- payment_transactions.amount_usd was the only 2dp vault money column.

Revision ID: p4q5r6s7t8u9
Revises: k3l4m5n6o7p8
Create Date: 2026-11-21 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "p4q5r6s7t8u9"
down_revision = "k3l4m5n6o7p8"
branch_labels = None
depends_on = None

_FKS = (
    ("e_invoices_sale_id_fkey", "sale_id", "sales"),
    ("e_invoices_return_id_fkey", "return_id", "product_returns"),
    ("e_invoices_maintenance_invoice_id_fkey", "maintenance_invoice_id", "maintenance_invoices"),
)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for name, column, target in _FKS:
            op.execute(f"ALTER TABLE e_invoices DROP CONSTRAINT IF EXISTS {name}")
            op.execute(
                f"ALTER TABLE e_invoices ADD CONSTRAINT {name} "
                f"FOREIGN KEY ({column}) REFERENCES {target}(id) ON DELETE SET NULL"
            )
    # SQLite needs batch mode; Postgres also accepts it and keeps the model
    # and database definitions aligned.
    with op.batch_alter_table("payroll_transactions") as batch:
        for column in ("basic_amount", "allowances", "deductions", "advances_deducted", "net_salary"):
            batch.alter_column(
                column,
                existing_type=sa.Numeric(10, 2),
                type_=sa.Numeric(15, 3),
                existing_nullable=True,
            )
    with op.batch_alter_table("payment_transactions") as batch:
        batch.alter_column(
            "amount_usd",
            existing_type=sa.Numeric(15, 2),
            type_=sa.Numeric(15, 3),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table("payroll_transactions") as batch:
        for column in ("basic_amount", "allowances", "deductions", "advances_deducted", "net_salary"):
            batch.alter_column(
                column,
                existing_type=sa.Numeric(15, 3),
                type_=sa.Numeric(10, 2),
                existing_nullable=True,
            )
    with op.batch_alter_table("payment_transactions") as batch:
        batch.alter_column(
            "amount_usd",
            existing_type=sa.Numeric(15, 3),
            type_=sa.Numeric(15, 2),
            existing_nullable=True,
        )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for name, column, target in _FKS:
            op.execute(f"ALTER TABLE e_invoices DROP CONSTRAINT IF EXISTS {name}")
            op.execute(
                f"ALTER TABLE e_invoices ADD CONSTRAINT {name} "
                f"FOREIGN KEY ({column}) REFERENCES {target}(id) ON DELETE CASCADE"
            )
