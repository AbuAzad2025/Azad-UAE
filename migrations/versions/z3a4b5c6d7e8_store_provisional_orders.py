"""store_provisional_orders: WhatsApp checkout provisional orders

Adds the store_provisional_orders table for the WhatsApp checkout flow.
Customers build a cart, click Buy, and get redirected to the tenant's
WhatsApp with a provisional invoice. The order stays pending until a
tenant admin approves it from the store admin panel, at which point it
is converted into a real Sale with stock deduction and GL posting.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "z3a4b5c6d7e8"
down_revision = "t7u8v9w0x1y2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "store_provisional_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provisional_number", sa.String(length=50), nullable=False, index=True),
        sa.Column("customer_name", sa.String(length=200), nullable=True),
        sa.Column("customer_phone", sa.String(length=50), nullable=True, index=True),
        sa.Column("customer_email", sa.String(length=120), nullable=True),
        sa.Column("cart_json", sa.JSON(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False, default="USD"),
        sa.Column("exchange_rate", sa.Numeric(precision=15, scale=6), nullable=False, default=1),
        sa.Column("subtotal_tx_ccy", sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column("subtotal_aed", sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            default="pending",
            index=True,
        ),
        sa.Column("whatsapp_message", sa.Text(), nullable=True),
        sa.Column("whatsapp_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "converted_sale_id",
            sa.Integer(),
            sa.ForeignKey("sales.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "provisional_number",
            name="uq_provisional_tenant_number",
        ),
        sa.Index("ix_provisional_tenant_status", "tenant_id", "status"),
        sa.Index("ix_provisional_tenant_created", "tenant_id", "created_at"),
    )


def downgrade():
    op.drop_table("store_provisional_orders")
