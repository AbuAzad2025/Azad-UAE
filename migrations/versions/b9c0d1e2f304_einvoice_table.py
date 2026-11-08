"""E-invoice artifacts — persist the statutory document per posted sale.

Revision ID: b9c0d1e2f304
Revises: a8b9c0d1e203
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b9c0d1e2f304"
down_revision = "a8b9c0d1e203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "e_invoices" in inspector.get_table_names():
        return
    op.create_table(
        "e_invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sale_id",
            sa.Integer(),
            sa.ForeignKey("sales.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("format", sa.String(50), nullable=False),
        sa.Column("xml_payload", sa.Text(), nullable=False),
        sa.Column("qr_base64", sa.Text(), nullable=True),
        sa.Column("invoice_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="generated"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "sale_id", name="uq_einvoice_tenant_sale"),
    )
    op.create_index("idx_einvoice_tenant_created", "e_invoices", ["tenant_id", "created_at"])
    op.create_index("ix_e_invoices_tenant_id", "e_invoices", ["tenant_id"])
    op.create_index("ix_e_invoices_sale_id", "e_invoices", ["sale_id"])


def downgrade() -> None:
    op.drop_table("e_invoices")
