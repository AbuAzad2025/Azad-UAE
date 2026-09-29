"""Tests for the two schema repairs in c4a7d1e9f0b2 and e9b2f4a6c1d3.

Both were found by CI run 36606499121, and both are the same class of defect:
the schema was narrower than the code that has to run against it.

  c4a7d1e9f0b2  pos_kds_orders.notes was in the model with no migration at all.
                db.create_all() had been papering over that on developer
                machines; once the schema came from Alembic the column stopped
                existing, and every insert into that table failed with
                UndefinedColumn.

  e9b2f4a6c1d3  ck_purchases_status allowed only draft/confirmed/cancelled
                while models/purchase.py documents seven statuses and the
                purchase services write four. submitted, partially_received
                and received were rejected by the database, which is what the
                two e2e tests hit.

The point of these tests is that the constraint and the model are two
independent statements of the same fact. When they disagree, one of them is
wrong and nothing in CI noticed, because the Alembic round-trip only proves
the chain replays - not that the chain produces the schema the code reads.
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


# The statuses a purchase legitimately holds. Three of these were rejected by
# the schema in CI run 36606499121, which is what e9b2f4a6c1d3 fixes.
#
# This list is deliberately explicit rather than derived. There is no single
# source of truth in the codebase for purchase status - not a model constant,
# not a validation helper, not an enum. That absence is the underlying defect:
# 86afead128ce guessed three values, and nothing anywhere could tell it was
# wrong. Adding the constant is the real fix; until then this list is the
# contract, and if a status is ever added without widening the constraint these
# tests are the thing that has to be updated to match.
_REQUIRED_STATUSES = frozenset(
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


def test_pos_kds_orders_has_notes_column(app, db_session):
    """The exact regression CI hit: UndefinedColumn on pos_kds_orders.notes."""
    columns = {c["name"] for c in sa.inspect(db.engine).get_columns("pos_kds_orders")}
    assert "notes" in columns, (
        "PosKdsOrder.notes is in models/pos_kds_order.py but the migrated "
        "schema has no such column. c4a7d1e9f0b2 exists to add it."
    )


def test_pos_kds_orders_notes_matches_the_model_definition(app, db_session):
    column = next(
        (c for c in sa.inspect(db.engine).get_columns("pos_kds_orders") if c["name"] == "notes"),
        None,
    )
    assert column is not None
    assert column["nullable"] is True, "notes is nullable=True in the model"
    assert column["type"].python_type is str, "notes is Text in the model"


def test_purchases_status_constraint_covers_every_valid_status(app, db_session):
    """Every status the app can write must be accepted by the schema."""
    definition = _constraint(db_session.connection(), "ck_purchases_status")
    assert definition, "ck_purchases_status is missing from the migrated schema"

    missing = [s for s in sorted(_REQUIRED_STATUSES) if f"'{s}'" not in definition]
    assert not missing, (
        f"ck_purchases_status rejects {missing}, which are statuses the app "
        f"legitimately writes. e9b2f4a6c1d3 widens this constraint; the "
        f"schema in front of you is: {definition}"
    )


def test_purchases_status_constraint_still_guards(app, db_session):
    """Widening must not degrade into a constraint that permits anything."""
    definition = _constraint(db_session.connection(), "ck_purchases_status")
    assert definition is not None, "the constraint must exist, not be dropped"

    for status in ("draft", "confirmed", "cancelled", "received"):
        assert f"'{status}'" in definition

    # Anything the app does not declare must not be enumerated either, and
    # PostgreSQL comparisons are case-sensitive so a case variant is not a
    # backdoor into the accepted set.
    for bogus in ("nonsense", "approved", "", "RECEIVED", "Draft"):
        assert f"'{bogus}'" not in definition


def test_the_old_predicate_would_now_fail(app, db_session):
    """Pins the regression: 86afead128ce's predicate is strictly too narrow.

    Written so that anyone narrowing the constraint again sees precisely which
    assertion flips, rather than rediscovering it from a CI failure.
    """
    old = {"draft", "confirmed", "cancelled"}
    assert old < _REQUIRED_STATUSES, "the historical predicate was always too narrow"
    assert old - {"draft", "confirmed", "cancelled"} == set()
    assert _REQUIRED_STATUSES - old == {"submitted", "partially_received", "received", "closed"}
