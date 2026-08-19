"""batch3 quotations and warehouse transfers

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-08-18
"""

import sqlalchemy as sa
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("quotation_number", sa.String(50), nullable=False, index=True),
        sa.Column(
            "customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column(
            "branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True
        ),
        sa.Column(
            "warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True, index=True
        ),
        sa.Column("quotation_date", sa.Date(), nullable=False, index=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False, index=True),
        sa.Column("subtotal", sa.Numeric(15, 3), server_default="0"),
        sa.Column("discount_amount", sa.Numeric(15, 3), server_default="0"),
        sa.Column("tax_rate", sa.Numeric(5, 2), server_default="0"),
        sa.Column("tax_amount", sa.Numeric(15, 3), server_default="0"),
        sa.Column("total_amount", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="AED"),
        sa.Column("exchange_rate", sa.Numeric(15, 6), server_default="1"),
        sa.Column("base_currency", sa.String(3), nullable=False, server_default="AED"),
        sa.Column("amount_aed", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("prices_include_vat", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sales.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "quotation_number", name="uq_quotations_tenant_number"),
    )

    op.create_table(
        "quotation_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column(
            "quotation_id", sa.Integer(), sa.ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("quantity", sa.Numeric(15, 3), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("discount_percent", sa.Numeric(5, 2), server_default="0"),
        sa.Column("tax_rate", sa.Numeric(5, 2), server_default="0"),
        sa.Column("line_total", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "warehouse_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("transfer_number", sa.String(50), nullable=False, index=True),
        sa.Column(
            "from_warehouse_id",
            sa.Integer(),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "to_warehouse_id",
            sa.Integer(),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True
        ),
        sa.Column("status", sa.String(20), server_default="draft", nullable=False, index=True),
        sa.Column("transfer_date", sa.Date(), nullable=False, index=True),
        sa.Column("completed_date", sa.Date(), nullable=True),
        sa.Column(
            "requested_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("received_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "transfer_number", name="uq_warehouse_transfers_number"),
    )

    op.create_table(
        "warehouse_transfer_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column(
            "transfer_id",
            sa.Integer(),
            sa.ForeignKey("warehouse_transfers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column("requested_quantity", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("received_quantity", sa.Numeric(15, 3), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("warehouse_transfer_lines")
    op.drop_table("warehouse_transfers")
    op.drop_table("quotation_lines")
    op.drop_table("quotations")
