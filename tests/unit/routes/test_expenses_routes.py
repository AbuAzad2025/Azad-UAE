from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query, app_factory, bypass_permission_auth, unauthenticated_client


def _mock_expense(**kwargs):
    exp = MagicMock()
    exp.id = kwargs.get('id', 1)
    exp.tenant_id = kwargs.get('tenant_id', 1)
    exp.branch_id = kwargs.get('branch_id', 1)
    exp.expense_number = kwargs.get('expense_number', 'EXP-001')
    exp.status = kwargs.get('status', 'confirmed')
    exp.amount = kwargs.get('amount', Decimal('100'))
    exp.currency = kwargs.get('currency', 'AED')
    exp.category_id = kwargs.get('category_id', 1)
    exp.payment_method = kwargs.get('payment_method', 'cash')
    exp.description = kwargs.get('description', 'Office supplies')
    exp.expense_date = kwargs.get('expense_date', date(2026, 1, 15))
    exp.is_reversed = False
    category = kwargs.get('category')
    if category is None:
        category = MagicMock(gl_account_code='5100')
    exp.category = category
    return exp


def _mock_category(gl_code='5100'):
    cat = MagicMock()
    cat.id = 1
    cat.name = 'Ops'
    cat.gl_account_code = gl_code
    return cat


@contextmanager
def _expense_patches(expense=None, tenant_get_raises=False, branch_scope=None):
    expense_q = _chain_query(all=[expense] if expense else [])
    cat_q = _chain_query(all=[_mock_category()])
    with ExitStack() as stack:
        stack.enter_context(patch('routes.expenses.render_template', return_value='ok'))
        stack.enter_context(patch('routes.expenses.tenant_query', side_effect=lambda m: cat_q if getattr(m, '__name__', '') == 'ExpenseCategory' else expense_q))
        stack.enter_context(patch('routes.expenses.get_active_tenant_id', return_value=1))
        stack.enter_context(patch('routes.expenses.require_active_tenant_id', return_value=1))
        stack.enter_context(patch('routes.expenses.tenant_get_or_404', return_value=expense if not tenant_get_raises else None))
        stack.enter_context(patch('routes.expenses.branch_scope_id', return_value=branch_scope))
        stack.enter_context(patch('routes.expenses.should_show_all_branch_columns', return_value=False))
        stack.enter_context(patch('extensions.db.session'))
        stack.enter_context(patch('services.logging_core.LoggingCore.log_audit'))
        stack.enter_context(patch('services.currency_service.CurrencyService.get_all_rates', return_value={}))
        stack.enter_context(patch('services.currency_service.CurrencyService.get_exchange_rate', return_value=Decimal('1')))
        stack.enter_context(patch('routes.expenses.resolve_default_currency', return_value='AED'))
        stack.enter_context(patch('routes.expenses.generate_number', return_value='EXP-NEW'))
        stack.enter_context(patch('routes.expenses._resolve_transaction_rate', return_value=Decimal('1')))
        stack.enter_context(patch('routes.expenses.post_or_fail'))
        stack.enter_context(patch('routes.expenses.GLService.ensure_core_accounts'))
        stack.enter_context(patch('routes.expenses.GLService.get_payment_credit_account', return_value='1101'))
        stack.enter_context(patch('routes.expenses.GLService.get_payment_credit_concept', return_value='CASH'))
        stack.enter_context(patch('services.cheque_service.process_cheque_issue'))
        stack.enter_context(patch('extensions.limiter.limit', return_value=lambda f: f))
        if tenant_get_raises:
            stack.enter_context(patch('routes.expenses.tenant_get_or_404', side_effect=NotFound()))
        render = stack.enter_context(patch('routes.expenses.render_template', return_value='ok'))
        yield {'render': render, 'expense': expense}


@pytest.fixture
def expenses_client(app_factory, bypass_permission_auth):
    from routes.expenses import expenses_bp
    app = app_factory(expenses_bp)
    return app.test_client()


def _archived_records_query(records):
    scoped = MagicMock()
    scoped.all.return_value = records
    root = MagicMock()
    root.filter.return_value = scoped
    return root


class TestExpensesAuth:
    def test_index_requires_login(self, expenses_client):
        with unauthenticated_client(expenses_client):
            resp = expenses_client.get('/expenses/')
        assert resp.status_code == 401


class TestExpensesIndex:
    def test_index_renders(self, expenses_client):
        subq = MagicMock()
        select_chain = MagicMock()
        select_chain.filter.return_value.scalar_subquery.return_value = subq
        with _expense_patches(expense=_mock_expense()), \
             patch('sqlalchemy.select', return_value=select_chain):
            resp = expenses_client.get('/expenses/')
        assert resp.status_code == 200

    def test_index_category_filter(self, expenses_client):
        subq = MagicMock()
        select_chain = MagicMock()
        select_chain.filter.return_value.scalar_subquery.return_value = subq
        with _expense_patches(), patch('sqlalchemy.select', return_value=select_chain):
            resp = expenses_client.get('/expenses/?category=2')
        assert resp.status_code == 200

    def test_index_branch_scope_filter(self, expenses_client):
        subq = MagicMock()
        select_chain = MagicMock()
        select_chain.filter.return_value.scalar_subquery.return_value = subq
        with _expense_patches(), patch('sqlalchemy.select', return_value=select_chain), \
             patch('utils.decorators.branch_scope_id', return_value=2):
            resp = expenses_client.get('/expenses/')
        assert resp.status_code == 200


class TestResolveTransactionRate:
    def test_resolve_transaction_rate(self, mocker):
        mocker.patch('utils.currency_utils.get_system_default_currency', return_value='AED')
        mocker.patch(
            'services.exchange_rate_service.ExchangeRateService.resolve_exchange_rate_for_transaction',
            return_value={'rate': '3.67'},
        )
        from routes.expenses import _resolve_transaction_rate
        assert _resolve_transaction_rate('USD', user_rate=3.67) == Decimal('3.67')


class TestExpensesCreate:
    def test_create_get(self, expenses_client):
        with _expense_patches():
            resp = expenses_client.get('/expenses/create')
        assert resp.status_code == 200

    def test_create_get_currency_fallback(self, expenses_client):
        with _expense_patches(), \
             patch('routes.expenses.resolve_default_currency', side_effect=RuntimeError('no tenant')):
            resp = expenses_client.get('/expenses/create')
        assert resp.status_code == 200

    def test_create_post_cash_success(self, expenses_client):
        expense = MagicMock(id=10, expense_number='EXP-NEW', tenant_id=1, branch_id=1, payment_method='cash')
        with _expense_patches(), \
             patch('routes.expenses.Expense', return_value=expense), \
             patch('routes.expenses._build_expense_gl_lines', return_value=[{'debit': 50}, {'credit': 50}]):
            resp = expenses_client.post('/expenses/create', data={
                'amount': '50',
                'category_id': '1',
                'description': 'Supplies',
                'payment_method': 'cash',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_post_cheque(self, expenses_client):
        expense = MagicMock(id=11, expense_number='EXP-CHQ', tenant_id=1, branch_id=1, payment_method='cheque',
                            cheque_number='CHQ-1', bank_name='Bank', supplier_name='Vendor', notes='n')
        with _expense_patches(), \
             patch('routes.expenses.Expense', return_value=expense), \
             patch('routes.expenses.Cheque', return_value=MagicMock()), \
             patch('routes.expenses._build_expense_gl_lines', return_value=[]):
            resp = expenses_client.post('/expenses/create', data={
                'amount': '200',
                'category_id': '1',
                'description': 'Cheque expense',
                'payment_method': 'cheque',
                'cheque_date': '2026-06-01',
                'cheque_number': 'CHQ-1',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_post_gl_failure_renders_form(self, expenses_client):
        expense = MagicMock(id=12, tenant_id=1, branch_id=1, payment_method='cash', category=MagicMock(gl_account_code='5100'))
        with _expense_patches(), \
             patch('routes.expenses.Expense', return_value=expense), \
             patch('routes.expenses.post_or_fail', side_effect=RuntimeError('GL fail')):
            resp = expenses_client.post('/expenses/create', data={
                'amount': '75',
                'category_id': '1',
                'payment_method': 'cash',
            })
        assert resp.status_code == 200

    def test_create_post_general_exception(self, expenses_client):
        with _expense_patches(), patch('routes.expenses.generate_number', side_effect=RuntimeError('boom')):
            resp = expenses_client.post('/expenses/create', data={'amount': '10'})
        assert resp.status_code == 200

    def test_create_post_invalid_cheque_date(self, expenses_client):
        expense = MagicMock(id=13, expense_number='EXP-BAD', tenant_id=1, branch_id=1, payment_method='cash')
        with _expense_patches(), \
             patch('routes.expenses.Expense', return_value=expense), \
             patch('routes.expenses._build_expense_gl_lines', return_value=[]):
            resp = expenses_client.post('/expenses/create', data={
                'amount': '40',
                'category_id': '1',
                'payment_method': 'cash',
                'cheque_date': 'not-a-date',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_post_gl_failure_currency_fallback(self, expenses_client):
        expense = MagicMock(id=14, tenant_id=1, branch_id=1, payment_method='cash', category=MagicMock(gl_account_code='5100'))
        with _expense_patches(), \
             patch('routes.expenses.Expense', return_value=expense), \
             patch('routes.expenses.post_or_fail', side_effect=RuntimeError('GL fail')), \
             patch('routes.expenses.resolve_default_currency', side_effect=RuntimeError('x')), \
             patch('routes.expenses.get_system_default_currency', return_value='AED'):
            resp = expenses_client.post('/expenses/create', data={
                'amount': '75',
                'category_id': '1',
                'payment_method': 'cash',
            })
        assert resp.status_code == 200


class TestExpensesViewScope:
    def test_view_success(self, expenses_client):
        with _expense_patches(expense=_mock_expense()):
            resp = expenses_client.get('/expenses/1')
        assert resp.status_code == 200

    def test_view_branch_forbidden(self, expenses_client):
        with _expense_patches(expense=_mock_expense(branch_id=5), branch_scope=2):
            resp = expenses_client.get('/expenses/1')
        assert resp.status_code == 403

    def test_view_tenant_404(self, expenses_client):
        with _expense_patches(tenant_get_raises=True):
            resp = expenses_client.get('/expenses/999')
        assert resp.status_code == 404

    def test_print_branch_forbidden(self, expenses_client):
        with _expense_patches(expense=_mock_expense(branch_id=9), branch_scope=1), \
             patch('routes.expenses.current_app') as app:
            app.config = {'COMPANY_NAME_AR': 'Co', 'COMPANY_ADDRESS': 'Addr', 'COMPANY_PHONE': '123'}
            resp = expenses_client.get('/expenses/1/print')
        assert resp.status_code == 403

    def test_print_success(self, expenses_client):
        with _expense_patches(expense=_mock_expense()), \
             patch('flask.current_app') as app:
            app.config.get.side_effect = lambda k: {'COMPANY_NAME_AR': 'Co', 'COMPANY_ADDRESS': 'Addr', 'COMPANY_PHONE': '123'}.get(k)
            resp = expenses_client.get('/expenses/1/print')
        assert resp.status_code == 200


class TestExpensesEdit:
    def test_edit_get(self, expenses_client):
        archived_cls = MagicMock()
        archived_cls.query.filter_by.return_value.first.return_value = None
        with _expense_patches(expense=_mock_expense()), patch('models.ArchivedRecord', archived_cls):
            resp = expenses_client.get('/expenses/1/edit')
        assert resp.status_code == 200

    def test_edit_archived_redirects(self, expenses_client):
        archived = MagicMock()
        with _expense_patches(expense=_mock_expense()), \
             patch('models.ArchivedRecord') as ar:
            ar.query.filter_by.return_value.first.return_value = archived
            resp = expenses_client.post('/expenses/1/edit', data={'amount': '100'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_financial_change_reposts(self, expenses_client):
        expense = _mock_expense(amount=Decimal('100'), currency='AED', category_id=1)
        with _expense_patches(expense=expense), \
             patch('models.ArchivedRecord') as ar, \
             patch('services.gl_helpers.assert_period_open'), \
             patch('utils.gl_tenant.reverse_document_gl'), \
             patch('routes.expenses._build_expense_gl_lines', return_value=[]), \
             patch('services.gl_posting.post_or_fail'):
            ar.query.filter_by.return_value.first.return_value = None
            resp = expenses_client.post('/expenses/1/edit', data={
                'amount': '200',
                'currency': 'AED',
                'category_id': '1',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_exception_rolls_back(self, expenses_client):
        expense = _mock_expense()
        with _expense_patches(expense=expense) as mocks, \
             patch('models.ArchivedRecord') as ar, \
             patch('services.gl_helpers.assert_period_open', side_effect=RuntimeError('closed period')):
            ar.query.filter_by.return_value.first.return_value = None
            session = patch('routes.expenses.db.session').start()
            resp = expenses_client.post('/expenses/1/edit', data={'amount': '50'})
            session.stop()
        assert resp.status_code == 200

    def test_edit_branch_forbidden(self, expenses_client):
        archived_cls = MagicMock()
        archived_cls.query.filter_by.return_value.first.return_value = None
        with _expense_patches(expense=_mock_expense(branch_id=7), branch_scope=2), \
             patch('models.ArchivedRecord', archived_cls):
            resp = expenses_client.get('/expenses/1/edit')
        assert resp.status_code == 403

    def test_edit_currency_fallback(self, expenses_client):
        expense = _mock_expense()
        with _expense_patches(expense=expense), \
             patch('models.ArchivedRecord') as ar, \
             patch('services.gl_helpers.assert_period_open'), \
             patch('routes.expenses.resolve_default_currency', side_effect=RuntimeError('no tenant')):
            ar.query.filter_by.return_value.first.return_value = None
            resp = expenses_client.post('/expenses/1/edit', data={
                'amount': '100',
                'currency': 'AED',
                'category_id': '1',
            })
        assert resp.status_code == 302


class TestExpensesDeleteCancel:
    def test_delete_without_links(self, expenses_client):
        expense = _mock_expense()
        with _expense_patches(expense=expense), \
             patch('models.Cheque') as chq, \
             patch('services.gl_service.GLService.reverse_entry'):
            chq.query.filter_by.return_value.first.return_value = None
            resp = expenses_client.post('/expenses/1/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_with_cleared_cheque_archives(self, expenses_client):
        expense = _mock_expense()
        cheque = MagicMock(status='cleared')
        archive_svc = MagicMock()
        with _expense_patches(expense=expense), \
             patch('models.Cheque') as chq, \
             patch('services.archive_service.ArchiveService', return_value=archive_svc):
            chq.query.filter_by.return_value.first.return_value = cheque
            resp = expenses_client.post('/expenses/1/delete', follow_redirects=False)
        assert resp.status_code == 302
        archive_svc.archive_record.assert_called()

    def test_cancel_with_cheque(self, expenses_client):
        expense = _mock_expense()
        cheque = MagicMock(status='pending')
        with _expense_patches(expense=expense), \
             patch('models.Cheque') as chq, \
             patch('services.gl_helpers.assert_period_open'), \
             patch('services.cheque_service.process_cheque_cancel'):
            chq.query.filter_by.return_value.first.return_value = cheque
            resp = expenses_client.post('/expenses/1/cancel', follow_redirects=False)
        assert resp.status_code == 302

    def test_cancel_without_cheque(self, expenses_client):
        expense = _mock_expense()
        with _expense_patches(expense=expense), \
             patch('models.Cheque') as chq, \
             patch('services.gl_helpers.assert_period_open'), \
             patch('utils.gl_tenant.reverse_document_gl'):
            chq.query.filter_by.return_value.first.return_value = None
            resp = expenses_client.post('/expenses/1/cancel', follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_branch_forbidden(self, expenses_client):
        with _expense_patches(expense=_mock_expense(branch_id=8), branch_scope=1):
            resp = expenses_client.post('/expenses/1/delete')
        assert resp.status_code == 403

    def test_delete_pending_cheque_removed(self, expenses_client):
        expense = _mock_expense()
        cheque = MagicMock(status='pending')
        with _expense_patches(expense=expense), \
             patch('models.Cheque') as chq, \
             patch('services.gl_service.GLService.reverse_entry'), \
             patch('services.cheque_service.process_cheque_cancel'):
            chq.query.filter_by.return_value.first.return_value = cheque
            resp = expenses_client.post('/expenses/1/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_delete_exception_redirects(self, expenses_client):
        expense = _mock_expense()
        with _expense_patches(expense=expense), \
             patch('models.Cheque') as chq, \
             patch('services.gl_service.GLService.reverse_entry', side_effect=RuntimeError('gl fail')):
            chq.query.filter_by.return_value.first.return_value = None
            resp = expenses_client.post('/expenses/1/delete', follow_redirects=False)
        assert resp.status_code == 302

    def test_cancel_branch_forbidden(self, expenses_client):
        with _expense_patches(expense=_mock_expense(branch_id=6), branch_scope=1):
            resp = expenses_client.post('/expenses/1/cancel')
        assert resp.status_code == 403

    def test_cancel_exception(self, expenses_client):
        expense = _mock_expense()
        with _expense_patches(expense=expense), \
             patch('models.Cheque') as chq, \
             patch('services.gl_helpers.assert_period_open', side_effect=RuntimeError('period closed')):
            chq.query.filter_by.return_value.first.return_value = None
            resp = expenses_client.post('/expenses/1/cancel', follow_redirects=False)
        assert resp.status_code == 302


class TestExpenseCategories:
    def test_categories_list(self, expenses_client):
        with _expense_patches():
            resp = expenses_client.get('/expenses/categories')
        assert resp.status_code == 200

    def test_create_category_json_success(self, expenses_client):
        category = type('Cat', (), {'id': 5, 'name': 'Travel', 'name_ar': 'سفر'})()
        with _expense_patches(), \
             patch('routes.expenses.ExpenseCategory', return_value=category):
            resp = expenses_client.post(
                '/expenses/categories/create',
                json={'name': 'Travel', 'name_ar': 'سفر'},
            )
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_create_category_form_success(self, expenses_client):
        with _expense_patches(), \
             patch('routes.expenses.ExpenseCategory', return_value=MagicMock(id=5)):
            resp = expenses_client.post(
                '/expenses/categories/create',
                data={'name': 'Travel', 'name_ar': 'سفر'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_create_category_validation_error_json(self, expenses_client):
        with _expense_patches(), \
             patch('routes.expenses._validate_gl_account_code', side_effect=ValueError('bad account')):
            resp = expenses_client.post(
                '/expenses/categories/create',
                json={'name': 'Bad', 'gl_account_code': '1130'},
            )
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_create_category_validation_error_form(self, expenses_client):
        with _expense_patches(), \
             patch('routes.expenses._validate_gl_account_code', side_effect=ValueError('bad account')):
            resp = expenses_client.post(
                '/expenses/categories/create',
                data={'name': 'Bad', 'gl_account_code': '1130'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_validate_gl_account_restricted_code(self):
        from routes.expenses import _validate_gl_account_code
        account = MagicMock(name='Cash', is_header=False, is_active=True)
        with patch('models.GLAccount') as gl:
            gl.query.filter_by.return_value.first.return_value = account
            with pytest.raises(ValueError, match='أصول'):
                _validate_gl_account_code('1130', 1)

    def test_validate_gl_account_inactive(self):
        from routes.expenses import _validate_gl_account_code
        account = MagicMock(name='Inactive', is_header=False, is_active=False)
        with patch('models.GLAccount') as gl:
            gl.query.filter_by.return_value.first.return_value = account
            with pytest.raises(ValueError, match='غير نشط'):
                _validate_gl_account_code('5100', 1)

    def test_validate_gl_account_wrong_prefix(self):
        from routes.expenses import _validate_gl_account_code
        account = MagicMock(name='Revenue', is_header=False, is_active=True)
        with patch('models.GLAccount') as gl:
            gl.query.filter_by.return_value.first.return_value = account
            with pytest.raises(ValueError, match='5xxx'):
                _validate_gl_account_code('4100', 1)

    def test_validate_gl_account_header_rejected(self):
        from routes.expenses import _validate_gl_account_code
        account = MagicMock(name='Header', is_header=True, is_active=True)
        with patch('models.GLAccount') as gl:
            gl.query.filter_by.return_value.first.return_value = account
            with pytest.raises(ValueError, match='رئيسي'):
                _validate_gl_account_code('5100', 1)

    def test_validate_gl_account_missing(self):
        from routes.expenses import _validate_gl_account_code
        with patch('models.GLAccount') as gl:
            gl.query.filter_by.return_value.first.return_value = None
            with pytest.raises(ValueError, match='غير موجود'):
                _validate_gl_account_code('9999', 1)

    def test_validate_gl_account_empty_code_allowed(self):
        from routes.expenses import _validate_gl_account_code
        assert _validate_gl_account_code(None, 1) is True

    def test_validate_gl_account_6990_allowed(self):
        from routes.expenses import _validate_gl_account_code
        account = MagicMock(name='Misc', is_header=False, is_active=True)
        with patch('models.GLAccount') as gl:
            gl.query.filter_by.return_value.first.return_value = account
            assert _validate_gl_account_code('6990', 1) is True


class TestExpensesArchive:
    def test_archived_list(self, expenses_client):
        archived = MagicMock(
            record_id=1,
            archived_at=datetime(2026, 1, 1),
            data={
                'expense_number': 'EXP-OLD',
                'expense_date': '2026-01-01T00:00:00',
                'category_name': 'Ops',
                'description': 'Old',
                'amount': '50',
                'currency': 'AED',
                'payment_method': 'cash',
            },
        )
        q = _archived_records_query([archived])
        with _expense_patches(), patch('routes.expenses.db.session.query', return_value=q), \
             patch('routes.expenses.get_active_tenant_id', return_value=1):
            resp = expenses_client.get('/expenses/archived')
        assert resp.status_code == 200

    def test_archived_list_populates_items(self, expenses_client):
        archived = MagicMock(
            record_id=3,
            archived_at=datetime(2026, 3, 1),
            data={
                'expense_number': 'EXP-ARC',
                'expense_date': '2026-03-01T10:00:00',
                'category_name': 'Travel',
                'description': 'Trip',
                'amount': '120',
                'currency': 'AED',
                'payment_method': 'card',
            },
        )
        q = _archived_records_query([archived])
        with _expense_patches(), patch('routes.expenses.db.session.query', return_value=q), \
             patch('routes.expenses.get_active_tenant_id', return_value=1):
            resp = expenses_client.get('/expenses/archived')
        assert resp.status_code == 200
        assert archived.data.get('expense_number') == 'EXP-ARC'

    def test_archive_expense(self, expenses_client):
        expense = _mock_expense()
        archive_svc = MagicMock()
        with _expense_patches(expense=expense), \
             patch('services.archive_service.ArchiveService', return_value=archive_svc):
            resp = expenses_client.post('/expenses/1/archive', follow_redirects=False)
        assert resp.status_code == 302

    def test_restore_expense(self, expenses_client):
        archived = MagicMock()
        with _expense_patches(), \
             patch('models.ArchivedRecord') as ar:
            ar.query.filter_by.return_value.first_or_404.return_value = archived
            resp = expenses_client.post('/expenses/1/restore', follow_redirects=False)
        assert resp.status_code == 302

    def test_archived_list_datetime_object(self, expenses_client):
        archived = MagicMock(
            record_id=2,
            archived_at=datetime(2026, 2, 1),
            data={
                'expense_number': 'EXP-DT',
                'expense_date': date(2026, 1, 15),
                'category_name': 'Ops',
                'description': 'Obj date',
                'amount': '25',
                'currency': 'AED',
                'payment_method': 'cash',
            },
        )
        q = _archived_records_query([archived])
        with _expense_patches(), patch('routes.expenses.db.session.query', return_value=q), \
             patch('routes.expenses.get_active_tenant_id', return_value=1):
            resp = expenses_client.get('/expenses/archived')
        assert resp.status_code == 200

    def test_archive_branch_forbidden(self, expenses_client):
        with _expense_patches(expense=_mock_expense(branch_id=4), branch_scope=1):
            resp = expenses_client.post('/expenses/1/archive')
        assert resp.status_code == 403

    def test_archive_exception(self, expenses_client):
        expense = _mock_expense()
        with _expense_patches(expense=expense), \
             patch('services.archive_service.ArchiveService', side_effect=RuntimeError('archive fail')):
            resp = expenses_client.post('/expenses/1/archive', follow_redirects=False)
        assert resp.status_code == 302

    def test_restore_exception(self, expenses_client):
        archived = MagicMock()
        with _expense_patches(), \
             patch('models.ArchivedRecord') as ar, \
             patch('routes.expenses.db.session.commit', side_effect=RuntimeError('db')):
            ar.query.filter_by.return_value.first_or_404.return_value = archived
            resp = expenses_client.post('/expenses/1/restore', follow_redirects=False)
        assert resp.status_code == 302


class TestArchivedExpenseRow:
    def test_archived_expense_row_parses_string_date(self):
        from routes.expenses import _archived_expense_row
        archived = MagicMock(
            record_id=5,
            archived_at=datetime(2026, 4, 1),
            data={
                'expense_number': 'EXP-5',
                'expense_date': '2026-04-01T08:00:00',
                'amount': '75',
            },
        )
        row = _archived_expense_row(archived)
        assert row['expense_number'] == 'EXP-5'
        assert row['amount'] == 75.0

    def test_archived_expense_row_handles_missing_data(self):
        from routes.expenses import _archived_expense_row
        archived = MagicMock(record_id=6, archived_at=datetime(2026, 4, 2), data=None)
        row = _archived_expense_row(archived)
        assert row['id'] == 6
        assert row['amount'] == 0.0


class TestBuildExpenseGlLines:
    def test_cheque_payment_lines(self):
        from routes.expenses import _build_expense_gl_lines
        expense = _mock_expense(payment_method='cheque')
        lines = _build_expense_gl_lines(expense, tenant_id=1)
        assert lines[1]['account'] == '2120'
        assert lines[1]['concept_code'] == 'DEFERRED_CHEQUES_PAYABLE'

    def test_header_account_fallback(self):
        from routes.expenses import _build_expense_gl_lines
        expense = _mock_expense(category=MagicMock(gl_account_code='5100'))
        header = MagicMock(is_header=True)
        with patch('models.GLAccount') as gl, \
             patch('services.gl_service.GLService.get_payment_credit_account', return_value='1101'), \
             patch('services.gl_service.GLService.get_payment_credit_concept', return_value='CASH'):
            gl.query.filter_by.return_value.first.return_value = header
            lines = _build_expense_gl_lines(expense, tenant_id=1)
        assert lines[0]['account'] == '6990'
        assert lines[0]['concept_code'] == 'MISC_EXPENSE'
