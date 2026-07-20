"""
Tenant Limits / Quota Enforcement

Centralized limit checks for multi-tenant SaaS.
Usage in routes before db.session.add() / db.session.commit().
"""

from __future__ import annotations

from datetime import datetime, timezone
from flask_login import current_user
from extensions import db
import logging

from utils.tenanting import get_active_tenant_id

logger = logging.getLogger(__name__)


class TenantLimitError(Exception):
    """Raised when a tenant exceeds its plan limit."""

    wa_upgrade_link: str = ""

    def __init__(self, resource: str, limit: int, current: int):
        self.resource = resource
        self.limit = limit
        self.current = current
        msg = f"لقد تجاوزت الحد المسموح ({limit} {resource}). الحالي: {current}."
        if not TenantLimitError.wa_upgrade_link:
            try:
                from flask import current_app

                link = current_app.config.get("DEVELOPER_WHATSAPP", "")
                if not link:
                    from models.system_settings import SystemSettings

                    _settings = SystemSettings.get_current()
                    link = _settings.get_custom_setting("developer_whatsapp") if _settings else ""
                if link:
                    link = link.strip().replace(" ", "").lstrip("+")
                    if not link.startswith("https"):
                        link = f"https://wa.me/{link}"
                    TenantLimitError.wa_upgrade_link = link
            except Exception:
                logger.debug("Failed to resolve developer WhatsApp upgrade link", exc_info=True)
            msg += (
                f"\n\nيمكنك التواصل مع المطور للترقية إلى باقة أعلى عبر "
                f'<a href="{TenantLimitError.wa_upgrade_link}" target="_blank" class="alert-link">واتساب</a>.'
            )
        super().__init__(msg)


def _active_tenant():
    """Get current tenant for the logged-in user."""
    try:
        from models import Tenant

        tid = get_active_tenant_id(current_user)
        if tid:
            return db.session.get(Tenant, int(tid))
    except Exception:
        logger.debug("Failed to resolve active tenant for limit check", exc_info=True)


def _month_start():
    return datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def check_limit(
    resource: str,
    *,
    model,
    tenant_id_field: str = "tenant_id",
    extra_filter=None,
    error_if_disabled: bool = False,
) -> None:
    """Generic limit checker.

    Args:
        resource: human-readable name (users, branches, products...)
        model: SQLAlchemy model class to count
        tenant_id_field: column name holding tenant FK
        extra_filter: optional callable(query) -> query for extra conditions
        error_if_disabled: if True, raises even when limit is 0 (feature disabled)
    """
    tenant = _active_tenant()
    if not tenant:
        return  # no tenant context — skip (owner/platform mode)

    limit_attr = f"max_{resource}"
    limit_val = getattr(tenant, limit_attr, None)
    if limit_val is None:
        return  # no limit configured for this resource

    if limit_val == 0 and error_if_disabled:
        raise TenantLimitError(resource, 0, 0)

    if limit_val <= 0:
        return  # unlimited / disabled

    tid = tenant.id
    q = db.session.query(model).filter(getattr(model, tenant_id_field) == tid)
    if extra_filter:
        q = extra_filter(q)
    current_count = q.count()

    if current_count >= limit_val:
        raise TenantLimitError(resource, limit_val or 0, current_count)


def check_monthly_limit(
    resource: str,
    *,
    model,
    date_field: str,
    tenant_id_field: str = "tenant_id",
    extra_filter=None,
) -> None:
    """Check a per-month limit (e.g. max_invoices_per_month)."""
    tenant = _active_tenant()
    if not tenant:
        return

    limit_attr = f"max_{resource}_per_month"
    limit_val = getattr(tenant, limit_attr, None)
    if limit_val is None:
        return
    if limit_val <= 0:
        return

    month_start = _month_start()
    tid = tenant.id
    q = db.session.query(model).filter(
        getattr(model, tenant_id_field) == tid,
        getattr(model, date_field) >= month_start,
    )
    if extra_filter:
        q = extra_filter(q)
    current_count = q.count()

    if current_count >= limit_val:
        raise TenantLimitError(f"{resource}_per_month", limit_val or 0, current_count)


def check_feature_enabled(feature_flag: str) -> bool:
    """Return True if the tenant has the feature enabled."""
    tenant = _active_tenant()
    if not tenant:
        return True  # no tenant context — allow (owner/platform)
    return getattr(tenant, feature_flag, True)


def enforce_feature(feature_flag: str, feature_name_ar: str) -> None:
    """Raise if feature is disabled for this tenant."""
    tenant = _active_tenant()
    if not tenant:
        return
    enabled = getattr(tenant, feature_flag, True)
    if not enabled:
        raise TenantLimitError(feature_name_ar, 0, 0)


# ── Convenience helpers ──────────────────────────────────────


def check_users_limit() -> None:
    from models import User

    check_limit(
        "users",
        model=User,
        tenant_id_field="tenant_id",
        extra_filter=lambda q: q.filter_by(is_active=True),
    )


def check_branches_limit() -> None:
    from models import Branch

    check_limit("branches", model=Branch, tenant_id_field="tenant_id")


def check_warehouses_limit() -> None:
    from models import Warehouse

    check_limit("warehouses", model=Warehouse, tenant_id_field="tenant_id")


def check_products_limit() -> None:
    from models import Product

    check_limit(
        "products",
        model=Product,
        tenant_id_field="tenant_id",
        extra_filter=lambda q: q.filter_by(is_active=True),
    )


def check_customers_limit() -> None:
    from models import Customer

    check_limit(
        "customers",
        model=Customer,
        tenant_id_field="tenant_id",
        extra_filter=lambda q: q.filter_by(is_active=True),
    )


def check_suppliers_limit() -> None:
    from models import Supplier

    check_limit(
        "suppliers",
        model=Supplier,
        tenant_id_field="tenant_id",
        extra_filter=lambda q: q.filter_by(is_active=True),
    )


def check_sales_monthly_limit() -> None:
    from models import Sale

    check_monthly_limit(
        "sales",
        model=Sale,
        date_field="sale_date",
        tenant_id_field="tenant_id",
        extra_filter=lambda q: q.filter_by(status="confirmed"),
    )


def check_invoices_monthly_limit() -> None:
    from models import Sale

    check_monthly_limit(
        "invoices",
        model=Sale,
        date_field="sale_date",
        tenant_id_field="tenant_id",
        extra_filter=lambda q: q.filter_by(status="confirmed"),
    )
