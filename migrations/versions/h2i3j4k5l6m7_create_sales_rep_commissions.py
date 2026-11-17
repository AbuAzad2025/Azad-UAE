"""create sales_rep_commissions (table declared by the model, missing from the chain)

The alembic-vs-create_all parity gate caught this: SalesRepCommission existed in
models/sales_rep_commission.py but no revision ever created the table, so any
environment built by ``flask db upgrade`` had no place to store per-line sales
commission calculations.

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-11-17 08:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "h2i3j4k5l6m7"
down_revision = "g1h2i3j4k5l6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sales_rep_commissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("sale_line_id", sa.Integer(), nullable=True),
        sa.Column("sales_rep_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("commission_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("commission_amount", sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("is_paid", sa.Boolean(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sale_line_id"], ["sale_lines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sales_rep_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("sales_rep_commissions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sales_rep_commissions_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sales_rep_commissions_sale_id"), ["sale_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sales_rep_commissions_sale_line_id"), ["sale_line_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sales_rep_commissions_sales_rep_id"), ["sales_rep_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sales_rep_commissions_product_id"), ["product_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sales_rep_commissions_is_paid"), ["is_paid"], unique=False)
        batch_op.create_index(batch_op.f("ix_sales_rep_commissions_created_at"), ["created_at"], unique=False)


def downgrade():
    with op.batch_alter_table("sales_rep_commissions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sales_rep_commissions_created_at"))
        batch_op.drop_index(batch_op.f("ix_sales_rep_commissions_is_paid"))
        batch_op.drop_index(batch_op.f("ix_sales_rep_commissions_product_id"))
        batch_op.drop_index(batch_op.f("ix_sales_rep_commissions_sales_rep_id"))
        batch_op.drop_index(batch_op.f("ix_sales_rep_commissions_sale_line_id"))
        batch_op.drop_index(batch_op.f("ix_sales_rep_commissions_sale_id"))
        batch_op.drop_index(batch_op.f("ix_sales_rep_commissions_tenant_id"))
    op.drop_table("sales_rep_commissions")
