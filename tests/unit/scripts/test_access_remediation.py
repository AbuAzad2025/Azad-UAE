"""Guards for the route-access remediation sweep."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_ledger_admin_routes_use_finance_admin_guard() -> None:
    source = (ROOT / "routes" / "ledger.py").read_text(encoding="utf-8")
    block = source[source.index('@ledger_bp.route("/admin-dashboard")') : source.index("def admin_settings")]
    assert block.count("@finance_admin_required") >= 10
    assert "@admin_required" not in block


def test_finance_admin_policy_allows_only_finance_roles() -> None:
    source = (ROOT / "utils" / "decorators.py").read_text(encoding="utf-8")
    block = source[source.index("def finance_admin_required") : source.index("def seller_or_above")]
    assert "RoleEnum.MANAGER.value" in block
    assert "RoleEnum.ACCOUNTANT.value" in block
    assert "is_admin_surface_user" in block
    assert "is_global_owner_user" in block


def test_public_catalog_uses_bracket_lookup() -> None:
    source = (ROOT / "templates" / "store" / "public_catalog.html").read_text(encoding="utf-8")
    assert "catalog['items']" in source
    assert "catalog.items" not in source


def test_print_context_supplies_totals_and_json() -> None:
    source = (ROOT / "routes" / "printing.py").read_text(encoding="utf-8")
    for needle in ("total_debit", "total_credit", "trial_balance_json"):
        assert needle in source


def test_matrix_generator_cannot_repeat_its_old_bugs() -> None:
    source = (ROOT / "scripts" / "ops" / "generate_page_access_report.py").read_text(encoding="utf-8")
    # DEBUG handlers re-raise HTTP exceptions as 500, so a refused page was
    # recorded as a server error in the first matrix.
    assert 'app.config["DEBUG"] = False' in source
    # Visiting logout mid-sweep redirected every later page to login (302),
    # which the old matrix wrongly counted as "allowed".
    assert '"/auth/logout"' in source
    assert "SIDE_EFFECT_URLS" in source


def test_seed_provisions_public_store() -> None:
    source = (ROOT / "scripts" / "ops" / "seed_clean_isolation_db.py").read_text(encoding="utf-8")
    assert '"tenant_stores"' in source
    assert 'warehouse_type="online"' in source
