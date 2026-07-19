"""
Tenant isolation — each company (tenant) is fully separated.
Company users (including super_admin) cannot access another tenant's data.
Only platform owners (is_owner) may switch tenants via session.
"""

from __future__ import annotations

from contextlib import contextmanager

from flask import abort, g, has_request_context, session
from flask_login import current_user

import logging

from extensions import db

logger = logging.getLogger(__name__)

ACTIVE_TENANT_SESSION_KEY = "active_tenant_id"


def _resolve_user(user=None):
    if user is not None:
        return user
    try:
        candidate = current_user._get_current_object()
    except Exception:
        return None
    return candidate if getattr(candidate, "is_authenticated", False) else None


def is_platform_owner(user=None) -> bool:
    """Platform operator (Azad) — may switch active tenant."""
    user = _resolve_user(user)
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_owner", False)
    )


def is_global_tenant_user(user=None) -> bool:
    """Only platform owner can change active tenant context."""
    return is_platform_owner(user)


def get_active_tenant_id(user=None) -> int | None:
    """
    Resolve tenant for the current request.
    Company users are locked to user.tenant_id (session cannot override).
    """
    user = _resolve_user(user)
    if not user or not getattr(user, "is_authenticated", False):
        # Fall back to the per-request tenant set by the factory's
        # before_request (g.active_tenant_id). This is the authoritative value
        # for the whole request and avoids resolving current_user again at
        # query-execution time (which can otherwise yield None and silently
        # empty every tenant-scoped list).
        try:
            if has_request_context():
                from flask import g

                g_tid = getattr(g, "active_tenant_id", None)
                if g_tid is not None:
                    return int(g_tid)
        except Exception:
            logger.debug(
                "Failed to resolve active tenant from g context", exc_info=True
            )
        return None

    if not is_platform_owner(user):
        tid = getattr(user, "tenant_id", None)
        return int(tid or 0) if tid else None

    if has_request_context():
        raw = session.get(ACTIVE_TENANT_SESSION_KEY)
        if raw is not None and raw != "":
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass

    tid2 = getattr(user, "tenant_id", None)
    return int(tid2 or 0) if tid2 else None


def require_active_tenant_id(user=None) -> int:
    tid = get_active_tenant_id(user)
    if tid is None:
        abort(403, description="لا توجد شركة نشطة مرتبطة بهذا الحساب.")
    return tid


def model_has_tenant(model) -> bool:
    return hasattr(model, "tenant_id")


def apply_tenant_scope(query, model, user=None):
    """Filter query to the active tenant. Empty result if owner has no tenant selected."""
    tid = get_active_tenant_id(user)
    if tid is not None and model_has_tenant(model):
        return query.filter(model.tenant_id == tid)
    if is_platform_owner(user) and model_has_tenant(model):
        return query.filter(model.tenant_id < 0)
    return query


def tenant_query(model, user=None):
    return apply_tenant_scope(model.query, model, user)


def assert_tenant_record(record, *, user=None, or_404: bool = True) -> bool:
    if record is None:
        if or_404:
            abort(404)
        return False

    tid = get_active_tenant_id(user)
    rec_tid = getattr(record, "tenant_id", None)

    if rec_tid is None:
        if is_platform_owner(user):
            return True
        if or_404:
            abort(404)
        return False

    if tid is None:
        if or_404:
            abort(403 if is_platform_owner(user) else 404)
        return False

    if int(rec_tid or 0) != int(tid or 0):
        if or_404:
            abort(404)
        return False
    return True


def tenant_get(model, pk, *, user=None, or_404: bool = True):
    obj = db.session.get(model, int(pk))
    if obj is None:
        if or_404:
            abort(404)
        return None
    assert_tenant_record(obj, user=user, or_404=or_404)
    return obj


def tenant_get_or_404(model, pk, user=None):
    return tenant_get(model, pk, user=user, or_404=True)


def assign_tenant_id(record, user=None):
    if getattr(record, "tenant_id", None):
        return record
    record.tenant_id = require_active_tenant_id(user)
    return record


def scoped_user_query(
    user=None, *, active_only: bool = False, exclude_owners: bool = False
):
    """User queries with tenant isolation (User is exempt from ORM auto-scoping)."""
    from models.user import User

    user = _resolve_user(user)
    query = User.query
    if exclude_owners:
        query = query.filter(User.is_owner.is_(False))
    if active_only:
        query = query.filter(User.is_active)

    tid = get_active_tenant_id(user)
    if tid is not None:
        return query.filter(User.tenant_id == tid)
    if is_platform_owner(user):
        return query
    return query.filter(User.tenant_id < 0)


def require_report_tenant_id(user=None) -> int:
    """Reports require an active tenant — blocks cross-tenant views for platform owner without selection."""
    return require_active_tenant_id(user)


def set_active_tenant(tenant_id, user=None):
    from models.tenant import Tenant

    if tenant_id is None or tenant_id == "":
        session.pop(ACTIVE_TENANT_SESSION_KEY, None)
        return

    user = _resolve_user(user)

    # Validate tenant_id is integer
    try:
        tenant_id = int(tenant_id)
    except (TypeError, ValueError):
        raise ValueError("Invalid tenant ID")

    # If not authenticated, reject non-empty tenant_id
    if not user or not getattr(user, "is_authenticated", False):
        raise ValueError("Unauthenticated users cannot set tenant_id")

    # Platform owner may set any active tenant
    if is_platform_owner(user):
        pass  # Allow platform owner to set any tenant
    else:
        # Normal user may only set their own user.tenant_id
        user_tenant_id = getattr(user, "tenant_id", None)
        if user_tenant_id is None:
            raise ValueError("Normal users must have a tenant_id")
        try:
            user_tenant_id = int(user_tenant_id or 0)
        except (TypeError, ValueError):
            raise ValueError("Normal users must have a valid integer tenant_id")
        if tenant_id != user_tenant_id:
            raise ValueError("Normal users can only set their own tenant_id")

    # Validate tenant exists and is active
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        raise ValueError("Tenant not found")

    if not tenant.is_active or getattr(tenant, "is_suspended", False):
        raise ValueError("Tenant is not active or is suspended")

    session[ACTIVE_TENANT_SESSION_KEY] = tenant_id


def clear_active_tenant():
    session.pop(ACTIVE_TENANT_SESSION_KEY, None)


@contextmanager
def without_tenant_scope():
    """Disable automatic ORM tenant filters (system init, migrations, cross-tenant admin tools)."""
    prev = getattr(g, "skip_tenant_scope", False) if has_request_context() else False
    if has_request_context():
        g.skip_tenant_scope = True
    try:
        yield
    finally:
        if has_request_context():
            g.skip_tenant_scope = prev


def get_tenant_status(tenant_id: int | None) -> dict:
    """Return tenant status dict; used by middleware and public pages."""
    from models.tenant import Tenant

    if tenant_id is None:
        return {"ok": True, "suspended": False, "reason": None}

    tenant = db.session.get(Tenant, int(tenant_id))
    if tenant is None:
        return {
            "ok": False,
            "suspended": True,
            "reason": "Tenant not found",
            "tenant": None,
        }

    if not tenant.is_active or getattr(tenant, "is_suspended", False):
        return {
            "ok": False,
            "suspended": True,
            "reason": tenant.suspension_reason or "Tenant suspended",
            "tenant": tenant,
        }
    return {"ok": True, "suspended": False, "reason": None, "tenant": tenant}
