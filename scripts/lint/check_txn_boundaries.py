"""Static gate for transaction boundaries.

``utils.db_safety.atomic_transaction`` commits the *entire* session on exit. When
a service calls it, the service decides the commit boundary, and any unrelated
write the caller had pending is committed or rolled back along with it. AGENTS.md
therefore reserves the commit boundary for ``routes/``.

This script makes that rule machine-checkable. It reports:

* ``db.session.commit()`` / ``db.session.rollback()`` anywhere under ``services/``
  -- a service must never end a transaction it does not own;
* ``atomic_transaction(...)`` used under ``services/``, except in the explicit
  entry-point allowlist below.

Entry points are the deliberate exception. A Celery task, a CLI command or a
scheduler has no route above it, so *it* is the outermost boundary; without a
transaction there the work is flushed and never committed. ``celery_tasks.py``
was in exactly that state before this gate existed: two
``atomic_transaction`` blocks sat *inside* a ``for`` loop, so each iteration
committed independently and the abandoned-cart reminder counters were a
partial-write hazard. Those belong at the top of the task, not in the loop.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVICES_DIR = PROJECT_ROOT / "services"
BASELINE_PATH = Path(__file__).resolve().parent / "txn_boundaries_baseline.txt"

# Modules that are themselves a transaction boundary (Celery / CLI / scheduler)
# and therefore must be able to commit.
ENTRY_POINT_ALLOWLIST = {
    "celery_tasks.py",
}

COMMIT_ROLLBACK_CALLS = {"commit", "rollback"}


def _session_attr_chain(node: ast.AST) -> list[str] | None:
    """Return the dotted attribute chain for ``a.b.c``, else None."""
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return list(reversed(parts))
    return None


def _is_db_session_call(node: ast.Call) -> str | None:
    """Return 'commit'/'rollback' when the call is db.session.<method>()."""
    if not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr not in COMMIT_ROLLBACK_CALLS:
        return None
    chain = _session_attr_chain(node.func)
    if chain and chain[-2:] == ["session", node.func.attr] and "db" in chain:
        return node.func.attr
    return None


def _is_atomic_transaction_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "atomic_transaction"


def _load_baseline() -> set[str]:
    """Read the accepted-violation snapshot, if one exists.

    The gate lands before the cleanup it is meant to enforce, so the existing
    violations are recorded rather than left for the next author to rediscover.
    Only *new* violations fail, which keeps the gate enforceable from day one
    instead of being switched off until the backlog is clear.
    """
    if not BASELINE_PATH.is_file():
        return set()
    return {
        line.strip()
        for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _write_baseline(findings: set[str]) -> None:
    body = "\n".join(sorted(findings))
    BASELINE_PATH.write_text(
        "# Accepted transaction-boundary violations in services/.\n"
        "# Each line is '<relpath>:<lineno>:<message>'.\n"
        "# Delete a line as you fix it; the gate fails on anything not listed.\n"
        "# Regenerate with: python scripts/lint/check_txn_boundaries.py --write-baseline\n"
        f"{body}\n",
        encoding="utf-8",
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    write_baseline = "--write-baseline" in sys.argv

    if not SERVICES_DIR.is_dir():
        print(f"::error::{SERVICES_DIR} does not exist")
        return 1

    failures: list[tuple[str, int, str]] = []
    scanned = 0

    for path in sorted(SERVICES_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        scanned += 1
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        is_entry_point = path.name in ENTRY_POINT_ALLOWLIST
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (OSError, SyntaxError) as exc:
            failures.append((rel, 0, f"unparseable: {exc}"))
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                method = _is_db_session_call(node)
                if method:
                    failures.append(
                        (
                            rel,
                            node.lineno,
                            f"db.session.{method}() in services/ - only the caller "
                            f"(routes/, or an allowlisted entry point) may end a transaction",
                        )
                    )

            if not is_entry_point and _is_atomic_transaction_name(node):
                failures.append(
                    (
                        rel,
                        getattr(node, "lineno", 0),
                        "atomic_transaction() in services/ - the commit boundary belongs "
                        "to routes/; use db.session.flush() here",
                    )
                )

    findings = {f"{rel}:{line}: {message}" for rel, line, message in failures}

    if write_baseline:
        _write_baseline(findings)
        print(f"Wrote baseline with {len(findings)} accepted violation(s) to {BASELINE_PATH.name}.")
        return 0

    baseline = _load_baseline()
    new_findings = findings - baseline
    resolved = baseline - findings

    print(
        f"Transaction-boundary gate: scanned {scanned} service file(s) - "
        f"{len(findings)} violation(s), {len(baseline)} baselined, "
        f"{len(new_findings)} new. Allowlisted entry points: "
        f"{', '.join(sorted(ENTRY_POINT_ALLOWLIST)) or 'none'}"
    )
    for item in sorted(new_findings):
        print(f"::error::{item}")
    for item in sorted(resolved):
        print(f"::warning::baselined violation no longer occurs, drop it from the baseline: {item}")

    return 1 if new_findings else 0


if __name__ == "__main__":
    sys.exit(main())
