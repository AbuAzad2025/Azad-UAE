"""Batch 2: procurement (PR/PO/GRN), leave balance, overtime, leave type carry-forward

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-08-17 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    # --- Purchase Requisitions ---
    op.create_table(
        "purchase_requisitions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("requisition_number", sa.String(50), nullable=False, index=True),
        sa.Column(
            "requester_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column(
            "department_id", sa.Integer, sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
        ),
        sa.Column(
            "branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True
        ),
        sa.Column("requested_date", sa.Date, nullable=False, index=True),
        sa.Column("needed_by_date", sa.Date, nullable=True),
        sa.Column("priority", sa.String(20), server_default="normal"),
        sa.Column("status", sa.String(20), server_default="draft", index=True),
        sa.Column("justification", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("rejected_reason", sa.String(500), nullable=True),
        sa.Column("po_id", sa.Integer, sa.ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("tenant_id", "requisition_number", name="uq_pr_tenant_number"),
    )

    op.create_table(
        "purchase_requisition_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column(
            "requisition_id",
            sa.Integer,
            sa.ForeignKey("purchase_requisitions.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column("quantity", sa.Numeric(15, 3), nullable=False),
        sa.Column("unit_cost_estimate", sa.Numeric(15, 3), server_default="0"),
        sa.Column("notes", sa.String(255), nullable=True),
    )

    # --- Purchase Orders ---
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("po_number", sa.String(50), nullable=False, index=True),
        sa.Column(
            "supplier_id", sa.Integer, sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column(
            "warehouse_id", sa.Integer, sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True, index=True
        ),
        sa.Column(
            "branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True
        ),
        sa.Column(
            "requisition_id",
            sa.Integer,
            sa.ForeignKey("purchase_requisitions.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("order_date", sa.Date, nullable=False, index=True),
        sa.Column("expected_delivery_date", sa.Date, nullable=True),
        sa.Column("subtotal", sa.Numeric(15, 3), server_default="0"),
        sa.Column("tax_amount", sa.Numeric(15, 3), server_default="0"),
        sa.Column("total_amount", sa.Numeric(15, 3), server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="AED"),
        sa.Column("status", sa.String(20), server_default="draft", index=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("confirmed_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("tenant_id", "po_number", name="uq_po_tenant_number"),
    )

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column(
            "po_id", sa.Integer, sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column(
            "product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column("quantity", sa.Numeric(15, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(15, 3), nullable=False),
        sa.Column("line_total", sa.Numeric(15, 3), nullable=False),
        sa.Column("received_quantity", sa.Numeric(15, 3), server_default="0"),
        sa.Column("notes", sa.String(255), nullable=True),
    )

    # --- Goods Receipts ---
    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("grn_number", sa.String(50), nullable=False, index=True),
        sa.Column(
            "po_id", sa.Integer, sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column(
            "supplier_id", sa.Integer, sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column(
            "warehouse_id", sa.Integer, sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True, index=True
        ),
        sa.Column(
            "branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True
        ),
        sa.Column("received_date", sa.Date, nullable=False, index=True),
        sa.Column(
            "received_by", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column("status", sa.String(20), server_default="draft", index=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "grn_number", name="uq_grn_tenant_number"),
    )

    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column(
            "grn_id", sa.Integer, sa.ForeignKey("goods_receipts.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column(
            "po_line_id",
            sa.Integer,
            sa.ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
        ),
        sa.Column("ordered_quantity", sa.Numeric(15, 3), nullable=False),
        sa.Column("received_quantity", sa.Numeric(15, 3), nullable=False),
        sa.Column("condition", sa.String(20), server_default="acceptable"),
        sa.Column("notes", sa.String(255), nullable=True),
    )

    # --- Leave Balance Ledger ---
    op.create_table(
        "leave_balances",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column(
            "leave_type_id",
            sa.Integer,
            sa.ForeignKey("leave_types.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("year", sa.Integer, nullable=False, index=True),
        sa.Column("entitled_days", sa.Numeric(5, 1), nullable=False, server_default="0"),
        sa.Column("carried_forward", sa.Numeric(5, 1), nullable=False, server_default="0"),
        sa.Column("taken_days", sa.Numeric(5, 1), nullable=False, server_default="0"),
        sa.Column("pending_days", sa.Numeric(5, 1), nullable=False, server_default="0"),
        sa.Column("remaining_days", sa.Numeric(5, 1), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("tenant_id", "user_id", "leave_type_id", "year", name="uq_leave_balance_user_type_year"),
    )

    # --- Overtime Entries ---
    op.create_table(
        "overtime_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column(
            "branch_id", sa.Integer, sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
        ),
        sa.Column("overtime_date", sa.Date, nullable=False, index=True),
        sa.Column("hours", sa.Numeric(5, 2), nullable=False),
        sa.Column("rate_multiplier", sa.Numeric(4, 2), nullable=False, server_default="1.0"),
        sa.Column("overtime_type", sa.String(20), nullable=False, server_default="standard"),
        sa.Column("status", sa.String(20), server_default="pending", index=True),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("rejected_reason", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # --- LeaveType: add carry-forward columns ---
    op.add_column("leave_types", sa.Column("carry_forward_days", sa.Integer, server_default="0"))
    op.add_column("leave_types", sa.Column("max_carry_forward", sa.Integer, server_default="0"))


def downgrade():
    op.drop_column("leave_types", "max_carry_forward")
    op.drop_column("leave_types", "carry_forward_days")
    op.drop_table("overtime_entries")
    op.drop_table("leave_balances")
    op.drop_table("goods_receipt_lines")
    op.drop_table("goods_receipts")
    op.drop_table("purchase_order_lines")
    op.drop_table("purchase_orders")
    op.drop_table("purchase_requisition_lines")
    op.drop_table("purchase_requisitions")
