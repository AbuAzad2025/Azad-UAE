"""drop ck_pws_quantity - negative stock is governed by the warehouse flag

``86afead128ce`` added ``ck_pws_quantity`` as ``quantity >= 0``, forbidding
negative stock unconditionally. That contradicts the rest of the system:

  - ``warehouses.allow_negative_inventory`` is a real column, default false.
  - ``services/stock_service.py`` implements the rule as

        if new_qty_pws < 0 and not warehouse.allow_negative_inventory:
            log_financial(...)
            raise ValueError(...)

    in both branches - when a stock row exists and when it does not.
  - ``test_negative_inventory_ils_sale.py`` has a test named
    ``test_sale_with_zero_stock_negative_inventory_allowed`` that asserts the
    opted-in case works end to end.

So the service deliberately permits negative stock for a warehouse that opts in,
and the constraint rejected it. Three tests failed against a migrated database
with::

    CheckViolation: new row for relation "product_warehouse_stock" violates
    check constraint "ck_pws_quantity"

A CHECK constraint cannot express this rule. "quantity >= 0 *unless* this
warehouse opts out" needs a lookup into another table, and CHECK constraints are
not allowed to reference other tables. That is presumably why the constraint was
written unconditionally: the honest form is not available at that layer.

The service is the correct enforcement point, and the stronger one. It runs
under ``SELECT FOR UPDATE`` on the product_warehouse_stock row, so the
check-and-write is atomic against a concurrent movement. A CHECK constraint is
evaluated per row with no such lock, so two concurrent sales could each read
sufficient stock and each write a negative quantity past it.

Enforcement therefore lives in ``StockService``, and this revision removes the
schema-level version that contradicted it.

downgrade() restores the constraint, and refuses first if any row would
violate it. Recreating a constraint over rows that break it is not a
reversible migration; it is a broken database.

Revision ID: f1c6a8d3b5e9
Revises: e9b2f4a6c1d3
Create Date: 2026-09-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1c6a8d3b5e9"
down_revision = "e9b2f4a6c1d3"
branch_labels = None
depends_on = None

_TABLE = "product_warehouse_stock"
_CONSTRAINT = "ck_pws_quantity"
_PREDICATE = "quantity >= 0"


def _has_constraint(bind) -> bool:
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :n"),
            {"n": _CONSTRAINT},
        ).fetchone()
    )


def _negative_rows(bind) -> int:
    return int(
        bind.execute(
            sa.text(f"SELECT count(*) FROM {_TABLE} WHERE quantity < 0"),
        ).scalar_one()
    )


def upgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        return
    if not _has_constraint(bind):
        return
    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.drop_constraint(_CONSTRAINT, type_="check")


def downgrade() -> None:
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        return
    if _has_constraint(bind):
        return

    negatives = _negative_rows(bind)
    if negatives:
        raise RuntimeError(
            f"cannot restore {_CONSTRAINT}: {_TABLE} holds {negatives} row(s) with "
            "a negative quantity. Those rows are legitimate for warehouses with "
            "allow_negative_inventory set, and recreating the constraint would "
            "leave the table permanently un-writable for stock movements. "
            "Correct the quantities or drop the affected warehouses' opt-in "
            "before retrying."
        )

    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.create_check_constraint(_CONSTRAINT, sa.text(_PREDICATE))
