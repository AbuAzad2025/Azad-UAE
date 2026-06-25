from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query, app_factory, bypass_admin_auth, bypass_permission_auth, unauthenticated_client


def _mock_account(code='1101', balance=Decimal('1000'), **kwargs):
    acct = MagicMock()
    acct.id = kwargs.get('id', 1)
    acct.code = code
    acct.name = kwargs.get('name', f'Account {code}')
    acct.name_ar = kwargs.get('name_ar', f'حساب {code}')
    acct.full_name = kwargs.get('full_name', f'{code} Account')
    acct.type = kwargs.get('type', 'asset')
    acct.level = kwargs.get('level', 0)
    acct.parent_id = kwargs.get('parent_id')
    acct.is_active = kwargs.get('is_active', True)
    acct.is_header = kwargs.get('is_header', False)
    acct.get_balance = MagicMock(return_value=balance)
    return acct


def _statement_result():
    return {
        'transactions': [],
        'total_debit': Decimal('0'),
        'total_credit': Decimal('0'),
        'closing_balance': Decimal('0'),
        'opening_balance': Decimal('0'),
    }


def _gl_sum_query(credit=Decimal('150'), debit=Decimal('20')):
    state = {'toggle': False}

    def scalar_side():
        state['toggle'] = not state['toggle']
        return credit if state['toggle'] else debit

    q = _chain_query()
    q.scalar.side_effect = scalar_side
    q.filter.return_value.scalar.side_effect = scalar_side
    return q


def _ledger_query_side_effect(credit_val=Decimal('600'), debit_val=Decimal('100')):
    def query_side(*args, **kwargs):
        q = _chain_query()
        is_credit = bool(args) and 'credit' in str(args[0]).lower()
        val = credit_val if is_credit else debit_val
        q.scalar.return_value = val
        q.filter.return_value.scalar.return_value = val
        return q
    return query_side


def _scope_accounts_by_type(accounts_by_type):
    def fake_scope(query, **kwargs):
        m = MagicMock()
        query_text = str(query).lower()
        if 'revenue' in query_text or "code.like('4%')" in query_text.replace(' ', ''):
            m.all.return_value = accounts_by_type.get('revenue', [])
        elif 'expense' in query_text or "code.like('5%')" in query_text or "code.like('6%')" in query_text:
            m.all.return_value = accounts_by_type.get('expense', [])
        elif 'asset' in query_text:
            m.all.return_value = accounts_by_type.get('asset', [])
        elif 'liability' in query_text:
            m.all.return_value = accounts_by_type.get('liability', [])
        elif 'equity' in query_text:
            m.all.return_value = accounts_by_type.get('equity', [])
        else:
            merged = []
            for items in accounts_by_type.values():
                merged.extend(items)
            m.all.return_value = merged
        return m
    return fake_scope


def _scoped_accounts_query(accounts=None):
    accounts = accounts or [_mock_account()]
    q = MagicMock()
    q.filter_by.return_value.order_by.return_value.all.return_value = accounts
    q.filter.return_value.order_by.return_value.all.return_value = accounts
    q.filter.return_value.limit.return_value.all.return_value = accounts
    q.filter_by.return_value.first_or_404.return_value = accounts[0]
    q.order_by.return_value.limit.return_value.all.return_value = accounts
    return q


def _entry_mock(branch_id=1, entry_id=1):
    entry = MagicMock()
    entry.id = entry_id
    entry.branch_id = branch_id
    entry.entry_number = 'JE-001'
    entry.lines.all.return_value = []
    entry.reverse_entry.return_value = MagicMock(id=99, entry_number='JE-REV')
    return entry


@contextmanager
def _ledger_patches(**kwargs):
    accounts = kwargs.get('accounts', [_mock_account()])
    entry = kwargs.get('entry')
    statement = kwargs.get('statement', _statement_result())
    trial = kwargs.get('trial', {'lines': [], 'total_debit': 0, 'total_credit': 0})
    vat = kwargs.get('vat', {'output': 0, 'input': 0})
    branches = kwargs.get('branches', [MagicMock(id=1, name='Main')])
    with ExitStack() as stack:
        stack.enter_context(patch('routes.ledger.render_template', return_value='ok'))
        stack.enter_context(patch('routes.ledger.get_accessible_branches', return_value=branches))
        stack.enter_context(patch('routes.ledger.branch_scope_id', return_value=kwargs.get('branch_scope')))
        stack.enter_context(patch('routes.ledger.user_can_access_branch', return_value=kwargs.get('can_access_branch', True)))
        stack.enter_context(patch('utils.gl_tenant.scope_gl_accounts', side_effect=lambda q, **kw: _scoped_accounts_query(accounts)))
        stack.enter_context(patch('utils.gl_tenant.scope_journal_entries', side_effect=lambda q, **kw: _chain_query(all=[])))
        stack.enter_context(patch('utils.gl_tenant.gl_entry_query', return_value=_chain_query(all=[], first=entry)))
        stack.enter_context(patch('utils.gl_tenant.gl_account_query', return_value=_scoped_accounts_query(accounts)))
        stack.enter_context(patch('utils.gl_tenant.scoped_model_query', return_value=_chain_query(all=[], count=0)))
        stack.enter_context(patch('utils.tenanting.tenant_query', return_value=_chain_query(all=[], count=0)))
        stack.enter_context(patch('utils.gl_tenant.active_tenant_id', return_value=1))
        stack.enter_context(patch('utils.tenanting.require_active_tenant_id', return_value=1))
        stack.enter_context(patch('utils.tenanting.get_active_tenant_id', return_value=1))
        stack.enter_context(patch('routes.ledger.GLService.get_account_statement', return_value=statement))
        stack.enter_context(patch('routes.ledger.GLService.get_trial_balance', return_value=trial))
        stack.enter_context(patch('routes.ledger.GLService.get_vat_report', return_value=vat))
        stack.enter_context(patch('routes.ledger.GLService.get_accounts_tree', return_value=[]))
        stack.enter_context(patch('routes.ledger.GLService.create_manual_entry', return_value=_entry_mock()))
        stack.enter_context(patch('routes.ledger.LoggingCore.log_audit'))
        stack.enter_context(patch('routes.ledger.db.session'))
        stack.enter_context(patch('routes.ledger.CashFlowService.generate_cash_flow', return_value={'sections': []}))
        stack.enter_context(patch('routes.ledger.AgingAnalysisService.get_receivables_aging', return_value={}))
        stack.enter_context(patch('routes.ledger.AgingAnalysisService.get_payables_aging', return_value={}))
        stack.enter_context(patch('routes.ledger.AgingAnalysisService.verify_receivables_with_gl', return_value={}))
        stack.enter_context(patch('routes.ledger.AgingAnalysisService.verify_payables_with_gl', return_value={}))
        stack.enter_context(patch('services.depreciation_service.DepreciationService.run_monthly', return_value={'posted': 2, 'skipped': 1, 'errors': []}))
        render = stack.enter_context(patch('routes.ledger.render_template', return_value='ok'))
        yield {'render': render, 'entry': entry}


@pytest.fixture
def ledger_client(app_factory, bypass_permission_auth):
    from routes.ledger import ledger_bp
    app = app_factory(ledger_bp)
    return app.test_client()


@pytest.fixture
def ledger_admin_client(app_factory, bypass_admin_auth):
    from routes.ledger import ledger_bp
    app = app_factory(ledger_bp)
    return app.test_client()


class TestLedgerAuth:
    def test_index_requires_login(self, ledger_client):
        with unauthenticated_client(ledger_client):
            resp = ledger_client.get('/ledger/')
        assert resp.status_code == 401


class TestLedgerPages:
    def test_index(self, ledger_client):
        with _ledger_patches() as mocks:
            resp = ledger_client.get('/ledger/')
        assert resp.status_code == 200
        mocks['render'].assert_called()

    def test_account_ledger(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.get('/ledger/account/1?date_from=2026-01-01&branch_id=2')
        assert resp.status_code == 200

    def test_trial_balance(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.get('/ledger/trial-balance')
        assert resp.status_code == 200

    def test_journal_entries(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.get('/ledger/journal-entries?page=1')
        assert resp.status_code == 200

    def test_journal_entries_branch_filter(self, ledger_client):
        with _ledger_patches(branch_scope=2):
            resp = ledger_client.get('/ledger/journal-entries')
        assert resp.status_code == 200

    def test_vat_report_disabled_redirects(self, ledger_client):
        tenant = MagicMock(id=1)
        with _ledger_patches(), \
             patch('models.tenant.Tenant.get_current', return_value=tenant), \
             patch('utils.tax_settings.is_tax_enabled', return_value=False):
            resp = ledger_client.get('/ledger/vat-report', follow_redirects=False)
        assert resp.status_code == 302

    def test_vat_report_enabled(self, ledger_client):
        tenant = MagicMock(id=1)
        with _ledger_patches(), \
             patch('models.tenant.Tenant.get_current', return_value=tenant), \
             patch('utils.tax_settings.is_tax_enabled', return_value=True), \
             patch('utils.tax_settings.vat_country', return_value='AE'):
            resp = ledger_client.get('/ledger/vat-report')
        assert resp.status_code == 200

    def test_gl_periods_get(self, ledger_client):
        period = MagicMock(year=2026, month=1)
        with _ledger_patches(), patch('models.gl.GLPeriod') as gp:
            gp.query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [period]
            resp = ledger_client.get('/ledger/periods')
        assert resp.status_code == 200

    def test_gl_periods_post_close(self, ledger_client):
        with _ledger_patches(), patch('models.gl.GLPeriod') as gp:
            gp.query.filter_by.return_value.first.return_value = None
            resp = ledger_client.post('/ledger/periods', data={'year': '2026', 'month': '3', 'action': 'close'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_run_depreciation_success(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.post('/ledger/run-depreciation', data={'year': '2026', 'month': '1'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_run_depreciation_with_errors(self, ledger_client):
        with _ledger_patches(), \
             patch('services.depreciation_service.DepreciationService.run_monthly', return_value={'posted': 0, 'skipped': 0, 'errors': ['fail']}):
            resp = ledger_client.post('/ledger/run-depreciation', data={'year': '2026', 'month': '1'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_income_statement(self, ledger_client):
        rev = _mock_account(code='4100', type='revenue', name='Sales')
        exp = _mock_account(code='5100', type='expense', name='Rent')
        scope = _scope_accounts_by_type({'revenue': [rev], 'expense': [exp]})
        with _ledger_patches(), \
             patch('utils.gl_tenant.scope_gl_accounts', side_effect=scope), \
             patch('routes.ledger.db.session.query', side_effect=_ledger_query_side_effect()), \
             patch('utils.tenanting.get_active_tenant_id', return_value=1):
            resp = ledger_client.get('/ledger/income-statement?date_from=2026-01-01&date_to=2026-06-01&branch_id=1')
        assert resp.status_code == 200

    def test_income_statement_no_tenant_filter(self, ledger_client):
        rev = _mock_account(code='4100', type='revenue', name='Sales')
        scope = _scope_accounts_by_type({'revenue': [rev], 'expense': []})
        with _ledger_patches(), \
             patch('utils.gl_tenant.scope_gl_accounts', side_effect=scope), \
             patch('routes.ledger.db.session.query', side_effect=_ledger_query_side_effect()), \
             patch('utils.tenanting.get_active_tenant_id', return_value=None):
            resp = ledger_client.get('/ledger/income-statement')
        assert resp.status_code == 200

    def test_balance_sheet(self, ledger_client):
        asset = _mock_account(code='1100', type='asset', name='Cash')
        liability = _mock_account(code='2100', type='liability', name='AP')
        equity = _mock_account(code='3100', type='equity', name='Capital')
        rev = _mock_account(code='4100', type='revenue', name='Sales')
        exp = _mock_account(code='5100', type='expense', name='Rent')
        scope = _scope_accounts_by_type({
            'asset': [asset],
            'liability': [liability],
            'equity': [equity],
            'revenue': [rev, rev],
            'expense': [exp],
        })
        with _ledger_patches(branch_scope=1), \
             patch('utils.gl_tenant.scope_gl_accounts', side_effect=scope), \
             patch('routes.ledger.db.session.query', side_effect=_ledger_query_side_effect(
                 credit_val=Decimal('800'), debit_val=Decimal('100'),
             )):
            resp = ledger_client.get('/ledger/balance-sheet?date_to=2026-06-30')
        assert resp.status_code == 200

    def test_accounts_tree(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.get('/ledger/accounts-tree')
        assert resp.status_code == 200

    def test_account_statement(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.get('/ledger/account/1/statement')
        assert resp.status_code == 200

    def test_cash_flow(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.get('/ledger/cash-flow')
        assert resp.status_code == 200

    def test_cash_flow_error_redirects(self, ledger_client):
        with _ledger_patches(), \
             patch('routes.ledger.CashFlowService.generate_cash_flow', side_effect=RuntimeError('bad period')):
            resp = ledger_client.get('/ledger/cash-flow', follow_redirects=False)
        assert resp.status_code == 302

    def test_aging_receivables(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.get('/ledger/aging-analysis?type=receivables')
        assert resp.status_code == 200

    def test_aging_payables(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.get('/ledger/aging-analysis?type=payables')
        assert resp.status_code == 200

    def test_aging_error_redirects(self, ledger_client):
        with _ledger_patches(), \
             patch('routes.ledger.AgingAnalysisService.get_receivables_aging', side_effect=RuntimeError('fail')):
            resp = ledger_client.get('/ledger/aging-analysis', follow_redirects=False)
        assert resp.status_code == 302

    def test_budget_vs_actual(self, ledger_client):
        budget = MagicMock(status='active', lines=[], total_budgeted=100, total_actual=80, total_variance=20, variance_percentage=20)
        budget.update_actuals = MagicMock()
        line = MagicMock(account=MagicMock(), budgeted_amount=50, actual_amount=40, variance=10, variance_percentage=20, variance_status='ok', variance_status_ar='جيد')
        budget.lines = [line]
        bq = MagicMock()
        bq.filter_by.return_value.all.return_value = [budget]
        with _ledger_patches(), patch('models.Budget') as budget_cls:
            budget_cls.query = bq
            resp = ledger_client.get('/ledger/budget-vs-actual')
        assert resp.status_code == 200

    def test_budget_vs_actual_branch_filter(self, ledger_client):
        budget = MagicMock(status='active', lines=[], total_budgeted=50, total_actual=40, total_variance=10, variance_percentage=20)
        budget.update_actuals = MagicMock()
        budget.lines = []
        filtered = MagicMock()
        filtered.all.return_value = [budget]
        bq = MagicMock()
        bq.filter_by.return_value = filtered
        with _ledger_patches(branch_scope=2), patch('models.Budget') as budget_cls:
            budget_cls.query = bq
            resp = ledger_client.get('/ledger/budget-vs-actual')
        assert resp.status_code == 200


class TestLedgerManualEntry:
    def test_manual_entry_get(self, ledger_client):
        with _ledger_patches():
            resp = ledger_client.get('/ledger/manual-entry')
        assert resp.status_code == 200

    def test_manual_entry_post_success(self, ledger_client):
        entry = _entry_mock(entry_id=55)
        with _ledger_patches(), patch('routes.ledger.GLService.create_manual_entry', return_value=entry):
            resp = ledger_client.post('/ledger/manual-entry', data={
                'description': 'Adjustment',
                'entry_date': '2026-06-01',
                'line_0_account': '1101',
                'line_0_debit': '100',
                'line_0_credit': '0',
                'line_1_account': '4100',
                'line_1_debit': '0',
                'line_1_credit': '100',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_manual_entry_value_error(self, ledger_client):
        with _ledger_patches(), \
             patch('routes.ledger.GLService.create_manual_entry', side_effect=ValueError('unbalanced')):
            resp = ledger_client.post('/ledger/manual-entry', data={'description': 'x'})
        assert resp.status_code == 200

    def test_manual_entry_generic_error(self, ledger_client):
        with _ledger_patches(), \
             patch('routes.ledger.GLService.create_manual_entry', side_effect=RuntimeError('db')):
            resp = ledger_client.post('/ledger/manual-entry', data={'description': 'x'})
        assert resp.status_code == 200

    def test_manual_entry_invalid_line_values(self, ledger_client):
        entry = _entry_mock(entry_id=56)
        with _ledger_patches(), patch('routes.ledger.GLService.create_manual_entry', return_value=entry):
            resp = ledger_client.post('/ledger/manual-entry', data={
                'description': 'Bad lines',
                'line_0_account': '1101',
                'line_0_debit': 'not-a-number',
                'line_0_credit': 'also-bad',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_manual_entry_requested_branch(self, ledger_client):
        entry = _entry_mock(entry_id=57)
        with _ledger_patches(branch_scope=None, can_access_branch=True), \
             patch('routes.ledger.GLService.create_manual_entry', return_value=entry) as create:
            resp = ledger_client.post('/ledger/manual-entry', data={
                'description': 'Branch pick',
                'branch_id': '3',
                'line_0_account': '1101',
                'line_0_debit': '50',
                'line_0_credit': '0',
                'line_1_account': '4100',
                'line_1_debit': '0',
                'line_1_credit': '50',
            }, follow_redirects=False)
        assert resp.status_code == 302
        assert create.call_args.kwargs['branch_id'] == 3

    def test_manual_entry_scoped_branch(self, ledger_client):
        entry = _entry_mock(entry_id=58)
        with _ledger_patches(branch_scope=4), \
             patch('routes.ledger.GLService.create_manual_entry', return_value=entry) as create:
            resp = ledger_client.post('/ledger/manual-entry', data={
                'description': 'Scoped',
                'branch_id': '9',
                'line_0_account': '1101',
                'line_0_debit': '10',
                'line_0_credit': '0',
                'line_1_account': '4100',
                'line_1_debit': '0',
                'line_1_credit': '10',
            }, follow_redirects=False)
        assert resp.status_code == 302
        assert create.call_args.kwargs['branch_id'] == 4

    def test_manual_entry_branch_parse_error(self, ledger_client):
        entry = _entry_mock(entry_id=59)
        with _ledger_patches(branch_scope=None, can_access_branch=False), \
             patch('routes.ledger.GLService.create_manual_entry', return_value=entry) as create:
            resp = ledger_client.post('/ledger/manual-entry', data={
                'description': 'Parse fail',
                'branch_id': 'bad',
                'line_0_account': '1101',
                'line_0_debit': '10',
                'line_0_credit': '0',
                'line_1_account': '4100',
                'line_1_debit': '0',
                'line_1_credit': '10',
            }, follow_redirects=False)
        assert resp.status_code == 302
        create.assert_called_once()


class TestLedgerEntryViews:
    def test_view_entry_success(self, ledger_client):
        entry = _entry_mock(branch_id=1)
        eq = _chain_query(all=[])
        eq.filter_by.return_value.first_or_404.return_value = entry
        with _ledger_patches(entry=entry), \
             patch('utils.gl_tenant.gl_entry_query', return_value=eq):
            resp = ledger_client.get('/ledger/entry/1')
        assert resp.status_code == 200

    def test_view_entry_branch_forbidden(self, ledger_client):
        entry = _entry_mock(branch_id=5)
        eq = _chain_query(all=[])
        eq.filter_by.return_value.first_or_404.return_value = entry
        with _ledger_patches(entry=entry, branch_scope=2), \
             patch('utils.gl_tenant.gl_entry_query', return_value=eq):
            resp = ledger_client.get('/ledger/entry/1')
        assert resp.status_code == 403

    def test_reverse_entry_success(self, ledger_client):
        entry = _entry_mock(branch_id=1)
        eq = _chain_query(all=[])
        eq.filter_by.return_value.first_or_404.return_value = entry
        with _ledger_patches(entry=entry), \
             patch('utils.gl_tenant.gl_entry_query', return_value=eq):
            resp = ledger_client.post('/ledger/entry/1/reverse', data={'description': 'reverse'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_reverse_entry_branch_forbidden(self, ledger_client):
        entry = _entry_mock(branch_id=9)
        eq = _chain_query(all=[])
        eq.filter_by.return_value.first_or_404.return_value = entry
        with _ledger_patches(entry=entry, branch_scope=1), \
             patch('utils.gl_tenant.gl_entry_query', return_value=eq):
            resp = ledger_client.post('/ledger/entry/1/reverse', follow_redirects=False)
        assert resp.status_code == 403

    def test_reverse_entry_value_error(self, ledger_client):
        entry = _entry_mock(branch_id=1)
        entry.reverse_entry.side_effect = ValueError('cannot reverse')
        eq = _chain_query(all=[])
        eq.filter_by.return_value.first_or_404.return_value = entry
        with _ledger_patches(entry=entry), \
             patch('utils.gl_tenant.gl_entry_query', return_value=eq):
            resp = ledger_client.post('/ledger/entry/1/reverse', follow_redirects=False)
        assert resp.status_code == 302

    def test_reverse_entry_generic_error(self, ledger_client):
        entry = _entry_mock(branch_id=1)
        entry.reverse_entry.side_effect = RuntimeError('db fail')
        eq = _chain_query(all=[])
        eq.filter_by.return_value.first_or_404.return_value = entry
        with _ledger_patches(entry=entry), \
             patch('utils.gl_tenant.gl_entry_query', return_value=eq):
            resp = ledger_client.post('/ledger/entry/1/reverse', follow_redirects=False)
        assert resp.status_code == 302


class TestLedgerApi:
    def test_search_accounts(self, ledger_client):
        acct = _mock_account()
        with _ledger_patches(accounts=[acct]):
            resp = ledger_client.get('/ledger/api/accounts/search?q=110')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data[0]['code'] == '1101'

    def test_calculate_journal_balance_balanced(self, ledger_client):
        resp = ledger_client.post(
            '/ledger/api/calculate-journal-balance',
            json={'lines': [{'debit': 100, 'credit': 0}, {'debit': 0, 'credit': 100}]},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['is_balanced'] is True

    def test_calculate_journal_balance_unbalanced(self, ledger_client):
        resp = ledger_client.post(
            '/ledger/api/calculate-journal-balance',
            json={'lines': [{'debit': 100, 'credit': 0}, {'debit': 0, 'credit': 50}]},
        )
        data = resp.get_json()
        assert data['is_balanced'] is False

    def test_calculate_journal_balance_no_data(self, ledger_client):
        resp = ledger_client.post('/ledger/api/calculate-journal-balance', json=None)
        assert resp.status_code == 400

    def test_calculate_journal_balance_empty_object(self, ledger_client):
        resp = ledger_client.post('/ledger/api/calculate-journal-balance', json={})
        assert resp.status_code == 400

    def test_calculate_journal_balance_bad_payload(self, ledger_client):
        resp = ledger_client.post('/ledger/api/calculate-journal-balance', data='not-json', content_type='text/plain')
        assert resp.status_code == 400


class TestLedgerAdmin:
    def test_admin_dashboard(self, ledger_admin_client):
        with _ledger_patches(accounts=[_mock_account(balance=Decimal('5000'))]):
            resp = ledger_admin_client.get('/ledger/admin-dashboard')
        assert resp.status_code == 200

    def test_admin_dashboard_high_balance_accounts(self, ledger_admin_client):
        high = _mock_account(code='1101', balance=Decimal('5000'))
        low = _mock_account(code='1102', balance=Decimal('50'))
        acct_q = MagicMock()
        acct_q.count.return_value = 2
        acct_q.filter_by.return_value.count.return_value = 2
        acct_q.filter.return_value.all.return_value = [high]
        acct_q.filter_by.return_value.all.return_value = [high, low]
        acct_q.order_by.return_value.limit.return_value.all.return_value = []
        entry_q = MagicMock()
        entry_q.count.return_value = 5
        entry_q.filter_by.return_value.count.return_value = 4
        entry_q.order_by.return_value.limit.return_value.all.return_value = []
        scoped_q = MagicMock()
        scoped_q.count.return_value = 1
        scoped_q.filter_by.return_value.count.return_value = 1
        tenant_q = MagicMock()
        tenant_q.count.return_value = 0
        tenant_q.filter_by.return_value.count.return_value = 0
        with _ledger_patches(), \
             patch('utils.gl_tenant.gl_account_query', return_value=acct_q), \
             patch('utils.gl_tenant.gl_entry_query', return_value=entry_q), \
             patch('utils.gl_tenant.scoped_model_query', return_value=scoped_q), \
             patch('utils.tenanting.tenant_query', return_value=tenant_q):
            resp = ledger_admin_client.get('/ledger/admin-dashboard')
        assert resp.status_code == 200

    def test_admin_accounts(self, ledger_admin_client):
        with _ledger_patches():
            resp = ledger_admin_client.get('/ledger/admin-accounts')
        assert resp.status_code == 200

    def test_admin_add_account_get(self, ledger_admin_client):
        with _ledger_patches():
            resp = ledger_admin_client.get('/ledger/admin-accounts/add')
        assert resp.status_code == 200

    def test_admin_add_account_duplicate(self, ledger_admin_client):
        dup = _mock_account(code='1001')
        q = _scoped_accounts_query([dup])
        q.filter_by.return_value.first.return_value = dup
        with _ledger_patches(), \
             patch('utils.gl_tenant.gl_account_query', return_value=q), \
             patch('routes.ledger.resolve_default_currency', return_value='AED'):
            resp = ledger_admin_client.post('/ledger/admin-accounts/add', data={
                'code': '1001', 'name': 'Dup', 'type': 'asset',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_admin_add_account_success(self, ledger_admin_client):
        acct = MagicMock(id=77, full_name='New Acct')
        q = _scoped_accounts_query([])
        q.filter_by.return_value.first.return_value = None
        with _ledger_patches(), \
             patch('utils.gl_tenant.gl_account_query', return_value=q), \
             patch('routes.ledger.resolve_default_currency', return_value='AED'), \
             patch('models.GLAccount', return_value=acct):
            resp = ledger_admin_client.post('/ledger/admin-accounts/add', data={
                'code': '2001', 'name': 'New', 'type': 'asset',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_admin_add_account_with_parent(self, ledger_admin_client):
        parent = _mock_account(code='1000', level=1)
        acct = MagicMock(id=78, full_name='Child Acct')
        q = _scoped_accounts_query([parent])
        q.filter_by.return_value.first.side_effect = [None, parent]
        with _ledger_patches(), \
             patch('utils.gl_tenant.gl_account_query', return_value=q), \
             patch('routes.ledger.resolve_default_currency', return_value='AED'), \
             patch('models.GLAccount', return_value=acct):
            resp = ledger_admin_client.post('/ledger/admin-accounts/add', data={
                'code': '1001', 'name': 'Child', 'type': 'asset', 'parent_id': '1',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_admin_add_account_currency_fallback(self, ledger_admin_client):
        acct = MagicMock(id=79, full_name='Fallback Acct')
        q = _scoped_accounts_query([])
        q.filter_by.return_value.first.return_value = None
        with _ledger_patches(), \
             patch('utils.gl_tenant.gl_account_query', return_value=q), \
             patch('routes.ledger.resolve_default_currency', side_effect=RuntimeError('no tenant')), \
             patch('routes.ledger.get_system_default_currency', return_value='AED'), \
             patch('models.GLAccount', return_value=acct):
            resp = ledger_admin_client.post('/ledger/admin-accounts/add', data={
                'code': '2003', 'name': 'Fallback', 'type': 'asset',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_admin_add_account_exception(self, ledger_admin_client):
        q = _scoped_accounts_query([])
        q.filter_by.return_value.first.return_value = None
        with _ledger_patches(), \
             patch('utils.gl_tenant.gl_account_query', return_value=q), \
             patch('routes.ledger.resolve_default_currency', return_value='AED'), \
             patch('models.GLAccount', return_value=MagicMock()), \
             patch('routes.ledger.db.session.commit', side_effect=RuntimeError('fail')):
            resp = ledger_admin_client.post('/ledger/admin-accounts/add', data={
                'code': '2002', 'name': 'Fail', 'type': 'asset',
            })
        assert resp.status_code == 200

    def test_admin_vaults(self, ledger_admin_client):
        with _ledger_patches():
            resp = ledger_admin_client.get('/ledger/admin-vaults')
        assert resp.status_code == 200

    def test_admin_journals(self, ledger_admin_client):
        with _ledger_patches():
            resp = ledger_admin_client.get('/ledger/admin-journals')
        assert resp.status_code == 200

    def test_admin_reports(self, ledger_admin_client):
        with _ledger_patches():
            resp = ledger_admin_client.get('/ledger/admin-reports')
        assert resp.status_code == 200

    def test_admin_trial_balance_invalid_dates(self, ledger_admin_client):
        acct = _mock_account(code='4001', balance=Decimal('100'))
        with _ledger_patches(accounts=[acct]):
            resp = ledger_admin_client.get(
                '/ledger/admin-trial-balance',
                query_string={'date_from': 'bad', 'date_to': 'also-bad'},
            )
        assert resp.status_code == 200

    def test_admin_trial_balance_valid_dates(self, ledger_admin_client):
        acct = _mock_account(code='4001', balance=Decimal('250'))
        with _ledger_patches(accounts=[acct]):
            resp = ledger_admin_client.get(
                '/ledger/admin-trial-balance',
                query_string={'date_from': '2026-01-01', 'date_to': '2026-06-30'},
            )
        assert resp.status_code == 200

    def test_admin_balance_sheet(self, ledger_admin_client):
        assets = [_mock_account(code='1000', type='asset', balance=Decimal('1000'))]
        liabilities = [_mock_account(code='2000', type='liability', balance=Decimal('-400'))]
        equity = [_mock_account(code='3000', type='equity', balance=Decimal('-600'))]

        def filter_by(**kwargs):
            inner = MagicMock()
            t = kwargs.get('type')
            if t == 'asset':
                inner.order_by.return_value.all.return_value = assets
            elif t == 'liability':
                inner.order_by.return_value.all.return_value = liabilities
            elif t == 'equity':
                inner.order_by.return_value.all.return_value = equity
            return inner

        q = MagicMock()
        q.filter_by.side_effect = filter_by
        with _ledger_patches(), patch('utils.gl_tenant.gl_account_query', return_value=q):
            resp = ledger_admin_client.get('/ledger/admin-balance-sheet')
        assert resp.status_code == 200

    def test_admin_balance_sheet_invalid_date(self, ledger_admin_client):
        q = MagicMock()
        q.filter_by.return_value.order_by.return_value.all.return_value = []
        with _ledger_patches(), patch('utils.gl_tenant.gl_account_query', return_value=q):
            resp = ledger_admin_client.get('/ledger/admin-balance-sheet?as_of_date=invalid')
        assert resp.status_code == 200

    def test_admin_income_statement(self, ledger_admin_client):
        revenues = [_mock_account(code='4100', type='revenue', balance=Decimal('-500'))]
        expenses = [_mock_account(code='5100', type='expense', balance=Decimal('200'))]

        def filter_by(**kwargs):
            inner = MagicMock()
            if kwargs.get('type') == 'revenue':
                inner.order_by.return_value.all.return_value = revenues
            elif kwargs.get('type') == 'expense':
                inner.order_by.return_value.all.return_value = expenses
            return inner

        q = MagicMock()
        q.filter_by.side_effect = filter_by
        with _ledger_patches(), patch('utils.gl_tenant.gl_account_query', return_value=q):
            resp = ledger_admin_client.get('/ledger/admin-income-statement')
        assert resp.status_code == 200

    def test_admin_income_statement_invalid_dates(self, ledger_admin_client):
        q = MagicMock()
        q.filter_by.return_value.order_by.return_value.all.return_value = []
        with _ledger_patches(), patch('utils.gl_tenant.gl_account_query', return_value=q):
            resp = ledger_admin_client.get('/ledger/admin-income-statement?date_from=bad&date_to=also-bad')
        assert resp.status_code == 200

    def test_admin_settings(self, ledger_admin_client):
        with _ledger_patches():
            resp = ledger_admin_client.get('/ledger/admin-settings')
        assert resp.status_code == 200


class TestEffectiveBranchId:
    def test_scoped_branch_takes_priority(self, ledger_client):
        with _ledger_patches(branch_scope=3):
            resp = ledger_client.get('/ledger/?branch_id=9')
        assert resp.status_code == 200

    def test_invalid_branch_id_ignored(self, ledger_client):
        with _ledger_patches(branch_scope=None, can_access_branch=False):
            resp = ledger_client.get('/ledger/account/1?branch_id=not-int')
        assert resp.status_code == 200
