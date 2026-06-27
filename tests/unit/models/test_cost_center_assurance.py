from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from models.cost_center import CostCenter


class _Col:
    def __eq__(self, other):
        return self

    def between(self, a, b):
        return self

    def has(self, **kwargs):
        return self


class TestCostCenterModel:
    def test_repr(self, sample_tenant):
        cc = CostCenter(
            tenant_id=sample_tenant.id,
            code='CC01',
            name_ar='مركز',
            name_en='Center',
        )
        assert 'CC01' in repr(cc)
        assert 'مركز' in repr(cc)

    def test_full_name(self, sample_tenant):
        cc = CostCenter(tenant_id=sample_tenant.id, code='CC02', name_ar='قسم', name_en='Dept')
        assert cc.full_name == 'CC02 - قسم'

    def test_full_name_falls_back_to_en(self, sample_tenant):
        cc = CostCenter(tenant_id=sample_tenant.id, code='CC03', name_ar='', name_en='English')
        assert 'English' in cc.full_name

    @pytest.mark.parametrize('center_type,label', [
        ('department', 'قسم'),
        ('branch', 'فرع'),
        ('project', 'مشروع'),
        ('product_line', 'خط إنتاج'),
        ('custom', 'custom'),
    ])
    def test_center_type_ar(self, sample_tenant, center_type, label):
        cc = CostCenter(
            tenant_id=sample_tenant.id, code='X', name_ar='N', center_type=center_type,
        )
        assert cc.center_type_ar == label

    def test_get_performance_without_period(self, mocker, sample_tenant):
        cc = CostCenter(tenant_id=sample_tenant.id, code='P1', name_ar='Perf')
        cc.id = 10
        revenue_q = MagicMock()
        revenue_q.join.return_value.filter.return_value.scalar.return_value = Decimal('1000')
        expense_q = MagicMock()
        expense_q.join.return_value.filter.return_value.scalar.return_value = Decimal('400')
        session = mocker.patch('models.cost_center.db.session')
        session.query.side_effect = [revenue_q, expense_q]
        from models import GLJournalLine, GLJournalEntry
        GLJournalLine.credit = _Col()
        GLJournalLine.debit = _Col()
        GLJournalLine.cost_center_id = _Col()
        GLJournalLine.account = _Col()
        GLJournalEntry.entry_date = _Col()
        perf = cc.get_performance()
        assert perf['revenues'] == 1000.0
        assert perf['expenses'] == 400.0
        assert perf['profit'] == 600.0
        assert perf['margin'] == 60.0

    def test_get_performance_with_period(self, mocker, sample_tenant):
        cc = CostCenter(tenant_id=sample_tenant.id, code='P2', name_ar='Perf2')
        cc.id = 11
        revenue_q = MagicMock()
        revenue_q.join.return_value.filter.return_value.filter.return_value.scalar.return_value = Decimal('0')
        expense_q = MagicMock()
        expense_q.join.return_value.filter.return_value.filter.return_value.scalar.return_value = Decimal('50')
        session = mocker.patch('models.cost_center.db.session')
        session.query.side_effect = [revenue_q, expense_q]
        from models import GLJournalLine, GLJournalEntry
        GLJournalLine.credit = _Col()
        GLJournalLine.debit = _Col()
        GLJournalLine.cost_center_id = _Col()
        GLJournalLine.account = _Col()
        GLJournalEntry.entry_date = _Col()
        perf = cc.get_performance(period_start=date(2025, 1, 1), period_end=date(2025, 12, 31))
        assert perf['revenues'] == 0.0
        assert perf['margin'] == 0.0
