"""
Tenant isolation — each company (tenant) is fully separated.
Company users (including super_admin) cannot access another tenant's data.
Only platform owners (is_owner) may switch tenants via session.
"""

from __future__ import annotations

from contextlib import contextmanager

from flask import abort, g, has_request_context, session
from flask_login import current_user

from extensions import db

ACTIVE_TENANT_SESSION_KEY = "active_tenant_id"


def _resolve_user(user=None):
    if user is not None:
        return user
    try:
        return current_user
    except Exception:
        return None


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
        return None

    if not is_platform_owner(user):
        tid = getattr(user, "tenant_id", None)
        return int(tid) if tid else None

    if has_request_context():
        raw = session.get(ACTIVE_TENANT_SESSION_KEY)
        if raw is not None and raw != "":
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass

    tid2 = getattr(user, "tenant_id", None)
    return int(tid2) if tid2 else None


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
        return True

    if tid is None:
        if or_404:
            abort(403 if is_platform_owner(user) else 404)
        return False

    if int(rec_tid) != int(tid):
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


def set_active_tenant(tenant_id):
    if tenant_id is None or tenant_id == "":
        session.pop(ACTIVE_TENANT_SESSION_KEY, None)
        return
    session[ACTIVE_TENANT_SESSION_KEY] = int(tenant_id)


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
