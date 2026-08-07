"""package money columns float -> numeric(14,3)

- packages.price and package_purchases.amount_paid were Float — binary
  floating point drifts on money. Convert to exact Numeric(14, 3), rounding
  any legacy float artifacts to the 0.001 quantum in the same ALTER.

Revision ID: g8c4b2d91e10
Revises: f7b3a1c82e09
Create Date: 2026-07-24 23:45:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "g8c4b2d91e10"
down_revision = "f7b3a1c82e09"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "packages",
        "price",
        type_=sa.Numeric(14, 3),
        existing_type=sa.Float(),
        existing_nullable=False,
        postgresql_using='ROUND("price"::numeric, 3)',
    )
    op.alter_column(
        "package_purchases",
        "amount_paid",
        type_=sa.Numeric(14, 3),
        existing_type=sa.Float(),
        existing_nullable=False,
        postgresql_using='ROUND("amount_paid"::numeric, 3)',
    )


def downgrade():
    op.alter_column(
        "package_purchases",
        "amount_paid",
        type_=sa.Float(),
        existing_type=sa.Numeric(14, 3),
        existing_nullable=False,
    )
    op.alter_column(
        "packages",
        "price",
        type_=sa.Float(),
        existing_type=sa.Numeric(14, 3),
        existing_nullable=False,
    )
