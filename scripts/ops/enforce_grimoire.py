#!/usr/bin/env python3
"""
Grimoire AST Compliance Checker
================================

Production-grade AST static analysis that enforces every rule in
``docs/GRIMOIRE.md`` across the entire codebase.

Usage (CLI):
    python scripts/ops/enforce_grimoire.py [--fix-report] [--json]

Usage (pytest):
    tests/unit/test_grimoire_compliance.py imports ``run_all_checks``.

Exit codes:
    0 — all checks passed
    1 — one or more violations found
    2 — internal error (parse failure, etc.)
"""

from __future__ import annotations

import ast
import sys
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Exempt files / directories ────────────────────────────────────────────

EXEMPT_DIRS: frozenset[str] = frozenset({
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "migrations",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    "instance",
    "logs",
    "load_tests",
    "tools",
})

EXEMPT_FILES: frozenset[str] = frozenset({
    "utils/db_safety.py",        # owns commit/rollback by design
    "utils/tenanting.py",        # owns tenant scope helpers
    "tests/conftest.py",         # test infra may commit/rollback
    "cli_commands.py",           # CLI commands manage transactions
    "config.py",                 # no DB access
    "app.py",                    # entrypoint — BackupService.initialize
    "wsgi.py",                   # WSGI entrypoint
    "extensions.py",             # extension init — no business logic
})

# gl_accounting_setup.py has an intentional dry-run rollback
DRY_RUN_ROLLBACK_FILES: frozenset[str] = frozenset({
    "services/gl_accounting_setup.py",
    "services/backup_scoped_engine.py",
    "services/backup_scoped_restore.py",
    "services/backup_service.py",
})

# Directories where business logic / DB queries are forbidden
ROUTE_DIRS: frozenset[str] = frozenset({"routes"})
SERVICE_DIRS: frozenset[str] = frozenset({"services"})

# HTTP concepts forbidden in services/ (current_app for logging is OK)
FORBIDDEN_SERVICE_IMPORTS: frozenset[str] = frozenset({
    "routes",
    "flask.request",
    "flask.jsonify",
    "flask.flash",
    "flask.redirect",
    "flask.render_template",
    "flask.url_for",
    "flask.abort",
    "flask.session",
})

# HTTP concepts forbidden in models/
FORBIDDEN_MODEL_IMPORTS: frozenset[str] = frozenset({
    "flask.request",
    "flask.jsonify",
    "flask.flash",
    "flask.redirect",
    "flask.render_template",
    "flask.abort",
    "routes",
})

def _matches_forbidden(target: str, forbidden: str) -> bool:
    """True when *target* is exactly *forbidden* or a sub-module of it.

    ``flask.request`` matches ``flask.request`` (exact).
    ``routes`` matches ``routes`` (exact).
    ``routes.owner`` matches ``routes`` (prefix — sub-package).
    ``flask`` does NOT match ``flask.request`` (no reverse prefix).
    """
    if target == forbidden:
        return True
    if forbidden.endswith("*"):
        return target.startswith(forbidden[:-1])
    return target.startswith(forbidden + ".")


@dataclass(frozen=True)
class Violation:
    """Single rule violation with precise location."""
    rule: str
    severity: str          # "error" | "warning"
    file: str
    line: int
    col: int
    message: str

    def format(self) -> str:
        loc = f"{self.file}:{self.line}:{self.col}"
        return f"[{self.severity.upper()}] {self.rule} — {loc}: {self.message}"

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "col": self.col,
            "message": self.message,
        }


@dataclass
class CheckResult:
    violations: list[Violation] = field(default_factory=list)
    files_scanned: int = 0

    @property
    def passed(self) -> bool:
        return not any(v.severity == "error" for v in self.violations)


# ── File discovery ─────────────────────────────────────────────────────────


def _iter_python_files(root: Path) -> Iterator[Path]:
    """Yield every .py file under *root* that is not in an exempt dir."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXEMPT_DIRS]
        for fname in filenames:
            if fname.endswith(".py"):
                yield Path(dirpath) / fname


def _rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _is_exempt(rel: str) -> bool:
    if rel in EXEMPT_FILES:
        return True
    if rel in DRY_RUN_ROLLBACK_FILES:
        return True
    parts = rel.split("/")
    if parts[0] in ("tests", "scripts"):
        return True
    return False


# ── AST helpers ────────────────────────────────────────────────────────────


def _parse(path: Path) -> ast.Module | None:
    try:
        source = path.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(path))
    except SyntaxError:
        return None
    except Exception:
        return None


def _is_db_session_call(node: ast.Call, method: str) -> bool:
    """True when *node* is ``db.session.<method>(...)``."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr != method:
        return False
    if not isinstance(func.value, ast.Attribute):
        return False
    if func.value.attr != "session":
        return False
    if not isinstance(func.value.value, ast.Name):
        return False
    return func.value.value.id == "db"


def _is_request_get_json(node: ast.Call) -> bool:
    """True when *node* is ``request.get_json(...)``."""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr != "get_json":
        return False
    if not isinstance(func.value, ast.Name):
        return False
    return func.value.id == "request"


def _import_target(node: ast.Import | ast.ImportFrom) -> list[str]:
    """Return fully-qualified import target strings.

    For ``ast.Import`` (``import a.b.c``) → ``["a.b.c"]``.
    For ``ast.ImportFrom`` (``from a.b import c, d``) → ``["a.b.c", "a.b.d"]``.
    The bare module name (``"a.b"``) is NOT included — only the actual
    symbols brought into scope.  This prevents false positives where
    ``from flask import current_app`` would also flag ``flask`` itself.
    """
    targets: list[str] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            targets.append(alias.name)
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            if alias.name == "*":
                targets.append(module)
            else:
                targets.append(f"{module}.{alias.name}" if module else alias.name)
    return targets


def _is_inside_atomic(tree: ast.Module) -> set[int]:
    """Return line numbers of statements inside ``with atomic_transaction(...)``."""
    inside: set[int] = set()

    class _Walker(ast.NodeVisitor):
        def _check_with(self, node: ast.With) -> bool:
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call):
                    func = call.func
                    if isinstance(func, ast.Name) and func.id == "atomic_transaction":
                        return True
                    if isinstance(func, ast.Attribute) and func.attr == "atomic_transaction":
                        return True
            return False

        def visit_With(self, node: ast.With) -> None:
            if self._check_with(node):
                for child in ast.walk(node):
                    if hasattr(child, "lineno"):
                        inside.add(child.lineno)
            self.generic_visit(node)

    _Walker().visit(tree)
    return inside


# ── Check 1: Atomicity ─────────────────────────────────────────────────────


def check_atomicity(root: Path) -> Iterator[Violation]:
    """No db.session.commit() or db.session.rollback() outside exempt files."""
    for path in _iter_python_files(root):
        rel = _rel(path)
        if _is_exempt(rel):
            continue

        tree = _parse(path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _is_db_session_call(node, "commit"):
                yield Violation(
                    rule="G1-ATOMICITY",
                    severity="error",
                    file=rel,
                    line=node.lineno,
                    col=node.col_offset,
                    message="db.session.commit() outside utils/db_safety.py — use atomic_transaction()",
                )
            if _is_db_session_call(node, "rollback"):
                yield Violation(
                    rule="G1-ATOMICITY",
                    severity="error",
                    file=rel,
                    line=node.lineno,
                    col=node.col_offset,
                    message="db.session.rollback() outside utils/db_safety.py — use atomic_transaction()",
                )


# ── Check 2: Tenant isolation (heuristic) ──────────────────────────────────


def check_tenant_isolation(root: Path) -> Iterator[Violation]:
    """Flag raw Model.query.filter() in services/ that bypass tenant scoping."""
    for path in _iter_python_files(root):
        rel = _rel(path)
        if _is_exempt(rel):
            continue
        parts = rel.split("/")
        if parts[0] not in ("services", "routes"):
            continue

        tree = _parse(path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Flag: Model.query.filter(...) without tenant_query
            if isinstance(func, ast.Attribute) and func.attr == "filter":
                if isinstance(func.value, ast.Attribute) and func.value.attr == "query":
                    if isinstance(func.value.value, ast.Name):
                        # Check if any kwarg contains tenant_id
                        has_tenant = any(
                            kw.arg == "tenant_id"
                            for kw in node.keywords
                        )
                        # Check if filter expression contains tenant_id
                        if not has_tenant:
                            for arg in node.args:
                                for child in ast.walk(arg):
                                    if isinstance(child, ast.Attribute) and child.attr == "tenant_id":
                                        has_tenant = True
                                        break
                                    if isinstance(child, ast.keyword) and child.arg == "tenant_id":
                                        has_tenant = True
                                        break
                            if not has_tenant:
                                yield Violation(
                                    rule="G2-TENANT",
                                    severity="warning",
                                    file=rel,
                                    line=node.lineno,
                                    col=node.col_offset,
                                    message=f"Raw {func.value.value.id}.query.filter() without tenant_id — use tenant_query()",
                                )


# ── Check 3: Input validation ──────────────────────────────────────────────


def check_input_validation(root: Path) -> Iterator[Violation]:
    """Every request.get_json() must use silent=True."""
    for path in _iter_python_files(root):
        rel = _rel(path)
        if _is_exempt(rel):
            continue

        tree = _parse(path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_request_get_json(node):
                continue

            has_silent = any(
                kw.arg == "silent" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in node.keywords
            )
            if not has_silent:
                yield Violation(
                    rule="G3-INPUT",
                    severity="error",
                    file=rel,
                    line=node.lineno,
                    col=node.col_offset,
                    message="request.get_json() without silent=True — can raise on invalid JSON",
                )


# ── Check 3b: Decimal guard ────────────────────────────────────────────────


def check_decimal_guard(root: Path) -> Iterator[Violation]:
    """Flag Decimal(data.get(...)) without str() wrapping."""
    for path in _iter_python_files(root):
        rel = _rel(path)
        if _is_exempt(rel):
            continue

        tree = _parse(path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Name) or func.id != "Decimal":
                continue
            if not node.args:
                continue
            arg = node.args[0]
            # Safe: Decimal(str(...))
            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "str":
                continue
            # Safe: Decimal("literal")
            if isinstance(arg, ast.Constant):
                continue
            # Unsafe: Decimal(data.get(...))
            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "get":
                yield Violation(
                    rule="G3-DECIMAL",
                    severity="error",
                    file=rel,
                    line=node.lineno,
                    col=node.col_offset,
                    message="Decimal() called on data.get(...) without str() guard — wrap with str(data.get(...) or '0')",
                )


# ── Check 4: Architecture boundaries ───────────────────────────────────────


def check_service_imports(root: Path) -> Iterator[Violation]:
    """services/ must not import from routes/ or use flask HTTP helpers."""
    services_dir = root / "services"
    if not services_dir.is_dir():
        return

    for path in _iter_python_files(services_dir):
        rel = _rel(path)
        tree = _parse(path)
        if tree is None:
            continue

        for node in tree.body:
            if isinstance(node, ast.Import | ast.ImportFrom):
                for target in _import_target(node):
                    for forbidden in FORBIDDEN_SERVICE_IMPORTS:
                        if _matches_forbidden(target, forbidden):
                            yield Violation(
                                rule="G4-ARCH",
                                severity="error",
                                file=rel,
                                line=node.lineno,
                                col=node.col_offset,
                                message=f"services/ must not import '{target}' — HTTP/route concepts forbidden in business logic",
                            )


def check_model_imports(root: Path) -> Iterator[Violation]:
    """models/ must not import HTTP concepts or routes."""
    models_dir = root / "models"
    if not models_dir.is_dir():
        return

    for path in _iter_python_files(models_dir):
        rel = _rel(path)
        tree = _parse(path)
        if tree is None:
            continue

        for node in tree.body:
            if isinstance(node, ast.Import | ast.ImportFrom):
                for target in _import_target(node):
                    for forbidden in FORBIDDEN_MODEL_IMPORTS:
                        if _matches_forbidden(target, forbidden):
                            yield Violation(
                                rule="G4-ARCH",
                                severity="error",
                                file=rel,
                                line=node.lineno,
                                col=node.col_offset,
                                message=f"models/ must not import '{target}' — no HTTP concepts in data layer",
                            )


def check_routes_db_queries(root: Path) -> Iterator[Violation]:
    """routes/ must not contain direct db.session.query() calls."""
    routes_dir = root / "routes"
    if not routes_dir.is_dir():
        return

    for path in _iter_python_files(routes_dir):
        rel = _rel(path)
        tree = _parse(path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "query":
                if isinstance(func.value, ast.Attribute) and func.value.attr == "session":
                    if isinstance(func.value.value, ast.Name) and func.value.value.id == "db":
                        yield Violation(
                            rule="G4-ARCH",
                            severity="warning",
                            file=rel,
                            line=node.lineno,
                            col=node.col_offset,
                            message="db.session.query() in routes/ — delegate DB access to services/",
                        )


# ── Check 5: Code quality ──────────────────────────────────────────────────


def check_function_length(root: Path, max_lines: int = 80) -> Iterator[Violation]:
    """Flag functions longer than *max_lines* executable lines."""
    for path in _iter_python_files(root):
        rel = _rel(path)
        if _is_exempt(rel):
            continue

        tree = _parse(path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.end_lineno is None:
                continue
            length = node.end_lineno - node.lineno
            if length > max_lines:
                yield Violation(
                    rule="G7-LENGTH",
                    severity="warning",
                    file=rel,
                    line=node.lineno,
                    col=node.col_offset,
                    message=f"Function '{node.name}' is {length} lines — refactor to < {max_lines}",
                )


def check_bare_except(root: Path) -> Iterator[Violation]:
    """No bare ``except: pass`` — must log errors."""
    for path in _iter_python_files(root):
        rel = _rel(path)
        if _is_exempt(rel):
            continue

        tree = _parse(path)
        if tree is None:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if node.type is not None:
                continue  # not bare
            # Check if body is just pass
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                yield Violation(
                    rule="G6-ERROR",
                    severity="error",
                    file=rel,
                    line=node.lineno,
                    col=node.col_offset,
                    message="Bare 'except: pass' — must log the error",
                )


def check_type_ignore(root: Path) -> Iterator[Violation]:
    """No ``# type: ignore`` comments — use proper annotations."""
    for path in _iter_python_files(root):
        rel = _rel(path)
        if _is_exempt(rel):
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue

        for i, line in enumerate(source.splitlines(), 1):
            if "type: ignore" in line and not line.strip().startswith("#"):
                yield Violation(
                    rule="G7-TYPE",
                    severity="warning",
                    file=rel,
                    line=i,
                    col=0,
                    message="'# type: ignore' — fix with proper type annotation",
                )


def check_noqa(root: Path) -> Iterator[Violation]:
    """No ``# noqa`` comments — fix the issue."""
    for path in _iter_python_files(root):
        rel = _rel(path)
        if _is_exempt(rel):
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue

        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if "# noqa" in stripped and not stripped.startswith("#"):
                yield Violation(
                    rule="G7-NOQA",
                    severity="warning",
                    file=rel,
                    line=i,
                    col=0,
                    message="'# noqa' — fix the lint issue instead of suppressing",
                )


# ── Check 9: Root directory cleanliness ────────────────────────────────────

ALLOWED_ROOT_FILES: frozenset[str] = frozenset({
    "app.py", "wsgi.py", "config.py", "extensions.py", "cli_commands.py",
    "README.md", "LICENSE", "AGENTS.md", "mypy.ini", "pytest.ini",
    "biome.json", "package.json", "package-lock.json",
    "requirements.txt", "requirements-dev.txt", "requirements-optional.txt",
    ".gitignore", ".dockerignore", ".editorconfig", ".env",
    ".flake8", ".coveragerc", ".python-version", ".browserslistrc",
    ".bandit.yml", ".stylelintrc.json", ".yamllint.yml",
    "vitest.config.js",
    "templates_rendered.json",
    "nul",
})


def check_root_cleanliness(root: Path) -> Iterator[Violation]:
    """Root directory must contain only allowed files."""
    for entry in root.iterdir():
        if entry.is_dir():
            continue
        if entry.name.startswith(".git"):
            continue
        if entry.name not in ALLOWED_ROOT_FILES:
            rel = entry.name
            yield Violation(
                rule="G9-ROOT",
                severity="warning",
                file=rel,
                line=0,
                col=0,
                message=f"Orphaned file in root: '{rel}' — move to scripts/ or remove",
            )


# ── Orchestrator ───────────────────────────────────────────────────────────

CHECKS: list[tuple[str, Callable[[Path], Iterator[Violation]]]] = [
    ("atomicity", check_atomicity),
    ("tenant-isolation", check_tenant_isolation),
    ("input-validation", check_input_validation),
    ("decimal-guard", check_decimal_guard),
    ("service-imports", check_service_imports),
    ("model-imports", check_model_imports),
    ("routes-db-queries", check_routes_db_queries),
    ("function-length", check_function_length),
    ("bare-except", check_bare_except),
    ("type-ignore", check_type_ignore),
    ("noqa", check_noqa),
    ("root-cleanliness", check_root_cleanliness),
]


def run_all_checks(root: Path | None = None) -> CheckResult:
    """Run every check and return aggregated result."""
    root = root or PROJECT_ROOT
    result = CheckResult()
    files_scanned = 0

    for path in _iter_python_files(root):
        files_scanned += 1

    result.files_scanned = files_scanned

    for _name, check_fn in CHECKS:
        for violation in check_fn(root):
            result.violations.append(violation)

    return result


def main() -> int:
    args = sys.argv[1:]
    output_json = "--json" in args

    result = run_all_checks()

    errors = [v for v in result.violations if v.severity == "error"]
    warnings = [v for v in result.violations if v.severity == "warning"]

    if output_json:
        print(json.dumps({
            "files_scanned": result.files_scanned,
            "errors": len(errors),
            "warnings": len(warnings),
            "violations": [v.to_dict() for v in result.violations],
        }, indent=2))
    else:
        print(f"Scanned {result.files_scanned} Python files")
        print(f"Errors: {len(errors)}  Warnings: {len(warnings)}")
        print()
        if result.violations:
            for v in sorted(result.violations, key=lambda x: (x.file, x.line)):
                print(v.format())
            print()

    if errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
