"""Cheque model — status, archive, queries, tenant-scoped statistics."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest_plugins = ['tests.unit.conftest']

import models.cheque as cheque_mod
from models.cheque import Cheque

_GET_INCOMING = Cheque.get_incoming_cheques
_GET_OUTGOING = Cheque.get_outgoing_cheques
_GET_DUE_SOON = Cheque.get_due_soon_cheques
_GET_OVERDUE = Cheque.get_overdue_cheques
_UPDATE_ALL = Cheque.update_all_statuses
_GET_STATS = Cheque.get_statistics

_COL_DUE_DATE = Cheque.due_date
_COL_DAYS_UNTIL_DUE = Cheque.days_until_due
_COL_TENANT_ID = Cheque.tenant_id
_COL_BRANCH_ID = Cheque.branch_id
_COL_AMOUNT_AED = Cheque.amount_aed
_COL_IS_OVERDUE = Cheque.is_overdue
_COL_IS_ACTIVE = Cheque.is_active
_COL_STATUS = Cheque.status


@pytest.fixture(autouse=True)
def _autouse_mock_db(mock_db):
    pass


def _cheque_stub(**kwargs):
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
    def _fake_cheque_cls(self, query):
        return SimpleNamespace(
            query=query,
            due_date=_COL_DUE_DATE,
            tenant_id=_COL_TENANT_ID,
            branch_id=_COL_BRANCH_ID,
            days_until_due=_COL_DAYS_UNTIL_DUE,
            is_overdue=_COL_IS_OVERDUE,
            is_active=_COL_IS_ACTIVE,
            status=_COL_STATUS,
            amount_aed=_COL_AMOUNT_AED,
        )

    def test_get_incoming_cheques_scoped(self, mocker, mock_db):
        row = SimpleNamespace(due_date=date.today())
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = [row]
        mocker.patch.object(cheque_mod, 'Cheque', self._fake_cheque_cls(q))

        result = _GET_INCOMING(tenant_id=1, customer_id=2, status='pending')
        assert result == [row]
        q.filter_by.assert_any_call(cheque_type='incoming', is_active=True)

    def test_get_outgoing_cheques(self, mocker, mock_db):
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = []
        mocker.patch.object(cheque_mod, 'Cheque', self._fake_cheque_cls(q))

        _GET_OUTGOING(tenant_id=3, supplier_id=4, status='pending')
        q.filter_by.assert_any_call(supplier_id=4)

    def test_update_all_statuses(self, mocker, mock_db):
        pending = _cheque_stub(status='pending', due_date=date.today() + timedelta(days=1))
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        q.all.return_value = [pending]
        mocker.patch.object(cheque_mod, 'Cheque', self._fake_cheque_cls(q))

        _UPDATE_ALL(tenant_id=1, branch_id=2)
        assert pending.days_until_due is not None

    def test_get_statistics(self, mocker, mock_db):
        base_q = MagicMock()
        base_q.filter_by.return_value = base_q
        base_q.filter.return_value = base_q
        base_q.count.side_effect = [2, 1, 1, 0, 0, 0, 0]
        mocker.patch.object(cheque_mod, 'Cheque', self._fake_cheque_cls(base_q))

        amount_q = MagicMock()
        amount_q.filter_by.return_value = amount_q
        amount_q.filter.return_value = amount_q
        amount_q.scalar.side_effect = [Decimal('1500'), Decimal('800')]
        session = MagicMock()
        session.query.return_value = amount_q
        mocker.patch.object(cheque_mod, 'db', SimpleNamespace(session=session, func=cheque_mod.db.func))

        stats = _GET_STATS(tenant_id=1, branch_id=3)
        assert stats['total_incoming'] == 2
        assert stats['incoming_amount'] == 1500.0
        assert stats['bounced'] == 0

    def test_get_due_soon_filters_branch(self, mocker, mock_db):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = []
        fake = self._fake_cheque_cls(q)
        fake.update_all_statuses = MagicMock()
        mocker.patch.object(cheque_mod, 'Cheque', fake)
        _GET_DUE_SOON(tenant_id=1, branch_id=9)
        assert q.filter.called
        fake.update_all_statuses.assert_called_once_with(tenant_id=1, branch_id=9)

    def test_get_overdue_filters_tenant(self, mocker, mock_db):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = []
        fake = self._fake_cheque_cls(q)
        fake.update_all_statuses = MagicMock()
        mocker.patch.object(cheque_mod, 'Cheque', fake)
        _GET_OVERDUE(tenant_id=1)
        assert q.filter.called

    def test_get_overdue_filters_branch(self, mocker, mock_db):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.all.return_value = []
        fake = self._fake_cheque_cls(q)
        fake.update_all_statuses = MagicMock()
        mocker.patch.object(cheque_mod, 'Cheque', fake)
        _GET_OVERDUE(branch_id=9)
        assert q.filter.called
