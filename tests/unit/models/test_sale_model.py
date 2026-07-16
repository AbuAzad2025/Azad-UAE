from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch


def _line(qty='2', price='50', discount='0', cost='30'):
    line = MagicMock()
    line.line_total = Decimal(qty) * Decimal(price)
    line.quantity = Decimal(qty)
    line.unit_price = Decimal(price)
    line.discount_percent = Decimal(discount)
    line.cost_price = Decimal(cost)
    line.get_profit.return_value = Decimal('40')
    line.product = MagicMock(name='Widget')
    line.to_dict.return_value = {'id': 1}
    return line


class TestSaleProperties:
    def test_amount_base_getters(self):
        from models.sale import Sale

        sale = Sale()
        sale.amount_aed = Decimal('200')
        sale.paid_amount_aed = Decimal('80')
        assert sale.amount_base == Decimal('200')
        assert sale.paid_amount_base == Decimal('80')
        assert sale.base_amount == Decimal('200')

    def test_repr(self):
        from models.sale import Sale

        sale = Sale(sale_number='S-99')
        assert 'S-99' in repr(sale)

    def test_amount_base_setters(self):
        from models.sale import Sale

        sale = Sale()
        sale.amount_base = Decimal('150')
        assert sale.amount_aed == Decimal('150')
        sale.paid_amount_base = Decimal('75')
        assert sale.paid_amount_aed == Decimal('75')
        sale.base_amount = Decimal('300')
        assert sale.amount_aed == Decimal('300')

    def test_balance_due_aliases(self):
        from models.sale import Sale

        sale = Sale()
        sale.balance_due = Decimal('25')
        assert sale.balance_due_base == Decimal('25')
        assert sale.balance_due_aed == Decimal('25')


class TestSaleCalculateTotals:
    def test_exclusive_vat(self):
        from models.sale import Sale

        sale = Sale()
        sale.prices_include_vat = False
        sale.discount_amount = Decimal('0')
        sale.shipping_cost = Decimal('0')
        sale.tax_rate = Decimal('5')
        sale.currency = 'AED'
        sale.exchange_rate = Decimal('1')
        sale.tenant_id = 1
        sale.paid_amount = Decimal('0')
        sale.lines = [_line()]
        with patch('utils.currency_utils.resolve_tenant_base_currency', return_value='AED'):
            sale.calculate_totals()
        assert sale.total_amount > sale.subtotal
        assert sale.tax_amount > Decimal('0')

    def test_inclusive_vat(self):
        from models.sale import Sale

        sale = Sale()
        sale.prices_include_vat = True
        sale.discount_amount = Decimal('0')
        sale.shipping_cost = Decimal('0')
        sale.tax_rate = Decimal('5')
        sale.currency = 'AED'
        sale.exchange_rate = Decimal('1')
        sale.tenant_id = 1
        sale.paid_amount = Decimal('0')
        sale.lines = [_line()]
        with patch('utils.currency_utils.resolve_tenant_base_currency', return_value='AED'):
            sale.calculate_totals()
        assert sale.tax_amount >= Decimal('0')

    def test_inclusive_vat_zero_rate(self):
        from models.sale import Sale

        sale = Sale()
        sale.prices_include_vat = True
        sale.tax_rate = Decimal('0')
        sale.currency = 'AED'
        sale.exchange_rate = Decimal('1')
        sale.tenant_id = 1
        sale.paid_amount = Decimal('0')
        sale.discount_amount = Decimal('0')
        sale.shipping_cost = Decimal('0')
        sale.lines = [_line()]
        with patch('utils.currency_utils.resolve_tenant_base_currency', return_value='AED'):
            sale.calculate_totals()
        assert sale.tax_amount == Decimal('0')

    def test_foreign_currency_conversion(self):
        from models.sale import Sale

        sale = Sale()
        sale.prices_include_vat = False
        sale.tax_rate = Decimal('0')
        sale.currency = 'USD'
        sale.exchange_rate = Decimal('3.67')
        sale.tenant_id = 1
        sale.paid_amount = Decimal('0')
        sale.discount_amount = Decimal('0')
        sale.shipping_cost = Decimal('0')
        sale.lines = [_line()]
        with patch('utils.currency_utils.resolve_tenant_base_currency', return_value='AED'):
            sale.calculate_totals()
        assert sale.amount_aed != sale.total_amount


class TestSalePaymentStatus:
    @staticmethod
    def _payment(amount, confirmed=True, method='cash'):
        p = MagicMock()
        p.payment_confirmed = confirmed
        p.payment_method = method
        p.amount_aed = Decimal(str(amount))
        return p

    def test_recalculate_paid(self):
        from models.sale import Sale

        sale = Sale()
        sale.amount_aed = Decimal('100')
        sale.currency = 'AED'
        sale.exchange_rate = Decimal('1')
        sale.tenant_id = 1
        sale.payments = [self._payment(100)]
        sale.returns = []
        with patch('utils.currency_utils.resolve_tenant_base_currency', return_value='AED'):
            sale.recalculate_payment_status()
        assert sale.payment_status == 'paid'
        assert sale.balance_due == Decimal('0')

    def test_recalculate_overpayment_keeps_negative_balance(self):
        from models.sale import Sale

        sale = Sale()
        sale.amount_aed = Decimal('100')
        sale.currency = 'AED'
        sale.exchange_rate = Decimal('1')
        sale.tenant_id = 1
        sale.payments = [self._payment(150)]
        sale.returns = []
        with patch('utils.currency_utils.resolve_tenant_base_currency', return_value='AED'):
            sale.recalculate_payment_status()
        assert sale.payment_status == 'paid'
        assert sale.balance_due < Decimal('0')

        from models.sale import Sale

        sale = Sale()
        sale.amount_aed = Decimal('100')
        sale.currency = 'AED'
        sale.exchange_rate = Decimal('1')
        sale.tenant_id = 1
        sale.payments = [self._payment(40)]
        sale.returns = []
        with patch('utils.currency_utils.resolve_tenant_base_currency', return_value='AED'):
            sale.recalculate_payment_status()
        assert sale.payment_status == 'partial'

    def test_recalculate_pending_cheque(self):
        from models.sale import Sale

        sale = Sale()
        sale.amount_aed = Decimal('100')
        sale.currency = 'AED'
        sale.exchange_rate = Decimal('1')
        sale.tenant_id = 1
        sale.payments = [self._payment(50, confirmed=False, method='cheque')]
        sale.returns = []
        with patch('utils.currency_utils.resolve_tenant_base_currency', return_value='AED'):
            sale.recalculate_payment_status()
        assert sale.payment_status == 'pending_cheque'

    def test_recalculate_with_returns(self):
        from models.sale import Sale

        sale = Sale()
        sale.amount_aed = Decimal('100')
        sale.currency = 'AED'
        sale.exchange_rate = Decimal('1')
        sale.tenant_id = 1
        sale.payments = []
        ret = MagicMock(status='approved', amount_aed=Decimal('20'))
        sale.returns = [ret]
        with patch('utils.currency_utils.resolve_tenant_base_currency', return_value='AED'):
            sale.recalculate_payment_status()
        assert sale.payment_status == 'partial'

    def test_recalculate_currency_exception_fallback(self):
        from models.sale import Sale

        sale = Sale()
        sale.amount_aed = Decimal('100')
        sale.currency = 'USD'
        sale.exchange_rate = Decimal('1')
        sale.tenant_id = 1
        sale.paid_amount = None
        sale.payments = [self._payment(10)]
        sale.returns = []
        with patch('utils.currency_utils.resolve_tenant_base_currency', side_effect=RuntimeError('fail')):
            sale.recalculate_payment_status()
        assert sale.paid_amount is not None

    def test_pending_cheques_amount(self):
        from models.sale import Sale

        sale = Sale()
        sale.payments = [self._payment(30, confirmed=False, method='cheque')]
        assert sale.pending_cheques_amount == Decimal('30')

    def test_confirmed_payments_amount(self):
        from models.sale import Sale

        sale = Sale()
        sale.payments = [self._payment(75)]
        assert sale.confirmed_payments_amount == Decimal('75')

    def test_pending_cheques_amount_exception(self):
        from models.sale import Sale

        bad = MagicMock(payment_confirmed=False, payment_method='cheque')
        type(bad).amount_aed = property(lambda _self: (_ for _ in ()).throw(RuntimeError('bad')))
        sale = Sale()
        sale.payments = [bad]
        assert sale.pending_cheques_amount == Decimal('0')

    def test_confirmed_payments_amount_exception(self):
        from models.sale import Sale

        bad = MagicMock(payment_confirmed=True)
        type(bad).amount_aed = property(lambda _self: (_ for _ in ()).throw(RuntimeError('bad')))
        sale = Sale()
        sale.payments = [bad]
        assert sale.confirmed_payments_amount == Decimal('0')


class TestSaleHelpers:
    def test_get_profit_empty_lines(self):
        from models.sale import Sale

        sale = Sale()
        sale.lines = []
        assert sale.get_profit() == Decimal('0')

    def test_get_profit_with_lines(self):
        from models.sale import Sale

        sale = Sale()
        sale.lines = [_line()]
        assert sale.get_profit() == Decimal('40')

    def test_to_dict(self):
        from models.sale import Sale

        sale = Sale()
        sale.id = 1
        sale.sale_number = 'S-001'
        sale.customer = MagicMock(name='Ali')
        sale.seller = MagicMock(username='seller')
        sale.sale_date = datetime(2025, 6, 1, tzinfo=timezone.utc)
        sale.total_amount = Decimal('100')
        sale.paid_amount = Decimal('50')
        sale.balance_due = Decimal('50')
        sale.currency = 'AED'
        sale.payment_status = 'partial'
        sale.status = 'confirmed'
        sale.lines = [_line()]
        data = sale.to_dict(include_lines=True, include_cost=True)
        assert data['sale_number'] == 'S-001'
        assert 'lines' in data
        assert 'profit' in data


class TestSaleLine:
    def test_repr(self):
        from models.sale import SaleLine

        line = SaleLine(product_id=7, quantity=Decimal('3'))
        assert '7' in repr(line)

    def test_calculate_line_total(self):
        from models.sale import SaleLine

        line = SaleLine()
        line.quantity = Decimal('2')
        line.unit_price = Decimal('50')
        line.discount_percent = Decimal('10')
        line.calculate_line_total()
        assert line.line_total == Decimal('90.000')

    def test_get_profit(self):
        from models.sale import SaleLine

        line = SaleLine()
        line.quantity = Decimal('2')
        line.unit_price = Decimal('50')
        line.cost_price = Decimal('30')
        line.discount_percent = Decimal('0')
        assert line.get_profit() == Decimal('40.000')

    def test_to_dict_with_cost(self):
        from models.sale import SaleLine

        line = SaleLine()
        line.id = 1
        line.product = MagicMock(name='Part')
        line.quantity = Decimal('1')
        line.unit_price = Decimal('10')
        line.discount_percent = Decimal('0')
        line.line_total = Decimal('10')
        line.cost_price = Decimal('5')
        data = line.to_dict(include_cost=True)
        assert 'profit' in data
