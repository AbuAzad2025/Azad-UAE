"""Payment and Receipt models — confirmation, rejection, display helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _payment_stub(**kwargs):
    from models.payment import Payment

    class Stub:
        id = kwargs.get('id', 1)
        payment_number = kwargs.get('payment_number', 'PAY-1')
        payment_type = kwargs.get('payment_type', 'sale_payment')
        payment_method = kwargs.get('payment_method', 'cash')
        payment_confirmed = kwargs.get('payment_confirmed', True)
        rejection_reason = kwargs.get('rejection_reason')
        direction = kwargs.get('direction', 'incoming')
        amount = kwargs.get('amount', Decimal('100'))
        amount_aed = kwargs.get('amount_aed', Decimal('100'))
        currency = kwargs.get('currency', 'AED')
        payment_date = kwargs.get('payment_date', datetime.now(timezone.utc))
        cheque_id = kwargs.get('cheque_id')
        sale = kwargs.get('sale')
        sale_id = kwargs.get('sale_id')

        base_amount = Payment.base_amount
        get_method_display = Payment.get_method_display
        confirm_payment = Payment.confirm_payment
        reject_payment = Payment.reject_payment
        is_pending = Payment.is_pending
        status_ar = Payment.status_ar
        direction_ar = Payment.direction_ar
        to_dict = Payment.to_dict
        __repr__ = Payment.__repr__

    return Stub()


def _receipt_stub(**kwargs):
    from models.payment import Receipt

    class Stub:
        id = kwargs.get('id', 1)
        receipt_number = kwargs.get('receipt_number', 'RCPT-1')
        payment_method = kwargs.get('payment_method', 'cheque')
        payment_confirmed = kwargs.get('payment_confirmed', False)
        rejection_reason = kwargs.get('rejection_reason')
        direction = kwargs.get('direction', 'incoming')
        source_type = kwargs.get('source_type', 'sale')
        source_id = kwargs.get('source_id', 10)
        amount = kwargs.get('amount', Decimal('200'))
        amount_aed = kwargs.get('amount_aed', Decimal('200'))
        currency = kwargs.get('currency', 'AED')
        receipt_date = kwargs.get('receipt_date', datetime.now(timezone.utc))
        cheque_id = kwargs.get('cheque_id', 5)
        customer = kwargs.get('customer', SimpleNamespace(name='Customer'))

        base_amount = Receipt.base_amount
        get_method_display = Receipt.get_method_display
        confirm_receipt = Receipt.confirm_receipt
        reject_receipt = Receipt.reject_receipt
        is_pending = Receipt.is_pending
        status_ar = Receipt.status_ar
        source_type_ar = Receipt.source_type_ar
        direction_ar = Receipt.direction_ar
        get_source_info = Receipt.get_source_info
        to_dict = Receipt.to_dict
        __repr__ = Receipt.__repr__

    return Stub()


class TestPayment:
    def test_repr(self):
        assert 'PAY-1' in repr(_payment_stub())

    def test_base_amount_alias(self):
        p = _payment_stub(amount_aed=Decimal('50'))
        assert p.base_amount == Decimal('50')
        p.base_amount = Decimal('60')
        assert p.amount_aed == Decimal('60')

    def test_get_method_display(self):
        assert _payment_stub(payment_method='cash').get_method_display() == 'نقدي'
        assert _payment_stub(payment_method='unknown_x').get_method_display('en') == 'unknown_x'

    def test_confirm_payment_updates_sale(self):
        sale = MagicMock()
        p = _payment_stub(payment_confirmed=False, sale=sale)
        p.confirm_payment()
        assert p.payment_confirmed is True
        assert p.confirmation_date is not None
        sale.recalculate_payment_status.assert_called_once()

    def test_reject_payment(self):
        sale = MagicMock()
        p = _payment_stub(payment_confirmed=True, sale=sale)
        p.reject_payment('bounced')
        assert p.payment_confirmed is False
        assert p.rejection_reason == 'bounced'
        sale.recalculate_payment_status.assert_called_once()

    def test_is_pending_and_status_ar(self):
        assert _payment_stub(payment_confirmed=False).is_pending is True
        assert _payment_stub(payment_confirmed=True).status_ar == 'مؤكدة'
        assert _payment_stub(payment_confirmed=False, rejection_reason='x').status_ar == 'مرفوضة'

    def test_direction_ar(self):
        assert _payment_stub(direction='incoming').direction_ar == 'وارد'

    def test_get_method_display_en(self):
        assert _payment_stub(payment_method='card').get_method_display('en') == 'Card'

    def test_reject_payment_without_sale(self):
        p = _payment_stub(payment_confirmed=True, sale=None)
        p.reject_payment('nsf')
        assert p.payment_confirmed is False

    def test_to_dict(self):
        data = _payment_stub().to_dict()
        assert data['payment_number'] == 'PAY-1'
        assert data['status_ar'] == 'مؤكدة'


class TestReceipt:
    def test_base_amount_alias(self):
        r = _receipt_stub(amount_aed=Decimal('75'))
        assert r.base_amount == Decimal('75')
        r.base_amount = Decimal('80')
        assert r.amount_aed == Decimal('80')

    def test_direction_and_pending_labels(self):
        r = _receipt_stub(payment_confirmed=False, direction='outgoing')
        assert r.is_pending is True
        assert r.direction_ar == 'صادر'

    def test_source_type_unknown(self):
        assert _receipt_stub(source_type='custom').source_type_ar == 'غير محدد'

    def test_repr(self):
        assert 'RCPT-1' in repr(_receipt_stub())

    def test_confirm_receipt(self):
        r = _receipt_stub(payment_confirmed=False)
        r.confirm_receipt()
        assert r.payment_confirmed is True

    def test_get_method_display(self):
        assert _receipt_stub(payment_method='cash').get_method_display() == 'نقدي'

    def test_reject_receipt_reverses_linked_payments(self, mocker):
        sale = MagicMock()
        linked = MagicMock(
            payment_confirmed=True,
            sale_id=1,
            sale=sale,
        )
        mock_payment = mocker.patch('models.payment.Payment')
        mock_payment.query.filter.return_value.all.return_value = [linked]
        r = _receipt_stub(payment_confirmed=True)
        r.reject_receipt('returned')
        assert linked.payment_confirmed is False
        assert linked.rejection_reason == 'returned'
        sale.recalculate_payment_status.assert_called_once()

    def test_status_and_source_labels(self):
        r = _receipt_stub(payment_confirmed=False)
        assert r.status_ar == 'معلق'
        assert r.source_type_ar == 'مبيعات'

    def test_get_source_info_sale(self, mocker):
        sale = MagicMock(
            sale_number='S-100',
            sale_date=datetime(2025, 1, 1),
            total_amount=Decimal('500'),
        )
        mocker.patch('models.payment.db.session.get', return_value=sale)
        info = _receipt_stub(source_type='sale', source_id=10).get_source_info()
        assert info['number'] == 'S-100'

    def test_get_source_info_none(self):
        assert _receipt_stub(source_type='manual', source_id=None).get_source_info() is None

    def test_status_rejected(self):
        r = _receipt_stub(payment_confirmed=False, rejection_reason='bounced')
        assert r.status_ar == 'مرفوض'

    def test_to_dict(self):
        data = _receipt_stub().to_dict()
        assert data['receipt_number'] == 'RCPT-1'
        assert data['customer'] == 'Customer'
