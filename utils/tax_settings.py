"""Per-tenant tax/VAT settings — optional per company."""
from __future__ import annotations

from decimal import Decimal

VAT_RATES_BY_COUNTRY = {
    'AE': Decimal('5.00'),
    'IL': Decimal('17.00'),
    'PS': Decimal('16.00'),
}

VAT_COUNTRY_LABELS = {
    'AE': 'الإمارات (5%)',
    'IL': 'إسرائيل (17%)',
    'PS': 'فلسطين (16%)',
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
    if not is_tax_enabled(tenant_id):
        return Decimal('0')
    tenant = _resolve_tenant(tenant_id)
    if tenant is None:
        return Decimal('0')
    stored = getattr(tenant, 'default_tax_rate', None)
    if stored is not None and Decimal(str(stored)) >= Decimal('0'):
        return Decimal(str(stored))
    return VAT_RATES_BY_COUNTRY.get(vat_country(tenant_id), Decimal('0'))


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
