"""
خدمة المواقف الضريبية - Fiscal Position Service
Inspired by Odoo's account.fiscal.position
"""

from extensions import db
from models import FiscalPosition, FiscalPositionTaxRule, Customer, TaxCalculationRule


class FiscalPositionService:

    @staticmethod
    def get_for_customer(customer_id):
        """
        Return the fiscal position applicable for a customer.
        Checks explicit assignment first, then auto-matching rules.
        """
        customer = db.session.get(Customer,customer_id)
        if not customer:
            return None

        # Explicit assignment
        if hasattr(customer, 'fiscal_position_id') and customer.fiscal_position_id:
            return db.session.get(FiscalPosition,customer.fiscal_position_id)

        # Auto-match by country
        tenant_id = customer.tenant_id
        country = getattr(customer, 'country', None) or getattr(customer, 'address_country', None)
        if country:
            pos = FiscalPosition.query.filter(
                FiscalPosition.tenant_id == tenant_id,
                FiscalPosition.is_active == True,
                FiscalPosition.auto_apply == True,
                FiscalPosition.country_code == country
            ).first()
            if pos:
                return pos

        return FiscalPosition.query.filter_by(
            tenant_id=tenant_id, code='local', is_active=True
        ).first()

    @staticmethod
    def apply_to_sale(sale, customer_id=None):
        """
        Apply fiscal position rules to a sale's taxes and accounts.
        Mutates sale lines in place.
        """
        if customer_id is None:
            customer_id = getattr(sale, 'customer_id', None)
        if not customer_id:
            return sale

        pos = FiscalPositionService.get_for_customer(customer_id)
        if not pos:
            return sale

        for line in sale.lines:
            # Map tax
            if hasattr(line, 'tax_id') and line.tax_id:
                mapped = pos.map_tax(line.tax_id)
                if mapped != line.tax_id:
                    line.tax_id = mapped

            # Map income account
            if hasattr(line, 'income_account_id') and line.income_account_id:
                mapped = pos.map_account(line.income_account_id)
                if mapped != line.income_account_id:
                    line.income_account_id = mapped

        return sale

    @staticmethod
    def compute_tax_for_line(line, fiscal_position_id=None, customer_id=None):
        """
        Compute tax amount for a sale line considering fiscal position.
        Returns (tax_amount, tax_rate).
        """
        from decimal import Decimal

        if fiscal_position_id is None and customer_id:
            pos = FiscalPositionService.get_for_customer(customer_id)
            fiscal_position_id = pos.id if pos else None

        # Get tax rule
        source_tax_id = getattr(line, 'tax_id', None)
        if fiscal_position_id and source_tax_id:
            rule = FiscalPositionTaxRule.query.filter_by(
                fiscal_position_id=fiscal_position_id,
                source_tax_id=source_tax_id,
                rule_type='tax'
            ).first()
            if rule and rule.destination_tax:
                tax_rate = Decimal(str(rule.destination_tax.rate or 0))
            else:
                tax = db.session.get(TaxCalculationRule,source_tax_id)
                tax_rate = Decimal(str(tax.rate if tax else 0))
        else:
            tax = db.session.get(TaxCalculationRule,source_tax_id) if source_tax_id else None
            tax_rate = Decimal(str(tax.rate if tax else 0))

        net = Decimal(str(line.unit_price or 0)) * Decimal(str(line.quantity or 1))
        tax_amount = (net * tax_rate / Decimal('100')).quantize(Decimal('0.001'))
        return tax_amount, tax_rate
