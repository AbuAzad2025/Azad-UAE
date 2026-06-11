"""
Tax Calculation Service — Phase 9
Dispatches to country-specific strategy based on Tenant.vat_country.
"""

from decimal import Decimal
from extensions import db


class TaxService:
    """خدمة حساب الضريبة حسب الدولة"""

    @staticmethod
    def _get_strategy(tenant_id=None):
        from utils.localization import get_strategy
        from utils.tenanting import get_active_tenant_id
        from models import Tenant

        if tenant_id is None:
            tenant_id = get_active_tenant_id()
        tenant = Tenant.query.get(tenant_id) if tenant_id else None
        country = (getattr(tenant, 'vat_country', None) or 'AE').strip().upper()
        return get_strategy(country)

    @classmethod
    def calculate_sale_tax(cls, sale, tenant_id=None) -> dict:
        """
        حساب ضريبة البيع (Output VAT) استناداً إلى strategy الدولة.
        """
        strategy = cls._get_strategy(tenant_id)
        amount = Decimal(str(sale.amount_aed or 0))
        tax_rate = Decimal(str(sale.tax_rate or 0))
        result = strategy.calculate_tax(amount, tax_rate)
        return {
            'strategy': strategy.country_code,
            'tax_amount': result['tax_amount'],
            'net_amount': result['net_amount'],
            'total_amount': result['total_amount'],
            'rate_applied': result['rate_applied'],
        }

    @classmethod
    def calculate_purchase_tax(cls, purchase, tenant_id=None) -> dict:
        """
        حساب ضريبة المشتريات (Input VAT / VAT Recovery).
        """
        strategy = cls._get_strategy(tenant_id)
        amount = Decimal(str(purchase.amount_aed or 0))
        tax_rate = Decimal(str(purchase.tax_rate or 0))
        result = strategy.calculate_tax(amount, tax_rate)
        return {
            'strategy': strategy.country_code,
            'tax_amount': result['tax_amount'],
            'net_amount': result['net_amount'],
            'total_amount': result['total_amount'],
            'rate_applied': result['rate_applied'],
        }

    @classmethod
    def get_vat_return(cls, date_from: str, date_to: str, tenant_id=None) -> dict:
        """
        تقرير VAT موحد — يستخدم GL (القيود المحاسبية) بدلاً من فواتير المبيعات/المشتريات مباشرة.
        """
        from services.gl_service import GLService

        strategy = cls._get_strategy(tenant_id)
        try:
            gl_report = GLService.get_vat_report(
                date_from=date_from or None,
                date_to=date_to or None,
                tenant_id=tenant_id,
            )
            output_vat = Decimal(str(gl_report.get('vat_output', 0)))
            input_vat = Decimal(str(gl_report.get('vat_input', 0)))
        except Exception:
            output_vat = Decimal('0')
            input_vat = Decimal('0')

        result = strategy.format_tax_return(output_vat, input_vat, date_from, date_to)
        result['source'] = 'gl'
        return result
