"""Pins the schema-constraint repairs that CI keeps rediscovering.

Each test here corresponds to a constraint or column that was wrong in the
migrated schema while the models and services disagreed with it, and that only
surfaced once the test suite stopped building its database with db.create_all().

The recurring shape: the schema and the code are two independent statements of
the same fact, nothing compares them, and a locally-passing suite is
structurally blind to it because the one test covering the path mocks the writer.
"""

from __future__ import annotations

import sqlalchemy as sa

from extensions import db


def _constraint(connection, name):
    row = connection.execute(
        sa.text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n"),
        {"n": name},
    ).fetchone()
    return row[0] if row else None


# --------------------------------------------------------------------------
# a3d7f1b9c6e2 - ck_sales_status
# --------------------------------------------------------------------------

# 86afead128ce allowed draft/confirmed/cancelled/returned.
# utils.field_validators.ALLOWED_SALE_STATUSES is
# pending/confirmed/cancelled/completed, and store_checkout_service.py:253 passes
# sale_status="pending" - the deferred-fulfilment storefront path.
_VALID_SALE_STATUSES = frozenset({"draft", "pending", "confirmed", "completed", "cancelled", "returned"})


def test_sales_status_constraint_accepts_every_valid_status(app, db_session):
    definition = _constraint(db_session.connection(), "ck_sales_status")
    assert definition, "ck_sales_status is missing from the migrated schema"

    missing = [s for s in sorted(_VALID_SALE_STATUSES) if f"'{s}'" not in definition]
    assert not missing, (
        f"ck_sales_status rejects {missing}, but ALLOWED_SALE_STATUSES in "
        f"utils/field_validators.py lists them as valid. A storefront checkout that "
        f"defers fulfilment writes status='pending' and would fail with CheckViolation. "
        f"Schema: {definition}"
    )


def test_sales_status_constraint_still_guards(app, db_session):
    definition = _constraint(db_session.connection(), "ck_sales_status")
    assert definition is not None
    for bogus in ("nonsense", "PENDING", ""):
        assert f"'{bogus}'" not in definition


def test_storefront_writes_a_status_the_schema_allows():
    """The two sources must not drift apart again.

    store_checkout_service passes sale_status='pending'; if someone narrows the
    constraint without noticing, this fails before a customer checkout does.
    """
    import inspect
    import re

    from services import store_checkout_service

    statuses = set(re.findall(r'sale_status\s*=\s*["\']([a-z_]+)["\']', inspect.getsource(store_checkout_service)))
    assert statuses, "could not read the sale_status values from the checkout service"
    assert statuses <= _VALID_SALE_STATUSES, (
        f"store checkout writes {statuses - _VALID_SALE_STATUSES}, which is neither in "
        "ALLOWED_SALE_STATUSES nor in ck_sales_status"
    )


# --------------------------------------------------------------------------
# c4a7d1e9f0b2 - pos_kds_orders.notes
# --------------------------------------------------------------------------


def test_pos_kds_orders_has_notes_column(app, db_session):
    """The exact regression: UndefinedColumn on pos_kds_orders.notes."""
    columns = {c["name"] for c in sa.inspect(db.engine).get_columns("pos_kds_orders")}
    assert "notes" in columns, (
        "PosKdsOrder.notes is in models/pos_kds_order.py but the migrated schema has no "
        "such column. c4a7d1e9f0b2 exists to add it."
    )


def test_pos_kds_orders_notes_matches_the_model(app, db_session):
    column = next(
        (c for c in sa.inspect(db.engine).get_columns("pos_kds_orders") if c["name"] == "notes"),
        None,
    )
    assert column is not None
    assert column["nullable"] is True
    assert column["type"].python_type is str


# --------------------------------------------------------------------------
# e9b2f4a6c1d3 - ck_purchases_status
# --------------------------------------------------------------------------

# There is deliberately no single source of truth for purchase status anywhere
# in the codebase - not a model constant, not a validator. That absence is the
# underlying defect: 86afead128ce hard-coded three values against a model that
# documents seven, and nothing could tell it was wrong.
_REQUIRED_PURCHASE_STATUSES = frozenset(
    {
        "draft",
        "submitted",
        "confirmed",
        "partially_received",
        "received",
        "closed",
        "cancelled",
    }
)


def test_purchases_status_constraint_covers_every_valid_status(app, db_session):
    definition = _constraint(db_session.connection(), "ck_purchases_status")
    assert definition, "ck_purchases_status is missing from the migrated schema"

    missing = [s for s in sorted(_REQUIRED_PURCHASE_STATUSES) if f"'{s}'" not in definition]
    assert not missing, (
        f"ck_purchases_status rejects {missing}, which are statuses the app legitimately writes. Schema: {definition}"
    )


def test_purchases_status_constraint_still_guards(app, db_session):
    definition = _constraint(db_session.connection(), "ck_purchases_status")
    assert definition is not None
    for bogus in ("nonsense", "approved", "Draft"):
        assert f"'{bogus}'" not in definition
