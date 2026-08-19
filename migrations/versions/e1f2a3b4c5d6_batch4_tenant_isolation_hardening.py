"""Batch 4: Tenant Isolation Hardening - StorePaymentMethod tenant_id, ErrorAuditLog nullable tenant_id

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-08-19
"""

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    # Add tenant_id to store_payment_methods
    op.add_column(
        "store_payment_methods",
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )

    # Backfill existing records with tenant_id = 1 (default tenant)
    # This assumes tenant with id=1 exists. In production, this should be handled carefully.
    op.execute("UPDATE store_payment_methods SET tenant_id = 1 WHERE tenant_id IS NULL")

    # Now make it NOT NULL and add unique constraint
    op.alter_column("store_payment_methods", "tenant_id", nullable=False)
    op.drop_index("ix_store_payment_methods_code", table_name="store_payment_methods")
    op.create_unique_constraint(
        "uq_store_payment_method_tenant_code",
        "store_payment_methods",
        ["tenant_id", "code"],
    )

    # ErrorAuditLog already has tenant_id (nullable) - ensure it's properly set up
    # No changes needed as it already exists and is nullable


def downgrade():
    # Remove unique constraint
    op.drop_constraint("uq_store_payment_method_tenant_code", "store_payment_methods", type_="unique")

    # Recreate the old unique index on code
    op.create_index("ix_store_payment_methods_code", "store_payment_methods", ["code"], unique=True)

    # Remove tenant_id column
    op.drop_column("store_payment_methods", "tenant_id")
