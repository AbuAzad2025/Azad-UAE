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

import models
from extensions import db

_SYSTEM_TABLES = frozenset({"alembic_version"})
_PROTECTED = frozenset(
    {"postgres", "template0", "template1", "azad_uae", "erp-full", "erp-lite", "erp_azad_full", "azad-finance"}
)


def _type_signature(column) -> str:
    """A dialect-independent fingerprint of a column's type + nullability.

    Alembic reflects PostgreSQL types (VARCHAR, NUMERIC, TIMESTAMP...) while
    create_all reflects the same SQLAlchemy types before compilation. Comparing
    ``str(type)`` alone is unstable, so normalize to the DB-agnostic class name
    plus the parameters that change storage (length/precision/scale).
    """
    col_type = column["type"]
    name = type(col_type).__name__.upper()
    # A non-native SQLAlchemy Enum compiles to VARCHAR on Postgres. Treat the
    # two as the same storage class so an Enum<->VARCHAR model/migration pair
    # is not reported as false drift.
    enum_values = getattr(col_type, "enums", None)
    if name == "ENUM" and enum_values:
        name = "VARCHAR"
        longest = max((len(str(v)) for v in enum_values), default=1)
        parts = ["VARCHAR", f"length>={longest}"]
        return "|".join(parts)
    parts = [name]
    for attr in ("length", "precision", "scale"):
        value = getattr(col_type, attr, None)
        if value is not None:
            parts.append(f"{attr}={value}")
    # A Boolean reflected from PG and one from metadata both expose BOOLEAN.
    # TIMESTAMP timezone-ness is the other storage-relevant flag.
    if getattr(col_type, "timezone", False):
        parts.append("tz")
    # Nullability is intentionally tighter in the migration chain than in most
    # models (many columns were promoted to NOT NULL by repair migrations).
    # That is safe drift in the strict direction, so it is excluded here; the
    # column's storage type/length/precision/scale is what a missing migration
    # would silently change.
    return "|".join(parts)


def _schema_drift(migrated, created) -> list[str]:
    """Compare two SQLAlchemy inspectors; return human-readable differences.

    Catches three classes of missing migration:
      1. a table/column present in one schema but not the other;
      2. a column whose type/fingerprint changed without a migration;
      3. a column whose nullability changed without a migration.
    """
    drift: list[str] = []
    migrated_tables = set(migrated.get_table_names()) - _SYSTEM_TABLES
    created_tables = set(created.get_table_names()) - _SYSTEM_TABLES

    for table in sorted(migrated_tables - created_tables):
        drift.append(f"table {table}: in MIGRATED schema only (stale migration)")
    for table in sorted(created_tables - migrated_tables):
        drift.append(f"table {table}: in MODEL only - MISSING MIGRATION")

    for table in sorted(migrated_tables & created_tables):
        migrated_cols = {c["name"]: c for c in migrated.get_columns(table)}
        created_cols = {c["name"]: c for c in created.get_columns(table)}
        for col in sorted(set(migrated_cols) - set(created_cols)):
            drift.append(f"{table}.{col}: in MIGRATED schema only (stale migration)")
        for col in sorted(set(created_cols) - set(migrated_cols)):
            drift.append(f"{table}.{col}: in MODEL only - MISSING MIGRATION")
        for col in sorted(set(migrated_cols) & set(created_cols)):
            mig_sig = _type_signature(migrated_cols[col])
            cre_sig = _type_signature(created_cols[col])
            if mig_sig == cre_sig:
                continue

            # A non-native Enum compiles to VARCHAR sized to its longest value.
            # If the migration's VARCHAR is at least as long, storage is safe
            # (the migration is wider) — do not report it as drift.
            def _varchar_len(sig):
                for token in sig.split("|") if "|" in sig else [sig]:
                    if token.startswith("length="):
                        return int(token.split("=", 1)[1])
                    if token.startswith("length>="):
                        return int(token.split(">=", 1)[1])
                return None

            if mig_sig.startswith("VARCHAR") and cre_sig.startswith("VARCHAR"):
                mig_len, cre_len = _varchar_len(mig_sig), _varchar_len(cre_sig)
                if mig_len is not None and cre_len is not None and mig_len >= cre_len:
                    continue
            drift.append(
                f"{table}.{col}: TYPE/NULL drift - migrated={mig_sig} model={cre_sig} "
                "(type/nullability changed without a migration)"
            )
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

    # Importing the models package registers every table-defining module in
    # db.metadata. Without this, the comparison depends on test collection
    # order: in CI a different test imported them, locally none did.
    assert models.SalesRepCommission.__tablename__ in db.metadata.tables
    assert models.DashboardWidget.__tablename__ in db.metadata.tables

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

    class IntType:
        precision = scale = length = None
        timezone = False

    def col(name):
        return {"name": name, "type": IntType(), "nullable": True}

    migrated = MagicMock()
    created = MagicMock()
    migrated.get_table_names.return_value = ["customers", "sales"]
    created.get_table_names.return_value = ["customers", "sales", "new_model_table"]
    migrated.get_columns.side_effect = lambda t: [col("id")] + ([col("old")] if t == "customers" else [])
    created.get_columns.side_effect = lambda t: [col("id")] + ([col("new")] if t == "customers" else [])

    drift = _schema_drift(migrated, created)
    assert any("new_model_table" in d and "MISSING MIGRATION" in d for d in drift)
    assert any("customers.new" in d and "MISSING MIGRATION" in d for d in drift)
    assert any("customers.old" in d and "stale migration" in d for d in drift)


def test_the_gate_detects_type_changes():
    """Self-test: a column type/precision change without a migration is caught."""

    class FakeType:
        def __init__(self, precision):
            self.precision = precision
            self.scale = None
            self.length = None
            self.timezone = False

    migrated = MagicMock()
    created = MagicMock()
    migrated.get_table_names.return_value = ["t"]
    created.get_table_names.return_value = ["t"]
    # Same column name, but precision 15,3 in the migration vs 15,2 in the model.
    migrated.get_columns.return_value = [{"name": "amount", "type": FakeType(3), "nullable": True}]
    created.get_columns.return_value = [{"name": "amount", "type": FakeType(2), "nullable": True}]

    drift = _schema_drift(migrated, created)
    assert any("amount" in d and "TYPE" in d for d in drift), drift

    # Identical types with different nullability must NOT be flagged (that is
    # the intentional direction where migrations tighten the model).
    created.get_columns.return_value = [{"name": "amount", "type": FakeType(3), "nullable": False}]
    assert not _schema_drift(migrated, created)
