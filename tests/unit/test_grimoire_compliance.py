"""Pytest suite for Grimoire AST compliance enforcement.

Imports the enforcement engine from ``scripts/ops/enforce_grimoire.py``
and asserts that the codebase passes every check.

Each test function corresponds to one GRIMOIRE rule group.
Failures show exact file paths, line numbers, and messages.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ops.enforce_grimoire import (
    run_all_checks,
    check_atomicity,
    check_input_validation,
    check_decimal_guard,
    check_service_imports,
    check_model_imports,
    check_routes_db_queries,
    check_function_length,
    check_bare_except,
    check_type_ignore,
    check_root_cleanliness,
    Violation,
)


def _format_violations(violations: list[Violation]) -> str:
    if not violations:
        return ""
    lines = [v.format() for v in violations]
    return "\n".join(lines)


def test_no_commit_outside_db_safety():
    """G1: db.session.commit() only in utils/db_safety.py."""
    violations = list(check_atomicity(PROJECT_ROOT))
    commits = [v for v in violations if "commit()" in v.message]
    assert not commits, "Forbidden commit() calls:\n" + _format_violations(commits)


def test_no_rollback_outside_db_safety():
    """G1: db.session.rollback() only in utils/db_safety.py + dry-run files."""
    violations = list(check_atomicity(PROJECT_ROOT))
    rollbacks = [v for v in violations if "rollback()" in v.message]
    assert not rollbacks, "Forbidden rollback() calls:\n" + _format_violations(rollbacks)


def test_request_get_json_silent():
    """G3: Every request.get_json() must use silent=True."""
    violations = list(check_input_validation(PROJECT_ROOT))
    assert not violations, "Missing silent=True:\n" + _format_violations(violations)


def test_decimal_guard():
    """G3: Decimal() must not receive raw data.get() without str() wrap."""
    violations = list(check_decimal_guard(PROJECT_ROOT))
    assert not violations, "Unguarded Decimal():\n" + _format_violations(violations)


def test_services_no_route_imports():
    """G4: services/ must not import from routes/ or flask HTTP helpers."""
    violations = list(check_service_imports(PROJECT_ROOT))
    assert not violations, "Forbidden imports in services/:\n" + _format_violations(violations)


def test_models_no_http_concepts():
    """G4: models/ must not import HTTP concepts or routes."""
    violations = list(check_model_imports(PROJECT_ROOT))
    assert not violations, "Forbidden imports in models/:\n" + _format_violations(violations)


def test_routes_no_direct_db_queries():
    """G4: routes/ should not contain direct db.session.query() calls."""
    violations = list(check_routes_db_queries(PROJECT_ROOT))
    # Warnings only — not a hard failure, but should be tracked
    if violations:
        pytest.skip("db.session.query() in routes/ (warnings):\n" + _format_violations(violations))


def test_no_bare_except_pass():
    """G6: No bare 'except: pass' — must log errors."""
    violations = list(check_bare_except(PROJECT_ROOT))
    assert not violations, "Bare except: pass found:\n" + _format_violations(violations)


def test_no_type_ignore():
    """G7: No '# type: ignore' — use proper annotations (warning-level)."""
    violations = list(check_type_ignore(PROJECT_ROOT))
    if violations:
        count = len(violations)
        pytest.skip(f"{count} '# type: ignore' found (warnings):\n" + _format_violations(violations))


def test_function_length():
    """G7: Functions should not exceed 80 lines."""
    violations = list(check_function_length(PROJECT_ROOT))
    # Warnings — report but don't fail
    if violations:
        count = len(violations)
        pytest.skip(f"{count} functions exceed 80 lines (warnings):\n" + _format_violations(violations))


def test_root_cleanliness():
    """G9: Root directory must contain only allowed files."""
    violations = list(check_root_cleanliness(PROJECT_ROOT))
    assert not violations, "Orphaned root files:\n" + _format_violations(violations)


def test_full_compliance_summary():
    """Run all checks and print a summary (informational, not a hard assert)."""
    result = run_all_checks(PROJECT_ROOT)
    errors = [v for v in result.violations if v.severity == "error"]
    warnings = [v for v in result.violations if v.severity == "warning"]
    print(f"\n{'=' * 60}")
    print("Grimoire Compliance Summary")
    print(f"{'=' * 60}")
    print(f"Files scanned: {result.files_scanned}")
    print(f"Errors:   {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    if result.violations:
        print("\nViolations:")
        for v in sorted(result.violations, key=lambda x: (x.file, x.line)):
            print(f"  {v.format()}")
    print(f"{'=' * 60}")
