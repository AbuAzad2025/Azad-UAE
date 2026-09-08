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
        "routes.pos",
        "routes.store",
        "routes.api",
        "routes.api_enhanced",
        "routes.owner_admin",
    }
)


def _all_blueprints(module_path: str) -> list:
    """Walk a routes.X module and return every ``flask.Blueprint``
    instance exported by it without triggering Flask's app-context-bound
    LocalProxy access.

    For a single-module file like ``routes.sales`` we look at
    ``vars(mod)``. For a sub-package like ``routes.owner`` we recurse
    one level to surface each sub-blueprint individually.

    Filter rules:

    * skip dunder attrs
    * skip type objects (we want instances, not classes)
    * accept only objects whose type's ``__module__`` is
      ``flask.blueprints`` — this is the actual Blueprint class and
      rules out unrelated imports like ``decimal.Decimal`` that happen
      to expose a ``register`` method.
    """
    try:
        mod = importlib.import_module(module_path)
    except ImportError:
        return []
    out = []
    mod_dict = vars(mod)
    for attr_name, attr in mod_dict.items():
        if attr_name.startswith("__"):
            continue
        if isinstance(attr, type):
            continue
        if getattr(type(attr), "__module__", "") == "flask.blueprints":
            out.append(attr)
    if not out and module_path.startswith("routes.") and module_path.count(".") == 1:
        sub_pkg = module_path
        try:
            sub_mods = importlib.import_module(sub_pkg)
        except ImportError:
            return []
        for sub_name, sub_attr in vars(sub_mods).items():
            if isinstance(sub_attr, type) or sub_name.startswith("__"):
                continue
            full = f"{sub_pkg}.{sub_name}"
            try:
                sub = importlib.import_module(full)
            except ImportError:
                continue
            if not hasattr(sub, "__file__") or not sub.__file__:
                continue
            for _k, attr in vars(sub).items():
                if getattr(type(attr), "__module__", "") == "flask.blueprints":
                    out.append(attr)
    return out


# ---------------------------------------------------------------------------
# 1. Every blueprint in routes/ must declare at least one view function.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_path", _BLUEPRINT_MODULES)
def test_blueprint_declares_views(module_path):
    """Each blueprint module must export at least one Blueprint with
    registered views. We bind the blueprint to a real Flask app, then
    count registered URL rules whose endpoint starts with the blueprint
    name (since ``bp.view_functions`` is a Werkzeug LocalProxy that
    does not enumerate views at this level)."""
    bps = _all_blueprints(module_path)
    if not bps:
        pytest.skip(f"{module_path} has no Blueprint attribute")
    from flask import Flask

    app = Flask(__name__)
    app.config["TESTING"] = True
    bp_names = {bp.name for bp in bps}
    for bp in bps:
        app.register_blueprint(bp)
    with app.test_request_context("/"):
        rules = [r for r in app.url_map.iter_rules() if r.endpoint.split(".", 1)[0] in bp_names]
    assert rules, f"{module_path} registered zero view functions"


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
        "routes.billing_webhooks",
        "routes.stock_sync",
        "routes.api_docs",
        "routes.webhooks",
    }
)


_PUBLIC_BUT_AUTHED = frozenset(
    {
        "routes.main",
        "routes.api",
        "routes.api_enhanced",
    }
)


def _module_source_path(module_path: str) -> tuple:
    """Locate the source file backing `routes.X` modules, recursing one
    level for sub-packages like `routes.owner`. Returns (Path, sub_module)
    or (None, None) if it cannot be located."""
    try:
        mod = importlib.import_module(module_path)
    except ImportError:
        return (None, None)
    file_path = Path(str(mod.__file__))
    if file_path.exists() and file_path.name != "__init__.py":
        return (file_path, mod)
    sub_pkg = module_path
    try:
        sub_pkg_mod = importlib.import_module(sub_pkg)
    except ImportError:
        return (None, None)
    for sub_name in sorted(dir(sub_pkg_mod)):
        if sub_name.startswith("__") or isinstance(getattr(sub_pkg_mod, sub_name, None), type):
            continue
        full = f"{sub_pkg}.{sub_name}"
        try:
            sub = importlib.import_module(full)
        except ImportError:
            continue
        if not hasattr(sub, "__file__") or not sub.__file__:
            continue
        sub_path = Path(str(sub.__file__))
        if sub_path.exists() and sub_path.name != "__init__.py":
            return (sub_path, sub)
    return (None, None)


@pytest.mark.parametrize("module_path", _BLUEPRINT_MODULES)
def test_non_public_module_uses_role_decorator(module_path):
    if module_path in _PUBLIC_BLUEPRINT_MODULES:
        pytest.skip(f"{module_path} is a public surface")
    file_path, _sub = _module_source_path(module_path)
    if file_path is None:
        pytest.skip(f"{module_path} source not locatable")
    src = file_path.read_text(encoding="utf-8", errors="ignore")
    matches = re.search(
        r"@(login_required|permission_required|admin_required|"
        r"owner_required|owner_only|company_admin_required|"
        r"branch_manager_required|accountant_required|seller_or_above)",
        src,
    )
    assert matches, f"{module_path} source has no role/permission decorator"


@pytest.mark.parametrize(
    "module_path",
    [
        "routes.main",
        "routes.api",
        "routes.api_enhanced",
    ],
)
def test_public_authed_module_has_views_and_some_auth(module_path):
    """Pseudo-public touchpoints (`routes.main`, `routes.api`,
    `routes.api_enhanced`) must declare both a Flask blueprint with
    registered views AND at least one auth/perm decorator in their
    source — otherwise anonymous traffic could reach tenant-data
    surfaces."""
    bps = _all_blueprints(module_path)
    if not bps:
        pytest.skip(f"{module_path} has no Blueprint attribute")
    from flask import Flask

    app = Flask(__name__)
    app.config["TESTING"] = True
    bp_names = {bp.name for bp in bps}
    for bp in bps:
        app.register_blueprint(bp)
    with app.test_request_context("/"):
        rules = [r for r in app.url_map.iter_rules() if r.endpoint.split(".", 1)[0] in bp_names]
    assert rules, f"{module_path} has no URL rules"
    file_path, _ = _module_source_path(module_path)
    if file_path is None:
        pytest.skip(f"{module_path} source not locatable")
    src = file_path.read_text(encoding="utf-8", errors="ignore")
    matches = re.search(
        r"@(login_required|permission_required|admin_required|"
        r"owner_required|owner_only|company_admin_required|"
        r"branch_manager_required|accountant_required|seller_or_above)",
        src,
    )
    assert matches, f"{module_path} source has no role/permission decorator"


def test_public_surface_module_has_views():
    """`routes.public` is intentionally an unauthenticated surface —
    assert it has registered views (so it isn't empty), but the
    source is allowed to declare no auth decorators."""
    module_path = "routes.public"
    bps = _all_blueprints(module_path)
    if not bps:
        pytest.skip(f"{module_path} has no Blueprint attribute")
    from flask import Flask

    app = Flask(__name__)
    app.config["TESTING"] = True
    bp_names = {bp.name for bp in bps}
    for bp in bps:
        app.register_blueprint(bp)
    with app.test_request_context("/"):
        rules = [r for r in app.url_map.iter_rules() if r.endpoint.split(".", 1)[0] in bp_names]
    assert rules, f"{module_path} is empty — the public surface has no views"


# ---------------------------------------------------------------------------
# 8. Cross-tenant / cross-branch separation sanity
# ---------------------------------------------------------------------------


def test_branch_scope_id_helper_is_callable():
    from utils.branching import branch_scope_id

    assert callable(branch_scope_id)


def test_tenanting_get_active_tenant_id_callable():
    from utils.tenanting import get_active_tenant_id

    assert callable(get_active_tenant_id)
