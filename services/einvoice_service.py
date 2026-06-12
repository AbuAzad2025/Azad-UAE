"""
E-Invoice Service — Phase 9
Generates country-specific e-invoice XML + QR per LocalizationStrategy.
"""

from decimal import Decimal


class EInvoiceService:
    """خدمة توليد الفواتير الإلكترونية"""

    @staticmethod
    def generate(sale, country_code: str = None) -> dict:
        """
        توليد فاتورة إلكترونية لعملية البيع.
        """
        from utils.localization import get_strategy
        from utils.tenanting import get_active_tenant_id
        from models import Tenant

        if country_code is None:
            tenant_id = getattr(sale, 'tenant_id', None) or get_active_tenant_id()
            tenant = Tenant.query.get(tenant_id) if tenant_id else None
            country_code = (getattr(tenant, 'vat_country', None) or 'AE').strip().upper()

        strategy = get_strategy(country_code)
        return strategy.generate_einvoice(sale)
