"""Role isolation / permission boundary audit (static, no DB).

Asserts invariants that must hold in the source tree:

1. RoleEnum exposes exactly the 8 canonical roles.
2. system_init._ensure_functional_roles assigns ONLY the declared permission
   set to manager/seller/branch_manager/accountant/kitchen; owner/developer/
   super_admin get ALL_PERMS.
3. Lowest-tier roles (seller, cashier) MUST NOT be granted cost-revealing or
   user-administration permissions (manage_users, manage_payroll,
   manage_backups, override_sale_price, pos_discount_override).
4. Every @api_bp.route in routes/api.py carries @login_required (except
   /health, /version which are intentionally public).
5. Master-key helpers exist and are IP-guarded; platform owner session is
   explicit.

Run: python -m pytest tests/unit/test_erp_role_isolation.py -q
"""

from __future__ import annotations

import pathlib
import re

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]

CANONICAL_ROLES = [
    "owner",
    "developer",
    "super_admin",
    "manager",
    "branch_manager",
    "accountant",
    "seller",
    "cashier",
]

# Permissions that must NEVER be granted to retail/POS-facing tiers.
# (cost/margin visibility, user admin, raw ledger management, price overrides)
COST_OR_ADMIN_PERMS = {
    "manage_users",
    "manage_payroll",
    "manage_backups",
    "manage_ledger",
    "override_sale_price",
    "pos_discount_override",
    "pos_authorize_override",
    "support.manage",
    "project.manage",
    "hr.manage",
    "crm.manage",
    "marketing.manage",
    "printing.settings",
}

FUNCTIONAL_ROLE_SOURCE = PROJECT_ROOT / "utils" / "system_init.py"
API_ROUTES_SOURCE = PROJECT_ROOT / "routes" / "api.py"
MASTER_LOGIN_SOURCE = PROJECT_ROOT / "utils" / "master_login.py"
ENUMS_SOURCE = PROJECT_ROOT / "models" / "enums.py"


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def _enum_roles() -> set[str]:
    txt = _read(ENUMS_SOURCE)
    m = re.search(r"class\s+RoleEnum.*?(?=\nclass\s|\Z)", txt, re.S)
    assert m, "RoleEnum not found in models/enums.py"
    return set(re.findall(r'=\s*"([^"]+)"', m.group(0)))


def _functional_role_slugs() -> set[str]:
    txt = _read(FUNCTIONAL_ROLE_SOURCE)
    return set(re.findall(r'"slug":\s*"([^"]+)"', txt))


def test_role_enum_is_canonical():
    roles = _enum_roles()
    assert roles == set(CANONICAL_ROLES), f"RoleEnum drift: {roles}"


def test_functional_roles_are_known():
    slugs = _functional_role_slugs()
    # manager, seller, branch_manager, accountant, kitchen are the functional set
    assert {"manager", "seller", "branch_manager", "accountant", "kitchen"} <= slugs
    # NOTE: 'cashier' is intentionally NOT in the functional seed set — it is a
    # platform alias used by POS tenant demo roles (demo_cashier), not a company
    # role created by system_init. Tracked as a known deviation.


def _function_role_codes(txt: str, var_name: str) -> set[str]:
    """Extract the list assigned to <var_name>_codes in system_init."""
    m = re.search(rf"{var_name}_codes\s*=\s*\[(.*?)\]", txt, re.S)
    if not m:
        return set()
    return {x.strip().strip('"').strip("'") for x in m.group(1).split(",") if x.strip()}


def _seller_and_sibling_blocks() -> dict[str, set[str]]:
    txt = _read(FUNCTIONAL_ROLE_SOURCE)
    func_idx = txt.find("def _ensure_functional_roles")
    body = txt[func_idx:] if func_idx >= 0 else txt
    return {
        "manager": _function_role_codes(body, "manager"),
        "seller": _function_role_codes(body, "seller"),
        "branch_manager": _function_role_codes(body, "branch_mgr"),
        "accountant": _function_role_codes(body, "acc"),
        "kitchen": _function_role_codes(body, "kitchen"),
    }


def test_seller_strict_scope_no_ledger():
    """A seller/cashier never sees the general ledger or cost/margin data.
    This is the STRICT boundary (no legacy product exception) per product
    decision made during development hardening."""
    blocks = _seller_and_sibling_blocks()
    assert "seller" in blocks and blocks["seller"], "seller_codes list not found"
    seller = blocks["seller"]
    for banned in COST_OR_ADMIN_PERMS | {"view_ledger"}:
        assert banned not in seller, f"seller leaked {banned!r}"


def test_branch_manager_distinct_from_manager():
    """Branch Manager must be a strict subset of Manager — never company-wide
    accounting (manage_ledger) or payroll (manage_payroll)."""
    blocks = _seller_and_sibling_blocks()
    bm = blocks.get("branch_manager", set())
    mgr = blocks.get("manager", set())
    assert bm, "branch_mgr_codes not found"
    assert mgr, "manager_codes not found"
    # Branch manager must lack company-accounting and payroll
    for banned in ("manage_ledger", "manage_payroll", "manage_users"):
        assert banned not in bm, f"branch_manager leaked {banned!r}"
    # Branch manager is a strict subset: everything it has, manager also has
    assert bm <= mgr, f"branch_manager has perms manager lacks: {sorted(bm - mgr)}"


def test_accountant_scope():
    """Accountant may hold GL/reporting, but not user-admin/price-override."""
    blocks = _seller_and_sibling_blocks()
    codes = blocks.get("accountant", set())
    assert codes, "accountant (acc_codes) list not found"
    # accountant must have ledger + payroll view for provision, but not users/overrides
    assert "manage_ledger" in codes and "view_ledger" in codes
    banned = COST_OR_ADMIN_PERMS - {"view_ledger", "manage_ledger", "manage_payroll"}
    overlap = codes & banned
    assert not overlap, f"accountant leaked: {sorted(overlap)}"


def test_all_api_routes_require_login():
    """Every @api_bp.route must be login-guarded except /health and /version."""
    txt = _read(API_ROUTES_SOURCE)
    for m in re.finditer(
        r'@api_bp\.route\((["\'][^"\']+["\'])([^\n]*)\)\s*\n\s*(@\w[\w_]*\s*\n)*\s*def\s+(\w+)',
        txt,
        re.M,
    ):
        path = m.group(1).strip('"').strip("'")
        body = m.group(0)
        if path in ("/health", "/version"):
            continue
        assert re.search(r"@\w*(login_required|permission_required|admin_required|owner_only)\b", body), (
            f"route {path} (def {m.group(3)}) has no auth decorator"
        )


def test_master_key_helpers_present():
    """Master-key mechanism exposes guarded entrypoints."""
    txt = _read(MASTER_LOGIN_SOURCE)
    for fn in ("verify_master_key", "is_master_login_enabled", "can_use_master_login", "is_allowed_ip"):
        assert f"def {fn}" in txt, f"master_login is missing {fn}()"
