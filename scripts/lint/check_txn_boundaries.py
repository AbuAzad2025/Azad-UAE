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


def _load_baseline() -> dict[str, int]:
    """Read the accepted-violation snapshot, if one exists.

    The gate lands before the cleanup it is meant to enforce, so the existing
    violations are recorded rather than left for the next author to rediscover.
    Only *new* violations fail, which keeps the gate enforceable from day one
    instead of being switched off until the backlog is clear.

    The baseline maps ``<relpath>|<message>`` to how many times that exact
    problem is accepted in that file. Counting, rather than listing line
    numbers, is what makes the gate both stable and useful:

    * Keying on the line meant that editing a docstring above a call shifted it
      and the gate reported a brand new violation for code nobody had touched.
    * Keying on the pair alone meant the opposite failure: a file that already
      had one ``atomic_transaction`` would hide every further one added to it.

    Counting satisfies both - the identity survives an edit above the call, and
    adding a tenth call to a file with nine still fails the build.
    """
    if not BASELINE_PATH.is_file():
        return {}
    accepted: dict[str, int] = {}
    for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.lstrip().startswith("#"):
            continue
        key, _, count = line.rpartition("=")
        try:
            accepted[key.strip()] = int(count)
        except ValueError:
            continue
    return accepted


def _write_baseline(findings: dict[str, int]) -> None:
    body = "\n".join(f"{key}={count}" for key, count in sorted(findings.items()))
    BASELINE_PATH.write_text(
        "# Accepted transaction-boundary violations in services/.\n"
        "# Format: '<relpath>|<message>=<accepted count>'.\n"
        "# The count is what makes the gate stable under edits above a call and\n"
        "# still able to fail on a newly added one. Drop a line as you fix it.\n"
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

    counts: dict[str, int] = {}
    located: dict[str, int] = {}
    for rel, line, message in failures:
        key = f"{rel}|{message}"
        counts[key] = counts.get(key, 0) + 1
        # Report the first occurrence; that is enough to navigate to.
        located.setdefault(key, line)

    if write_baseline:
        _write_baseline(counts)
        total = sum(counts.values())
        print(f"Wrote baseline: {total} accepted violation(s) across {len(counts)} file/message pair(s).")
        return 0

    baseline = _load_baseline()
    new_findings: list[str] = []
    for key, count in sorted(counts.items()):
        allowed = baseline.get(key, 0)
        if count > allowed:
            new_findings.append(key)

    resolved = sorted(set(baseline) - set(counts))
    total_found = sum(counts.values())
    total_accepted = sum(baseline.values())

    print(
        f"Transaction-boundary gate: scanned {scanned} service file(s) - "
        f"{total_found} violation(s), {total_accepted} baselined, {len(new_findings)} new. "
        f"Allowlisted entry points: {', '.join(sorted(ENTRY_POINT_ALLOWLIST)) or 'none'}"
    )
    for key in new_findings:
        rel, _, message = key.partition("|")
        print(f"::error file={rel},line={located.get(key, 0)}::{message}")
    for key in resolved:
        print(f"::warning::baselined violation no longer occurs, drop it from the baseline: {key}")

    return 1 if new_findings else 0


if __name__ == "__main__":
    sys.exit(main())
