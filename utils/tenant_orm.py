"""
Automatic ORM-level tenant isolation for every SELECT and session.get().
Applies to all mapped models that expose a tenant_id column.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterable

from flask import g, has_request_context, request
from sqlalchemy import event, inspect as sa_inspect, true as sql_true
from sqlalchemy.orm import Session, with_loader_criteria

from extensions import db

_SKIP_BLUEPRINTS = frozenset({"auth", "public", "language", "tenants", "shop"})
# User is exempt: Flask-Login loads by id; tenant filtering is applied in user-management routes.
_ORM_EXEMPT_MODELS = frozenset({"User"})
_TENANT_MODELS: list[type] | None = None
_SESSION_GET_PATCHED = False


def _discover_tenant_models() -> list[type]:
    global _TENANT_MODELS
    if _TENANT_MODELS is not None:
        return _TENANT_MODELS

    classes: list[type] = []
    try:
        registry = db.Model.registry
        for mapper in registry.mappers:
            cls = mapper.class_
            if cls.__tablename__ == "tenants":
                continue
            if cls.__name__ in _ORM_EXEMPT_MODELS:
                continue
            if "tenant_id" in mapper.columns:
                classes.append(cls)
    except Exception:
        pass

    _TENANT_MODELS = classes
    return classes


def tenant_scope_enabled() -> bool:
    if not has_request_context():
        return False
    if getattr(g, "skip_tenant_scope", False):
        return False
    if request.endpoint == "static":
        return False
    bp = request.blueprint or ""
    if bp in _SKIP_BLUEPRINTS:
        return False
    try:
        from flask_login import current_user

        if not getattr(current_user, "is_authenticated", False):
            return False
    except Exception:
        return False
    return True


def _active_tenant_for_orm() -> int | None:
    from utils.tenanting import get_active_tenant_id

    return get_active_tenant_id()


def _criteria_for_model(tid: int | None):
    def _criteria(cls):
        if not hasattr(cls, "tenant_id"):
            return sql_true()
        if tid is None:
            return cls.tenant_id < 0
        return cls.tenant_id == tid

    return _criteria


def _validate_instance_tenant(obj) -> bool:
    if obj is None:
        return True
    if obj.__class__.__name__ in _ORM_EXEMPT_MODELS:
        return True
    mapper = sa_inspect(obj.__class__, raiseerr=False)
    if mapper is None or "tenant_id" not in mapper.columns:
        return True

    tid = _active_tenant_for_orm()
    rec_tid = getattr(obj, "tenant_id", None)
    if rec_tid is None:
        from utils.tenanting import is_platform_owner

        return is_platform_owner()
    if tid is None:
        return False
    return int(rec_tid) == int(tid)


def _patch_session_get():
    global _SESSION_GET_PATCHED
    if _SESSION_GET_PATCHED:
        return

    _orig_get = Session.get

    def _get_with_tenant(self, entity, ident, *args, **kwargs):
        obj = _orig_get(self, entity, ident, *args, **kwargs)
        if obj is None or not tenant_scope_enabled():
            return obj
        if kwargs.get("execution_options", {}).get("skip_tenant_scope"):
            return obj
        if not _validate_instance_tenant(obj):
            return None
        return obj

    Session.get = _get_with_tenant  # type: ignore[method-assign]
    _SESSION_GET_PATCHED = True


@event.listens_for(Session, "do_orm_execute")
def _inject_tenant_criteria(execute_state):
    if not execute_state.is_select:
        return
    if execute_state.execution_options.get("skip_tenant_scope"):
        return
    if not tenant_scope_enabled():
        return

    tid = _active_tenant_for_orm()
    criteria = _criteria_for_model(tid)
    statement = execute_state.statement

    for model_cls in _discover_tenant_models():
        statement = statement.options(
            with_loader_criteria(
                model_cls,
                criteria,
                include_aliases=True,
            )
        )

    execute_state.statement = statement


def register_tenant_orm_scoping(app):
    """Call once during app startup (after db.init_app)."""
    with app.app_context():
        _discover_tenant_models()
        _patch_session_get()
    app.logger.info(
        "[OK] Tenant ORM scoping active (%s models)",
        len(_discover_tenant_models()),
    )


# --- Backward-compatibility shims -------------------------------------------
# Some older modules import these helpers from utils.tenant_orm. The canonical
# implementations live in utils.tenanting; re-export them here (lazy import to
# avoid any import-cycle) without changing tenant logic.
def tenant_query(model, user=None):
    from utils.tenanting import tenant_query as _tenant_query

    return _tenant_query(model, user)


def model_has_tenant(model) -> bool:
    from utils.tenanting import model_has_tenant as _model_has_tenant

    return _model_has_tenant(model)
