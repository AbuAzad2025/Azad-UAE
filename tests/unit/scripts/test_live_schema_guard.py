"""The live schema guard must detect a missing CHECK constraint."""

from __future__ import annotations

import importlib.util
from pathlib import Path

GUARD = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "verify_live_schema_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_live_schema_guard", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_declared_constraints_exclude_intentionally_dropped():
    guard = _load()
    declared = guard._declared_constraints()
    # ck_pws_quantity was created in 86afead128ce but deliberately dropped in
    # f1c6a8d3b5e9 (negative stock is governed in StockService), so it must not
    # be reported as a guard the database is required to carry.
    assert "ck_pws_quantity" not in declared
    # ...while genuine guards are still required.
    assert "ck_gl_entries_status" in declared or any(n.startswith("ck_gl") for n in declared)
    assert declared, "no migration-declared CHECK constraints found — the guard would pass vacuously"


def test_a_missing_guard_fails(monkeypatch, capsys):
    """If a declared guard is absent from the live DB, main() must return 1."""
    import os

    guard = _load()
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        import pytest

        pytest.skip("no TEST_DATABASE_URL — cannot exercise a live DB")
    monkeypatch.setenv("DATABASE_URL", url)
    # Declare a guard that can never exist in a real migrated database.
    monkeypatch.setattr(guard, "_declared_constraints", lambda: {"ck_this_guard_does_not_exist"})
    code = guard.main()
    assert code == 1
    assert "ck_this_guard_does_not_exist" in capsys.readouterr().out
