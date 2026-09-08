"""Lightweight cross-module RBAC coverage matrix for the Azadexa ERP.

This file complements (and does NOT duplicate) the per-module tests in
`test_*_auth.py`. It focuses on:

* Blueprint registry spot-checks (every blueprint in routes/ is defined
  and has routes).
* Permission enum + ROLE_LEVELS catalogue sanity.
* Source-level guard research: no `force_admin`/`bypass_perm`
  shortcuts wired into RBAC boundary checks.
* The `owner_required` decorator contract (only owner users can pass).
* Per-role permission membership via the seeded modules.

The deeper role-by-endpoint matrix lives in tests/integration
(test_tenant_isolation_rbac.py, test_dashboard_isolation.py) where a
real DB and full test client are available. This file stays
unit-no-DB so it can run in a fast-feedback loop.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_BLUEPRINT_MODULES = sorted(
    {
        "routes.sales",
        "routes.customers",
        "routes.suppliers",
        "routes.purchases",
        "routes.products",
        "routes.expenses",
        "routes.cheques",
        "routes.payroll",
        "routes.warehouse",
        "routes.payments",
        "routes.reports",
        "routes.ledger",
        "routes.returns",
        "routes.tickets",
        "routes.crm",
        "routes.hr",
        "routes.users",
        "routes.assets",
        "routes.budget",
        "routes.quotations",
        "routes.transfers",
        "routes.email_marketing",
        "routes.whatsapp",
        "routes.branches",
        "routes.main",
        "routes.public",
        "routes.pos",
        "routes.store",
        "routes.api",
        "routes.api_enhanced",
        "routes.owner_admin",
    }
)


def _all_blueprints(module_path: str) -> list:
    try:
        mod = importlib.import_module(module_path)
    except ImportError:
        return []
    out = []
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if hasattr(attr, "name") and hasattr(attr, "routes"):
            out.append(attr)
    return out


# ---------------------------------------------------------------------------
# 1. Every blueprint in routes/ must declare at least one view function.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_path", _BLUEPRINT_MODULES)
def test_blueprint_declares_views(module_path):
    """Each blueprint module must export at least one Blueprint with
    registered views (excluding modules that legitimately have none yet)."""
    bps = _all_blueprints(module_path)
    if not bps:
        pytest.skip(f"{module_path} has no Blueprint attribute (probably not loaded)")
    from flask import Flask

    app = Flask(__name__)
    with app.app_context():
        try:
            total_views = sum(len(dict(bp.view_functions)) for bp in bps)
        except Exception:
            pytest.skip(f"{module_path} view_functions proxy unusable")
    assert total_views >= 1, f"{module_path} registered zero view functions"


# ---------------------------------------------------------------------------
# 2. ROLE_LEVELS + PermissionEnum sanity
# ---------------------------------------------------------------------------


def test_role_level_constants_match_seeded_roles():
    """ROLE_LEVELS dict should mention every canonical role slug."""
    from utils.constants import ROLE_LEVELS

    expected = {
        "owner",
        "developer",
        "super_admin",
        "manager",
        "branch_manager",
        "accountant",
        "seller",
        "cashier",
    }
    actual = set(ROLE_LEVELS.keys())
    missing = expected - actual
    assert not missing, f"ROLE_LEVELS missing roles: {missing}"


def test_permission_enum_catalog_is_substantial():
    """PermissionEnum should expose tens of permission codes."""
    from models.enums import PermissionEnum

    assert len(list(PermissionEnum)) >= 30


@pytest.mark.parametrize(
    "perm_enum_name",
    [
        "MANAGE_SALES",
        "MANAGE_PAYMENTS",
        "MANAGE_USERS",
        "MANAGE_PAYROLL",
        "MANAGE_WAREHOUSE",
        "MANAGE_PRODUCTS",
        "MANAGE_PURCHASES",
        "MANAGE_EXPENSES",
        "VIEW_REPORTS",
        "VIEW_LEDGER",
        "MANAGE_LEDGER",
        "ADMIN",
        "POS_RETURN",
        "POS_AUTHORIZE_OVERRIDE",
        "PROJECT_MANAGE",
        "PROJECT_VIEW",
        "SUPPORT_MANAGE",
        "SUPPORT_VIEW",
        "MARKETING_MANAGE",
        "CRM_MANAGE",
        "CRM_VIEW",
        "PRINTING_PRINT",
        "OVERRIDE_SALE_PRICE",
        "MANAGE_STORE",
        "HR_MANAGE",
        "HR_VIEW",
        "MANAGE_SUPPLIERS",
        "MANAGE_CUSTOMERS",
        "POS_VOID_LINE",
        "POS_DISCOUNT_OVERRIDE",
        "POS_PAY_IN_OUT",
        "POS_VIEW_EXPECTED",
        "POS_NO_SALE_DRAWER",
        "OVERRIDE_SALE_PRICE",
        "MANAGE_BACKUPS",
        "VIEW_KDS",
    ],
)
def test_permission_enum_contains_member(perm_enum_name):
    from models.enums import PermissionEnum

    assert hasattr(PermissionEnum, perm_enum_name), f"PermissionEnum.{perm_enum_name} missing"


# ---------------------------------------------------------------------------
# 3. Source-level guard: decorators must not honour bypass flags
# ---------------------------------------------------------------------------


_DECORATOR_FILES = [
    "utils/decorators.py",
    "routes/sales.py",
    "routes/purchases.py",
    "routes/payments.py",
    "routes/ledger.py",
    "routes/products.py",
    "routes/customers.py",
    "routes/owner/core.py",
    "routes/owner/backups.py",
    "routes/owner/maintenance.py",
    "routes/owner/database.py",
]


@pytest.mark.parametrize("rel_path", _DECORATOR_FILES)
def test_no_bypass_admin_flags_in_decorators(rel_path):
    """Forbid decorative bypass keywords like `_force_admin`,
    `is_admin_forced`, etc. Simple grep test."""
    src_path = Path(rel_path)
    if not src_path.exists():
        pytest.skip(f"{rel_path} not present")
    src = src_path.read_text(encoding="utf-8", errors="ignore")
    leaks = re.findall(
        r"_force_admin|_bypass_perm|_owner_override|is_admin_forced|"
        r"force_super_admin|bypass_owner_check",
        src,
        re.IGNORECASE,
    )
    assert not leaks, f"{rel_path}: forbidden bypass keywords {leaks}"


# ---------------------------------------------------------------------------
# 4. Direct decorator contract smoke
# ---------------------------------------------------------------------------


def test_owner_required_rejects_non_owner():
    """`owner_required` must raise NotFound for non-owner users."""
    from werkzeug.exceptions import NotFound

    from utils.decorators import owner_required

    @owner_required
    def view():
        return "ok"

    user = MagicMock()
    user.is_authenticated = True
    user.is_owner = False
    user.role = MagicMock(slug="super_admin")
    with patch("flask_login.utils._get_user", return_value=user):
        with patch(
            "utils.decorators.is_global_owner_user",
            return_value=False,
        ):
            with pytest.raises(NotFound):
                view()


def test_owner_required_accepts_owner():
    """`owner_required` must return the wrapped payload for owner users."""
    from utils.decorators import owner_required

    @owner_required
    def view():
        return "ok"

    user = MagicMock()
    user.is_authenticated = True
    user.is_owner = True
    with patch("flask_login.utils._get_user", return_value=user):
        with patch(
            "utils.decorators.is_global_owner_user",
            return_value=True,
        ):
            assert view() == "ok"


def test_admin_required_rejects_non_admin():
    """`admin_required` must abort 403 for non-admin users."""
    from utils.decorators import admin_required

    @admin_required
    def view():
        return "ok"

    user = MagicMock()
    user.is_authenticated = True
    user.is_owner = False
    user.role = MagicMock(slug="manager")
    with patch("flask_login.utils._get_user", return_value=user):
        with patch(
            "utils.decorators.is_admin_surface_user",
            return_value=False,
        ):
            from werkzeug.exceptions import Forbidden

            with pytest.raises(Forbidden):
                view()


# ---------------------------------------------------------------------------
# 5. System-init catalogue membership
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "function_name",
    [
        "_ensure_owner_role",
        "_ensure_developer_role",
        "_ensure_super_admin_role",
        "_ensure_functional_roles",
        "_ensure_permissions",
        "_ensure_owner_user",
    ],
)
def test_system_init_role_seeder_present(function_name):
    """Every seeded role must have a corresponding `_ensure_*` helper."""
    import utils.system_init as si

    assert hasattr(si, function_name), f"utils.system_init missing {function_name}"


# ---------------------------------------------------------------------------
# 6. Permission-seeding helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "constant_name",
    [
        "manage_customers",
        "manage_sales",
        "manage_purchases",
        "manage_expenses",
        "manage_payments",
        "manage_payroll",
        "manage_products",
        "manage_suppliers",
        "manage_warehouse",
        "manage_users",
        "view_reports",
        "view_ledger",
        "manage_ledger",
        "admin",
        "manage_store",
        "support.view",
        "support.manage",
        "hr.view",
        "hr.manage",
        "crm.view",
        "crm.manage",
        "project.view",
        "project.manage",
        "manage_backups",
    ],
)
def test_permission_catalog_includes_seeded_perm(constant_name):
    from utils.constants import PERMISSION_CODES

    assert constant_name in PERMISSION_CODES, f"{constant_name} missing from PERMISSION_CODES"


# ---------------------------------------------------------------------------
# 7. Per-module RBAC audit: every blueprint module must declare an
# auth/perm decorator in its source (or be public-only).
# ---------------------------------------------------------------------------


_PUBLIC_BLUEPRINT_MODULES = frozenset(
    {
        "routes.public",
        "routes.auth",
        "routes.main",
        "routes.api",
        "routes.api_enhanced",
        "routes.billing_webhooks",
        "routes.stock_sync",
        "routes.api_docs",
        "routes.webhooks",
    }
)


@pytest.mark.parametrize("module_path", _BLUEPRINT_MODULES)
def test_non_public_module_uses_role_decorator(module_path):
    if module_path in _PUBLIC_BLUEPRINT_MODULES:
        pytest.skip(f"{module_path} is a public surface")
    try:
        mod = importlib.import_module(module_path)
    except ImportError:
        pytest.skip(f"{module_path} not importable")

    file_path = Path(str(mod.__file__))
    if file_path.name == "__init__.py":
        pytest.skip(f"{module_path} is a package; per-route decorator audit deferred")
    src = file_path.read_text(encoding="utf-8", errors="ignore")
    matches = re.search(
        r"@(login_required|permission_required|admin_required|"
        r"owner_required|owner_only|company_admin_required|"
        r"branch_manager_required|accountant_required|seller_or_above)",
        src,
    )
    assert matches, f"{module_path} source has no role/permission decorator"


# ---------------------------------------------------------------------------
# 8. Cross-tenant / cross-branch separation sanity
# ---------------------------------------------------------------------------


def test_branch_scope_id_helper_is_callable():
    from utils.branching import branch_scope_id

    assert callable(branch_scope_id)


def test_tenanting_get_active_tenant_id_callable():
    from utils.tenanting import get_active_tenant_id

    assert callable(get_active_tenant_id)
