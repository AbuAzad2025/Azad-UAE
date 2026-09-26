"""Static gate for the Alembic graph.

The Work State block in AGENTS.md names the migration head, and a stale name there
has already misled a session into trusting the wrong revision. This script makes
that claim machine-checkable:

* exactly one head (a second head means `alembic upgrade head` is ambiguous);
* no revision points at a parent that does not exist (a dangling parent means the
  chain cannot be walked, which is how a dev database ends up stamped on a
  revision that no longer exists);
* every revision defines downgrade() so a round-trip stays possible.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"

REV = re.compile(r"^revision(?::\s*[^=]+)?\s*=\s*['\"]([^'\"]+)", re.M)
DOWN = re.compile(r"^down_revision(?::\s*[^=]+)?\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", re.M)


def main() -> int:
    if not VERSIONS.is_dir():
        print(f"FAIL: {VERSIONS} does not exist")
        return 1

    revisions: dict[str, str] = {}
    parents: dict[str, str | None] = {}
    missing_downgrade: list[str] = []

    for path in sorted(VERSIONS.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        rev = REV.search(text)
        if not rev:
            continue
        rid = rev.group(1)
        down = DOWN.search(text)
        revisions[rid] = path.name
        parents[rid] = down.group(1) if (down and down.group(1)) else None
        if "def downgrade(" not in text:
            missing_downgrade.append(path.name)

    if not revisions:
        print("FAIL: no alembic revisions found")
        return 1

    referenced = {p for p in parents.values() if p}
    heads = sorted(r for r in revisions if r not in referenced)
    roots = sorted(r for r, p in parents.items() if p is None)
    dangling = sorted(referenced - set(revisions))

    problems: list[str] = []
    if len(heads) != 1:
        problems.append(f"expected exactly 1 head, found {len(heads)}: {[(h, revisions[h]) for h in heads]}")
    if dangling:
        problems.append(f"dangling parent(s) referenced but not defined: {dangling}")
    if missing_downgrade:
        problems.append(f"revision(s) without downgrade(): {missing_downgrade}")
    if len(roots) != 1:
        problems.append(f"expected exactly 1 root, found {len(roots)}: {roots}")

    print(f"revisions : {len(revisions)}")
    print(f"roots     : {roots}")
    print(f"head      : {[(h, revisions[h]) for h in heads]}")

    if heads:
        chain: list[str] = []
        cur: str | None = heads[0]
        while cur:
            chain.append(cur)
            cur = parents.get(cur)
        print(f"chain len : {len(chain)}")
        if len(chain) != len(revisions):
            problems.append(f"chain from head covers {len(chain)} of {len(revisions)} revisions — graph is split")

    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        return 1
    print("OK: single head, no dangling parents, every revision reversible")
    return 0


if __name__ == "__main__":
    sys.exit(main())
