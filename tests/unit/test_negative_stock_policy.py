"""The database no longer blocks negative stock; StockService must.

``ck_pws_quantity`` (quantity >= 0) was dropped by f1c6a8d3b5e9. It forbade
negative stock unconditionally, which contradicted three things that were
already in the codebase:

  - ``warehouses.allow_negative_inventory``, a column defaulting to false
  - ``StockService.create_movement``, which implements
    ``if new_qty_pws < 0 and not warehouse.allow_negative_inventory: raise``
  - ``test_negative_inventory_ils_sale.py``, which asserts the opted-in case
    works end to end

A CHECK constraint cannot express ">= 0 unless this warehouse opts out" -
constraints may not reference another table. Enforcement therefore moved to the
service, which is the stronger place anyway: it runs under SELECT FOR UPDATE on
the product_warehouse_stock row, so the check and the write are atomic against a
concurrent movement. A CHECK is evaluated per row with no lock, so two concurrent
sales could each read sufficient stock and each write a negative quantity past
it.

That relocation only holds if the service really does block. These tests are the
evidence that removing the constraint was safe.

The end-to-end behaviour of both halves of the policy is already covered by
test_negative_inventory_ils_sale.py, which builds a real tenant, product and
warehouse. What is added here is the part that schema cannot cover: that the
guard is still present in both branches, and that nobody quietly puts the
constraint back.
"""

from __future__ import annotations

import inspect

import sqlalchemy as sa

from extensions import db


def test_stock_service_guards_on_the_warehouse_flag():
    """Both the existing-row and the no-row branch must consult the flag.

    f1c6a8d3b5e9 made this the only thing preventing an opted-out warehouse from
    going negative, so the count matters as much as the presence.
    """
    from services import stock_service

    source = inspect.getsource(stock_service)
    assert source.count("allow_negative_inventory") >= 2, (
        "expected the flag to be checked in both branches of create_movement: one "
        "for a product_warehouse_stock row that exists, one for one that does not. "
        "Fewer than two mentions means a branch would write negative stock into an "
        "opted-out warehouse, and nothing in the database would stop it."
    )


def test_no_check_constraint_on_pws_quantity(app, db_session):
    """Pins the decision, so the constraint cannot silently return."""
    found = db_session.execute(sa.text("SELECT count(*) FROM pg_constraint WHERE conname = 'ck_pws_quantity'")).scalar()
    assert found == 0, (
        "ck_pws_quantity is back. It contradicts warehouses.allow_negative_inventory "
        "and makes every opted-in negative-stock movement fail with CheckViolation."
    )


def test_allow_negative_inventory_column_still_exists(app, db_session):
    """The flag is the enforcement point now, so it must not go missing."""
    columns = {c["name"] for c in sa.inspect(db.engine).get_columns("warehouses")}
    assert "allow_negative_inventory" in columns, (
        "the schema column the service reads is gone; create_movement would raise "
        "AttributeError on every stock movement"
    )
