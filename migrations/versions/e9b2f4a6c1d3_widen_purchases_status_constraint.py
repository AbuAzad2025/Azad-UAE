"""widen ck_purchases_status to the statuses Purchase actually uses

``86afead128ce`` added ``ck_purchases_status`` allowing only::

    ('draft', 'confirmed', 'cancelled')

``models/purchase.py`` documents seven purchase statuses and the purchase
services write four of them::

    draft, submitted, confirmed, partially_received, received, closed, cancelled

So three statuses the code can legitimately produce - ``submitted``,
``partially_received`` and ``received`` - are rejected by the database. The e2e
suite hit this directly::

    IntegrityError: (psycopg2.errors.CheckViolation) new row for relation
    "purchases" violates check constraint "ck_purchases_status"

The constraint was written from an incomplete reading of the model, and the
Alembic round-trip could not catch it because the chain replays cleanly; it is
simply the wrong predicate.

This revision widens the constraint to the model's full status set. Before
widening it checks the live table for any value outside the new set and refuses
to proceed if it finds one, rather than silently leaving rows that the new
constraint would then reject.

Revision ID: e9b2f4a6c1d3
Revises: c4a7d1e9f0b2
Create Date: 2026-09-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e9b2f4a6c1d3"
down_revision = "c4a7d1e9f0b2"
branch_labels = None
depends_on = None

_TABLE = "purchases"
_CONSTRAINT = "ck_purchases_status"
_COLUMN = "status"

# The full set from models/purchase.py, not the three the constraint allowed.
_ALLOWED = (
    "draft",
    "submitted",
    "confirmed",
    "partially_received",
    "received",
    "closed",
    "cancelled",
)

# What 86afead128ce allowed, i.e. what downgrade() puts back.
_PREVIOUS = ("draft", "confirmed", "cancelled")


def _values() -> str:
    return "(" + ",".join(f"'{v}'" for v in _ALLOWED) + ")"


def _constraint_sql(allowed: tuple[str, ...]) -> str:
    # No leading CHECK: batch_op.create_check_constraint emits the keyword
    # itself, so including it produces "CHECK CHECK (...)".
    listed = ",".join(f"'{v}'" for v in allowed)
    return f"{_COLUMN} IN ({listed})"


def _unexpected_values(bind) -> list[str]:
    """Live values that the widened constraint would reject."""
    return [
        row[0]
        for row in bind.execute(
            sa.text(
                f"SELECT DISTINCT {_COLUMN}::text FROM {_TABLE} "
                f"WHERE {_COLUMN} IS NOT NULL AND {_COLUMN}::text NOT IN {_values()}"
            )
        )
        if row[0]
    ]


def upgrade() -> None:
    bind = op.get_bind()
    if "purchases" not in sa.inspect(bind).get_table_names():
        return

    unexpected = _unexpected_values(bind)
    if unexpected:
        raise RuntimeError(
            f"cannot widen {_CONSTRAINT}: {_TABLE}.{_COLUMN} holds value(s) "
            f"{unexpected} that are in neither the old nor the new allowed set. "
            "Map them before retrying - silently coercing purchase status is not "
            "safe."
        )

    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(_CONSTRAINT, sa.text(_constraint_sql(_ALLOWED)))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    live = {row[0] for row in bind.execute(sa.text(f"SELECT DISTINCT {_COLUMN}::text FROM {_TABLE}"))}
    blocked = sorted(live - set(_PREVIOUS))
    if blocked:
        raise RuntimeError(
            f"cannot narrow {_CONSTRAINT} back: {_TABLE}.{_COLUMN} holds "
            f"{blocked}, which the previous constraint rejected. Rows would be "
            "left in violation."
        )

    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(_CONSTRAINT, sa.text(_constraint_sql(_PREVIOUS)))
