"""add carrier_code to shipments

Adds a ``carrier_code`` column (String 30) to ``shipments`` so the
carrier tracking integration can identify which carrier API to query
(dhl / fedex / aramex / other).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("shipments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("carrier_code", sa.String(length=30), nullable=True))
        batch_op.create_index("ix_shipments_carrier_code", ["carrier_code"], unique=False)


def downgrade():
    with op.batch_alter_table("shipments", schema=None) as batch_op:
        batch_op.drop_index("ix_shipments_carrier_code")
        batch_op.drop_column("carrier_code")
