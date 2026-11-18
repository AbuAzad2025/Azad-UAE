"""Record where a document's exchange rate came from.

A sale/payment used to store only the numeric rate. Once the online lookup was
merged into the checkout payload, every rate was reported as user-entered and
there was no way to tell a live provider rate from a hand-typed one after the
fact. Add explicit provenance columns so the documents keep that answer.

Revision ID: k3l4m5n6o7p8
Revises: h2i3j4k5l6m10
Create Date: 2026-11-18 22:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "k3l4m5n6o7p8"
down_revision = "h2i3j4k5l6m10"
branch_labels = None
depends_on = None


def _columns():
    return (
        ("rate_source", sa.String(30)),
        ("rate_fetched_at", sa.DateTime(timezone=True)),
    )


def upgrade():
    for table in ("sales", "payments"):
        for name, column_type in _columns():
            op.add_column(table, sa.Column(name, column_type, nullable=True))


def downgrade():
    for table in ("sales", "payments"):
        for name, _column_type in reversed(_columns()):
            op.drop_column(table, name)
