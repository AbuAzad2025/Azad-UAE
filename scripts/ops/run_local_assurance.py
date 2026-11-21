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
    "tests/integration/test_csrf_live_enforcement.py",
]


def run(label: str, cmd: list[str], env: dict | None = None) -> bool:
    print(f"\n=== {label} ===")
    print(" + " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    tail = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
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

    # Browser-discovered JS defect guards:
    #  - sales-enhanced.js is loaded on every page but select2 only on sale forms;
    #  - an unavailable POS product card must explain itself on tap instead of
    #    silently ignoring the cashier (it looked disabled but had no handler);
    #  - the POS must send unit_price to the totals API, otherwise every line
    #    is priced at zero and all four KPIs read 0.00.
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    if not run(
        "vitest browser-defect guards",
        [
            npx,
            "vitest",
            "run",
            "tests/vitest/sales_enhanced_select2_guard.test.js",
            "tests/vitest/pos/pos_ui.test.js",
            "tests/vitest/pos/pos_cart.test.js",
        ],
    ):
        failures.append("vitest-browser-defects")

    # The full POS→GL→Shift→Billing lifecycle script sits at the root of
    # tests/ and is collected by no suite. Run it explicitly. It builds its
    # schema with create_all(), so it needs PostgreSQL (JSONB columns).
    db_url = (os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL") or "").strip()
    if db_url.startswith("postgresql"):
        import os as _os

        e2e_env = _os.environ.copy()
        e2e_env["TEST_DATABASE_URL"] = db_url
        if not run(
            "e2e full lifecycle",
            [sys.executable, "-m", "pytest", "tests/e2e_dry_run.py", "-q", "-p", "no:randomly", "--tb=line"],
            env=e2e_env,
        ):
            failures.append("e2e")
    else:
        print("\n=== e2e full lifecycle ===\n -> SKIPPED (needs a PostgreSQL DATABASE_URL)")

    # The live guard is read-only and points at an EXISTING migrated DB. The
    # pytest suite rebuilds its own throw-away DB and may drop/rename scratch
    # databases, so verify the target still exists before running the guard.
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url:
        import sqlalchemy as sa

        parsed_url = sa.engine.make_url(url)
        admin = sa.create_engine(parsed_url.set(database="postgres"), poolclass=NullPool)
        try:
            with admin.connect() as conn:
                exists = conn.execute(
                    sa.text("SELECT 1 FROM pg_database WHERE datname = :n"),
                    {"n": parsed_url.database},
                ).scalar()
        finally:
            admin.dispose()
        if not exists:
            print(f"\n=== live CHECK guard ===\n -> SKIPPED: database {parsed_url.database} no longer exists")
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
