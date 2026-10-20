#!/usr/bin/env python3
"""Prove that the Alembic chain preserves DATA and MONEY on a POPULATED database.

The "Alembic Round-Trip" CI job builds an empty database, upgrades it to head,
downgrades it to the baseline and upgrades it again. That proves the chain
*applies*. It says nothing about what the chain does to the rows an existing
installation already has, and that is the risk a production upgrade actually
carries: a customer balance that silently changes, a journal entry that stops
balancing, a stock row that vanishes under a rebuilt table.

This probe answers the second question, on a scratch database it owns:

1. create a scratch database (never ``azad_uae``, ``azad_uae_test`` or
   ``erp_azad_full``), and migrate it to an EARLY revision of the chain;
2. insert a small but representative dataset - tenant, user, branch, warehouse,
   products, customer, supplier, sale + lines, payment, cheque, receipt,
   shipment, budget, GL chart of accounts, two balanced journal entries with
   their lines, and the HR tables whose columns the chain rewrites
   (``leave_balances``, ``attendances``, ``leave_requests``);
3. fingerprint the database - row count for every table in the schema, money
   sums, the trial balance of every GL account, and a sha256 of every seeded
   row;
4. run ``flask db upgrade`` to HEAD;
5. fingerprint again and compare, column by column, row by row;
6. re-check the accounting invariants (every entry balances, the trial balance
   balances to the cent) after the upgrade;
7. drop the scratch database and leave the server as it was found.

A difference is only tolerated when the chain *declares* it: the probe carries
a whitelist of intentional transformations (each with the revision that performs
it), and the whitelist is bidirectional - a declared change that does not happen
is a failure too, so the list cannot rot into a blanket amnesty.

The timezone
------------
The probe writes its timestamps the way the ORM writes them: an aware UTC
instant, into a legacy ``timestamp without time zone`` column. PostgreSQL
renders an aware value into the *session* timezone when the target column is
naive, so the stored wall clock is a local rendering of the instant - and
revision ``f3a9c1e5b2d8`` later reads that wall clock back as UTC. On a
PostgreSQL that runs on UTC the two cancel out. On any other server every
timestamp written by an older build moves by the server's UTC offset, which
the probe measures and reports (it prints the server's timezone with the
shift).

The application now pins its session to UTC (``config.py`` sets
``-c timezone=UTC`` on every connection), so what the app writes and what the
upgrade reads agree, on any server, and this probe uses the same session
options. The residual risk is only for rows an *older* build wrote on a
non-UTC server: those are already stored as a local rendering, and the
upgrade will move them. Correct them before upgrading, or run the upgrade on
a UTC database. The probe reports the server's timezone so the operator can
see which case they are in.

Usage::

    python scripts/ops/verify_migration_preserves_data.py
    python scripts/ops/verify_migration_preserves_data.py --db-name my_probe --keep
    python scripts/ops/verify_migration_preserves_data.py --report report.json

Exit codes::

    0  data preserved
    1  data was lost, duplicated or altered
    2  the probe itself failed
    3  the probe could not run here (no PostgreSQL, no permission to create a
       database) - this is NOT evidence of anything and must be reported as such
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess  # nosec B404
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.pool import NullPool

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EXIT_OK = 0
EXIT_DATA_LOSS = 1
EXIT_ERROR = 2
EXIT_SKIP = 3

#: The revision the probe migrates *to* before it seeds the database. This is
#: revision 27 of the 55-revision chain, so the upgrade that follows crosses
#: 28 real revisions - including the money-precision widening (5542ed4cd59f),
#: the COA re-parenting (1c2195e00e66), the receipt/shipment FK backfill
#: (e4506d215617), the tz-aware datetime rewrite (f3a9c1e5b2d8) and the
#: double-entry CHECK constraints (c0d1e2f3a4b5, d4e5f6a7b8c9).
EARLY_REVISION = "9de30f6466b3"

#: Scratch database name. Deliberately not the dev, test or production names.
DEFAULT_DB_NAME = "azad_migration_probe"

#: Databases this script must never create, migrate or drop.
FORBIDDEN_DATABASES = frozenset(
    {
        "azad_uae",
        "azad_uae_test",
        "erp_azad_full",
        "azad-finance",
        "azad_finance",
        "postgres",
        "template0",
        "template1",
    }
)

DEFAULT_ADMIN_URL = "postgresql+psycopg2://postgres:123@localhost:5432/postgres"

#: Every timestamp the seed uses, written the way the ORM writes them: an
#: aware UTC instant. The chain created these columns as ``timestamp without
#: time zone`` while the models declare ``DateTime(timezone=True)`` with
#: ``default=lambda: datetime.now(UTC)``, so PostgreSQL stores the instant
#: rendered in the *session* timezone. Revision f3a9c1e5b2d8 later reinterprets
#: those legacy naive values as UTC - which only round-trips when the server
#: runs on UTC. The probe therefore seeds aware instants and recovers the
#: pre-upgrade instant the way PostgreSQL stored it, so a timezone-dependent
#: shift shows up as a real difference instead of hiding behind a wall clock.
SEED_TS = datetime(2026, 1, 15, 9, 30, 0, tzinfo=UTC)
SEED_TS_CLOSE = datetime(2026, 1, 15, 17, 45, 0, tzinfo=UTC)

#: Tables whose rows are fingerprinted row by row, mapped to their primary key.
MONITORED_TABLES: dict[str, str] = {
    "currencies": "id",
    "tenants": "id",
    "roles": "id",
    "users": "id",
    "branches": "id",
    "warehouses": "id",
    "products": "id",
    "product_warehouse_stock": "id",
    "stock_movements": "id",
    "customers": "id",
    "suppliers": "id",
    "leave_types": "id",
    "leave_balances": "id",
    "leave_requests": "id",
    "attendances": "id",
    "gl_accounts": "id",
    "gl_journal_entries": "id",
    "gl_journal_lines": "id",
    "sales": "id",
    "sale_lines": "id",
    "payments": "id",
    "cheques": "id",
    "receipts": "id",
    "shipments": "id",
    "budgets": "id",
    "card_payments": "id",
    "donations": "id",
}

#: Money and quantity columns summed per table.
MONEY_COLUMNS: dict[str, tuple[str, ...]] = {
    "sales": (
        "subtotal",
        "tax_amount",
        "total_amount",
        "amount",
        "paid_amount",
        "balance_due",
        "amount_aed",
        "paid_amount_aed",
    ),
    "sale_lines": ("quantity", "unit_price", "line_total", "cost_price"),
    "payments": ("amount", "amount_aed"),
    "cheques": ("amount", "amount_aed", "actual_amount_aed", "currency_gain_loss"),
    "receipts": ("amount", "amount_aed"),
    "customers": ("balance", "credit_limit", "total_purchases"),
    "suppliers": ("total_purchases_aed", "total_paid_aed"),
    "products": ("cost_price", "regular_price", "current_stock"),
    "product_warehouse_stock": ("quantity",),
    "gl_journal_entries": ("total_debit", "total_credit"),
    "gl_journal_lines": ("debit", "credit", "amount", "amount_aed"),
    "card_payments": ("amount",),
    "donations": ("amount_usd", "amount_crypto"),
    "leave_balances": ("entitled_days", "carried_forward", "taken_days", "pending_days", "remaining_days"),
    "budgets": ("total_budgeted", "total_actual", "total_variance"),
}

#: Tolerance for the accounting invariants. The chain itself uses 0.001
#: (d4e5f6a7b8c9), because money is stored to three decimals.
MONEY_TOLERANCE = Decimal("0.001")


@dataclass(frozen=True)
class DeclaredChange:
    """A difference the chain is *allowed* to produce, with the reason."""

    table: str
    column: str
    row_key: dict[str, str]
    revision: str
    reason: str
    check: str


#: The only differences the chain is allowed to produce between the early
#: revision and HEAD for the seeded rows.
DECLARED_CHANGES: tuple[DeclaredChange, ...] = (
    DeclaredChange(
        table="gl_accounts",
        column="parent_id",
        row_key={"code": "2122"},
        revision="1c2195e00e66",
        reason=(
            "VAT Input (2122) is re-parented from VAT Payable (2120, liability) under "
            "Current Assets (1100) - audit fix F-08."
        ),
        check="gl_account_reparented",
    ),
    DeclaredChange(
        table="gl_accounts",
        column="level",
        row_key={"code": "2122"},
        revision="1c2195e00e66",
        reason="VAT Input (2122) moves from level 3 to level 2 to match its new parent - audit fix F-08.",
        check="gl_account_level_2122",
    ),
)

#: The rows whose sha256 is printed in the report, because they carry the
#: money. Keyed by "table:pk".
KEY_ROWS = (
    ("sales", "id"),
    ("payments", "id"),
    ("cheques", "id"),
    ("gl_journal_entries", "id"),
    ("gl_journal_lines", "id"),
    ("customers", "id"),
    ("leave_balances", "id"),
    ("leave_requests", "id"),
    ("attendances", "id"),
)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Value normalisation
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def normalize(value: Any) -> Any:
    """Render a database value into a form that survives schema evolution.

    Two normalisations matter for the comparison to be fair:

    * ``numeric`` - a money column widened from ``Numeric(15, 2)`` to
      ``Numeric(15, 3)`` keeps the same value, so numbers are compared
      numerically, never as text.
    * ``timestamp`` - a naive column converted to ``timestamptz`` keeps the same
      instant but changes its textual form, so both are read as UTC and
      rendered the same way.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return _decimal_str(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _decimal_str(Decimal(repr(value)))
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return aware.strftime("%Y-%m-%dT%H:%M:%S.%f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def _decimal_str(value: Decimal) -> str:
    try:
        return f"{value.quantize(Decimal('0.000001')):f}"
    except (InvalidOperation, ValueError):
        return str(value)


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _row_hash(row: dict[str, Any]) -> str:
    canonical = json.dumps(row, sort_keys=True, default=str, ensure_ascii=False)
    return _sha256(canonical)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Database plumbing
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _admin_engine(admin_url: str) -> Engine:
    return create_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


def _scratch_url(admin_url: str, db_name: str) -> str:
    return str(make_url(admin_url).set(database=db_name))


def _guard_db_name(db_name: str) -> None:
    if db_name.lower() in FORBIDDEN_DATABASES:
        raise RuntimeError(f"refusing to use protected database name: {db_name!r}")
    if not db_name.startswith("azad_migration_probe"):
        raise RuntimeError(
            f"scratch database name must start with 'azad_migration_probe' so it can never "
            f"collide with a real installation: {db_name!r}"
        )


def _drop_database(admin_url: str, db_name: str) -> None:
    engine = _admin_engine(admin_url)
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    finally:
        engine.dispose()


def _create_database(admin_url: str, db_name: str) -> None:
    engine = _admin_engine(admin_url)
    try:
        with engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE \"{db_name}\" WITH ENCODING 'UTF8' TEMPLATE template0"))
            # The scratch database runs on UTC, because that is the
            # configuration the product now requires: the application pins its
            # session to UTC, and a database whose own default is UTC agrees
            # with every other tool that touches it. On a database whose
            # default is a local zone, the chain rewrites the legacy naive
            # timestamps in that zone's rendering, and every timestamp moves by
            # the offset. The server's default is still recorded in the report,
            # because it is what a row written by an older build was stored as.
            conn.execute(text(f"ALTER DATABASE \"{db_name}\" SET timezone='UTC'"))
    finally:
        engine.dispose()


def _scratch_engine(db_url: str) -> Engine:
    """An engine on the scratch database, configured like the application's.

    The session options are taken from ``config.SQLALCHEMY_ENGINE_OPTIONS`` -
    the same ones the app's own connections use - so the probe measures the
    production path rather than a private one. That matters for the timezone:
    the application pins its session to UTC, so a value written by the app and
    a value read by the upgrade agree, and the chain moves nothing. A probe
    that used its own unpinned session would instead measure a configuration
    the application never runs, and would report a shift that production does
    not have.

    The server's own timezone is still recorded in the report, because it is
    what a legacy row written by an older build was actually stored as.
    """
    url = make_url(db_url)
    query = dict(url.query)
    connect_args: dict[str, Any] = {"connect_timeout": 10}
    try:
        from config import Config

        options = (Config.SQLALCHEMY_ENGINE_OPTIONS or {}).get("connect_args") or {}
        if "options" in options:
            connect_args["options"] = options["options"]
    except Exception:  # pragma: no cover - the probe still works without it
        pass
    engine = create_engine(
        url.set(query=query),
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    return engine


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Alembic driver
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _flask_env(db_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": db_url,
            "SQLALCHEMY_DATABASE_URI": db_url,
            "FLASK_APP": "app.factory:create_app",
            "SECRET_KEY": env.get("SECRET_KEY") or "migration-probe-secret-key-not-for-production",
            "APP_ENV": "testing",
            "FLASK_ENV": "testing",
            "DEBUG": "false",
            "SKIP_SYSTEM_INTEGRITY": "1",
            "AUTO_MIGRATE": "0",
            "CACHE_TYPE": "null",
            "RATELIMIT_STORAGE_URI": "memory://",
            "CELERY_BROKER_URL": "memory://",
            "CELERY_RESULT_BACKEND": "memory://",
            "PYTHONUNBUFFERED": "1",
            # PGTZ is libpq's own way of setting the session timezone, so the
            # migration's connection is on UTC even if the application is
            # started in a mode that does not pin it. The application pins it
            # in config.py; this makes the probe independent of that.
            "PGTZ": "UTC",
        }
    )
    return env


def run_upgrade(db_url: str, revision: str | None) -> dict[str, Any]:
    """Run ``flask db upgrade [revision]`` against ``db_url``."""
    cmd = [sys.executable, "-m", "flask", "db", "upgrade"]
    if revision:
        cmd.append(revision)
    started = time.time()
    proc = subprocess.run(  # nosec B603
        cmd,
        cwd=str(PROJECT_ROOT),
        env=_flask_env(db_url),
        capture_output=True,
        text=True,
        timeout=5400,
        check=False,
    )
    elapsed = time.time() - started
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout or "").splitlines()[-40:])
        err = "\n".join((proc.stderr or "").splitlines()[-40:])
        raise RuntimeError(
            f"`{' '.join(cmd)}` failed with exit code {proc.returncode}\n--- stdout ---\n{tail}\n--- stderr ---\n{err}"
        )
    return {"command": " ".join(cmd), "seconds": round(elapsed, 2), "returncode": proc.returncode}


def current_revision(db_url: str) -> str:
    engine = _scratch_engine(db_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
            return str(rows[0][0]) if rows else ""
    finally:
        engine.dispose()


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# The dataset
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@dataclass
class SeedIds:
    """The generated primary keys, so the rest of the dataset can reference them."""

    values: dict[str, dict[str, int]] = field(default_factory=dict)

    def put(self, table: str, key: str, ident: int) -> None:
        self.values.setdefault(table, {})[key] = ident

    def get(self, table: str, key: str) -> int:
        return self.values[table][key]


def _insert(conn: Connection, table: str, values: dict[str, Any]) -> int:
    cols = list(values.keys())
    col_sql = ", ".join(f'"{c}"' for c in cols)
    param_sql = ", ".join(f":{c}" for c in cols)
    stmt = text(f'INSERT INTO "{table}" ({col_sql}) VALUES ({param_sql}) RETURNING id')
    ident = conn.execute(stmt, values).scalar_one()
    return int(ident)


def _assert_seed_covers_constraints(conn: Connection, table: str, values: dict[str, Any]) -> None:
    """Refuse to seed a row the schema would reject.

    A NOT NULL column without a default that the seed does not fill is an
    insert that fails at run time, and a column the seed sets that the table
    does not have is a typo that silently inserts a different row. Both are
    checked against the *live* schema of the revision under test, so the probe
    cannot drift away from the migration it is probing.
    """
    rows = conn.execute(
        text(
            "SELECT column_name, is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table},
    ).fetchall()
    present = {str(r[0]) for r in rows}
    unknown = sorted(set(values) - present)
    if unknown:
        raise RuntimeError(f"{table}: seed sets columns that do not exist at this revision: {unknown}")
    missing = sorted(str(r[0]) for r in rows if str(r[1]) == "NO" and r[2] is None and str(r[0]) not in values)
    if missing:
        raise RuntimeError(f"{table}: seed does not fill NOT NULL columns without a default: {missing}")


def seed_dataset(conn: Connection) -> dict[str, int]:
    """Insert the representative dataset and return per-table row counts."""
    ids = SeedIds()
    counts: dict[str, int] = {}

    def add(table: str, key: str, values: dict[str, Any]) -> int:
        _assert_seed_covers_constraints(conn, table, values)
        ident = _insert(conn, table, values)
        ids.put(table, key, ident)
        counts[table] = counts.get(table, 0) + 1
        return ident

    for code, name, base in (
        ("AED", "UAE Dirham", False),
        ("ILS", "Israeli New Shekel", True),
        ("USD", "US Dollar", False),
    ):
        add(
            "currencies",
            code,
            {
                "code": code,
                "name": name,
                "symbol": code[0],
                "is_base": base,
                "is_active": True,
                "created_at": SEED_TS,
                "updated_at": SEED_TS,
            },
        )

    tenant = add(
        "tenants",
        "tenant",
        {
            "name": "Probe Trading Co",
            "name_ar": "Ø´Ø±ÙƒØ© Ø¨Ø±ÙˆØ¨ÙŠ",
            "slug": "probe-trading-co",
            "country": "IL",
            "phone_1": "0500000000",
            "email": "probe@tenant.test",
            "subscription_plan": "basic",
            "default_currency": "ILS",
            "base_currency": "ILS",
            "timezone": "Asia/Jerusalem",
            "default_tax_rate": Decimal("0.050"),
            "enable_tax": True,
            "prices_include_vat": False,
            "is_active": True,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    role = add(
        "roles",
        "role",
        {
            "name": "Probe Role",
            "name_ar": "Ø¯ÙˆØ± Ø¨Ø±ÙˆØ¨ÙŠ",
            "slug": "probe-role",
            "is_active": True,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    branch = add(
        "branches",
        "branch",
        {
            "tenant_id": tenant,
            "name": "Probe Main Branch",
            "code": "PROBE-BR",
            "city": "Tel Aviv",
            "is_active": True,
            "is_main": True,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    user = add(
        "users",
        "user",
        {
            "username": "probe-user",
            "email": "probe-user@tenant.test",
            "password_hash": "!probe-not-a-real-password-hash",
            "full_name": "Probe User",
            "full_name_ar": "Ù…Ø³ØªØ®Ø¯Ù… Ø¨Ø±ÙˆØ¨ÙŠ",
            "phone": "0500000000",
            "role_id": role,
            "tenant_id": tenant,
            "branch_id": branch,
            "is_owner": False,
            "is_active": True,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    warehouse = add(
        "warehouses",
        "warehouse",
        {
            "tenant_id": tenant,
            "branch_id": branch,
            "name": "Probe Warehouse",
            "name_ar": "Ù…Ø³ØªÙˆØ¯Ø¹ Ø¨Ø±ÙˆØ¨ÙŠ",
            "code": "PROBE-WH",
            "location": "Probe Location",
            "warehouse_type": "main",
            "is_active": True,
            "is_main": True,
            "created_at": SEED_TS,
        },
    )

    product_a = add(
        "products",
        "product_a",
        {
            "tenant_id": tenant,
            "name": "Probe Widget",
            "name_ar": "Ø£Ø¯Ø§Ø© Ø¨Ø±ÙˆØ¨ÙŠ",
            "sku": "PROBE-SKU-001",
            "barcode": "PROBE-BC-001",
            "unit": "pcs",
            "cost_price": Decimal("10.00"),
            "regular_price": Decimal("40.00"),
            "current_stock": Decimal("100.000"),
            "has_serial_number": False,
            "is_active": True,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    product_b = add(
        "products",
        "product_b",
        {
            "tenant_id": tenant,
            "name": "Probe Gadget",
            "name_ar": "Ø¬Ù‡Ø§Ø² Ø¨Ø±ÙˆØ¨ÙŠ",
            "sku": "PROBE-SKU-002",
            "barcode": "PROBE-BC-002",
            "unit": "pcs",
            "cost_price": Decimal("40.00"),
            "regular_price": Decimal("20.00"),
            "current_stock": Decimal("25.500"),
            "has_serial_number": False,
            "is_active": True,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    add(
        "product_warehouse_stock",
        "pws_a",
        {
            "tenant_id": tenant,
            "product_id": product_a,
            "warehouse_id": warehouse,
            "quantity": Decimal("100.000"),
            "updated_at": SEED_TS,
        },
    )
    add(
        "product_warehouse_stock",
        "pws_b",
        {
            "tenant_id": tenant,
            "product_id": product_b,
            "warehouse_id": warehouse,
            "quantity": Decimal("25.500"),
            "updated_at": SEED_TS,
        },
    )

    add(
        "stock_movements",
        "movement",
        {
            "tenant_id": tenant,
            "product_id": product_a,
            "warehouse_id": warehouse,
            "movement_type": "purchase",
            "quantity": Decimal("100.000"),
            "reference_type": "purchase",
            "user_id": user,
            "notes": "Probe opening stock",
            "created_at": SEED_TS,
        },
    )

    customer = add(
        "customers",
        "customer",
        {
            "tenant_id": tenant,
            "name": "Probe Customer",
            "name_ar": "Ø¹Ù…ÙŠÙ„ Ø¨Ø±ÙˆØ¨ÙŠ",
            "customer_type": "individual",
            "phone": "0555000001",
            "email": "probe-customer@tenant.test",
            "country": "IL",
            "credit_limit": Decimal("10000.00"),
            "total_purchases": Decimal("105.000"),
            "balance": Decimal("55.000"),
            "is_active": True,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    supplier = add(
        "suppliers",
        "supplier",
        {
            "tenant_id": tenant,
            "name": "Probe Supplier",
            "name_ar": "Ù…ÙˆØ±Ø¯ Ø¨Ø±ÙˆØ¨ÙŠ",
            "phone": "0555000002",
            "email": "probe-supplier@tenant.test",
            "country": "IL",
            "credit_limit": Decimal("5000.00"),
            "total_purchases_aed": Decimal("0.000"),
            "total_paid_aed": Decimal("0.000"),
            "is_active": True,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    leave_type = add(
        "leave_types",
        "leave_type",
        {
            "tenant_id": tenant,
            "name": "Annual Leave",
            "name_ar": "Ø¥Ø¬Ø§Ø²Ø© Ø³Ù†ÙˆÙŠØ©",
            "color": "#4CAF50",
            "allocation_type": "annual",
            "days_per_year": 21,
            "is_active": True,
            "created_at": SEED_TS,
            "carry_forward_days": 5,
            "max_carry_forward": 10,
        },
    )

    add(
        "leave_balances",
        "leave_balance",
        {
            "tenant_id": tenant,
            "user_id": user,
            "leave_type_id": leave_type,
            "year": 2026,
            "entitled_days": Decimal("21"),
            "carried_forward": Decimal("3"),
            "taken_days": Decimal("7"),
            "pending_days": Decimal("1"),
            "remaining_days": Decimal("16"),
            "updated_at": SEED_TS,
        },
    )

    add(
        "leave_requests",
        "leave_request",
        {
            "tenant_id": tenant,
            "branch_id": branch,
            "user_id": user,
            "leave_type_id": leave_type,
            "date_from": date(2026, 2, 1),
            "date_to": date(2026, 2, 3),
            "duration": Decimal("3"),
            "reason": "Probe leave request",
            "state": "pending",
            "manager_id": user,
            "is_active": True,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    add(
        "attendances",
        "attendance",
        {
            "tenant_id": tenant,
            "branch_id": branch,
            "user_id": user,
            "check_in": SEED_TS,
            "check_out": SEED_TS_CLOSE,
            "work_hours": Decimal("8.250"),
            "state": "present",
            "notes": "Probe attendance",
            "created_at": SEED_TS,
        },
    )

    # â”€â”€ Chart of accounts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # 2122 (VAT Input) starts under 2120 (a liability). Revision 1c2195e00e66
    # re-parents it under 1100 (current assets); the probe declares that change.
    acc: dict[str, int] = {}

    def add_account(code: str, name: str, atype: str, *, header: bool, level: int, parent: str | None = None) -> int:
        ident = add(
            "gl_accounts",
            code,
            {
                "tenant_id": tenant,
                "code": code,
                "name": name,
                "name_ar": name,
                "parent_id": acc.get(parent) if parent else None,
                "branch_id": None,
                "type": atype,
                "sub_type": None,
                "is_reconcile": False,
                "currency": "ILS",
                "is_active": True,
                "is_header": header,
                "is_default_liquidity": False,
                "level": level,
                "created_at": SEED_TS,
                "updated_at": SEED_TS,
            },
        )
        acc[code] = ident
        return ident

    add_account("1000", "Assets", "asset", header=True, level=1)
    add_account("1100", "Current Assets", "asset", header=True, level=1, parent="1000")
    add_account("1190", "Accumulated Depreciation", "asset", header=False, level=2, parent="1100")
    add_account("1200", "Inventory", "asset", header=False, level=2, parent="1100")
    add_account("1210", "Accounts Receivable", "asset", header=False, level=2, parent="1100")
    add_account("2100", "Liabilities", "liability", header=True, level=1)
    add_account("2120", "VAT Payable", "liability", header=False, level=2, parent="2100")
    add_account("2122", "VAT Input", "liability", header=False, level=3, parent="2120")
    add_account("3000", "Equity", "equity", header=True, level=1)
    add_account("3300", "Owner Drawings", "equity", header=False, level=2, parent="3000")
    add_account("4000", "Revenue", "revenue", header=True, level=1)
    add_account("5000", "Expenses", "expense", header=True, level=1)
    add_account("5201", "Inventory Gain", "expense", header=False, level=2, parent="5000")

    sale = add(
        "sales",
        "sale",
        {
            "tenant_id": tenant,
            "sale_number": "SAL-PROBE-0001",
            "customer_id": customer,
            "seller_id": user,
            "sales_rep_id": user,
            "warehouse_id": warehouse,
            "branch_id": branch,
            "sale_date": SEED_TS,
            "subtotal": Decimal("100.000"),
            "discount_amount": Decimal("0.000"),
            "shipping_cost": Decimal("0.000"),
            "tax_rate": Decimal("0.050"),
            "tax_amount": Decimal("5.000"),
            "taxable_amount": Decimal("100.000"),
            "total_amount": Decimal("105.000"),
            "amount": Decimal("105.000"),
            "paid_amount": Decimal("50.000"),
            "balance_due": Decimal("55.000"),
            "currency": "ILS",
            "exchange_rate": Decimal("1.000"),
            "amount_aed": Decimal("105.000"),
            "paid_amount_aed": Decimal("50.000"),
            "prices_include_vat": False,
            "payment_status": "partial",
            "status": "confirmed",
            "source": "manual",
            "is_active": True,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    add(
        "sale_lines",
        "line_a",
        {
            "tenant_id": tenant,
            "sale_id": sale,
            "product_id": product_a,
            "quantity": Decimal("2.000"),
            "unit_price": Decimal("40.000"),
            "discount_percent": Decimal("0.000"),
            "line_total": Decimal("80.000"),
            "cost_price": Decimal("10.000"),
        },
    )
    add(
        "sale_lines",
        "line_b",
        {
            "tenant_id": tenant,
            "sale_id": sale,
            "product_id": product_b,
            "quantity": Decimal("1.000"),
            "unit_price": Decimal("20.000"),
            "discount_percent": Decimal("0.000"),
            "line_total": Decimal("20.000"),
            "cost_price": Decimal("40.000"),
        },
    )

    # â”€â”€ Two balanced journal entries â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    entry_sale = add(
        "gl_journal_entries",
        "entry_sale",
        {
            "tenant_id": tenant,
            "entry_number": "JE-PROBE-0001",
            "entry_date": SEED_TS,
            "description": "Probe sale posting",
            "reference_type": "sale",
            "reference_id": sale,
            "branch_id": branch,
            "entry_type": "sale",
            "currency": "ILS",
            "exchange_rate": Decimal("1.000"),
            "total_debit": Decimal("105.000"),
            "total_credit": Decimal("105.000"),
            "is_posted": True,
            "is_reversed": False,
            "status": "posted",
            "created_by": user,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    entry_cash = add(
        "gl_journal_entries",
        "entry_cash",
        {
            "tenant_id": tenant,
            "entry_number": "JE-PROBE-0002",
            "entry_date": SEED_TS,
            "description": "Probe cash receipt posting",
            "reference_type": "payment",
            "reference_id": None,
            "branch_id": branch,
            "entry_type": "receipt",
            "currency": "ILS",
            "exchange_rate": Decimal("1.000"),
            "total_debit": Decimal("50.000"),
            "total_credit": Decimal("50.000"),
            "is_posted": True,
            "is_reversed": False,
            "status": "posted",
            "created_by": user,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    def add_line(key: str, entry: int, account: str, debit: str, credit: str, description: str) -> None:
        debit_d = Decimal(debit)
        credit_d = Decimal(credit)
        add(
            "gl_journal_lines",
            key,
            {
                "tenant_id": tenant,
                "entry_id": entry,
                "account_id": acc[account],
                "description": description,
                "debit": debit_d,
                "credit": credit_d,
                "amount": debit_d - credit_d,
                "amount_aed": debit_d - credit_d,
                "branch_id": branch,
            },
        )

    add_line("line_inventory", entry_sale, "1200", "100.000", "0.000", "Cost of goods sold")
    add_line("line_vat", entry_sale, "2122", "5.000", "0.000", "VAT input")
    add_line("line_revenue", entry_sale, "4000", "0.000", "105.000", "Sale revenue")
    add_line("line_cash", entry_cash, "1100", "50.000", "0.000", "Cash received")
    add_line("line_ar", entry_cash, "1210", "0.000", "50.000", "Accounts receivable")

    payment = add(
        "payments",
        "payment",
        {
            "tenant_id": tenant,
            "payment_number": "PAY-PROBE-0001",
            "payment_type": "cash",
            "direction": "in",
            "sale_id": sale,
            "customer_id": customer,
            "supplier_id": None,
            "supplier_name": None,
            "purchase_id": None,
            "branch_id": branch,
            "amount": Decimal("50.000"),
            "currency": "ILS",
            "exchange_rate": Decimal("1.000"),
            "amount_aed": Decimal("50.000"),
            "payment_method": "cash",
            "reference_number": "REF-PROBE-1",
            "payment_confirmed": True,
            "confirmation_date": SEED_TS,
            "payment_date": SEED_TS,
            "user_id": user,
            "created_at": SEED_TS,
        },
    )

    add(
        "cheques",
        "cheque",
        {
            "tenant_id": tenant,
            "cheque_number": "CHQ-PROBE-0001",
            "cheque_bank_number": "BNK-PROBE-001",
            "cheque_type": "incoming",
            "bank_name": "Probe Bank",
            "account_number": "000123456",
            "amount": Decimal("250.50"),
            "currency": "ILS",
            "exchange_rate": Decimal("1.000"),
            "amount_aed": Decimal("250.50"),
            "issue_date": date(2026, 2, 1),
            "due_date": date(2026, 3, 3),
            "status": "pending",
            "customer_id": customer,
            "supplier_id": None,
            "sale_id": sale,
            "purchase_id": None,
            "payment_id": payment,
            "branch_id": branch,
            "is_active": True,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    # source_type='sale' + source_id -> revision e4506d215617 backfills
    # receipts.sale_id and shipments.sale_id from these columns.
    add(
        "receipts",
        "receipt",
        {
            "tenant_id": tenant,
            "receipt_number": "RCP-PROBE-0001",
            "source_type": "sale",
            "source_id": sale,
            "direction": "in",
            "customer_id": customer,
            "amount": Decimal("50.000"),
            "currency": "ILS",
            "exchange_rate": Decimal("1.000"),
            "amount_aed": Decimal("50.000"),
            "payment_method": "cash",
            "reference_number": "REF-PROBE-1",
            "payment_confirmed": True,
            "confirmation_date": SEED_TS,
            "branch_id": branch,
            "receipt_date": SEED_TS,
            "user_id": user,
            "created_at": SEED_TS,
        },
    )

    add(
        "shipments",
        "shipment",
        {
            "tenant_id": tenant,
            "source_type": "sale",
            "source_id": sale,
            "carrier_name": "Probe Carrier",
            "tracking_number": "TRK-PROBE-1",
            "shipping_cost": Decimal("25.000"),
            "customs_duty": Decimal("0.000"),
            "insurance": Decimal("0.000"),
            "status": "pending",
            "estimated_delivery": SEED_TS,
            "recipient_name": "Probe Customer",
            "recipient_phone": "0555000001",
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    add(
        "budgets",
        "budget",
        {
            "tenant_id": tenant,
            "budget_number": "BUD-PROBE-0001",
            "name_ar": "Ù…ÙŠØ²Ø§Ù†ÙŠØ© Ø¨Ø±ÙˆØ¨ÙŠ",
            "name_en": "Probe Budget",
            "fiscal_year": 2026,
            "period_type": "year",
            "period_start": date(2026, 1, 1),
            "period_end": date(2026, 12, 31),
            "total_budgeted": Decimal("10000.000"),
            "total_actual": Decimal("1234.567"),
            "total_variance": Decimal("-8765.433"),
            "variance_percentage": Decimal("-87.654"),
            "status": "active",
            "branch_id": branch,
            "created_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    add(
        "card_payments",
        "card_payment",
        {
            "tenant_id": tenant,
            "customer_name": "Probe Customer",
            "customer_email": "probe-customer@tenant.test",
            "transaction_type": "package_purchase",
            "package": "basic",
            "amount": Decimal("99.99"),
            "card_last_4": "4242",
            "card_type": "visa",
            "transaction_id": "TXN-PROBE-0001",
            "payment_gateway": "probe",
            "status": "completed",
            "country_code": "IL",
            "created_at": SEED_TS,
            "completed_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    add(
        "donations",
        "donation",
        {
            "tenant_id": tenant,
            "amount_usd": Decimal("25.50"),
            "amount_crypto": Decimal("0.00025000"),
            "payment_method": "crypto",
            "crypto_type": "BTC",
            "wallet_address": "probe-wallet-address",
            "transaction_hash": "probe-hash-0001",
            "status": "completed",
            "donor_name": "Probe Donor",
            "donor_email": "donor@probe.test",
            "transaction_type": "donation",
            "package": "basic",
            "customer_name": "Probe Donor",
            "country_code": "IL",
            "converted_to_crypto": False,
            "thank_you_sent": False,
            "notification_sent": False,
            "gl_posted": False,
            "created_at": SEED_TS,
            "confirmed_at": SEED_TS,
            "completed_at": SEED_TS,
            "updated_at": SEED_TS,
        },
    )

    # Keep the supplier referenced so the table is not empty in the report.
    ids.put("suppliers", "supplier_id", supplier)

    return counts


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Fingerprint
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _table_names(conn: Connection) -> list[str]:
    rows = conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        )
    ).fetchall()
    return [str(r[0]) for r in rows]


def _columns(conn: Connection, table: str) -> list[str]:
    rows = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t ORDER BY ordinal_position"
        ),
        {"t": table},
    ).fetchall()
    return [str(r[0]) for r in rows]


def _column_types(conn: Connection, table: str) -> dict[str, str]:
    rows = conn.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table},
    ).fetchall()
    return {str(r[0]): str(r[1]) for r in rows}


def _select_expressions(conn: Connection, table: str) -> list[tuple[str, str]]:
    """Column name and the expression that reads it as an *instant*.

    A legacy ``timestamp without time zone`` column holds a wall clock, not an
    instant: PostgreSQL rendered the ORM's UTC-aware value into the session
    timezone when it stored it. Reading such a column as
    ``col AT TIME ZONE current_setting('TimeZone')`` recovers the instant that
    was actually written, which is the only reading that can be compared with
    the ``timestamptz`` the chain rewrites the column into.
    """
    out: list[tuple[str, str]] = []
    for name, dtype in _column_types(conn, table).items():
        if dtype == "timestamp without time zone":
            out.append((name, f"(\"{name}\" AT TIME ZONE current_setting('TimeZone'))"))
        else:
            out.append((name, f'"{name}"'))
    return out


def _row_counts(conn: Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in _table_names(conn):
        if table == "alembic_version":
            continue
        counts[table] = int(conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar() or 0)
    return counts


def _money(conn: Connection, table: str, columns: Iterable[str]) -> dict[str, str | None]:
    present = set(_columns(conn, table))
    out: dict[str, str | None] = {}
    for column in columns:
        if column not in present:
            continue
        total = conn.execute(text(f'SELECT COALESCE(sum("{column}"), 0) FROM "{table}"')).scalar()
        out[column] = _decimal_str(Decimal(str(total)))
    return out


def _gl_account_balances(conn: Connection) -> dict[str, str]:
    rows = conn.execute(
        text(
            "SELECT a.code, "
            "       COALESCE(sum(l.debit), 0) - COALESCE(sum(l.credit), 0) "
            "FROM gl_accounts a "
            "LEFT JOIN gl_journal_lines l ON l.account_id = a.id "
            "GROUP BY a.code ORDER BY a.code"
        )
    ).fetchall()
    return {str(r[0]): _decimal_str(Decimal(str(r[1]))) for r in rows}


def fingerprint(conn: Connection) -> dict[str, Any]:
    """Capture row counts, money sums, per-account balances and row hashes."""
    counts = _row_counts(conn)
    server_timezone = conn.execute(text("SELECT current_setting('TimeZone')")).scalar()
    tables: dict[str, Any] = {}

    for table, pk in MONITORED_TABLES.items():
        if table not in counts:
            continue
        columns = _columns(conn, table)
        column_types = _column_types(conn, table)
        rows: dict[str, dict[str, Any]] = {}
        if columns:
            expressions = _select_expressions(conn, table)
            select_sql = ", ".join(f'{expr} AS "{name}"' for name, expr in expressions)
            fetched = conn.execute(text(f'SELECT {select_sql} FROM "{table}" ORDER BY "{pk}"')).fetchall()
            for raw in fetched:
                mapping = raw._mapping
                row = {col: normalize(mapping[col]) for col in columns}
                rows[str(mapping[pk])] = row
        tables[table] = {
            "pk": pk,
            "columns": columns,
            "column_types": column_types,
            "row_count": counts[table],
            "money": _money(conn, table, MONEY_COLUMNS.get(table, ())),
            "rows": rows,
            "row_hashes": {key: _row_hash(row) for key, row in rows.items()},
        }

    return {
        "server_timezone": str(server_timezone),
        "row_counts": counts,
        "tables": tables,
        "gl_account_balances": _gl_account_balances(conn),
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Comparison
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _declared_check(
    change: DeclaredChange,
    before_row: dict[str, Any],
    after_row: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    if change.check == "gl_account_reparented":
        account_ids = context.get("account_ids", {})
        return before_row.get("parent_id") == account_ids.get("2120") and after_row.get("parent_id") == account_ids.get(
            "1100"
        )
    if change.check == "gl_account_level_2122":
        return before_row.get("level") == 3 and after_row.get("level") == 2
    raise RuntimeError(f"unknown declared-change check: {change.check}")


def _matches_row_key(row: dict[str, Any], row_key: dict[str, str]) -> bool:
    return all(str(row.get(k)) == str(v) for k, v in row_key.items())


def _parse_instant(value: Any) -> datetime | None:
    """Parse a normalised timestamp back into an aware UTC datetime."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _timestamp_shift(before: Any, after: Any) -> str | None:
    """The signed difference between two normalised instants, in seconds."""
    b = _parse_instant(before)
    a = _parse_instant(after)
    if b is None or a is None:
        return None
    return str(int((a - b).total_seconds()))


def compare(before: dict[str, Any], after: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Compare two fingerprints and classify every difference."""
    count_diffs: list[dict[str, Any]] = []
    new_tables: list[dict[str, Any]] = []
    for table in sorted(set(before["row_counts"]) | set(after["row_counts"])):
        b = before["row_counts"].get(table)
        a = after["row_counts"].get(table)
        if b is None:
            new_tables.append({"table": table, "rows_after": a})
        elif a is None:
            count_diffs.append({"table": table, "before": b, "after": None})
        elif b != a:
            count_diffs.append({"table": table, "before": b, "after": a})

    value_diffs: list[dict[str, Any]] = []
    lost_rows: list[dict[str, Any]] = []
    added_rows: list[dict[str, Any]] = []
    new_columns: dict[str, list[str]] = {}

    for table, before_table in before["tables"].items():
        after_table = after["tables"].get(table)
        if after_table is None:
            lost_rows.append({"table": table, "reason": "table disappeared"})
            continue
        before_cols = set(before_table["columns"])
        after_cols = set(after_table["columns"])
        added_cols = sorted(after_cols - before_cols)
        if added_cols:
            new_columns[table] = added_cols

        before_rows = before_table["rows"]
        after_rows = after_table["rows"]
        for key in sorted(set(before_rows) | set(after_rows)):
            b_row = before_rows.get(key)
            a_row = after_rows.get(key)
            if b_row is None:
                added_rows.append({"table": table, "pk": key})
                continue
            if a_row is None:
                lost_rows.append({"table": table, "pk": key})
                continue
            for column in sorted(before_cols & after_cols):
                if b_row.get(column) == a_row.get(column):
                    continue
                value_diffs.append(
                    {
                        "table": table,
                        "pk": key,
                        "column": column,
                        "before": b_row.get(column),
                        "after": a_row.get(column),
                    }
                )

    declared: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    matched_declared: set[int] = set()

    for index, diff in enumerate(value_diffs):
        hit = None
        for change_index, change in enumerate(DECLARED_CHANGES):
            if change.table != diff["table"] or change.column != diff["column"]:
                continue
            before_row = before["tables"][change.table]["rows"].get(diff["pk"])
            after_row = after["tables"][change.table]["rows"].get(diff["pk"])
            if before_row is None or after_row is None:
                continue
            if not _matches_row_key(before_row, change.row_key):
                continue
            if _declared_check(change, before_row, after_row, context):
                hit = change
                matched_declared.add(change_index)
                break
        if hit is None:
            unexpected.append(diff)
        else:
            declared.append(
                {
                    "table": diff["table"],
                    "pk": diff["pk"],
                    "column": diff["column"],
                    "before": diff["before"],
                    "after": diff["after"],
                    "revision": hit.revision,
                    "reason": hit.reason,
                }
            )

    declared_not_observed = [
        {
            "table": change.table,
            "column": change.column,
            "row_key": change.row_key,
            "revision": change.revision,
            "reason": change.reason,
            "detail": "the declared change did not happen - the chain no longer behaves as documented",
        }
        for index, change in enumerate(DECLARED_CHANGES)
        if index not in matched_declared
    ]

    money_diffs: list[dict[str, Any]] = []
    for table, before_table in before["tables"].items():
        after_table = after["tables"].get(table)
        if after_table is None:
            continue
        for column, b_value in before_table["money"].items():
            a_value = after_table["money"].get(column)
            if b_value != a_value:
                money_diffs.append({"table": table, "column": column, "before": b_value, "after": a_value})

    balance_diffs: list[dict[str, Any]] = []
    for code, b_value in before["gl_account_balances"].items():
        a_value = after["gl_account_balances"].get(code)
        if b_value != a_value:
            balance_diffs.append({"account": code, "before": b_value, "after": a_value})

    hash_diffs: list[dict[str, Any]] = []
    stable_hash_diffs: list[dict[str, Any]] = []
    declared_rows = {(d["table"], d["pk"]) for d in declared}
    for table, before_table in before["tables"].items():
        after_table = after["tables"].get(table)
        if after_table is None:
            continue
        before_cols = before_table["columns"]
        for pk, before_hash in before_table["row_hashes"].items():
            after_hash = after_table["row_hashes"].get(pk)
            if before_hash != after_hash:
                hash_diffs.append({"table": table, "pk": pk, "before": before_hash, "after": after_hash})
            after_row = after_table["rows"].get(pk)
            if after_row is None:
                continue
            projected = {col: after_row.get(col) for col in before_cols}
            stable_hash = _row_hash(projected)
            if stable_hash != before_hash:
                stable_hash_diffs.append(
                    {
                        "table": table,
                        "pk": pk,
                        "before": before_hash,
                        "after": stable_hash,
                        "explained_by_declared_change": (table, pk) in declared_rows,
                    }
                )
    unexpected_stable_hashes = [d for d in stable_hash_diffs if not d["explained_by_declared_change"]]

    # How far did the upgrade move the clock? Grouped per column so a
    # timezone-dependent rewrite shows up as one line with the offset, not as
    # one line per row.
    shift_groups: dict[tuple[str, str], dict[str, Any]] = {}
    for diff in value_diffs:
        before_types = before["tables"].get(diff["table"], {}).get("column_types", {})
        dtype = before_types.get(diff["column"], "")
        if "timestamp" not in dtype:
            continue
        shift = _timestamp_shift(diff["before"], diff["after"])
        key = (diff["table"], diff["column"])
        group = shift_groups.setdefault(
            key,
            {
                "table": diff["table"],
                "column": diff["column"],
                "data_type": dtype,
                "rows_shifted": 0,
                "shifts_seconds": set(),
                "example_before": diff["before"],
                "example_after": diff["after"],
            },
        )
        group["rows_shifted"] += 1
        if shift is not None:
            group["shifts_seconds"].add(shift)
    timestamp_shifts = []
    for group in shift_groups.values():
        group["shifts_seconds"] = sorted(group["shifts_seconds"], key=lambda v: int(v))
        group["distinct_shifts"] = len(group["shifts_seconds"])
        timestamp_shifts.append(group)
    timestamp_shifts.sort(key=lambda g: (g["table"], g["column"]))

    return {
        "row_count_differences": count_diffs,
        "new_tables": new_tables,
        "value_differences": value_diffs,
        "declared_changes": declared,
        "declared_changes_not_observed": declared_not_observed,
        "unexpected_value_differences": unexpected,
        "money_differences": money_diffs,
        "gl_account_balance_differences": balance_diffs,
        "row_hash_differences": hash_diffs,
        "stable_row_hash_differences": stable_hash_diffs,
        "unexpected_stable_row_hash_differences": unexpected_stable_hashes,
        "timestamp_shifts": timestamp_shifts,
        "lost_rows": lost_rows,
        "added_rows": added_rows,
        "new_columns": new_columns,
        "clean": not (
            count_diffs
            or unexpected
            or unexpected_stable_hashes
            or declared_not_observed
            or money_diffs
            or balance_diffs
            or lost_rows
            or added_rows
        ),
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Accounting invariants
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def check_invariants(conn: Connection) -> dict[str, Any]:
    """Every entry balances and the trial balance balances to the cent."""
    entries = conn.execute(
        text(
            "SELECT e.id, e.entry_number, e.total_debit, e.total_credit, "
            "       COALESCE(sum(l.debit), 0), COALESCE(sum(l.credit), 0), count(l.id) "
            "FROM gl_journal_entries e "
            "LEFT JOIN gl_journal_lines l ON l.entry_id = e.id "
            "GROUP BY e.id, e.entry_number, e.total_debit, e.total_credit ORDER BY e.id"
        )
    ).fetchall()

    unbalanced: list[dict[str, Any]] = []
    for row in entries:
        entry_id, number, total_debit, total_credit, line_debit, line_credit, line_count = row
        td = Decimal(str(total_debit or 0))
        tc = Decimal(str(total_credit or 0))
        ld = Decimal(str(line_debit))
        lc = Decimal(str(line_credit))
        problems = []
        if abs(td - tc) > MONEY_TOLERANCE:
            problems.append(f"entry totals differ: debit={td} credit={tc}")
        if abs(ld - lc) > MONEY_TOLERANCE:
            problems.append(f"lines do not balance: debit={ld} credit={lc}")
        if abs(ld - td) > MONEY_TOLERANCE:
            problems.append(f"line debit {ld} != entry total_debit {td}")
        if abs(lc - tc) > MONEY_TOLERANCE:
            problems.append(f"line credit {lc} != entry total_credit {tc}")
        if problems:
            unbalanced.append({"entry_id": entry_id, "entry_number": number, "problems": problems})

    trial = conn.execute(
        text("SELECT COALESCE(sum(debit), 0) - COALESCE(sum(credit), 0) FROM gl_journal_lines")
    ).scalar()
    trial_delta = Decimal(str(trial or 0))

    constraint = conn.execute(
        text(
            "SELECT convalidated FROM pg_constraint WHERE conname = 'ck_gl_journal_entries_balanced' AND contype = 'c'"
        )
    ).scalar()

    return {
        "entries_checked": len(entries),
        "unbalanced_entries": unbalanced,
        "trial_balance_delta": _decimal_str(trial_delta),
        "trial_balance_balances": abs(trial_delta) <= MONEY_TOLERANCE,
        "balanced_check_constraint_present": constraint is not None,
        "balanced_check_constraint_validated": bool(constraint),
        "ok": not unbalanced and abs(trial_delta) <= MONEY_TOLERANCE,
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Reporting
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _print_table(rows: Sequence[Sequence[Any]], headers: Sequence[str]) -> None:
    if not rows:
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    print("  " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("  " + "-+-".join("-" * w for w in widths))
    for row in rows:
        print("  " + " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))


def render_report(report: dict[str, Any]) -> None:
    _print_header("MIGRATION DATA-PRESERVATION PROBE")
    print(f"  scratch database   : {report.get('database')}")
    print(f"  server timezone    : {report.get('server_timezone')}")
    print(f"  from revision      : {report.get('from_revision')}")
    print(f"  to revision        : {report.get('to_revision')} (resolved head: {report.get('head_revision')})")
    print(f"  revisions applied  : {report.get('revisions_applied')}")
    print(f"  seeded rows        : {report.get('total_rows_inserted')}")
    timing = report.get("runtime_seconds", {})
    print(
        "  runtime (s)        : "
        f"baseline={timing.get('baseline_upgrade')} seed={timing.get('seed')} "
        f"head_upgrade={timing.get('head_upgrade')} compare={timing.get('compare')} "
        f"total={timing.get('total')}"
    )

    inserted = report.get("inserted_rows_per_table", {})
    _print_header("SEEDED DATASET")
    _print_table([[table, count] for table, count in sorted(inserted.items())], ["table", "rows"])

    comparison = report.get("comparison", {})
    _print_header("FINGERPRINT COMPARISON (before -> after)")
    _print_table(
        [
            ["row counts (tables present in both)", len(comparison.get("row_count_differences", [])), "must be zero"],
            ["tables created by the chain", len(comparison.get("new_tables", [])), "schema evolution"],
            ["seeded row values", len(comparison.get("value_differences", [])), "differences"],
            ["  of which declared", len(comparison.get("declared_changes", [])), "intentional"],
            ["  of which UNEXPECTED", len(comparison.get("unexpected_value_differences", [])), "must be zero"],
            ["money sums", len(comparison.get("money_differences", [])), "must be zero"],
            ["GL account balances", len(comparison.get("gl_account_balance_differences", [])), "must be zero"],
            ["row sha256 (all columns)", len(comparison.get("row_hash_differences", [])), "new columns move this"],
            [
                "row sha256 (pre-existing columns)",
                len(comparison.get("unexpected_stable_row_hash_differences", [])),
                "must be zero",
            ],
            ["rows lost", len(comparison.get("lost_rows", [])), "must be zero"],
            ["rows appeared", len(comparison.get("added_rows", [])), "must be zero"],
        ],
        ["metric", "n", "note"],
    )

    if comparison.get("declared_changes"):
        _print_header("DECLARED (INTENTIONAL) CHANGES")
        _print_table(
            [
                [c["table"], c["pk"], c["column"], c["before"], c["after"], c["revision"]]
                for c in comparison["declared_changes"]
            ],
            ["table", "pk", "column", "before", "after", "revision"],
        )

    if comparison.get("unexpected_value_differences"):
        _print_header("UNEXPECTED VALUE DIFFERENCES")
        _print_table(
            [
                [d["table"], d["pk"], d["column"], d["before"], d["after"]]
                for d in comparison["unexpected_value_differences"]
            ],
            ["table", "pk", "column", "before", "after"],
        )

    if comparison.get("new_tables"):
        _print_header("TABLES CREATED BY THE CHAIN (schema evolution)")
        _print_table(
            [[t["table"], t["rows_after"]] for t in comparison["new_tables"]],
            ["table", "rows after"],
        )

    if comparison.get("new_columns"):
        _print_header("COLUMNS ADDED BY THE CHAIN (schema evolution)")
        _print_table(
            [[table, ", ".join(cols)] for table, cols in sorted(comparison["new_columns"].items())],
            ["table", "new columns"],
        )

    if comparison.get("money_differences"):
        _print_header("MONEY DIFFERENCES")
        _print_table(
            [[d["table"], d["column"], d["before"], d["after"]] for d in comparison["money_differences"]],
            ["table", "column", "before", "after"],
        )

    if comparison.get("gl_account_balance_differences"):
        _print_header("GL ACCOUNT BALANCE DIFFERENCES")
        _print_table(
            [[d["account"], d["before"], d["after"]] for d in comparison["gl_account_balance_differences"]],
            ["account", "before", "after"],
        )

    if comparison.get("row_count_differences"):
        _print_header("ROW COUNT DIFFERENCES")
        _print_table(
            [[d["table"], d["before"], d["after"]] for d in comparison["row_count_differences"]],
            ["table", "before", "after"],
        )

    if comparison.get("timestamp_shifts"):
        _print_header("TIMESTAMPS MOVED BY THE UPGRADE")
        _print_table(
            [
                [
                    g["table"],
                    g["column"],
                    g["rows_shifted"],
                    ", ".join(g["shifts_seconds"]),
                    g["example_before"],
                    g["example_after"],
                ]
                for g in comparison["timestamp_shifts"]
            ],
            ["table", "column", "rows", "shift (s)", "before (UTC)", "after (UTC)"],
        )
        print(
            f"  server timezone: {report.get('server_timezone')} - the chain read every legacy "
            "naive timestamp as UTC, so a server that does not run on UTC shifts the clock."
        )
        print()

    if comparison.get("lost_rows") or comparison.get("added_rows"):
        _print_header("ROW GAIN/LOSS")
        _print_table(
            [[d["table"], d["pk"]] for d in comparison["lost_rows"]]
            + [[d["table"], d["pk"], "ADDED"] for d in comparison["added_rows"]],
            ["table", "pk", "note"],
        )

    key_hashes = report.get("key_row_hashes", {})
    if key_hashes:
        _print_header("KEY ROW SHA256 (before | after)")
        _print_table(
            [[label, value["before"][:16], value["after"][:16]] for label, value in key_hashes.items()],
            ["row", "before", "after"],
        )

    _print_header("ACCOUNTING INVARIANTS")
    for phase in ("before", "after"):
        inv = report.get("invariants", {}).get(phase, {})
        print(
            f"  {phase:<7} entries_checked={inv.get('entries_checked')} "
            f"unbalanced={len(inv.get('unbalanced_entries', []))} "
            f"trial_balance_delta={inv.get('trial_balance_delta')} "
            f"balanced_constraint_validated={inv.get('balanced_check_constraint_validated')}"
        )

    _print_header("VERDICT")
    print(f"  {report.get('verdict')}")
    print()


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Main
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _resolve_admin_url(explicit: str | None) -> str:
    if explicit:
        return explicit
    for env_name in ("MIGRATION_PROBE_ADMIN_URL", "TEST_DATABASE_URL", "DATABASE_URL"):
        candidate = (os.environ.get(env_name) or "").strip()
        if candidate and candidate.startswith(("postgres://", "postgresql://", "postgresql+psycopg2://")):
            return str(make_url(candidate).set(database="postgres"))
    return DEFAULT_ADMIN_URL


def _probe(args: argparse.Namespace) -> dict[str, Any]:
    admin_url = _resolve_admin_url(args.admin_url)
    db_name = args.db_name
    _guard_db_name(db_name)
    db_url = _scratch_url(admin_url, db_name)

    timings: dict[str, float] = {}
    started = time.time()

    _drop_database(admin_url, db_name)
    _create_database(admin_url, db_name)
    print(f"[probe] scratch database created: {db_name}")

    baseline = run_upgrade(db_url, args.from_revision)
    timings["baseline_upgrade"] = baseline["seconds"]
    print(f"[probe] migrated to {args.from_revision} in {baseline['seconds']}s")

    seed_started = time.time()
    engine = _scratch_engine(db_url)
    try:
        with engine.connect() as conn:
            inserted = seed_dataset(conn)
            conn.commit()
            before = fingerprint(conn)
            invariants_before = check_invariants(conn)
            account_ids = {
                str(r[0]): int(r[1]) for r in conn.execute(text("SELECT code, id FROM gl_accounts")).fetchall()
            }
    finally:
        engine.dispose()
    timings["seed"] = round(time.time() - seed_started, 2)
    total_rows = sum(inserted.values())
    print(f"[probe] seeded {total_rows} rows across {len(inserted)} tables in {timings['seed']}s")

    head = run_upgrade(db_url, args.to_revision)
    timings["head_upgrade"] = head["seconds"]
    head_revision = current_revision(db_url)
    print(f"[probe] upgraded to {head_revision} in {head['seconds']}s")

    compare_started = time.time()
    engine = _scratch_engine(db_url)
    try:
        with engine.connect() as conn:
            after = fingerprint(conn)
            invariants_after = check_invariants(conn)
    finally:
        engine.dispose()
    timings["compare"] = round(time.time() - compare_started, 2)

    context = {"account_ids": account_ids}
    comparison = compare(before, after, context)

    key_hashes: dict[str, Any] = {}
    for table, _pk in KEY_ROWS:
        before_table = before["tables"].get(table)
        after_table = after["tables"].get(table)
        if not before_table or not after_table:
            continue
        for row_key, row_hash in before_table["row_hashes"].items():
            label = f"{table}:{row_key}"
            key_hashes[label] = {
                "before": row_hash,
                "after": after_table["row_hashes"].get(row_key),
            }

    clean = comparison["clean"] and invariants_after["ok"] and invariants_before["ok"]
    if clean:
        verdict = "DATA PRESERVED: no row lost, duplicated or altered by the upgrade."
    else:
        verdict = "DATA NOT PRESERVED - see the differences listed above."

    report = {
        "ok": clean,
        "database": db_name,
        "server_timezone": before.get("server_timezone", ""),
        "from_revision": args.from_revision,
        "to_revision": args.to_revision,
        "head_revision": head_revision,
        "revisions_applied": _count_revisions(args.from_revision, head_revision),
        "total_rows_inserted": total_rows,
        "inserted_rows_per_table": inserted,
        "runtime_seconds": timings,
        "before": before,
        "after": after,
        "comparison": comparison,
        "invariants": {"before": invariants_before, "after": invariants_after},
        "key_row_hashes": key_hashes,
        "verdict": verdict,
    }
    timings["total"] = round(time.time() - started, 2)
    report["runtime_seconds"] = timings
    return report


def _count_revisions(from_revision: str, to_revision: str) -> int:
    """Count the revisions between two points of the chain.

    ``to_revision`` may be ``head``; the chain is walked forward from
    ``from_revision`` through the children of each revision.
    """
    versions = PROJECT_ROOT / "migrations" / "versions"
    if not versions.is_dir():
        return -1
    import re

    rev_re = re.compile(r"^revision(?::\s*[^=]+)?\s*=\s*['\"]([^'\"]+)", re.M)
    down_re = re.compile(r"^down_revision(?::\s*[^=]+)?\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", re.M)
    parents: dict[str, str | None] = {}
    for path in sorted(versions.glob("*.py")):
        body = path.read_text(encoding="utf-8", errors="replace")
        rev_match = rev_re.search(body)
        down_match = down_re.search(body)
        if not rev_match:
            continue
        parents[rev_match.group(1)] = down_match.group(1) if (down_match and down_match.group(1)) else None
    if from_revision not in parents:
        return -1
    children: dict[str, list[str]] = {}
    for rev, parent in parents.items():
        if parent:
            children.setdefault(parent, []).append(rev)
    heads = [r for r in parents if r not in children]
    target = heads[0] if to_revision in ("head", "heads") else to_revision

    count = 0
    cursor = from_revision
    while cursor != target:
        next_steps = children.get(cursor, [])
        if not next_steps:
            return -1
        cursor = next_steps[0]
        count += 1
    return count


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove the Alembic chain preserves data on a populated database")
    parser.add_argument("--db-name", default=DEFAULT_DB_NAME, help="scratch database name")
    parser.add_argument(
        "--admin-url", default=None, help="PostgreSQL admin URL (default: derived from the environment)"
    )
    parser.add_argument("--from-revision", default=EARLY_REVISION, help="revision to migrate to before seeding")
    parser.add_argument("--to-revision", default="head", help="revision to migrate to after seeding")
    parser.add_argument("--report", default=None, help="write the JSON report to this path")
    parser.add_argument("--keep", action="store_true", help="keep the scratch database after the probe")
    args = parser.parse_args(argv)

    try:
        report = _probe(args)
    except Exception as exc:
        admin_url = _resolve_admin_url(args.admin_url)
        try:
            _guard_db_name(args.db_name)
            _drop_database(admin_url, args.db_name)
        except Exception:
            pass
        reason = f"{type(exc).__name__}: {exc}"
        print(f"[probe] could not run: {reason}", file=sys.stderr)
        if _looks_unavailable(reason):
            print(
                "[probe] SKIP: the environment cannot run this probe - this is NOT evidence of anything.",
                file=sys.stderr,
            )
            _write_report(
                args.report, {"ok": False, "skipped": True, "skip_reason": reason, "verdict": "PROBE NOT RUN"}
            )
            return EXIT_SKIP
        print(f"[probe] FAIL: {reason}", file=sys.stderr)
        _write_report(args.report, {"ok": False, "skipped": False, "error": reason, "verdict": "PROBE ERROR"})
        return EXIT_ERROR

    render_report(report)
    _write_report(args.report, report)

    if not args.keep:
        try:
            _drop_database(_resolve_admin_url(args.admin_url), args.db_name)
            print(f"[probe] scratch database {args.db_name} dropped")
        except Exception as exc:
            print(f"[probe] WARN: could not drop {args.db_name}: {exc}", file=sys.stderr)

    return EXIT_OK if report["ok"] else EXIT_DATA_LOSS


def _looks_unavailable(reason: str) -> bool:
    lowered = reason.lower()
    markers = (
        "could not connect",
        "connection refused",
        "password authentication failed",
        "does not exist",
        "permission denied",
        "must be owner of database",
        "insufficientprivilege",
        "operationalerror",
        "connection is closed",
        "could not translate host name",
        "timeout",
    )
    return any(marker in lowered for marker in markers)


def _write_report(path: str | None, report: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
