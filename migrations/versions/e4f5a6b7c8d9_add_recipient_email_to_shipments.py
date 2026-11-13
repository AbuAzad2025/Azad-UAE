"""add recipient_email to shipments

Adds a ``recipient_email`` column (String 200) to ``shipments`` so that
email notifications can be sent on status changes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("shipments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("recipient_email", sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table("shipments", schema=None) as batch_op:
        batch_op.drop_column("recipient_email")
