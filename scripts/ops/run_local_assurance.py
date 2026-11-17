#!/usr/bin/env python3
"""Local-only financial & schema assurance runner.

No CI, no GitHub: one command verifies every gate we rely on, on the machine.
It runs (in order):
  1. ruff + format
  2. mypy on the authored files
  3. alembic single-head check
  4. pytest: schema parity, migration-head gate, CFO financial assurance,
     reconciliation, isolation verifier tests, CLI tests
  5. the live CHECK-constraint guard against DATABASE_URL (if provided)

    python scripts/ops/run_local_assurance.py
    $env:DATABASE_URL = "postgresql+psycopg2://..."  # optional, enables step 5
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[2]

TESTS = [
    "tests/unit/models/test_schema_parity_migrations.py",
    "tests/unit/scripts/",
    "tests/integration/test_cfo_financial_assurance.py",
    "tests/unit/utils/test_balance_reconciliation.py",
]


def run(label: str, cmd: list[str]) -> bool:
    print(f"\n=== {label} ===")
    print(" + " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    tail = (result.stdout + result.stderr).strip().splitlines()
    for line in tail[-15:]:
        print("   " + line)
    ok = result.returncode == 0
    print(f" -> {'OK' if ok else 'FAIL'} (exit {result.returncode})")
    return ok


def main() -> int:
    failures: list[str] = []

    if not run("ruff lint", [sys.executable, "-m", "ruff", "check", "."]):
        failures.append("ruff")
    if not run("ruff format", [sys.executable, "-m", "ruff", "format", ".", "--check"]):
        failures.append("format")

    authored = [
        "models/payment_vault.py",
        "models/card_payment.py",
        "models/donation.py",
        "models/maintenance.py",
        "tests/unit/models/test_schema_parity_migrations.py",
        "scripts/ops/seed_clean_isolation_db.py",
        "scripts/ops/seed_financial_domains.py",
        "scripts/ops/verify_isolation_db.py",
        "scripts/ops/verify_live_schema_guard.py",
        "scripts/ops/reconcile_historical_balances.py",
        "tests/integration/test_cfo_financial_assurance.py",
    ]
    if not run(
        "mypy (authored files)",
        [
            sys.executable,
            "-m",
            "mypy",
            *authored,
            "--ignore-missing-imports",
            "--no-error-summary",
            "--explicit-package-bases",
        ],
    ):
        failures.append("mypy")

    if not run("alembic single head", [sys.executable, "scripts/lint/check_migration_head.py"]):
        failures.append("migration-head")

    if not run(
        "pytest assurance suite", [sys.executable, "-m", "pytest", *TESTS, "-q", "-p", "no:randomly", "--tb=line"]
    ):
        failures.append("pytest")

    # The live guard is read-only and points at an EXISTING migrated DB. The
    # pytest suite rebuilds its own throw-away DB and may drop/rename scratch
    # databases, so verify the target still exists before running the guard.
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url:
        import sqlalchemy as sa

        db_url = sa.engine.make_url(url)
        admin = sa.create_engine(db_url.set(database="postgres"), poolclass=NullPool)
        try:
            with admin.connect() as conn:
                exists = conn.execute(
                    sa.text("SELECT 1 FROM pg_database WHERE datname = :n"),
                    {"n": db_url.database},
                ).scalar()
        finally:
            admin.dispose()
        if not exists:
            print(f"\n=== live CHECK guard ===\n -> SKIPPED: database {db_url.database} no longer exists")
        else:
            if not run("live CHECK guard", [sys.executable, "scripts/ops/verify_live_schema_guard.py"]):
                failures.append("live-check-guard")
    else:
        print("\n=== live CHECK guard ===")
        print(" -> SKIPPED (set DATABASE_URL to enable)")

    print("\n========================================")
    if failures:
        print("FAILED gates: " + ", ".join(failures))
        return 1
    print("ALL LOCAL ASSURANCE GATES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
