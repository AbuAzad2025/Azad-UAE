from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import models

from runtime_core.branch_repair import (
    _ensure_column,
    _ensure_index,
    _first_non_null,
    ensure_branch_isolation_schema_and_data,
)


def _inspector(columns):
    insp = MagicMock()
    insp.get_columns.return_value = [{'name': c} for c in columns]
    return insp


def _empty_query_model():
    m = MagicMock()
    m.query.filter.return_value.all.return_value = []
    m.query.all.return_value = []
    return m


@pytest.fixture
def restore_models():
    names = ['Branch', 'Warehouse', 'User', 'Sale', 'Purchase', 'Expense', 'Payment', 'Receipt', 'Cheque', 'GLJournalEntry', 'Tenant']
    saved = {n: getattr(models, n) for n in names}
    yield
    for n, v in saved.items():
        setattr(models, n, v)


class TestHelpers:
    def test_first_non_null(self):
        assert _first_non_null(None, 0, 5) == 0

    def test_first_non_null_all_none(self):
        assert _first_non_null(None, None) is None

    def test_ensure_column_skips_existing(self, mocker):
        mocker.patch('runtime_core.branch_repair.inspect', return_value=_inspector(['branch_id']))
        conn = MagicMock()
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch('runtime_core.branch_repair.db.engine.begin', return_value=ctx)
        assert _ensure_column('payments', 'branch_id', 'branch_id INTEGER') is False

    def test_ensure_column_adds_missing(self, mocker):
        mocker.patch('runtime_core.branch_repair.inspect', return_value=_inspector([]))
        conn = MagicMock()
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch('runtime_core.branch_repair.db.engine.begin', return_value=ctx)
        assert _ensure_column('payments', 'branch_id', 'branch_id INTEGER') is True

    def test_ensure_index(self, mocker):
        conn = MagicMock()
        ctx = MagicMock()
        ctx.__enter__.return_value = conn
        mocker.patch('runtime_core.branch_repair.db.engine.begin', return_value=ctx)
        _ensure_index('ix_pay', 'payments', 'branch_id')
        conn.execute.assert_called_once()


class TestEnsureBranchIsolation:
    def test_full_flow(self, app, mocker, restore_models):
        mocker.patch('runtime_core.branch_repair._ensure_column', return_value=True)
        mocker.patch('runtime_core.branch_repair._ensure_index')
        mocker.patch('utils.branching.GLOBAL_ROLE_SLUGS', set())
        mock_db = mocker.patch('runtime_core.branch_repair.db')

        main = MagicMock(id=10)
        Branch = MagicMock()
        Branch.query.filter_by.return_value.order_by.return_value.first.return_value = main
        models.Branch = Branch

        wh = MagicMock(branch_id=None)
        Warehouse = _empty_query_model()
        Warehouse.query.filter.return_value.all.return_value = [wh]
        models.Warehouse = Warehouse

        user = MagicMock(branch_id=None, is_owner=False, role=MagicMock(slug='seller'))
        User = MagicMock()
        User.query.all.return_value = [user]
        models.User = User

        sale = MagicMock(branch_id=None, warehouse=MagicMock(branch_id=3), seller=None)
        Sale = _empty_query_model()
        Sale.query.filter.return_value.all.return_value = [sale]
        models.Sale = Sale

        purchase = MagicMock(branch_id=None, warehouse=None, user=MagicMock(branch_id=4))
        Purchase = _empty_query_model()
        Purchase.query.filter.return_value.all.return_value = [purchase]
        models.Purchase = Purchase

        expense = MagicMock(branch_id=None, user=MagicMock(branch_id=5))
        Expense = _empty_query_model()
        Expense.query.filter.return_value.all.return_value = [expense]
        models.Expense = Expense

        payment = MagicMock(branch_id=None, sale=MagicMock(branch_id=6), user=None)
        Payment = _empty_query_model()
        Payment.query.filter.return_value.all.return_value = [payment]
        models.Payment = Payment

        receipt = MagicMock(branch_id=None, source_type='sale', source_id=1, user=None)
        Receipt = _empty_query_model()
        Receipt.query.filter.return_value.all.return_value = [receipt]
        models.Receipt = Receipt

        cheque = MagicMock(branch_id=None, payment_record=None, receipt_record=None, expense=MagicMock(branch_id=7))
        Cheque = _empty_query_model()
        Cheque.query.filter.return_value.all.return_value = [cheque]
        models.Cheque = Cheque

        gl_entry = MagicMock(branch_id=None, reference_type='Payment', reference_id=1, user=None)
        GLJournalEntry = _empty_query_model()
        GLJournalEntry.query.filter.return_value.all.return_value = [gl_entry]
        models.GLJournalEntry = GLJournalEntry

        mock_db.session.get.return_value = MagicMock(branch_id=8)

        result = ensure_branch_isolation_schema_and_data()
        assert result['main_branch_id'] == 10
        assert result['schema_changes'] == 3
        assert sale.branch_id == 3
        mock_db.session.flush.assert_called_once()

    def test_creates_main_branch_when_missing(self, app, mocker, restore_models):
        mocker.patch('runtime_core.branch_repair._ensure_column', return_value=False)
        mocker.patch('runtime_core.branch_repair._ensure_index')
        mocker.patch('utils.branching.GLOBAL_ROLE_SLUGS', set())
        mocker.patch('runtime_core.branch_repair.db')

        Branch = MagicMock()
        Branch.query.filter_by.return_value.order_by.return_value.first.return_value = None
        new_branch = MagicMock(id=1)
        Branch.return_value = new_branch
        models.Branch = Branch
        for name in ('Warehouse', 'User', 'Sale', 'Purchase', 'Expense', 'Payment', 'Receipt', 'Cheque', 'GLJournalEntry'):
            setattr(models, name, _empty_query_model())
        Tenant = MagicMock()
        Tenant.query.filter_by.return_value.order_by.return_value.first.return_value = MagicMock(id=1)
        models.Tenant = Tenant

        result = ensure_branch_isolation_schema_and_data()
        assert result['main_branch_id'] == 1

    def test_gl_reference_type_branches(self, app, mocker, restore_models):
        mocker.patch('runtime_core.branch_repair._ensure_column', return_value=False)
        mocker.patch('runtime_core.branch_repair._ensure_index')
        mocker.patch('utils.branching.GLOBAL_ROLE_SLUGS', set())
        mock_db = mocker.patch('runtime_core.branch_repair.db')
        main = MagicMock(id=2)
        Branch = MagicMock()
        Branch.query.filter_by.return_value.order_by.return_value.first.return_value = main
        models.Branch = Branch
        for name in ('Warehouse', 'User', 'Sale', 'Purchase', 'Expense', 'Payment', 'Receipt', 'Cheque'):
            setattr(models, name, _empty_query_model())
        entries = []
        for ref in ('Receipt', 'Expense', 'sale', 'purchase', 'cheque_receive'):
            e = MagicMock(branch_id=None, reference_type=ref, reference_id=1, user=None)
            entries.append(e)
        GLJournalEntry = _empty_query_model()
        GLJournalEntry.query.filter.return_value.all.return_value = entries
        models.GLJournalEntry = GLJournalEntry
        mock_db.session.get.return_value = MagicMock(branch_id=99)
        ensure_branch_isolation_schema_and_data()
        assert all(e.branch_id == 99 for e in entries)
