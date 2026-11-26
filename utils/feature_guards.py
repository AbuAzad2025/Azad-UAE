"""SaaS feature gating — ``@feature_required`` route decorator.

Locks a whole module entry point behind the tenant's ``enable_<feature>``
flag (copied from the subscribed Package at activation):

- API requests (``/api/...`` or JSON) → ``403 {"error": "FEATURE_LOCKED", "feature": ...}``
- Web requests → ``403`` with a localized upgrade hint.

No tenant context (owner/platform mode) → allowed through.

Built on the same flag resolution as ``require_subscription_feature``
(utils/decorators.py) — nullable POS sub-features inherit the plan default.
"""

from __future__ import annotations

from functools import wraps

from flask import abort, jsonify, request
from flask_babel import gettext

from extensions import db
from utils.pos_features import POS_SUBFEATURES, pos_feature_enabled


def _wants_json() -> bool:
    if request.path.startswith("/api/") or "/api/" in request.path:
        return True
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]


def feature_required(feature_name: str):
    """Gate a route by the tenant's ``enable_<feature_name>`` flag."""

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            denial = _feature_denial(feature_name)
            if denial is not None:
                return denial
            return f(*args, **kwargs)

        return wrapper

    return decorator


def _feature_denial(feature_name: str):
    """Return a denial response when the feature is locked, else None."""
    from flask_login import current_user

    from models.tenant import Tenant
    from utils.auth_helpers import is_global_owner_user
    from utils.tenanting import get_active_tenant_id

    # Platform owner/developer manages modules and packages, not tenant data.
    # Tenant-scoped owners stay gated like any other tenant user.
    if is_global_owner_user(current_user):
        return None

    tid = get_active_tenant_id()
    if not tid:
        return None  # owner/platform context
    tenant = db.session.get(Tenant, int(tid))
    if tenant is None:
        abort(403, description=gettext("المستأجر غير موجود"))

    # Resolve the explicit enable_<name> column FIRST. The bare name can be an
    # ORM backref (Tenant.expenses is a dynamic relationship from Expense), and
    # reading that instead of enable_expenses denies a module that is enabled.
    # The bare name is still honoured for non-prefixed flags such as
    # allow_custom_integrations, which have no enable_ column.
    enabled = getattr(tenant, f"enable_{feature_name}", None)
    if enabled is None and feature_name in POS_SUBFEATURES:
        # Nullable POS sub-feature: NULL inherits the plan default *before* a
        # bare-name lookup, which can be an ORM backref (or a mock attribute).
        enabled = pos_feature_enabled(tenant, feature_name)
    if enabled is None:
        enabled = getattr(tenant, feature_name, None)
    if enabled is None:
        enabled = True  # a flag with no column is not a locked module

    if enabled:
        return None
    if _wants_json():
        return jsonify({"error": "FEATURE_LOCKED", "feature": feature_name}), 403
    abort(
        403,
        description=gettext(
            "Feature %(feature)s is not enabled on your current plan. Upgrade your plan to enable it.",
            feature=feature_name,
        ),
    )


# Platform-wide module switches from System Settings. These were rendered as
# owner-panel checkboxes but never enforced, so turning one off changed nothing.
SYSTEM_MODULE_FLAGS = {
    "sales": "enable_sales",
    "returns": "enable_sales",
    "quotations": "enable_sales",
    "purchases": "enable_purchases",
    "products": "enable_inventory",
    "warehouse": "enable_inventory",
    "transfers": "enable_inventory",
    "uinv": "enable_inventory",
    "customers": "enable_customers",
    "suppliers": "enable_suppliers",
    "expenses": "enable_expenses",
    "ledger": "enable_gl",
    "advanced_ledger": "enable_gl",
    "admin_ledger": "enable_gl",
    "reports": "enable_reports",
    "treasury": "enable_reports",
}


def system_module_denial(blueprint: str):
    """Deny a tenant blueprint whose platform-wide module switch is off."""
    flag = SYSTEM_MODULE_FLAGS.get(blueprint)
    if not flag:
        return None
    from models.system_settings import SystemSettings

    settings = SystemSettings.query.filter_by(is_active=True).first()
    if settings is None or bool(getattr(settings, flag, True)):
        return None
    abort(
        403,
        description=gettext(
            "Module %(flag)s is disabled for this installation.",
            flag=flag,
        ),
    )


def deny_if_locked(feature_name: str):
    """Public form of the denial check for routes with mixed entity types."""
    return _feature_denial(feature_name)


def feature_enabled(feature_name: str) -> bool:
    """Boolean form of the flag check, for redacting optional response fields.

    Same resolution order as ``_feature_denial`` (exact column first, then
    ``enable_<name>``, then the POS plan default). Unlike it, this never
    produces a denial response: the endpoint stays usable and only the
    module-specific fields are omitted when the flag is off. Platform-owner
    (no tenant) context is treated as enabled.
    """
    from flask_login import current_user

    from models.tenant import Tenant
    from utils.auth_helpers import is_global_owner_user
    from utils.tenanting import get_active_tenant_id

    if is_global_owner_user(current_user):
        return True
    tid = get_active_tenant_id()
    if not tid:
        return True
    tenant = db.session.get(Tenant, int(tid))
    if tenant is None:
        return False
    # Same resolution order as _feature_denial: the flag column wins over a
    # same-named ORM relationship.
    enabled = getattr(tenant, f"enable_{feature_name}", None)
    if enabled is None and feature_name in POS_SUBFEATURES:
        enabled = pos_feature_enabled(tenant, feature_name)
    if enabled is None:
        enabled = getattr(tenant, feature_name, None)
    return True if enabled is None else bool(enabled)


def install_feature_gate(bp, feature_name: str) -> None:
    """Lock every route of a blueprint behind the tenant's feature flag."""

    @bp.before_request
    def _check_feature_flag():  # noqa: ANN202 — flask before_request hook
        return _feature_denial(feature_name)
