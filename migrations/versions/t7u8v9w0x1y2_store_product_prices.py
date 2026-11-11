"""store_product_prices: per-currency storefront pricing

Adds the store_product_prices table so each product can carry explicit
prices in multiple currencies (e.g. USD for the online storefront) alongside
the tenant base-currency price. Prices are tenant-scoped and unique per
(product, currency).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "t7u8v9w0x1y2"
down_revision = "n9o2p3q4r5s6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "store_product_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=False, index=True),
        sa.Column("price", sa.Numeric(precision=15, scale=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1", index=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0", index=True),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="manual"),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
            index=True,
        ),
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
            "product_id",
            "currency_code",
            name="uq_store_price_tenant_product_currency",
        ),
        sa.Index("ix_store_price_tenant_currency", "tenant_id", "currency_code"),
        sa.Index("ix_store_price_tenant_active", "tenant_id", "is_active"),
    )


def downgrade():
    op.drop_table("store_product_prices")
