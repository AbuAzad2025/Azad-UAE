"""Prove that the Alembic chain preserves DATA and MONEY on a POPULATED database.

The "Alembic Round-Trip" CI job builds an empty database, upgrades it to head,
downgrades it to the baseline and upgrades it again. That proves the chain
*applies*. It says nothing about what the chain does to the rows an existing
installation already has - and that is the risk a production upgrade carries:
a customer balance that silently changes, a journal entry that stops balancing,
a stock row that vanishes under a rebuilt table.

This module runs ``scripts/ops/verify_migration_preserves_data.py`` against a
scratch database of its own and asserts that the upgrade lost, duplicated or
altered nothing.

Safety rules for this file:

* it never touches ``azad_uae_test`` (or any other real database) - it
  creates a database named ``azad_migration_probe_*`` and drops it again;
* it skips - loudly, with a reason - when the environment cannot run the probe
  (no PostgreSQL, no permission to create a database). A skipped probe is not
  evidence, so the skip reason is written to the report as well;
* it needs no app fixture and no seeded test database, so it is independent of
  whatever the rest of the integration slice did to the shared test database.

A note on the timestamp assertions
----------------------------------
Revision ``f3a9c1e5b2d8`` rewrites every legacy ``timestamp without time
zone`` column as ``timestamptz`` by reading the stored wall clock as UTC. The
ORM writes ``datetime.now(UTC)`` into those columns, and PostgreSQL renders an
aware value into the *session* timezone when the target column is naive - so
on a PostgreSQL that does not run on UTC the legacy values are local
renderings of UTC instants, and the migration moves every one of them by the
server's UTC offset.

That makes one assertion environment-dependent: on a UTC server nothing
moves, on any other server every timestamp moves. The probe measures the
movement and reports it; ``test_timestamps_were_not_shifted`` fails on a
server that is not on UTC, and says by how much.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROBE_SCRIPT = PROJECT_ROOT / "scripts" / "ops" / "verify_migration_preserves_data.py"

#: The script under test refuses these names; the test asserts that it does.
PROTECTED_DATABASES = ("azad_uae", "azad_uae_test", "erp_azad_full", "azad-finance", "postgres")

#: Exit codes of the probe script.
EXIT_OK = 0
EXIT_DATA_LOSS = 1
EXIT_ERROR = 2
EXIT_SKIP = 3


def _admin_url() -> str:
    """The PostgreSQL admin URL, derived from the environment's database URL.

    ``tests/conftest.py`` has already pointed ``TEST_DATABASE_URL`` at the test
    database; this replaces the database name with ``postgres`` so the probe can
    create and drop its own scratch database.
    """
    for env_name in ("MIGRATION_PROBE_ADMIN_URL", "TEST_DATABASE_URL", "DATABASE_URL"):
        candidate = (os.environ.get(env_name) or "").strip()
        if candidate.startswith(("postgres://", "postgresql://", "postgresql+psycopg2://")):
            parsed = urlparse(candidate)
            return urlunparse(parsed._replace(path="/postgres"))
    return "postgresql+psycopg2://postgres:123@localhost:5432/postgres"


def _can_create_databases(admin_url: str, db_name: str) -> tuple[bool, str]:
    """Check that PostgreSQL is reachable and that a database may be created."""
    engine = create_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE \"{db_name}\" WITH ENCODING 'UTF8' TEMPLATE template0"))
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        engine.dispose()


def _drop_database(admin_url: str, db_name: str) -> None:
    engine = create_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
    except Exception:
        pass
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def probe_report(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Run the probe against a scratch database and return its JSON report."""
    if not PROBE_SCRIPT.is_file():
        pytest.skip(f"probe script is missing: {PROBE_SCRIPT}")

    admin_url = _admin_url()
    db_name = f"azad_migration_probe_pytest_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    assert db_name.startswith("azad_migration_probe")
    assert db_name not in PROTECTED_DATABASES

    can_create, reason = _can_create_databases(admin_url, db_name)
    if not can_create:
        pytest.skip(
            "the migration data-preservation probe cannot run in this environment "
            f"(no usable PostgreSQL or no permission to create a database): {reason}. "
            "This is NOT evidence that the migration chain preserves data."
        )

    report_path = tmp_path_factory.mktemp("migration_probe") / "report.json"
    cmd = [
        sys.executable,
        str(PROBE_SCRIPT),
        "--db-name",
        db_name,
        "--admin-url",
        admin_url,
        "--report",
        str(report_path),
    ]
    try:
        proc = subprocess.run(  # nosec B603
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=5400,
            check=False,
        )
    finally:
        _drop_database(admin_url, db_name)

    report: dict[str, Any] = {}
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))

    if proc.returncode == EXIT_SKIP:
        pytest.skip(
            "the migration data-preservation probe could not run here: "
            f"{report.get('skip_reason', proc.stderr[-500:])}. "
            "This is NOT evidence that the migration chain preserves data."
        )
    if proc.returncode == EXIT_ERROR:
        pytest.fail(
            "the migration data-preservation probe failed to run:\n"
            f"{report.get('error', proc.stderr[-2000:])}\n"
            f"--- stdout ---\n{proc.stdout[-2000:]}"
        )

    report["_exit_code"] = proc.returncode
    report["_stdout"] = proc.stdout
    report["_stderr"] = proc.stderr
    report["_scratch_database"] = db_name
    return report


@pytest.fixture(scope="module")
def comparison(probe_report: dict[str, Any]) -> dict[str, Any]:
    return probe_report["comparison"]


def _column_type(probe_report: dict[str, Any], table: str, column: str) -> str:
    types = probe_report["before"]["tables"].get(table, {}).get("column_types", {})
    return str(types.get(column, ""))


def test_probe_refuses_protected_database_names() -> None:
    """The probe must never be pointed at a real installation.

    This test needs no PostgreSQL: it imports the probe script and checks the
    guard it applies to the scratch database name.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("migration_probe_under_test", PROBE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    for name in PROTECTED_DATABASES:
        with pytest.raises(RuntimeError):
            module._guard_db_name(name)

    # A name that is not clearly scratch is refused as well.
    with pytest.raises(RuntimeError):
        module._guard_db_name("azad_uae_test_scratch")
    module._guard_db_name("azad_migration_probe_ok")


def test_upgrade_preserves_row_counts(comparison: dict[str, Any]) -> None:
    assert comparison["row_count_differences"] == [], (
        f"the upgrade changed the row count of a table that existed before it: {comparison['row_count_differences']}"
    )
    assert comparison["lost_rows"] == [], f"rows disappeared during the upgrade: {comparison['lost_rows']}"
    assert comparison["added_rows"] == [], f"rows appeared during the upgrade: {comparison['added_rows']}"


def test_upgrade_preserves_money(comparison: dict[str, Any]) -> None:
    assert comparison["money_differences"] == [], (
        f"a money sum changed during the upgrade: {comparison['money_differences']}"
    )
    assert comparison["gl_account_balance_differences"] == [], (
        f"a GL account balance changed during the upgrade: {comparison['gl_account_balance_differences']}"
    )


def test_upgrade_preserves_non_timestamp_values(probe_report: dict[str, Any], comparison: dict[str, Any]) -> None:
    """No value outside the timestamp columns may change."""
    offenders = []
    for diff in comparison["unexpected_value_differences"]:
        dtype = _column_type(probe_report, diff["table"], diff["column"])
        if "timestamp" in dtype:
            continue
        offenders.append(diff)
    assert offenders == [], f"the upgrade altered a value that existed before it: {offenders}"
    assert comparison["declared_changes_not_observed"] == [], (
        "a change the chain is documented to perform did not happen, so the probe's "
        f"expectations are stale: {comparison['declared_changes_not_observed']}"
    )


def test_timestamps_were_not_shifted(probe_report: dict[str, Any], comparison: dict[str, Any]) -> None:
    """The upgrade must not move the clock.

    Revision f3a9c1e5b2d8 reads every legacy naive timestamp as UTC. The ORM
    writes UTC-aware instants into those columns and PostgreSQL renders them in
    the session timezone, so on a PostgreSQL that does not run on UTC the
    upgrade moves every timestamp by the server's UTC offset.
    """
    shifts = comparison["timestamp_shifts"]
    if not shifts:
        return
    offsets = sorted({int(value) for group in shifts for value in group["shifts_seconds"]})
    rows = sum(group["rows_shifted"] for group in shifts)
    columns = ", ".join(f"{group['table']}.{group['column']}" for group in shifts[:6])
    pytest.fail(
        f"the upgrade moved {rows} timestamp(s) by {offsets} second(s) across "
        f"{len(shifts)} column(s) ({columns}{', ...' if len(shifts) > 6 else ''}). "
        f"Server timezone: {probe_report.get('server_timezone')!r}. "
        "Revision f3a9c1e5b2d8 interprets the legacy naive timestamps as UTC, but the ORM "
        "wrote them as UTC instants rendered into the session timezone, so on a server that "
        "does not run on UTC the chain shifts every timestamp by the UTC offset. "
        "Run the migration on a PostgreSQL whose TimeZone is UTC, or correct the legacy "
        "values before upgrading."
    )


def test_upgrade_preserves_accounting_invariants(probe_report: dict[str, Any]) -> None:
    invariants = probe_report["invariants"]
    before = invariants["before"]
    after = invariants["after"]

    assert before["ok"], f"the seeded ledger did not balance before the upgrade: {before}"
    assert after["ok"], f"the ledger did not balance after the upgrade: {after}"
    assert after["unbalanced_entries"] == []
    assert after["trial_balance_balances"], (
        f"the trial balance does not balance after the upgrade: {after['trial_balance_delta']}"
    )
    assert after["balanced_check_constraint_validated"], "the double-entry CHECK constraint is not validated at HEAD"


def test_probe_exercised_a_real_multi_step_upgrade(probe_report: dict[str, Any]) -> None:
    """Guard against a probe that silently did nothing and reported success."""
    assert probe_report["revisions_applied"] >= 10, (
        f"the probe only applied {probe_report['revisions_applied']} revisions - that is not a meaningful upgrade"
    )
    assert probe_report["total_rows_inserted"] >= 40, (
        f"the probe only seeded {probe_report['total_rows_inserted']} rows - that is not a meaningful dataset"
    )
    assert probe_report["head_revision"], "the probe did not resolve the head revision"
    assert probe_report["head_revision"] != probe_report["from_revision"], "the probe did not actually upgrade anything"


def test_probe_verdict_matches_its_own_measurements(probe_report: dict[str, Any]) -> None:
    """The verdict must follow from the measurements, not from a hard-coded answer."""
    comparison = probe_report["comparison"]
    measured_clean = (
        not comparison["row_count_differences"]
        and not comparison["unexpected_value_differences"]
        and not comparison["declared_changes_not_observed"]
        and not comparison["money_differences"]
        and not comparison["gl_account_balance_differences"]
        and not comparison["lost_rows"]
        and not comparison["added_rows"]
    )
    assert measured_clean == bool(probe_report["ok"]), (
        "the probe's verdict disagrees with its own measurements: "
        f"verdict ok={probe_report['ok']}, measurements clean={measured_clean}"
    )
    expected_exit = EXIT_OK if measured_clean else EXIT_DATA_LOSS
    assert probe_report["_exit_code"] == expected_exit, (
        f"the probe exited {probe_report['_exit_code']} but its measurements imply {expected_exit}"
    )


def test_probe_did_not_touch_the_protected_databases(probe_report: dict[str, Any]) -> None:
    scratch = probe_report["_scratch_database"]
    assert scratch not in PROTECTED_DATABASES
    assert probe_report["database"] == scratch
    assert scratch.startswith("azad_migration_probe")


def test_money_values_are_the_expected_ones(probe_report: dict[str, Any]) -> None:
    """The probe must have measured real money, not zeros.

    A probe that compares empty tables proves nothing, so the seeded sale, the
    payment and the cheque are checked by value on both sides of the upgrade.
    """
    before = probe_report["before"]["tables"]
    after = probe_report["after"]["tables"]

    assert before["sales"]["money"]["total_amount"] == "105.000000"
    assert after["sales"]["money"]["total_amount"] == "105.000000"
    assert before["payments"]["money"]["amount"] == "50.000000"
    assert after["payments"]["money"]["amount"] == "50.000000"
    assert before["cheques"]["money"]["amount"] == "250.500000"
    assert after["cheques"]["money"]["amount"] == "250.500000"
    assert before["gl_journal_lines"]["money"]["debit"] == "155.000000"
    assert after["gl_journal_lines"]["money"]["debit"] == "155.000000"
    assert before["gl_journal_lines"]["money"]["credit"] == "155.000000"
    assert after["gl_journal_lines"]["money"]["credit"] == "155.000000"
