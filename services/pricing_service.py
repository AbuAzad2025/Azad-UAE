from decimal import Decimal, ROUND_HALF_UP
from extensions import db


class PricingService:

    @staticmethod
    def get_price(product, customer_type='regular', qty=1):
        from models.product_price_tier import ProductPriceTier

        qty = Decimal(str(qty))

        tier = ProductPriceTier.query.filter_by(
            product_id=product.id,
            is_active=True,
        ).filter(
            ProductPriceTier.min_quantity <= qty
        ).order_by(
            ProductPriceTier.min_quantity.desc()
        ).first()

        if tier:
            return tier.price

        if customer_type == 'partner' and getattr(product, 'partner_price', None):
            return product.regular_price * (1 - (Decimal(str(product.partner_price)) / 100))
        elif customer_type == 'merchant' and getattr(product, 'merchant_price', None):
            return product.regular_price * (1 - (Decimal(str(product.merchant_price)) / 100))

        return product.regular_price

    @staticmethod
    def get_price_for_sale_line(product, qty, customer, sales_rep=None):
        from models.product_price_tier import ProductPriceTier

        qty = Decimal(str(qty))
        customer_type = customer.customer_type if customer else 'regular'

        tier = ProductPriceTier.query.filter_by(
            product_id=product.id,
            is_active=True,
        ).filter(
            ProductPriceTier.min_quantity <= qty
        ).order_by(
            ProductPriceTier.min_quantity.desc()
        ).first()

        unit_price = PricingService.get_price(product, customer_type, qty)
        discount = Decimal('0')

        if customer_type in ('partner', 'merchant'):
            disc_pct = getattr(product, f'{customer_type}_price', None)
            if disc_pct:
                discount = Decimal(str(disc_pct))

        commission_rate = Decimal('0')
        if sales_rep:
            commission_rate = Decimal(str(getattr(sales_rep, 'commission_rate', 0) or 0))

        return {
            'unit_price': unit_price,
            'tier_code': tier.tier_code if tier else None,
            'discount_applied': discount,
            'commission_rate': commission_rate,
        }

    @staticmethod
    def format_price(price, currency='AED'):
        from decimal import Decimal
        from utils.currency_utils import format_currency_value
        return format_currency_value(Decimal(str(price)), currency)