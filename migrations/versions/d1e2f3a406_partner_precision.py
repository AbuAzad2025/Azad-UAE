"""Partner precision: link product partners to company partners + scope-commission totals.

* customers.partner_id — optional link from a product-level customer partner
  (``customer_type='partner'``) to the same person's company-level ``Partner``
  record, so one human can hold both roles and be reported on in one place.
  Nullable and SET NULL on delete: unlinking is always safe.
* partner_profit_distributions.total_commissions — product commissions accrued
  for the scope in the period (net of return reversals), deducted from the
  distributable net profit so company partners never share a profit that the
  product-level commission leg already took.

Revision ID: d1e2f3a406
Revises: c0d1e2f3a405
Create Date: 2026-11-08
"""

from __future__ import annotations

import contextlib

import sqlalchemy as sa
from alembic import op

revision = "d1e2f3a406"
down_revision = "c0d1e2f3a405"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    customer_cols = {c["name"] for c in inspector.get_columns("customers")}
    if "partner_id" not in customer_cols:
        with op.batch_alter_table("customers") as batch_op:
            batch_op.add_column(sa.Column("partner_id", sa.Integer(), nullable=True))
            batch_op.create_index("ix_customers_partner_id", ["partner_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_customers_partner_id",
                "partners",
                ["partner_id"],
                ["id"],
                ondelete="SET NULL",
            )

    dist_cols = {c["name"] for c in inspector.get_columns("partner_profit_distributions")}
    if "total_commissions" not in dist_cols:
        with op.batch_alter_table("partner_profit_distributions") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "total_commissions",
                    sa.Numeric(15, 3),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    dist_cols = {c["name"] for c in inspector.get_columns("partner_profit_distributions")}
    if "total_commissions" in dist_cols:
        with op.batch_alter_table("partner_profit_distributions", schema=None) as batch_op:
            batch_op.drop_column("total_commissions")

    customer_cols = {c["name"] for c in inspector.get_columns("customers")}
    if "partner_id" in customer_cols:
        with op.batch_alter_table("customers", schema=None) as batch_op, contextlib.suppress(Exception):
            batch_op.drop_constraint("fk_customers_partner_id", type_="foreignkey")
        with op.batch_alter_table("customers", schema=None) as batch_op, contextlib.suppress(Exception):
            batch_op.drop_index("ix_customers_partner_id")
        with op.batch_alter_table("customers", schema=None) as batch_op:
            batch_op.drop_column("partner_id")
