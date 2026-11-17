"""A model with no migration must fail the moment it is introduced.

The suite's main database is built by ``alembic upgrade head`` (see the ``app``
fixture), so a column added to a model without a migration is invisible to it.
This test builds a SECOND database from the same model metadata with
``db.create_all()`` and diffs the two schemas. Any table or column that exists
in one and not the other is a missing (or stale) migration, and fails here
instead of surfacing weeks later in a migrated environment.

``alembic_version`` is the only allowed difference: it is owned by Alembic and
does not exist in the model metadata.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from extensions import db

_SYSTEM_TABLES = frozenset({"alembic_version"})
_PROTECTED = frozenset(
    {"postgres", "template0", "template1", "azad_uae", "erp-full", "erp-lite", "erp_azad_full", "azad-finance"}
)


def _schema_drift(migrated, created) -> list[str]:
    """Compare two SQLAlchemy inspectors; return human-readable differences."""
    drift: list[str] = []
    migrated_tables = set(migrated.get_table_names()) - _SYSTEM_TABLES
    created_tables = set(created.get_table_names()) - _SYSTEM_TABLES

    for table in sorted(migrated_tables - created_tables):
        drift.append(f"table {table}: in MIGRATED schema only (stale migration)")
    for table in sorted(created_tables - migrated_tables):
        drift.append(f"table {table}: in MODEL only - MISSING MIGRATION")

    for table in sorted(migrated_tables & created_tables):
        migrated_cols = {c["name"] for c in migrated.get_columns(table)}
        created_cols = {c["name"] for c in created.get_columns(table)}
        for col in sorted(migrated_cols - created_cols):
            drift.append(f"{table}.{col}: in MIGRATED schema only (stale migration)")
        for col in sorted(created_cols - migrated_cols):
            drift.append(f"{table}.{col}: in MODEL only - MISSING MIGRATION")
    return drift


def _urls():
    test_url = sa.engine.make_url(os.environ["TEST_DATABASE_URL"])
    name = f"{test_url.database}_createall"
    assert name not in _PROTECTED and name.endswith("_createall"), f"Refusing unsafe scratch DB name: {name}"
    return test_url, name


def _admin_engine(test_url):
    return sa.create_engine(
        test_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 3},
    )


@pytest.fixture(scope="module")
def metadata_schema():
    """A throw-away schema built purely from db.metadata (db.create_all)."""
    test_url, name = _urls()

    admin = _admin_engine(test_url)
    try:
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
            conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()

    engine = sa.create_engine(test_url.set(database=name), poolclass=NullPool)
    try:
        db.metadata.create_all(engine)
        yield sa.inspect(engine), name
    finally:
        engine.dispose()
        admin = _admin_engine(test_url)
        try:
            with admin.connect() as conn:
                conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        finally:
            admin.dispose()


def test_migrated_and_model_schemas_are_identical(app, metadata_schema):
    created, name = metadata_schema
    drift = _schema_drift(sa.inspect(db.engine), created)
    assert not drift, "Alembic chain vs model metadata drift:\n  " + "\n  ".join(drift[:40]) + f"\n  scratch: {name}"


def test_the_gate_actually_detects_a_missing_migration():
    """Self-test: a column present only in create_all must fail the gate.

    Without this, a bug in the comparison (or a future 'temporary' skip) could
    leave the gate green while reporting nothing.
    """
    migrated = MagicMock()
    created = MagicMock()
    migrated.get_table_names.return_value = ["customers", "sales"]
    created.get_table_names.return_value = ["customers", "sales", "new_model_table"]
    migrated.get_columns.side_effect = lambda t: [{"name": "id"}] + ([{"name": "old"}] if t == "customers" else [])
    created.get_columns.side_effect = lambda t: [{"name": "id"}] + ([{"name": "new"}] if t == "customers" else [])

    drift = _schema_drift(migrated, created)
    assert any("new_model_table" in d and "MISSING MIGRATION" in d for d in drift)
    assert any("customers.new" in d and "MISSING MIGRATION" in d for d in drift)
    assert any("customers.old" in d and "stale migration" in d for d in drift)
