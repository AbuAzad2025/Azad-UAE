"""add pos_kds_orders.notes

``PosKdsOrder.notes`` (``models/pos_kds_order.py``) has been in the model for a
while, but no migration ever created the column. ``squash_001_baseline`` builds
``pos_kds_orders`` with eleven columns and ``notes`` is not one of them.

Nothing noticed, because ``db.create_all()`` used to reconcile model metadata
against the live database. On a developer's machine the column simply appeared.
Once that shortcut was removed, the column stopped existing everywhere the
schema came from Alembic, and the model tests started failing with::

    UndefinedColumn: column "notes" of relation "pos_kds_orders" does not exist

This revision gives the column a real definition so the migrated schema matches
the model. It is nullable ``Text`` with no server default, matching the model,
and it is added to the end of the table so existing row order is untouched.

``scripts/lint/check_model_schema_parity.py`` is what surfaced this. It diffs
``db.metadata`` against the live schema on a database built purely by
``flask db upgrade``; the CI Alembic round-trip could not, because that only
proves the chain replays, not that the chain produces the schema the code reads.

Revision ID: c4a7d1e9f0b2
Revises: b1f4c7a92d60
Create Date: 2026-09-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4a7d1e9f0b2"
down_revision = "b1f4c7a92d60"
branch_labels = None
depends_on = None

_TABLE = "pos_kds_orders"
_COLUMN = "notes"


def _has_column(bind) -> bool:
    return _COLUMN in {c["name"] for c in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind):
        return
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.add_column(sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_column(_COLUMN)
