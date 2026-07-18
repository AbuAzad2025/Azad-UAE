"""
Automatic ORM-level tenant isolation:
- SELECT auto-scoping via do_orm_execute + with_loader_criteria
- INSERT/UPDATE/DELETE guard via before_flush (TenantIsolationError)
"""

from __future__ import annotations


from flask import g, has_request_context, request
from sqlalchemy import event, inspect as sa_inspect, true as sql_true
from sqlalchemy.orm import with_loader_criteria

from extensions import db


class TenantIsolationError(Exception):
    """Raised when a write operation violates tenant isolation."""


_SKIP_BLUEPRINTS = frozenset(
    {
        "auth",  # Login/logout/register — platform-level auth, not tenant data
        "public",  # Landing, pricing, features — platform-level marketing pages only
        "language",  # Language switcher — no tenant data accessed
        "tenants",  # Tenant context switching — platform-owner-only via is_global_tenant_user
        "shop",  # Public tenant stores — exempt by design (see below)
    }
)
# User is exempt: Flask-Login loads by id; tenant filtering is applied in user-management routes.
_ORM_EXEMPT_MODELS = frozenset({"User", "Package", "PackagePurchase"})

# ── shop blueprint exemption rationale ─────────────────────────────────────
# The 'shop' blueprint (/s/<slug>/...) displays tenant-store pages and is
# intentionally exempt from ORM automatic tenant scoping because:
#
# 1. Anonymous visitors have no Flask-Login user — tenant_scope_enabled()
#    returns False for unauthenticated users anyway, so the exemption has no
#    practical effect for the unauthenticated case.
#
# 2. Tenant resolution is URL-driven: every route calls _resolve_store(slug)
#    which resolves tenant_id from TenantStore.store_slug, not from the
#    the ORM scoping which relies on g.active_tenant_id.
#
# 3. Every shop route and every StoreService/StoreCheckoutService method
#    explicitly filters ALL queries by the resolved tenant_id:
#    - Product.query.filter_by(..., tenant_id=store.tenant_id)
#    - Sale.query.filter_by(..., tenant_id=store.tenant_id)
#    - Customer.query.filter_by(..., tenant_id=store.tenant_id)
#    - etc.
#
# SAFETY: The existing storefront_isolation_test.py and the comprehensive
# test_multi_tenant_isolation_full.py verify that cross-tenant data leakage
# does not occur in any shop flow (catalog, product detail, cart, checkout,
# orders, order tokens, account orders).
#
# ALTERNATIVE: Rather than listing "shop" here, we could set
# g.public_tenant_id during _resolve_store() and have the ORM listener check
# for it. That would be more explicit but adds complexity. The current
# approach explicitly scopes every query and is tested.
# ────────────────────────────────────────────────────────────────────────────
_TENANT_MODELS: list[type] | None = None


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

    if not classes:
        # Don't cache an empty result — the registry may not have been
        # populated yet (models loaded after this first call).  The
        # registration call (factory.py) will set the cache once all
        # models are available.
        return []
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
    # Prefer the per-request value set by the factory's before_request
    # (g.active_tenant_id), which is stable for the whole request. Re-resolving
    # current_user at ORM-execute time can return None for lazy loads / nested
    # queries, which previously made the listener inject `tenant_id < 0`
    # (i.e. WHERE false) and emptied every tenant-scoped list.
    try:
        from flask import g

        if getattr(g, "active_tenant_id", None) is not None:
            return int(g.active_tenant_id)
    except Exception:
        pass
    from utils.tenanting import get_active_tenant_id

    return get_active_tenant_id()


def _criteria_for_model(tid: int | None):
    # When no active tenant is resolved for a scoped request, platform owners
    # legitimately operate across all tenants ("all companies" scope) and must
    # NOT have every row hidden. Non-owner company users cannot reach a scoped
    # blueprint with tid=None (the factory aborts 403); their manual query
    # helpers already apply the correct filter. So we substitute tid=-1 for the
    # "hide everything" case and tid=0 for the "show all" case, keeping the
    # lambda closure free of non-SQL variables.
    from utils.tenanting import is_platform_owner

    effective_tid = tid
    if tid is None:
        effective_tid = 0 if is_platform_owner() else -1

    def _criteria(cls):
        if not hasattr(cls, "tenant_id"):
            return sql_true()
        if effective_tid == -1:
            return cls.tenant_id < 0
        if effective_tid == 0:
            return sql_true()
        return cls.tenant_id == effective_tid

    return _criteria




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
        if model_cls.__name__ in _ORM_EXEMPT_MODELS:
            continue
        statement = statement.options(
            with_loader_criteria(
                model_cls,
                criteria,
                include_aliases=True,
            )
        )

    execute_state.statement = statement


# ── Write-path guard (INSERT / UPDATE / DELETE) ─────────────────────────
# Every tenant-bearing object being flushed must match the active tenant.
# The guard skips when there is no request context (Celery/CLI) or when
# g.skip_tenant_scope is True (without_tenant_scope() context manager).
#
# INSERT: if obj.tenant_id is None it is auto-stamped; if it differs from
#   the active tenant TenantIsolationError is raised.
# UPDATE / DELETE: any tenant-bearing row whose tenant_id is non-NULL and
#   does NOT match the active tenant triggers an error.
# -------------------------------------------------------------------------


@event.listens_for(Session, "before_flush")
def _inject_tenant_write_guard(session, flush_context, instances):
    if not has_request_context():
        return
    if getattr(g, "skip_tenant_scope", False):
        return

    tid = _active_tenant_for_orm()
    tenant_models = _discover_tenant_models()

    # ── INSERT guard + auto-stamp ─────────────────────────────────────
    for obj in session.new:
        if obj.__class__ not in tenant_models:
            continue
        mapper = sa_inspect(obj.__class__, raiseerr=False)
        if mapper is None or "tenant_id" not in mapper.columns:
            continue
        obj_tid = getattr(obj, "tenant_id", None)
        if obj_tid is None:
            if tid is not None:
                obj.tenant_id = tid
        elif tid is not None and int(obj_tid or 0) != int(tid or 0):
            _log_cross_tenant_warning(obj.__class__.__name__, obj_tid, tid)
            raise TenantIsolationError(
                f"Cross-tenant INSERT on {obj.__class__.__name__}: "
                f"obj.tenant_id={obj_tid} != active_tenant={tid}"
            )

    # ── UPDATE guard ──────────────────────────────────────────────────
    for obj in session.dirty:
        if obj.__class__ not in tenant_models:
            continue
        mapper = sa_inspect(obj.__class__, raiseerr=False)
        if mapper is None or "tenant_id" not in mapper.columns:
            continue
        obj_tid = getattr(obj, "tenant_id", None)
        if obj_tid is None:
            continue
        if tid is not None and int(obj_tid or 0) != int(tid or 0):
            _log_cross_tenant_warning(obj.__class__.__name__, obj_tid, tid)
            raise TenantIsolationError(
                f"Cross-tenant UPDATE on {obj.__class__.__name__}: "
                f"obj.tenant_id={obj_tid} != active_tenant={tid}"
            )

    # ── DELETE guard ──────────────────────────────────────────────────
    for obj in session.deleted:
        if obj.__class__ not in tenant_models:
            continue
        mapper = sa_inspect(obj.__class__, raiseerr=False)
        if mapper is None or "tenant_id" not in mapper.columns:
            continue
        obj_tid = getattr(obj, "tenant_id", None)
        if obj_tid is None:
            continue
        if tid is not None and int(obj_tid or 0) != int(tid or 0):
            _log_cross_tenant_warning(obj.__class__.__name__, obj_tid, tid)
            raise TenantIsolationError(
                f"Cross-tenant DELETE on {obj.__class__.__name__}: "
                f"obj.tenant_id={obj_tid} != active_tenant={tid}"
            )


def _log_cross_tenant_warning(model_name: str, obj_tid, active_tid):
    try:
        from flask import current_app

        current_app.logger.warning(
            "[TENANT_ISOLATION] Cross-tenant write blocked: %s obj.tenant_id=%s active_tenant=%s",
            model_name,
            obj_tid,
            active_tid,
        )
    except Exception:
        pass


def register_tenant_orm_scoping(app):
    """Call once during app startup (after db.init_app)."""
    with app.app_context():
        _discover_tenant_models()
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
