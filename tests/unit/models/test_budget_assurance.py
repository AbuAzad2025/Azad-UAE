"""Budget and BudgetLine models — actuals, activation, variance helpers."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.budget import Budget, BudgetLine


class _Col:
    def __eq__(self, other):
        return self

    def between(self, a, b):
        return self


@pytest.fixture
def mock_gl_columns(monkeypatch):
    from models import GLJournalLine, GLJournalEntry

    monkeypatch.setattr(GLJournalLine, 'debit', _Col())
    monkeypatch.setattr(GLJournalLine, 'credit', _Col())
    monkeypatch.setattr(GLJournalLine, 'account_id', _Col())
    monkeypatch.setattr(GLJournalEntry, 'entry_date', _Col())
    monkeypatch.setattr(GLJournalEntry, 'tenant_id', _Col())
    monkeypatch.setattr(GLJournalEntry, 'branch_id', _Col())


def _budget(**kwargs):
    b = Budget(
        tenant_id=kwargs.get('tenant_id', 1),
        budget_number=kwargs.get('budget_number', 'BUD-2025'),
        name_ar=kwargs.get('name_ar', 'موازنة'),
        fiscal_year=kwargs.get('fiscal_year', 2025),
        period_start=kwargs.get('period_start', date(2025, 1, 1)),
        period_end=kwargs.get('period_end', date(2025, 12, 31)),
        total_budgeted=kwargs.get('total_budgeted', Decimal('1000')),
        status=kwargs.get('status', 'draft'),
        branch_id=kwargs.get('branch_id'),
    )
    b.lines = kwargs.get('lines', [])
    return b


def _line(account_type='expense', budgeted=Decimal('100')):
    account = SimpleNamespace(type=account_type, code='6100')
    line = BudgetLine(
        tenant_id=1,
        budget_id=1,
        account_id=10,
        budgeted_amount=budgeted,
    )
    line.account = account
    return line


class TestBudgetProperties:
    def test_repr(self):
        assert 'BUD-2025' in repr(_budget())

    @pytest.mark.parametrize('status,label', [
        ('draft', 'مسودة'),
        ('active', 'نشطة'),
        ('closed', 'مغلقة'),
        ('custom', 'custom'),
    ])
    def test_status_ar(self, status, label):
        assert _budget(status=status).status_ar == label

    @pytest.mark.parametrize('period,label', [
        ('annual', 'سنوية'),
        ('quarterly', 'ربع سنوية'),
        ('monthly', 'شهرية'),
        ('custom', 'custom'),
    ])
    def test_period_type_ar(self, period, label):
        b = _budget()
        b.period_type = period
        assert b.period_type_ar == label


class TestBudgetUpdateActuals:
    def test_update_actuals_expense_account(self, mocker, mock_gl_columns, mock_db):
        budget = _budget(lines=[_line('expense', Decimal('200'))])
        debit_q = MagicMock()
        debit_q.filter.return_value.join.return_value.filter.return_value.scalar.return_value = Decimal('150')
        credit_q = MagicMock()
        credit_q.filter.return_value.join.return_value.filter.return_value.scalar.return_value = Decimal('50')
        mocker.patch('models.budget.db.session.query', side_effect=[debit_q, credit_q])
        budget.update_actuals()
        line = budget.lines[0]
        assert line.actual_amount == Decimal('100')
        assert line.variance == Decimal('-100')
        assert line.variance_percentage == Decimal('-50')
        assert budget.total_actual == Decimal('100')
        mock_db.commit.assert_called_once()

    def test_update_actuals_revenue_account(self, mocker, mock_gl_columns, mock_db):
        budget = _budget(lines=[_line('revenue', Decimal('500'))])
        debit_q = MagicMock()
        debit_q.filter.return_value.join.return_value.filter.return_value.scalar.return_value = Decimal('100')
        credit_q = MagicMock()
        credit_q.filter.return_value.join.return_value.filter.return_value.scalar.return_value = Decimal('400')
        mocker.patch('models.budget.db.session.query', side_effect=[debit_q, credit_q])
        budget.update_actuals()
        assert budget.lines[0].actual_amount == Decimal('300')

    def test_update_actuals_zero_budgeted_variance_pct(self, mocker, mock_gl_columns, mock_db):
        budget = _budget(total_budgeted=Decimal('0'), lines=[_line('expense', Decimal('0'))])
        debit_q = MagicMock()
        debit_q.filter.return_value.join.return_value.filter.return_value.scalar.return_value = Decimal('10')
        credit_q = MagicMock()
        credit_q.filter.return_value.join.return_value.filter.return_value.scalar.return_value = Decimal('0')
        mocker.patch('models.budget.db.session.query', side_effect=[debit_q, credit_q])
        budget.update_actuals()
        assert budget.lines[0].variance_percentage == 0

    def test_update_actuals_asset_account(self, mocker, mock_gl_columns, mock_db):
        budget = _budget(lines=[_line('asset', Decimal('100'))])
        debit_q = MagicMock()
        debit_filter = debit_q.filter.return_value.join.return_value.filter
        debit_filter.return_value.scalar.return_value = Decimal('0')
        credit_q = MagicMock()
        credit_filter = credit_q.filter.return_value.join.return_value.filter
        credit_filter.return_value.scalar.return_value = Decimal('0')
        mocker.patch('models.budget.db.session.query', side_effect=[debit_q, credit_q])
        budget.update_actuals()
        assert budget.lines[0].actual_amount == Decimal('0')

    def test_update_actuals_scopes_tenant_and_branch(self, mocker, mock_gl_columns, mock_db):
        budget = _budget(branch_id=7, lines=[_line('liability', Decimal('100'))])
        debit_q = MagicMock()
        debit_filter = debit_q.filter.return_value.join.return_value.filter
        debit_filter.return_value.scalar.return_value = Decimal('0')
        credit_q = MagicMock()
        credit_filter = credit_q.filter.return_value.join.return_value.filter
        credit_filter.return_value.scalar.return_value = Decimal('0')
        mocker.patch('models.budget.db.session.query', side_effect=[debit_q, credit_q])
        budget.update_actuals()
        assert debit_filter.call_count == 1
        assert credit_filter.call_count == 1

    def test_update_actuals_sets_budget_variance_percentage(self, mocker, mock_gl_columns, mock_db):
        budget = _budget(total_budgeted=Decimal('200'), lines=[_line('expense', Decimal('200'))])
        debit_q = MagicMock()
        debit_q.filter.return_value.join.return_value.filter.return_value.scalar.return_value = Decimal('100')
        credit_q = MagicMock()
        credit_q.filter.return_value.join.return_value.filter.return_value.scalar.return_value = Decimal('0')
        mocker.patch('models.budget.db.session.query', side_effect=[debit_q, credit_q])
        budget.update_actuals()
        assert budget.variance_percentage == Decimal('-50')


class TestBudgetLifecycle:
    def test_activate_from_draft(self, mock_db):
        budget = _budget(status='draft')
        budget.activate()
        assert budget.status == 'active'
        mock_db.commit.assert_called_once()

    def test_activate_rejects_non_draft(self, mock_db):
        budget = _budget(status='active')
        with pytest.raises(ValueError, match='نشطة مسبقاً'):
            budget.activate()
        mock_db.commit.assert_not_called()

    def test_close_from_active(self, mocker, mock_gl_columns, mock_db):
        budget = _budget(status='active', lines=[])
        mocker.patch.object(budget, 'update_actuals')
        budget.close()
        budget.update_actuals.assert_called_once()
        assert budget.status == 'closed'
        mock_db.commit.assert_called_once()

    def test_close_rejects_non_active(self, mock_db):
        budget = _budget(status='draft')
        with pytest.raises(ValueError, match='نشطة'):
            budget.close()


class TestBudgetLine:
    def test_repr(self):
        line = _line()
        assert '6100' in repr(line)

    @pytest.mark.parametrize('variance_pct,status', [
        (Decimal('2'), 'good'),
        (Decimal('10'), 'warning'),
        (Decimal('20'), 'danger'),
        (Decimal('-20'), 'danger'),
    ])
    def test_variance_status(self, variance_pct, status):
        line = _line()
        line.variance_percentage = variance_pct
        assert line.variance_status == status

    @pytest.mark.parametrize('variance_pct,label', [
        (Decimal('2'), 'ممتاز'),
        (Decimal('10'), 'يحتاج متابعة'),
        (Decimal('20'), 'انحراف كبير'),
    ])
    def test_variance_status_ar(self, variance_pct, label):
        line = _line()
        line.variance_percentage = variance_pct
        assert line.variance_status_ar == label
