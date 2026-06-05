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
        تجميع VAT Return: Output VAT (من المبيعات) - Input VAT (من المشتريات).
        """
        from models import Sale, Purchase

        strategy = cls._get_strategy(tenant_id)

        # Output VAT from confirmed sales in date range
        sales = Sale.query.filter(
            Sale.status == 'confirmed',
            Sale.sale_date >= date_from,
            Sale.sale_date <= date_to,
        )
        if tenant_id is not None:
            sales = sales.filter(Sale.tenant_id == tenant_id)
        output_vat = sum(
            Decimal(str(s.amount_aed or 0)) * Decimal(str(s.tax_rate or 0)) / Decimal('100')
            for s in sales.all()
        )

        # Input VAT from confirmed purchases in date range
        purchases = Purchase.query.filter(
            Purchase.status == 'confirmed',
            Purchase.purchase_date >= date_from,
            Purchase.purchase_date <= date_to,
        )
        if tenant_id is not None:
            purchases = purchases.filter(Purchase.tenant_id == tenant_id)
        input_vat = sum(
            Decimal(str(p.amount_aed or 0)) * Decimal(str(p.tax_rate or 0)) / Decimal('100')
            for p in purchases.all()
        )

        return strategy.format_tax_return(output_vat, input_vat, date_from, date_to)
