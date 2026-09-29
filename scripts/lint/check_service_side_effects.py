"""AST audit of the service layer: transaction boundaries and schema side effects.

Two rules, checked structurally rather than by grep:

1. Services never end a transaction. ``db.session.commit()`` and
   ``db.session.rollback()`` belong to utils/db_safety.py (and the route layer).
   ``flush()`` is the only verb a service may use.
2. Services never manage the schema or the connection. ``create_all``,
   ``drop_all``, ``create_engine``, ``engine.begin()`` and raw DDL belong to
   Alembic and to app/bootstrap.py, not to a service.

Run directly, or as a lint gate.
"""

from __future__ import annotations

import ast
import glob
import os
from collections import defaultdict

TXN_FORBIDDEN = ("commit", "rollback")
TXN_ALLOWED_FILE = "utils/db_safety.py"
SCHEMA_FORBIDDEN = (
    "create_all",
    "drop_all",
    "create_engine",
    "engine.begin",
    "MetaData",
    "DDL",
    "execute",
)
SCHEMA_ALLOWLIST = {
    # Read reporting and audit queries are not schema management.
    "services/logging_core.py",
    "services/audit_service.py",
    "services/error_log_service.py",
    "services/performance_monitor.py",
    "services/backup_service.py",
    "services/backup_scoped_engine.py",
    "services/backup_scoped_restore.py",
    "services/db_health_service.py",
    "services/maintenance_service.py",
    "services/schema_health_service.py",
    # Opens a connection to a SCRATCH database, not the application one. A
    # restore drill has to talk to the artifact's target directly, and it
    # refuses to run at all if that target matches DATABASE_URL (see its
    # resolve_scratch_database_url). Not schema management of the app.
    "services/restore_drill.py",
}

TARGET_DIRS = ("services",)
SKIP_PARTS = ("node_modules", ".venv", "site-packages", "__pycache__")


def _attr_chain(node: ast.AST) -> str:
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def audit_file(path: str) -> list[tuple[int, str, str]]:
    rel = path.replace("\\", "/")
    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
    except SyntaxError as exc:
        return [(exc.lineno or 0, "SYNTAX", str(exc))]

    out: list[tuple[int, str, str]] = []
    in_schema_fn = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            in_schema_fn = name.startswith(("_ensure_column", "_ensure_index", "verify_schema", "_run_alembic"))
        for sub in ast.walk(node) if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else [node]:
            if not isinstance(sub, ast.Call):
                continue
            chain = _attr_chain(sub.func)
            if not chain:
                continue
            tail = chain.rsplit(".", 1)[-1]

            if rel.endswith(TXN_ALLOWED_FILE):
                continue
            if tail in TXN_FORBIDDEN and ("session" in chain or "db." in chain):
                # A savepoint is not a transaction: begin_nested() returns a
                # SessionTransaction whose commit/rollback only undo that
                # savepoint. Flagging those would be a false positive on the
                # correct lock-retry pattern in stock_service.
                receiver = _attr_chain(sub.func.value) if isinstance(sub.func, ast.Attribute) else ""
                is_savepoint = receiver == "savepoint" or "begin_nested" in chain
                if is_savepoint:
                    continue
                out.append((sub.lineno, "TXN", f"{rel}: services must flush, not {tail}() ({chain})"))

            if rel.startswith(TARGET_DIRS) and rel not in SCHEMA_ALLOWLIST:
                if tail in ("create_all", "drop_all", "create_engine") or chain.endswith("engine.begin"):
                    out.append((sub.lineno, "SCHEMA", f"{rel}: schema/connection management outside Alembic ({chain})"))
                if in_schema_fn and tail == "execute" and "text(" in ast.unparse(sub):
                    out.append((sub.lineno, "DDL", f"{rel}: raw DDL in a service ({chain})"))
    return out


def main() -> int:
    findings: list[tuple[int, str, str]] = []
    files = 0
    for root in TARGET_DIRS:
        for path in glob.glob(os.path.join(root, "**", "*.py"), recursive=True):
            if any(p in path for p in SKIP_PARTS):
                continue
            files += 1
            findings.extend(audit_file(path))

    by_kind: dict[str, list[str]] = defaultdict(list)
    for _lineno, kind, msg in findings:
        by_kind[kind].append(msg)

    print(f"Side-effect gate: {files} service file(s) scanned - {len(findings)} finding(s).")
    for kind in sorted(by_kind):
        print(f"\n  [{kind}] {len(by_kind[kind])}")
        for msg in sorted(set(by_kind[kind]))[:25]:
            print(f"     {msg}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
