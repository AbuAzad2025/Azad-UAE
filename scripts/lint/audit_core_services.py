"""Targeted audit of inventory / payments / ledger services.

Deeper than the whole-layer gate: reports every commit/rollback call with its
function context (so an allowlisted one can be judged), and every write verb a
service uses, so it is visible at a glance that these services flush and let the
route commit.
"""

from __future__ import annotations

import ast
import os
from collections import Counter, defaultdict

GLOBS = (
    "services/*inventory*.py",
    "services/*stock*.py",
    "services/*payment*.py",
    "services/*receipt*.py",
    "services/*ledger*.py",
    "services/gl_*.py",
    "services/*cheque*.py",
)
WRITE_VERBS = {"add", "add_all", "bulk_save_objects", "bulk_insert_mappings", "delete", "merge"}
TXN = {"commit", "rollback", "flush", "begin_nested", "begin"}


def context_of(tree, target):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if sub is target:
                    return node.name
    return "<module>"


def main() -> int:
    files = sorted({f for g in GLOBS for f in __import__("glob").glob(g)})
    tx: Counter[str] = Counter()
    tx_detail: defaultdict[str, list[str]] = defaultdict(list)
    writes: Counter[str] = Counter()
    bad: list[str] = []

    for path in files:
        rel = os.path.basename(path)
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
        except SyntaxError as exc:
            print(f"  {rel}: SYNTAX ERROR {exc}")
            bad.append(rel)
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if not isinstance(f, ast.Attribute):
                continue
            fn = context_of(tree, node)
            verb = f.attr
            if verb in TXN:
                receiver = ast.unparse(f.value)
                chain = ast.unparse(f)
                # A SAVEPOINT is not a transaction. ``session.begin_nested()``
                # returns a SessionTransaction whose commit/rollback release or
                # undo that savepoint only - the caller's outer transaction is
                # untouched, which is the entire point of the retry pattern in
                # stock_service._safe_for_update. Only the *session's own*
                # commit/rollback end the transaction the route owns.
                is_savepoint = receiver == "savepoint" or "begin_nested" in chain
                if verb in ("commit", "rollback") and is_savepoint:
                    tx["savepoint." + verb] += 1
                    continue
                tx[verb] += 1
                tx_detail[verb].append(f"{rel}:{node.lineno} in {fn}() -> {chain}")
                if verb in ("commit", "rollback"):
                    bad.append(f"{rel}:{node.lineno} {verb} in {fn}()")
            if verb in WRITE_VERBS:
                writes[verb] += 1

    print(f"Targeted service audit: {len(files)} inventory/payment/ledger file(s)")
    print()
    print("  transaction verbs used:")
    for verb, n in sorted(tx.items(), key=lambda z: -z[1]):
        mark = "  <-- FORBIDDEN" if verb in ("commit", "rollback") else ""
        print(f"     {verb:14} {n:4}{mark}")
    print()
    print("  write verbs used (all should be flushed by the caller):")
    for verb, n in sorted(writes.items(), key=lambda z: -z[1]):
        print(f"     {verb:20} {n:4}")
    print()
    if bad:
        print(f"  VIOLATIONS: {len(bad)}")
        for b in bad[:20]:
            print(f"     {b}")
        return 1
    print("  no commit/rollback in any of these services - they flush, the route commits.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
