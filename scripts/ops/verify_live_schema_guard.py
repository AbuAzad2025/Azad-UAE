#!/usr/bin/env python3
"""Live schema guard — verify a migrated database still carries its guardrails.

Unlike the alembic-vs-create_all parity test (which rebuilds a scratch DB),
this script inspects an EXISTING database through DATABASE_URL and asserts
that the CHECK constraints introduced by the migration chain are still there.
It is safe to run against production: read-only, no schema changes.

    $env:DATABASE_URL = "postgresql+psycopg2://user@host/prod_db"
    python scripts/ops/verify_live_schema_guard.py

Exit 0 = all guards present; exit 1 = one or more guards missing.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "migrations" / "versions"

# Constraint names declared by the migration chain. A drop constraint is also
# a declaration of intent, so we only assert names that are never dropped.
# Migrations create checks via several spellings: op.create_check_constraint,
# raw `ADD CONSTRAINT ... CHECK`, and batched `batch_op.create_check_constraint`.
# The reliable signal is any occurrence of a `ck_*` name in a migration file.
_ANY_CK = re.compile(r"\b(ck_[a-z0-9_]+)\b", re.I)
# A later migration may drop a check it no longer wants. Detect an explicit
# DROP CONSTRAINT <name> or a drop_check_constraint(<file>, "<name>") call.
_DROP = re.compile(
    r"(?:DROP\s+CONSTRAINT\s+['\"]?(ck_[a-z0-9_]+)|drop_check_constraint\s*\([^)]*?['\"](ck_[a-z0-9_]+)['\"])",
    re.I,
)


def _declared_constraints() -> set[str]:
    created: set[str] = set()
    dropped: set[str] = set()
    for path in VERSIONS.glob("*.py"):
        src = path.read_text(encoding="utf-8", errors="replace")
        created.update(m.lower() for m in _ANY_CK.findall(src))
        dropped.update(m.lower() for m in _DROP.findall(src))
        # Migrations that drop a check often bind its name to a module-level
        # constant (e.g. _CONSTRAINT = "ck_x") and call drop_constraint(_CONSTRAINT).
        # Resolve those constants explicitly so we don't discard unrelated names.
        for _, value in re.findall(r"^([A-Z_][A-Z0-9_]*)\s*=\s*['\"](ck_[a-z0-9_]+)['\"]", src, re.I | re.M):
            if re.search(rf"drop_constraint\s*\(\s*{re.escape(_)}", src, re.I):
                dropped.add(value.lower())
    return created - dropped


def main() -> int:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is required")

    declared = _declared_constraints()
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            dialect = engine.dialect.name
            if dialect == "postgresql":
                live = {
                    row[0].lower()
                    for row in conn.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE contype='c' AND connamespace='public'::regnamespace"
                        )
                    )
                }
            else:  # SQLite / other — inspect via information_schema where available
                live = {
                    row[0].lower()
                    for row in conn.execute(
                        text(
                            "SELECT constraint_name FROM information_schema.table_constraints "
                            "WHERE constraint_type='CHECK'"
                        )
                    )
                }
    finally:
        engine.dispose()

    missing = sorted(declared - live)
    print(f"dialect={dialect} declared_check_constraints={len(declared)} live_check_constraints={len(live)}")
    if missing:
        for name in missing:
            print(f"FAIL: migration-declared CHECK constraint missing from database: {name}")
        return 1
    print("OK: every migration-declared CHECK guard is present in the live database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
