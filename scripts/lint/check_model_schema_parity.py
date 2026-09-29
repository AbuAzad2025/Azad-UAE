"""Compare live Alembic-built schema against the SQLAlchemy model metadata.

``db.create_all()`` silently reconciled model metadata with the database, which
meant a column added to a model but never given a migration simply appeared on
any developer's machine and never reached a migrated environment. The Alembic
round-trip in CI cannot catch that either: it only proves the chain replays, not
that the chain produces the schema the code expects.

This gate boots the app, reads ``db.metadata`` and the live ``information_schema``
and reports every table/column/index/constraint that exists in one and not the
other. It is meant to run against a database that was built purely by
``flask db upgrade``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import inspect, text  # noqa: E402

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_ERROR = 2

# Alembic owns this one; it is not a model and is expected to exist.
_SYSTEM_TABLES = frozenset({"alembic_version"})


def _column_drift(inspector, metadata) -> list[str]:
    findings: list[str] = []
    meta_tables = set(metadata.tables)
    live_tables = set(inspector.get_table_names())
    schema = inspector.default_schema_name

    for table in sorted(meta_tables & live_tables):
        live = {c["name"] for c in inspector.get_columns(table)}
        modelled = {c.name for c in metadata.tables[table].columns}
        for column in sorted(modelled - live):
            findings.append(f"column {schema}.{table}.{column} is in the model but not in the schema")
        for column in sorted(live - modelled):
            findings.append(f"column {schema}.{table}.{column} is in the schema but not in the model")

    for table in sorted(live_tables - meta_tables):
        if table in _SYSTEM_TABLES:
            continue
        findings.append(f"table {schema}.{table} is in the schema but not in the models")

    return findings


def _index_drift(inspector, metadata) -> list[str]:
    findings: list[str] = []
    shared = set(metadata.tables) & set(inspector.get_table_names())
    for table in sorted(shared):
        live = {i["name"] for i in inspector.get_indexes(table)}
        modelled = {i.name for i in metadata.tables[table].indexes if i.name is not None}
        for index in sorted(live - modelled):
            findings.append(f"index {table}.{index} is in the schema but not in the model")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument(
        "--indexes",
        action="store_true",
        help="also diff indexes (slower on a large database)",
    )
    args = parser.parse_args()

    import warnings

    from app import create_app
    from extensions import db

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        app = create_app()

    with app.app_context():
        if not app.extensions.get("schema_ready"):
            print(
                "Model/schema parity: SKIPPED - the database is not migrated. Run `flask db upgrade` first.",
            )
            return EXIT_OK

        inspector = inspect(db.engine)
        version = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        table_count = len(inspector.get_table_names())

        findings = _column_drift(inspector, db.metadata)
        if args.indexes:
            findings += _index_drift(inspector, db.metadata)

        print(f"Model/schema parity: head={version} tables={table_count}")
        if not findings:
            print("OK: models and the migrated schema agree on every table and column.")
            return EXIT_OK

        print(f"DRIFT: {len(findings)} difference(s) between the models and the schema.")
        for line in findings[: args.limit]:
            print(f"  - {line}")
        if len(findings) > args.limit:
            print(f"  ... and {len(findings) - args.limit} more")
        print(
            "  A model column with no migration reaches developer's machines via\n"
            "  db.create_all() and never reaches a migrated environment. Give every\n"
            "  column a migration, or remove it from the model."
        )
        return EXIT_DRIFT


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - a lint gate must not traceback
        print(f"Model/schema parity: ERROR - {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(EXIT_ERROR)
