"""Per-tenant tax/VAT settings — optional per company."""

from __future__ import annotations

import logging
from decimal import Decimal

from utils.country_tax import COUNTRY_TAX_PROFILES, vat_rate_for_country
from utils.regional_defaults import FALLBACK_VAT_COUNTRY

# Statutory VAT rates — derived from the single source of truth in
# utils/country_tax.py. Re-exported here (not duplicated) so every existing
# importer keeps working and cannot drift from the profiles.
VAT_RATES_BY_COUNTRY = {code: Decimal(str(p["vat_rate"])) for code, p in COUNTRY_TAX_PROFILES.items()}

VAT_COUNTRY_LABELS = {
    "PS": f"فلسطين ({vat_rate_for_country('PS')}%)",
    "IL": f"إسرائيل ({vat_rate_for_country('IL')}%)",
    "AE": f"الإمارات ({vat_rate_for_country('AE')}%)",
    "SA": f"السعودية ({vat_rate_for_country('SA')}%)",
}


def _resolve_tenant(tenant_id=None):
    if tenant_id is not None:
        from extensions import db
        from models.tenant import Tenant

        return db.session.get(Tenant, int(tenant_id))
    try:
        from models.tenant import Tenant

        return Tenant.get_current()
    except Exception:
        logging.getLogger(__name__).debug("Tenant.get_current() failed; no current tenant", exc_info=True)
        return None


def _resolve_main_branch(tenant_id):
    """Resolve the main branch for a tenant; returns None if no branch exists."""
    from models.branch import Branch

    if tenant_id is not None:
        branch = Branch.query.filter_by(tenant_id=int(tenant_id), is_main=True).first()
        if branch:
            return branch.id
    return None


def is_tax_enabled(tenant_id=None) -> bool:
    tenant = _resolve_tenant(tenant_id)
    if tenant is None:
        return False
    return bool(getattr(tenant, "enable_tax", False))


def vat_country(tenant_id=None) -> str:
    tenant = _resolve_tenant(tenant_id)
    if tenant is None:
        return FALLBACK_VAT_COUNTRY
    return (getattr(tenant, "vat_country", None) or FALLBACK_VAT_COUNTRY).strip().upper()


def default_tax_rate(tenant_id=None) -> Decimal:
    """Return the tenant's VAT rate.

    Priority: the tenant's own configured rate if set, otherwise the
    statutory rate of the tenant's VAT country (utils/country_tax.py).
    Zero when tax is disabled. A stored rate is never overridden — a
    tenant pinned to a custom rate keeps it — but a tenant with no
    configured rate now inherits its country's statutory rate instead of
    silently getting zero VAT.
    """
    if not is_tax_enabled(tenant_id):
        return Decimal("0")
    tenant = _resolve_tenant(tenant_id)
    if tenant is None:
        return Decimal("0")
    stored = getattr(tenant, "default_tax_rate", None)
    if stored is not None:
        try:
            stored_rate = Decimal(str(stored))
        except Exception:
            stored_rate = None
        if stored_rate is not None and stored_rate >= Decimal("0"):
            return stored_rate
    return vat_rate_for_country(vat_country(tenant_id))


def effective_tax_rate(tax_rate, tenant_id=None) -> Decimal:
    """Effective invoice VAT rate with country compliance.

    ``None`` means "not specified" → the tenant/country default. An explicit
    value is honored (0 = exempt/zero-rated, standard = standard). Tax
    disabled → 0.
    """
    if not is_tax_enabled(tenant_id):
        return Decimal("0")
    if tax_rate is None:
        return default_tax_rate(tenant_id)
    rate = Decimal(str(tax_rate))
    if rate < Decimal("0") or rate > Decimal("100"):
        raise ValueError("نسبة الضريبة يجب أن تكون بين 0 و 100")
    return rate


def get_prices_include_vat(tenant_id=None, branch_id=None) -> bool:
    """Return True if the tenant/branch uses VAT-inclusive pricing.

    Priority:
      1. Branch-level setting (if explicitly set)
      2. Tenant-level setting
      3. False (default)
    """
    if branch_id is not None:
        from extensions import db
        from models.branch import Branch

        branch = db.session.get(Branch, int(branch_id))
        if branch and branch.prices_include_vat is not None:
            return bool(branch.prices_include_vat)
    tenant = _resolve_tenant(tenant_id)
    if tenant is not None:
        return bool(getattr(tenant, "prices_include_vat", False))
    return False


def normalize_tax_rate(tax_rate, tenant_id=None) -> Decimal:
    """Return effective tax rate — zero when tenant has tax disabled.

    Kept for compatibility: a ``None`` rate means "use the tenant/country
    default" (see effective_tax_rate); an explicit rate is respected.
    """
    return effective_tax_rate(tax_rate, tenant_id)


def should_post_vat_gl(tenant_id=None) -> bool:
    return is_tax_enabled(tenant_id)


def suggested_rate_for_country(country_code: str) -> Decimal:
    return vat_rate_for_country(country_code)
