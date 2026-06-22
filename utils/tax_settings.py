"""Per-tenant tax/VAT settings — optional per company."""
from __future__ import annotations

from decimal import Decimal

VAT_RATES_BY_COUNTRY = {
    'PS': Decimal('16.00'),
    'IL': Decimal('17.00'),
    'AE': Decimal('5.00'),
}

VAT_COUNTRY_LABELS = {
    'PS': 'فلسطين (16%)',
    'IL': 'إسرائيل (17%)',
    'AE': 'الإمارات (5%)',
}


def _resolve_tenant(tenant_id=None):
    if tenant_id is not None:
        from models.tenant import Tenant
        from extensions import db
        return db.session.get(Tenant, int(tenant_id))
    try:
        from models.tenant import Tenant
        return Tenant.get_current()
    except Exception:
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
    return bool(getattr(tenant, 'enable_tax', False))


def vat_country(tenant_id=None) -> str:
    tenant = _resolve_tenant(tenant_id)
    if tenant is None:
        return 'AE'
    return (getattr(tenant, 'vat_country', None) or 'AE').strip().upper()


def default_tax_rate(tenant_id=None) -> Decimal:
    """Return tenant-configured tax rate. Falls back to 0 if not set."""
    if not is_tax_enabled(tenant_id):
        return Decimal('0')
    tenant = _resolve_tenant(tenant_id)
    if tenant is None:
        return Decimal('0')
    stored = getattr(tenant, 'default_tax_rate', None)
    if stored is not None and Decimal(str(stored)) >= Decimal('0'):
        return Decimal(str(stored))
    return Decimal('0')  # Removed hardcoded VAT_RATES_BY_COUNTRY fallback


def get_prices_include_vat(tenant_id=None, branch_id=None) -> bool:
    """Return True if the tenant/branch uses VAT-inclusive pricing.

    Priority:
      1. Branch-level setting (if explicitly set)
      2. Tenant-level setting
      3. False (default)
    """
    if branch_id is not None:
        from models.branch import Branch
        from extensions import db
        branch = db.session.get(Branch, int(branch_id))
        if branch and branch.prices_include_vat is not None:
            return bool(branch.prices_include_vat)
    tenant = _resolve_tenant(tenant_id)
    if tenant is not None:
        return bool(getattr(tenant, 'prices_include_vat', False))
    return False


def normalize_tax_rate(tax_rate, tenant_id=None) -> Decimal:
    """Return effective tax rate — zero when tenant has tax disabled."""
    if not is_tax_enabled(tenant_id):
        return Decimal('0')
    rate = Decimal(str(tax_rate if tax_rate is not None else 0))
    if rate < Decimal('0') or rate > Decimal('100'):
        raise ValueError('نسبة الضريبة يجب أن تكون بين 0 و 100')
    return rate


def should_post_vat_gl(tenant_id=None) -> bool:
    return is_tax_enabled(tenant_id)


def suggested_rate_for_country(country_code: str) -> Decimal:
    return VAT_RATES_BY_COUNTRY.get((country_code or '').strip().upper(), Decimal('0'))
