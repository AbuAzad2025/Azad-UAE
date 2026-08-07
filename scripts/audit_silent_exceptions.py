"""Silent-exception audit — CI gate.

Catches error-swallowing patterns that ruff/mypy cannot see. Zero tolerance:
no per-file ignores, no noqa-style opt-outs. If a pattern is legitimate, the
code must log or re-raise instead of being excluded here.

Rules (AST-based, all .py files under tracked source roots):
  SE1  except handler whose body only swallows (pass / ... / continue) with no logging call
  SE2  except handler returning a constant (None / [] / {} / False) with no logging call
  SE3  getattr(obj, 'tenant_id'|'branch_id', <default>) — hides missing-attribute bugs and
       can silently drop tenant scoping
  SE4  bare `except:` with no exception type
  SE5  in protected financial files, `except Exception` that neither re-raises nor logs
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOURCE_ROOTS = [
    "app",
    "ai_knowledge",
    "models",
    "routes",
    "services",
    "utils",
    "extensions.py",
    "wsgi.py",
    "config.py",
]

# Tenant isolation and financial integrity: SE3/SE5 apply here (and SE1/SE2 too).
PROTECTED_FILES = {
    "services/gl_service.py",
    "services/gl_posting.py",
    "services/payment_service.py",
    "services/receipt_service.py",
    "services/stock_service.py",
    "services/sale_service.py",
    "services/customer_service.py",
    "services/supplier_service.py",
    "services/cheque_service.py",
    "services/exchange_rate_service.py",
    "services/purchase_service.py",
    "routes/payment_vault.py",
    "utils/tenanting.py",
    "utils/tenant_orm.py",
    "utils/tenant_security.py",
    "utils/branching.py",
}

LOGGING_NAMES = {"logger", "logging", "log", "current_app", "app"}
SCOPING_ATTRS = {"tenant_id", "branch_id"}


class _HandlerVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.logs = False
        self.reraises = False

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            base = func.value
            if isinstance(base, ast.Call) and isinstance(base.func, ast.Attribute) and base.func.attr == "getLogger":
                if func.attr in {"debug", "info", "warning", "error", "exception", "critical", "log"}:
                    self.logs = True
                self.generic_visit(node)
                return
            name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
            if name in LOGGING_NAMES and func.attr in {
                "debug",
                "info",
                "warning",
                "error",
                "exception",
                "critical",
                "log",
            }:
                self.logs = True
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        self.reraises = True
        self.generic_visit(node)


def _handler_stats(handler: ast.ExceptHandler) -> _HandlerVisitor:
    visitor = _HandlerVisitor()
    for stmt in handler.body:
        visitor.visit(stmt)
    return visitor


def _is_swallow_only(handler: ast.ExceptHandler) -> bool:
    return all(
        isinstance(stmt, (ast.Pass, ast.Continue))
        or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis)
        for stmt in handler.body
    )


def _returns_constant(handler: ast.ExceptHandler) -> bool:
    for stmt in handler.body:
        if isinstance(stmt, ast.Return):
            value = stmt.value
            if value is None:
                return True
            if isinstance(value, ast.Constant) and value.value in (None, False):
                return True
            if isinstance(value, (ast.List, ast.Dict, ast.Set)) and not getattr(value, "elts", getattr(value, "keys", [])):
                return True
            if isinstance(value, ast.Tuple) and all(isinstance(e, ast.Constant) and e.value is None for e in value.elts):
                return True
    return False


def _is_broad_catch(handler: ast.ExceptHandler) -> bool:
    node = handler.type
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in {"Exception", "BaseException"}
    if isinstance(node, ast.Tuple):
        return any(isinstance(e, ast.Name) and e.id in {"Exception", "BaseException"} for e in node.elts)
    return False


def audit_file(path: Path, rel: str) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except SyntaxError as exc:
        return [f"{rel}:{exc.lineno}: SE0 unparsable file: {exc.msg}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            stats = _handler_stats(node)
            if node.type is None:
                errors.append(f"{rel}:{node.lineno}: SE4 bare `except:` — catch a specific exception type")
            elif _is_swallow_only(node) and not stats.logs:
                errors.append(f"{rel}:{node.lineno}: SE1 except swallows silently (pass/continue) without logging")
            elif _is_broad_catch(node) and _returns_constant(node) and not stats.logs:
                errors.append(f"{rel}:{node.lineno}: SE2 broad except returns constant silently without logging")
            if (
                rel in PROTECTED_FILES
                and isinstance(node.type, ast.Name)
                and node.type.id in {"Exception", "BaseException"}
                and not stats.reraises
                and not stats.logs
            ):
                errors.append(
                    f"{rel}:{node.lineno}: SE5 protected file catches Exception without logging or re-raise"
                )
        elif (
            rel in PROTECTED_FILES
            and isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
        ):
            if (
                len(node.args) >= 3
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value in SCOPING_ATTRS
            ):
                errors.append(
                    f"{rel}:{node.lineno}: SE3 getattr(..., {node.args[1].value!r}, default) hides missing scoping attribute"
                )
    return errors


def main() -> int:
    all_errors: list[str] = []
    for root in SOURCE_ROOTS:
        base = ROOT / root
        if base.is_file() and base.suffix == ".py":
            all_errors.extend(audit_file(base, root))
        elif base.is_dir():
            for path in sorted(base.rglob("*.py")):
                if any(part in {".venv", "node_modules", "__pycache__", ".ci-repro", ".ci-repro2"} for part in path.parts):
                    continue
                all_errors.extend(audit_file(path, path.relative_to(ROOT).as_posix()))
    for error in all_errors:
        print(f"::error::{error}")
    if all_errors:
        print(f"\nSilent-exception audit FAILED: {len(all_errors)} violation(s). Fix the code — this gate has no exceptions.")
        return 1
    print("Silent-exception audit passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
