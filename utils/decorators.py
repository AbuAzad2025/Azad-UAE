from functools import wraps
from typing import Any
from flask import abort, flash, redirect, url_for, request
from flask_login import current_user

from extensions import db
from models.enums import RoleEnum, PermissionEnum
from utils.branching import branch_scope_id_for, report_branch_scope_id_for
from utils.auth_helpers import is_admin_surface_user, is_global_owner_user
from utils.pos_features import POS_SUBFEATURES, pos_feature_enabled


def branch_scope_id():
    """يرجع branch_id لأي مستخدم غير عالمي لتطبيق عزل البيانات حسب الفرع."""
    return branch_scope_id_for(current_user)


def report_branch_scope_id():
    """نطاق الفرع في التقارير — المستخدم العالمي يبدأ من فرعه الافتراضي."""
    return report_branch_scope_id_for(current_user)


def permission_required(permission_code):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("الرجاء تسجيل الدخول أولاً", "warning")
                return redirect(url_for("auth.login"))

            if is_global_owner_user(current_user):
                return f(*args, **kwargs)

            code = permission_code.value if isinstance(permission_code, PermissionEnum) else permission_code
            if not current_user.has_permission(code):
                flash("ليس لديك صلاحية للوصول لهذه الصفحة", "danger")
                abort(403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def any_permission_required(*permission_codes):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("الرجاء تسجيل الدخول أولاً", "warning")
                return redirect(url_for("auth.login"))

            if is_global_owner_user(current_user):
                return f(*args, **kwargs)

            codes = [c.value if isinstance(c, PermissionEnum) else c for c in permission_codes if c]
            allowed = any(current_user.has_permission(code) for code in codes)
            if not allowed:
                flash("ليس لديك صلاحية للوصول لهذه الصفحة", "danger")
                abort(403)

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def admin_required(f):
    """لوحات الإدارة الحساسة: owner و super_admin فقط."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith("/owner/"):
                abort(404)
            flash("الرجاء تسجيل الدخول أولاً", "warning")
            return redirect(url_for("auth.login"))

        if not is_admin_surface_user(current_user):
            flash("هذه الصفحة للإدارة فقط", "danger")
            abort(403)

        return f(*args, **kwargs)

    return decorated_function


def seller_or_above(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith("/owner/"):
                abort(404)
            flash("الرجاء تسجيل الدخول أولاً", "warning")
            return redirect(url_for("auth.login"))

        from utils.constants import ROLE_LEVELS

        user_slug = getattr(getattr(current_user, "role", None), "slug", None)
        user_level = ROLE_LEVELS.get(user_slug, 0)
        if user_level < ROLE_LEVELS.get("seller", 10):
            flash("ليس لديك صلاحية للوصول لهذه الصفحة", "danger")
            abort(403)

        return f(*args, **kwargs)

    return decorated_function


def super_admin_required(f):
    """مطابق لـ admin_required: owner و super_admin فقط."""
    return admin_required(f)


def owner_required(f):
    """لوحة المالك: owner أو developer فقط."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(404)

        if not is_global_owner_user(current_user):
            abort(404)

        return f(*args, **kwargs)

    return decorated_function


def owner_only(f):
    """قفل صلاحيات المالك فقط - Owner-only access control.
    Returns 403 (not redirect) for unauthenticated requests so the
    owner-panel URL space is not revealed to anonymous clients.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(403)
        if not getattr(current_user, "is_owner", False):
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


def company_admin_required(f):
    """Tenant company admin surface — super_admin or manager with active tenant."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith("/owner/"):
                abort(404)
            flash("الرجاء تسجيل الدخول أولاً", "warning")
            return redirect(url_for("auth.login"))

        if is_global_owner_user(current_user):
            abort(404)

        from utils.tenanting import get_active_tenant_id

        slug = getattr(getattr(current_user, "role", None), "slug", None)
        if slug not in RoleEnum.company_admin_values() and not current_user.is_super_admin():
            abort(403)
        if not get_active_tenant_id(current_user):
            abort(403)

        return f(*args, **kwargs)

    return decorated_function


def owner_or_company_admin(f):
    """Platform owner/developer or tenant super_admin/manager."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith("/owner/"):
                abort(404)
            flash("الرجاء تسجيل الدخول أولاً", "warning")
            return redirect(url_for("auth.login"))

        if is_global_owner_user(current_user):
            return f(*args, **kwargs)

        from utils.tenanting import get_active_tenant_id

        slug = getattr(getattr(current_user, "role", None), "slug", None)
        if slug in RoleEnum.company_admin_values() or current_user.is_super_admin():
            if get_active_tenant_id(current_user):
                return f(*args, **kwargs)
        abort(403)

    return decorated_function


def branch_manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(404)

        if not (
            current_user.is_owner
            or current_user.is_super_admin()
            or (
                getattr(current_user, "role", None)
                and getattr(current_user.role, "slug", None) == RoleEnum.BRANCH_MANAGER.value
            )
        ):
            flash("هذه الصفحة لمدراء الفروع فقط", "danger")
            abort(403)

        return f(*args, **kwargs)

    return decorated_function


def accountant_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(404)

        if not (
            current_user.is_owner
            or current_user.is_super_admin()
            or (
                getattr(current_user, "role", None)
                and getattr(current_user.role, "slug", None) in RoleEnum.financial_values()
            )
        ):
            flash("هذه الصفحة للمحاسبين فقط", "danger")
            abort(403)

        return f(*args, **kwargs)

    return decorated_function


# ── SaaS subscription feature gate ────────────────────────────────────
# Blocks a route when the active tenant has a feature disabled or its
# subscription plan is lower than the required tier.
#
# Usage:
#   @require_subscription_feature('pos')
#   @require_subscription_feature('enterprise')
# ---------------------------------------------------------------------

# Known `enable_*` boolean columns on the Tenant model.
_FEATURE_COLUMNS = frozenset(
    {
        "multi_warehouse",
        "multi_currency",
        "gl",
        "ai",
        "reports",
        "api",
        "pos",
        "payroll",
        "cheques",
        "expenses",
        "store",
        # POS Phase 4 — SaaS sub-feature flags (nullable: NULL inherits the
        # plan-level default via utils/pos_features).
        "pos_promotions",
        "pos_multi_tender",
        "pos_returns",
        "pos_shifts",
    }
)

# Plan hierarchy (higher = more features).
_PLAN_LEVELS = {"basic": 10, "pro": 20, "enterprise": 30}


def require_subscription_feature(feature_name: str):
    """Gate a route by tenant feature flag or subscription plan.

    Feature names like 'pos', 'ai', 'payroll' map to the corresponding
    ``Tenant.enable_<name>`` column.
    Plan names ('pro', 'enterprise') require at least that plan tier.
    """

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from utils.tenanting import get_active_tenant_id
            from models.tenant import Tenant

            tid = get_active_tenant_id()
            if not tid:
                abort(403, description="لا يوجد مستأجر نشط")
            tenant = db.session.get(Tenant, int(tid))
            if not tenant:
                abort(403, description="المستأجر غير موجود")

            col = f"enable_{feature_name}"
            if col.replace("enable_", "") in _FEATURE_COLUMNS:
                value = getattr(tenant, col, True)
                if value is None and feature_name in POS_SUBFEATURES:
                    # Nullable POS sub-feature: NULL inherits the plan default.
                    value = pos_feature_enabled(tenant, feature_name)
                if not value:
                    abort(403, description=f'ميزة "{feature_name}" غير مفعلة لهذا الحساب')
                return f(*args, **kwargs)

            if feature_name in _PLAN_LEVELS:
                required = _PLAN_LEVELS[feature_name]
                current_plan = _PLAN_LEVELS.get(tenant.subscription_plan or "basic", 0)
                if current_plan < required:
                    abort(403, description=f"هذه الميزة تتطلب خطة {feature_name}")
                return f(*args, **kwargs)

            return f(*args, **kwargs)

        return wrapper

    return decorator


# ── External POS / API-key authentication decorator ──────────────────────
# Validates X-API-Key / X-API-Secret headers, resolves tenant, sets
# g.active_tenant_id so existing ORM auto-scoping (tenant_orm.py) fires
# with zero duplicated security code.
# ------------------------------------------------------------------------


def api_key_required(scope="read"):
    """Require a valid tenant-scoped API key for external integrations (POS sync)."""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import g, request, jsonify
            from extensions import db
            from utils.tenanting import without_tenant_scope, get_tenant_status
            from utils.db_safety import atomic_transaction
            from datetime import datetime, timezone

            raw_key = (request.headers.get("X-API-Key") or "").strip()
            raw_secret = (request.headers.get("X-API-Secret") or "").strip()

            if not raw_key or not raw_secret:
                return jsonify({"ok": False, "error": "Missing API credentials"}), 401

            with without_tenant_scope():
                from models import APIKey

                api_key = db.session.query(APIKey).filter_by(key=raw_key, secret=raw_secret, is_active=True).first()

            if not api_key:
                return jsonify({"ok": False, "error": "Invalid or inactive API key"}), 403

            # Tenant-scoped keys only (platform-level keys lack tenant_id)
            if api_key.tenant_id is None:
                return jsonify({"ok": False, "error": "API key not bound to a tenant"}), 403

            # Scope check
            key_scope = getattr(api_key, "scope", "write") or "write"
            if scope == "write" and key_scope == "read":
                return jsonify({"ok": False, "error": "Read-only API key"}), 403

            # Tenant health check (suspension, subscription expiry)
            status = get_tenant_status(api_key.tenant_id)
            if not status["ok"]:
                return (
                    jsonify({"ok": False, "error": status.get("reason") or "Tenant inactive"}),
                    403,
                )

            # Activate tenant for ORM auto-scoping
            g.active_tenant_id = api_key.tenant_id

            # Track usage (best-effort)
            try:
                with atomic_transaction("api_key_usage_tracking"):
                    api_key.last_used = datetime.now(timezone.utc)
                    api_key.usage_count = (api_key.usage_count or 0) + 1
                    db.session.flush()
            except Exception:
                pass

            return f(*args, **kwargs)

        return decorated_function

    return decorator


# ── Resource-limit enforcement decorator ──────────────────────────────
# Calls ``utils/tenant_limits.py`` convenience helpers before the route
# executes.  Raises HTTP 403 with a user-facing message when the limit
# is exceeded.
#
# Usage:
#   @enforce_resource_limit('users')
#   @enforce_resource_limit('invoices_monthly')
# ---------------------------------------------------------------------

_LIMIT_CHECKERS: dict[str, Any] = {}


def _load_limit_checkers():
    """Lazy-populate the limit-checker mapping (avoids import cycles)."""
    if _LIMIT_CHECKERS:
        return
    from utils.tenant_limits import (
        check_users_limit,
        check_branches_limit,
        check_warehouses_limit,
        check_products_limit,
        check_customers_limit,
        check_suppliers_limit,
        check_sales_monthly_limit,
        check_invoices_monthly_limit,
    )

    _LIMIT_CHECKERS["users"] = check_users_limit
    _LIMIT_CHECKERS["branches"] = check_branches_limit
    _LIMIT_CHECKERS["warehouses"] = check_warehouses_limit
    _LIMIT_CHECKERS["products"] = check_products_limit
    _LIMIT_CHECKERS["customers"] = check_customers_limit
    _LIMIT_CHECKERS["suppliers"] = check_suppliers_limit
    _LIMIT_CHECKERS["sales_monthly"] = check_sales_monthly_limit
    _LIMIT_CHECKERS["invoices_monthly"] = check_invoices_monthly_limit


def enforce_resource_limit(resource_name: str):
    """Gate a route by tenant resource quota (e.g. 'users', 'invoices_monthly').

    The underlying ``check_*_limit()`` raises ``TenantLimitError`` when the
    limit would be exceeded; this decorator translates it into HTTP 403 so
    both web and API routes receive a consistent response.
    """

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            _load_limit_checkers()
            checker = _LIMIT_CHECKERS.get(resource_name)
            if checker is not None:
                from utils.tenant_limits import TenantLimitError

                try:
                    checker()
                except TenantLimitError as e:
                    abort(403, description=str(e))
            return f(*args, **kwargs)

        return wrapper

    return decorator
