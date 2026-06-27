"""Cheque model — status, archive, queries, tenant-scoped statistics."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _cheque_stub(**kwargs):
    from models.cheque import Cheque

    class Stub:
        id = kwargs.get('id', 1)
        cheque_number = kwargs.get('cheque_number', 'CHQ-001')
        cheque_bank_number = kwargs.get('cheque_bank_number', 'BNK-001')
        bank_name = kwargs.get('bank_name', 'Bank')
        cheque_type = kwargs.get('cheque_type', 'incoming')
        status = kwargs.get('status', 'pending')
        due_date = kwargs.get('due_date', date.today() + timedelta(days=5))
        days_until_due = kwargs.get('days_until_due')
        is_overdue = kwargs.get('is_overdue', False)
        is_active = kwargs.get('is_active', True)
        amount = kwargs.get('amount', Decimal('1000'))
        amount_aed = kwargs.get('amount_aed', Decimal('1000'))
        exchange_rate = kwargs.get('exchange_rate', Decimal('1'))
        clearance_exchange_rate = kwargs.get('clearance_exchange_rate')
        actual_amount_aed = kwargs.get('actual_amount_aed')
        currency_gain_loss = kwargs.get('currency_gain_loss', Decimal('0'))
        currency = kwargs.get('currency', 'AED')
        issue_date = kwargs.get('issue_date', date.today())
        clearance_date = kwargs.get('clearance_date')
        drawer_name = kwargs.get('drawer_name', 'Drawer')
        payee_name = kwargs.get('payee_name', 'Payee')
        customer_id = kwargs.get('customer_id', 1)
        supplier_id = kwargs.get('supplier_id')
        archived_at = kwargs.get('archived_at')
        archive_reason = kwargs.get('archive_reason')

        cheque_type_ar = Cheque.cheque_type_ar
        base_amount = Cheque.base_amount
        actual_base_amount = Cheque.actual_base_amount
        is_due_soon = Cheque.is_due_soon
        status_ar = Cheque.status_ar
        is_confirmed = Cheque.is_confirmed
        is_pending = Cheque.is_pending
        update_status_based_on_date = Cheque.update_status_based_on_date
        archive = Cheque.archive
        restore = Cheque.restore
        to_dict = Cheque.to_dict
        __repr__ = Cheque.__repr__

    stub = Stub()
    if kwargs.get('set_base_amount') is not None:
        stub.base_amount = kwargs['set_base_amount']
    if kwargs.get('set_actual_base') is not None:
        stub.actual_base_amount = kwargs['set_actual_base']
    return stub


class TestChequeProperties:
    def test_repr(self):
        c = _cheque_stub()
        assert 'CHQ-001' in repr(c)

    def test_cheque_type_ar_mapping(self):
        assert _cheque_stub(cheque_type='incoming').cheque_type_ar == 'وارد'
        assert _cheque_stub(cheque_type='outgoing').cheque_type_ar == 'صادر'
        assert _cheque_stub(cheque_type='other').cheque_type_ar == 'other'

    def test_base_amount_aliases(self):
        c = _cheque_stub(amount_aed=Decimal('500'))
        assert c.base_amount == Decimal('500')
        c.base_amount = Decimal('750')
        assert c.amount_aed == Decimal('750')

    def test_actual_base_amount_aliases(self):
        c = _cheque_stub(actual_amount_aed=Decimal('400'))
        assert c.actual_base_amount == Decimal('400')
        c.actual_base_amount = Decimal('450')
        assert c.actual_amount_aed == Decimal('450')

    def test_status_ar_and_flags(self):
        c = _cheque_stub(status='cleared')
        assert c.status_ar == 'مصروف'
        assert c.is_confirmed is True
        assert c.is_pending is False

    def test_is_pending_statuses(self):
        for status in ('pending', 'deposited', 'under_collection'):
            assert _cheque_stub(status=status).is_pending is True

    def test_is_due_soon(self):
        assert _cheque_stub(days_until_due=3).is_due_soon is True
        assert _cheque_stub(days_until_due=10).is_due_soon is False
        assert _cheque_stub(days_until_due=None).is_due_soon is False

    def test_update_status_skips_terminal(self):
        c = _cheque_stub(status='cleared', due_date=date.today() - timedelta(days=1))
        c.update_status_based_on_date()
        assert c.is_overdue is False

    def test_update_status_overdue(self):
        c = _cheque_stub(status='pending', due_date=date.today() - timedelta(days=2))
        c.update_status_based_on_date()
        assert c.is_overdue is True
        assert c.days_until_due < 0

    def test_update_status_not_overdue(self):
        c = _cheque_stub(status='pending', due_date=date.today() + timedelta(days=3))
        c.update_status_based_on_date()
        assert c.is_overdue is False

    def test_archive_and_restore(self):
        c = _cheque_stub()
        c.archive('retired')
        assert c.is_active is False
        assert c.archive_reason == 'retired'
        c.restore()
        assert c.is_active is True
        assert c.archived_at is None

    def test_to_dict(self):
        c = _cheque_stub(
            due_date=date(2025, 6, 1),
            issue_date=date(2025, 5, 1),
            days_until_due=5,
        )
        data = c.to_dict()
        assert data['cheque_number'] == 'CHQ-001'
        assert data['type_ar'] == 'وارد'
        assert data['is_due_soon'] is True


class TestChequeQueries:
    def _mock_query(self, mocker, all_rows=None, count_val=0, scalar_val=Decimal('0')):
        from models import cheque as cheque_mod

        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = all_rows or []
        q.count.return_value = count_val
        mocker.patch.object(cheque_mod.Cheque, 'query', q)
        return q

    def test_get_incoming_cheques_scoped(self, mocker):
        row = SimpleNamespace(due_date=date.today())
        q = self._mock_query(mocker, all_rows=[row])
        from models.cheque import Cheque

        result = Cheque.get_incoming_cheques(tenant_id=1, customer_id=2, status='pending')
        assert result == [row]
        q.filter_by.assert_any_call(cheque_type='incoming', is_active=True)

    def test_get_outgoing_cheques(self, mocker):
        q = self._mock_query(mocker, all_rows=[])
        from models.cheque import Cheque

        Cheque.get_outgoing_cheques(tenant_id=3, supplier_id=4, status='pending')
        q.filter_by.assert_any_call(supplier_id=4)

    def test_update_all_statuses(self, mocker):
        pending = _cheque_stub(status='pending', due_date=date.today() + timedelta(days=1))
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.all.return_value = [pending]
        mocker.patch('models.cheque.Cheque.query', q)
        from models.cheque import Cheque

        Cheque.update_all_statuses(tenant_id=1, branch_id=2)
        assert pending.days_until_due is not None

    def test_get_statistics(self, mocker):
        from models import cheque as cheque_mod

        base_q = MagicMock()
        base_q.filter_by.return_value = base_q
        base_q.filter.return_value = base_q
        base_q.count.side_effect = [2, 1, 1, 0, 0, 0, 0]
        mocker.patch.object(cheque_mod.Cheque, 'query', base_q)

        amount_q = MagicMock()
        amount_q.filter_by.return_value = amount_q
        amount_q.filter.return_value = amount_q
        amount_q.scalar.side_effect = [Decimal('1500'), Decimal('800')]
        mocker.patch('models.cheque.db.session.query', return_value=amount_q)

        from models.cheque import Cheque

        stats = Cheque.get_statistics(tenant_id=1, branch_id=3)
        assert stats['total_incoming'] == 2
        assert stats['incoming_amount'] == 1500.0
        assert stats['bounced'] == 0

    def test_get_due_soon_filters_branch(self, mocker):
        mocker.patch('models.cheque.Cheque.update_all_statuses')
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = []
        mocker.patch('models.cheque.Cheque.query', q)
        from models.cheque import Cheque
        Cheque.get_due_soon_cheques(tenant_id=1, branch_id=9)
        assert q.filter.called

    def test_get_overdue_filters_branch(self, mocker):
        mocker.patch('models.cheque.Cheque.update_all_statuses')
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = []
        mocker.patch('models.cheque.Cheque.query', q)
        from models.cheque import Cheque
        Cheque.get_overdue_cheques(branch_id=9)
        assert q.filter.called
