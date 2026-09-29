"""widen ck_sales_status to the statuses the sale path actually writes

Same defect class as e9b2f4a6c1d3 (ck_purchases_status), found by the parallel
schema audit. ``86afead128ce`` added::

    ck_sales_status: status IN ('draft','confirmed','cancelled','returned')

``utils/field_validators.py`` declares::

    ALLOWED_SALE_STATUSES = frozenset({"pending", "confirmed", "cancelled", "completed"})

``SaleService.create_sale`` persists through ``validate_sale_status``, so
``pending`` and ``completed`` are values the code considers valid and the
database rejects. ``services/store_checkout_service.py:253`` passes
``sale_status="pending"`` - the deferred-fulfilment online-store path, and the
only call site in the codebase that passes the argument at all - so every
storefront checkout that defers fulfilment raises::

    IntegrityError: CheckViolation: new row for relation "sales" violates
    check constraint "ck_sales_status"

``StoreOrderService.order_counts`` also counts ``status="pending"``, so the
order dashboard is built on a value the database will not store.

It stayed hidden because the one test covering that path,
``tests/unit/services/test_store_checkout_service.py``, patches
``SaleService.create_sale`` with a MagicMock, so no real INSERT with
status='pending' is ever issued - structurally the same blindness as
ck_purchases_status, where the only writer was mocked at the boundary.

The two sources also disagree on which values are canonical: the constraint says
``draft``/``returned``, the validator says ``pending``/``completed``, and
``models/sale.py`` declares neither (its column is a bare String(20) defaulting
to "confirmed", with no CheckConstraint to arbitrate). The union is used here so
neither vocabulary stops working; introducing a single source of truth for sale
status is the real fix and is not in this commit.

upgrade() refuses if the table holds a status outside the new set, rather than
leaving rows the new constraint would reject. downgrade() refuses for the mirror
reason.

Revision ID: a3d7f1b9c6e2
Revises: f1c6a8d3b5e9
Create Date: 2026-09-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3d7f1b9c6e2"
down_revision = "f1c6a8d3b5e9"
branch_labels = None
depends_on = None

_TABLE = "sales"
_CONSTRAINT = "ck_sales_status"
_COLUMN = "status"

# Union of the constraint's list and ALLOWED_SALE_STATUSES.
_WIDENED = (
    "draft",
    "pending",
    "confirmed",
    "completed",
    "cancelled",
    "returned",
)

_PREVIOUS = ("draft", "confirmed", "cancelled", "returned")


def _predicate(allowed: tuple[str, ...]) -> str:
    # No leading CHECK - batch_op.create_check_constraint emits the keyword.
    listed = ",".join(f"'{v}'" for v in allowed)
    return f"{_COLUMN} IN ({listed})"


def _has_constraint(bind) -> bool:
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :n"),
            {"n": _CONSTRAINT},
        ).fetchone()
    )


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        return
    if not _has_constraint(bind):
        return

    unexpected = [
        row[0]
        for row in bind.execute(
            sa.text(
                f"SELECT DISTINCT {_COLUMN}::text FROM {_TABLE} "
                f"WHERE {_COLUMN} IS NOT NULL AND "
                f"{_COLUMN}::text NOT IN ({','.join(chr(39) + v + chr(39) for v in _WIDENED)})"
            )
        )
        if row[0]
    ]
    if unexpected:
        raise RuntimeError(
            f"cannot widen {_CONSTRAINT}: {_TABLE}.{_COLUMN} holds {unexpected}, which is "
            "in neither the old nor the new allowed set. Map them before retrying - "
            "silently coercing sale status is not safe."
        )

    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(_CONSTRAINT, sa.text(_predicate(_WIDENED)))


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        return
    if not _has_constraint(bind):
        return

    live = {row[0] for row in bind.execute(sa.text(f"SELECT DISTINCT {_COLUMN}::text FROM {_TABLE}")) if row[0]}
    blocked = sorted(live - set(_PREVIOUS))
    if blocked:
        raise RuntimeError(
            f"cannot narrow {_CONSTRAINT}: {_TABLE}.{_COLUMN} holds {blocked}, which the "
            "previous constraint rejected. Rows would be left in violation."
        )

    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="check")
        batch_op.create_check_constraint(_CONSTRAINT, sa.text(_predicate(_PREVIOUS)))
