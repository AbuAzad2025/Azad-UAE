import logging

from config import Config
from extensions import db

logger = logging.getLogger(__name__)


def get_system_default_currency() -> str:
    return getattr(Config, "DEFAULT_CURRENCY", None) or "ILS"


def context_aware_default_currency() -> str:
    """Resolve default currency from current Flask request tenant if available,
    falling back to system default currency. Used as SQLAlchemy column default."""
    try:
        from flask import has_request_context

        if has_request_context():
            from flask_login import current_user

            if current_user and current_user.is_authenticated:
                tenant_id = getattr(current_user, "tenant_id", None)
                if tenant_id:
                    from models.tenant import Tenant

                    tenant = db.session.get(Tenant, tenant_id)
                    if tenant and getattr(tenant, "default_currency", None):
                        val = tenant.default_currency.strip()
                        if val:
                            return val.upper()
        return get_system_default_currency()
    except Exception:
        return get_system_default_currency()


def resolve_default_currency(tenant=None) -> str:
    if tenant and hasattr(tenant, "default_currency"):
        val = (tenant.default_currency or "").strip()
        if val:
            return val.upper()
    try:
        from models.system_settings import SystemSettings

        settings = SystemSettings.get_current()
        val = (getattr(settings, "default_currency", None) or "").strip()
        if val:
            return val.upper()
    except Exception:
        logger.debug("Failed to resolve default currency from SystemSettings", exc_info=True)
    return get_system_default_currency()


def get_tenant_base_currency(tenant_id: int | None = None) -> str:
    """Return the tenant's base currency dynamically.
    Priority:
      1. tenant.base_currency
      2. tenant.default_currency
      3. system default (ILS)
    """
    if tenant_id is not None:
        try:
            from models.tenant import Tenant

            tenant = db.session.get(Tenant, int(tenant_id))
            if tenant:
                base = getattr(tenant, "base_currency", None)
                if base:
                    val = base.strip().upper()
                    if val:
                        return val
                default = getattr(tenant, "default_currency", None)
                if default:
                    val = default.strip().upper()
                    if val:
                        return val
        except Exception:
            logger.debug("Failed to resolve base currency for tenant %s", tenant_id, exc_info=True)
    return get_system_default_currency()


def resolve_tenant_base_currency(tenant=None, tenant_id=None) -> str:
    """Resolve the base currency for a tenant instance or tenant_id."""
    if tenant is not None:
        base = getattr(tenant, "base_currency", None)
        if base:
            val = base.strip().upper()
            if val:
                return val
        default = getattr(tenant, "default_currency", None)
        if default:
            val = default.strip().upper()
            if val:
                return val
    if tenant_id is not None:
        return get_tenant_base_currency(tenant_id)
    return get_system_default_currency()


def get_currency_symbol(code):
    from utils.constants import CURRENCIES

    for c_code, data in CURRENCIES:
        if c_code == code:
            return data.get("symbol", code)
    return code


def get_currency_name_ar(code):
    from utils.constants import CURRENCIES

    for c_code, data in CURRENCIES:
        if c_code == code:
            return data.get("ar", code)
    return code
