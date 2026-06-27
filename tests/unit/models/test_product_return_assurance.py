"""ProductReturn model — totals, aliases, lines."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from models.product_return import ProductReturn, ProductReturnLine


class TestProductReturnModel:
    def test_base_amount_alias(self):
        pr = ProductReturn()
        pr.amount_aed = Decimal('100.500')
        assert pr.base_amount == Decimal('100.500')
        pr.base_amount = Decimal('200')
        assert pr.amount_aed == Decimal('200')

    def test_calculate_totals_from_lines(self):
        pr = ProductReturn()
        pr.exchange_rate = Decimal('3.67')
        pr.refund_amount = None
        line1 = MagicMock(line_total=Decimal('50.00'))
        line2 = MagicMock(line_total=Decimal('25.50'))
        pr.lines = [line1, line2]
        pr.calculate_totals()
        assert pr.total_amount == Decimal('75.50')
        assert pr.amount_aed == Decimal('277.085')

    def test_calculate_totals_uses_refund_amount(self):
        pr = ProductReturn()
        pr.exchange_rate = Decimal('1')
        pr.refund_amount = Decimal('10')
        pr.lines = [MagicMock(line_total=Decimal('100'))]
        pr.calculate_totals()
        assert pr.amount_aed == Decimal('10.000')

    def test_calculate_totals_default_exchange_rate(self):
        pr = ProductReturn()
        pr.exchange_rate = None
        pr.refund_amount = Decimal('5')
        pr.lines = []
        pr.calculate_totals()
        assert pr.total_amount == Decimal('0')
        assert pr.amount_aed == Decimal('5.000')

    def test_repr(self):
        pr = ProductReturn()
        pr.return_number = 'RET-1'
        assert 'RET-1' in repr(pr)


class TestProductReturnLineModel:
    def test_repr(self):
        line = ProductReturnLine()
        line.product_id = 9
        line.quantity = Decimal('2')
        assert '9' in repr(line)
