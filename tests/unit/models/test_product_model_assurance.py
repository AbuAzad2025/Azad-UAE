"""Product and ProductCategory model — pricing, stock aliases, serialization."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock



class TestProductCategory:
    def test_repr_and_display_name(self):
        from models.product import ProductCategory

        cat = ProductCategory(name='Electronics', name_ar='إلكترونيات')
        assert 'Electronics' in repr(cat)
        assert cat.get_display_name('ar') == 'إلكترونيات'
        assert cat.get_display_name('en') == 'Electronics'


class TestProductModel:
    @staticmethod
    def _product(**kwargs):
        from models.product import Product

        p = Product(
            name='Widget',
            name_ar='أداة',
            regular_price=Decimal('100'),
            cost_price=Decimal('40'),
            current_stock=Decimal(kwargs.get('stock', '10')),
            min_stock_alert=Decimal(kwargs.get('min_stock', '5')),
        )
        p.merchant_price = kwargs.get('merchant_price')
        p.partner_price = kwargs.get('partner_price')
        p.category = kwargs.get('category')
        return p

    def test_repr(self):
        assert 'Widget' in repr(self._product())

    def test_stock_aliases(self):
        p = self._product()
        assert p.stock_quantity == Decimal('10')
        p.stock_quantity = Decimal('20')
        assert p.current_stock == Decimal('20')
        assert p.quantity_in_stock == Decimal('20')
        p.quantity_in_stock = Decimal('15')
        assert p.current_stock == Decimal('15')

    def test_get_price_for_customer(self):
        p = self._product(partner_price=Decimal('10'), merchant_price=Decimal('20'))
        assert p.get_price_for_customer('regular') == Decimal('100')
        assert p.get_price_for_customer('partner') == Decimal('90')
        assert p.get_price_for_customer('merchant') == Decimal('80')

    def test_stock_flags(self):
        p = self._product(stock='3', min_stock='5')
        assert p.is_low_stock() is True
        assert p.is_out_of_stock() is False
        p.current_stock = Decimal('0')
        assert p.is_out_of_stock() is True
        p.min_stock_alert = None
        assert p.is_low_stock() is False

    def test_get_display_name_english(self):
        p = self._product()
        assert p.get_display_name('en') == 'Widget'

        p = self._product()
        assert p.get_display_name('ar') == 'أداة'
        assert p.get_cost() == Decimal('40')
        assert p.get_stock() == Decimal('10')

    def test_to_dict_with_cost(self):
        p = self._product()
        p.id = 1
        p.category = MagicMock(name='Cat')
        p.is_active = True
        p.sku = 'SKU-1'
        p.barcode = 'BC-1'
        p.unit = 'pcs'
        data = p.to_dict(include_cost=True)
        assert data['is_low_stock'] is False
        assert data['cost_price'] == 40.0
