"""
Agent-2 coverage wave: drive routes/advanced_ledger.py and routes/ai.py to 100%.

Targets the residual uncovered branches not exercised by the existing suites
(test_advanced_ledger_routes.py / test_ai_routes.py / test_ai_routes_chunk1.py):

* advanced_ledger: missing-account warnings, GET render path, currency fallback,
  and the advanced-expense exception handler.
* ai: before/after-request access-policy branches, the chat owner-execute elif,
  internal context helpers, the full interactive wizard branches (option starts,
  "back" exits, validation errors, create/exception paths, list + search options),
  colon-syntax commands, and the Excel import/training helpers.
"""
from contextlib import ExitStack, contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import io
import numpy as np
import pandas as pd

from tests.unit.routes.test_advanced_ledger_routes import (
    _advanced_ledger_patches,
    advanced_ledger_client,
)


def _obj(**attrs):
    obj = MagicMock()
    for key, value in attrs.items():
        setattr(obj, key, value)
    return obj


# ===========================================================================
# advanced_ledger.py residual branches
# ===========================================================================
class TestAdvancedLedgerWave:
    def test_add_customs_tax_missing_account(self, advanced_ledger_client):
        """POST without gl_account_id -> warning flash + re-render (81-82)."""
        with _advanced_ledger_patches() as mocks:
            resp = advanced_ledger_client.post(
                '/ledger/advanced/customs-taxes/add',
                data={'name': 'NoAcct', 'name_ar': 'بدون حساب'},
            )
        assert resp.status_code == 200
        mocks['render'].assert_called()

    def test_add_expense_category_get(self, advanced_ledger_client):
        """GET render path of add_expense_category (175)."""
        with _advanced_ledger_patches() as mocks:
            resp = advanced_ledger_client.get('/ledger/advanced/expense-categories/add')
        assert resp.status_code == 200
        mocks['render'].assert_called()

    def test_add_advanced_expense_currency_fallback(self, advanced_ledger_client):
        """resolve_default_currency raises -> system default fallback (204-205)."""
        expense = MagicMock(expense_number='EXP-9', id=9)
        expense.calculate_taxes = MagicMock()
        with _advanced_ledger_patches(categories=[MagicMock(id=1)]), \
             patch('routes.advanced_ledger.AdvancedExpense', return_value=expense), \
             patch('routes.advanced_ledger.resolve_default_currency', side_effect=RuntimeError('no tenant')), \
             patch('routes.advanced_ledger.get_system_default_currency', return_value='AED') as gsd:
            resp = advanced_ledger_client.post('/ledger/advanced/advanced-expenses/add', data={
                'expense_date': '2026-06-01',
                'description': 'Fuel',
                'category_id': '1',
                'amount': '100',
                'exchange_rate': '1',
                'amount_aed': '100',
            }, follow_redirects=False)
        assert resp.status_code == 302
        gsd.assert_called_once()

    def test_add_advanced_expense_exception(self, advanced_ledger_client):
        """Exception inside add_advanced_expense -> handler + re-render (246-250)."""
        with _advanced_ledger_patches(categories=[MagicMock(id=1)]) as mocks, \
             patch('routes.advanced_ledger.resolve_default_currency', return_value='AED'), \
             patch('routes.advanced_ledger.AdvancedExpense', side_effect=RuntimeError('boom')), \
             patch('utils.error_messages.ErrorMessages.unexpected_error', return_value='err'), \
             patch('models.Supplier.query') as sup_q:
            sup_q.filter_by.return_value.with_entities.return_value.all.return_value = []
            resp = advanced_ledger_client.post('/ledger/advanced/advanced-expenses/add', data={
                'expense_date': '2026-06-01',
                'category_id': '1',
                'amount': '100',
            })
        assert resp.status_code == 200
        mocks['render'].assert_called()


# ===========================================================================
# ai.py - before/after request access policy
# ===========================================================================
def _state(**overrides):
    base = {
        'allowed': True,
        'global_enabled': True,
        'tenant_enabled': True,
        'tenant_id': 1,
        'reason': None,
        'is_platform_user': True,
        'ai_level': 'execute',
    }
    base.update(overrides)
    return base


@contextmanager
def _ai_state_client(app_factory, mock_user, state):
    from routes.ai_routes import ai_bp
    app = app_factory(ai_bp)
    patches = [
        patch('flask_login.utils._get_user', return_value=mock_user),
        patch('routes.ai_routes.get_ai_access_state', return_value=state),
        patch('routes.ai_routes.chat.get_ai_access_state', return_value=state),
        patch('utils.auth_helpers.is_global_owner_user', return_value=True),
        patch('utils.decorators.is_global_owner_user', return_value=True),
        patch('utils.decorators.is_admin_surface_user', return_value=True),
        patch('extensions.limiter.limit', return_value=lambda f: f),
        patch('utils.tenanting.get_active_tenant_id', return_value=1),
        patch('services.logging_core.LoggingCore.log_audit'),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield app.test_client()


class TestAiAccessPolicy:
    def test_insufficient_level_redirect(self, app_factory, mock_user):
        """Non-platform basic user hitting advanced endpoint (non-JSON) -> redirect (70-71)."""
        state = _state(is_platform_user=False, ai_level='basic')
        with _ai_state_client(app_factory, mock_user, state) as client:
            resp = client.get('/ai/predict-sales')
        assert resp.status_code == 302

    def test_denied_redirect_non_json(self, app_factory, mock_user):
        """Disabled AI, non-JSON request -> flash + redirect (89-90)."""
        state = _state(allowed=False, is_platform_user=False, reason='tenant_disabled')
        with _ai_state_client(app_factory, mock_user, state) as client:
            resp = client.post('/ai/chat', data='hi', content_type='text/plain')
        assert resp.status_code == 302

    def test_after_request_non_ai_endpoint(self, app_factory):
        """endpoint not starting with 'ai.' -> after_request passthrough (99)."""
        from routes.ai_routes import ai_bp, _audit_ai_requests
        app = app_factory(ai_bp)
        with app.test_request_context('/'):
            resp = MagicMock(status_code=200)
            assert _audit_ai_requests(resp) is resp

    def test_after_request_audit_failure_swallowed(self, ai_client):
        """log_audit raising in after_request is swallowed (119-120)."""
        with patch('routes.ai_routes.LoggingCore.log_audit', side_effect=RuntimeError('audit')), \
             patch('routes.ai_routes.AIService.get_neural_status', return_value={'ok': True}):
            resp = ai_client.get('/ai/neural-status')
        assert resp.status_code == 200


# ===========================================================================
# ai.py - chat owner-execute elif
# ===========================================================================
class TestChatOwnerExecuteElif:
    def test_owner_without_execute_level_uses_wizard(self, app_factory, mock_user):
        """can_execute_mutations False but owner -> _process_user_action (465)."""
        mock_user.is_owner = True
        state = _state(is_platform_user=False, ai_level='advanced')
        with _ai_state_client(app_factory, mock_user, state) as client, \
             patch('routes.ai_routes.chat._process_user_action', return_value='wizard-reply') as proc, \
             patch('routes.ai_routes.chat.AIService.chat_response', return_value='fallback'):
            resp = client.post('/ai/chat', json={'message': 'افعل شيئا'})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['action_executed'] is True
        proc.assert_called_once()


# ===========================================================================
# ai.py - internal context helpers
# ===========================================================================
class TestConversationHelpers:
    def test_autosave_pop(self):
        from routes.ai_routes import _conversation_ctx
        with patch('routes.ai_routes.shared._get_conversation_context', return_value={'x': 1}), \
             patch('routes.ai_routes._set_conversation_context') as setter:
            ctx = _conversation_ctx(1, 1)
            assert ctx.pop('x') == 1
        setter.assert_called()

    def test_conversation_set(self):
        from routes.ai_routes import _conversation_set
        with patch('extensions.db.session.add'), \
             patch('extensions.db.session.commit'):
            _conversation_set(7, {'a': 1}, 2)

    def test_conversation_clear(self):
        from routes.ai_routes import _conversation_clear
        with patch('extensions.db.session.commit'):
            _conversation_clear(7, 2)


# ===========================================================================
# ai.py - interactive wizard (_process_user_action) residual branches
# ===========================================================================
@contextmanager
def _wizard_env(ctx):
    with patch('routes.ai_routes.actions._conversation_ctx', return_value=ctx), \
         patch('routes.ai_routes.actions.get_active_tenant_id', return_value=1), \
         patch('routes.ai_routes.actions.train_local_ai'), \
         patch('routes.ai_routes.actions.assign_tenant_id'), \
         patch('extensions.db.session'):
        yield


def _run(message, user, ctx):
    from routes.ai_routes import _process_user_action
    with _wizard_env(ctx):
        return _process_user_action(message, user)


class TestBalanceWizardWave:
    def test_rasid_option_one_start(self, mock_user):
        ctx = {'last_action': 'رصيد'}
        result = _run('1', mock_user, ctx)
        assert ctx['option'] == '1'
        assert 'تعديل رصيد العميل' in result


class TestCustomerWizardWave:
    def test_help_text_step_three(self, mock_user):
        ctx = {'last_action': 'عميل', 'option': '1', 'step': 3, 'data': {}}
        result = _run('مساعدة', mock_user, ctx)
        assert 'العنوان' in result

    def test_help_text_step_two(self, mock_user):
        ctx = {'last_action': 'عميل', 'option': '1', 'step': 2, 'data': {}}
        result = _run('مساعدة', mock_user, ctx)
        assert 'رقم الهاتف' in result

    def test_option_two_empty(self, mock_user):
        ctx = {'last_action': 'عميل'}
        chain = MagicMock()
        chain.all.return_value = []
        with patch('models.customer.Customer') as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run('2', mock_user, ctx)
        assert 'لا يوجد عملاء' in result


class TestProductWizardWave:
    def test_option_one_start(self, mock_user):
        ctx = {'last_action': 'منتج'}
        result = _run('1', mock_user, ctx)
        assert ctx['option'] == '1'
        assert 'اسم المنتج' in result

    def test_back_exit(self, mock_user):
        ctx = {'last_action': 'منتج', 'option': '1', 'step': 1, 'data': {}}
        result = _run('عودة', mock_user, ctx)
        assert 'العودة للقائمة الرئيسية' in result

    def test_step_four_exception(self, mock_user):
        ctx = {'last_action': 'منتج', 'option': '1', 'step': 4,
               'data': {'name': 'A', 'part_number': 'B', 'price': 10.0}}
        with patch('models.product.Product', side_effect=RuntimeError('db fail')):
            result = _run('10', mock_user, ctx)
        assert 'خطأ في إنشاء المنتج' in result

    def test_option_two_empty(self, mock_user):
        ctx = {'last_action': 'منتج'}
        chain = MagicMock()
        chain.all.return_value = []
        with patch('models.product.Product') as Product:
            Product.query.filter_by.return_value = chain
            result = _run('2', mock_user, ctx)
        assert 'لا يوجد منتجات' in result

    def test_option_three_search(self, mock_user):
        ctx = {'last_action': 'منتج'}
        result = _run('3', mock_user, ctx)
        assert 'البحث عن منتج' in result


class TestInvoiceWizardWave:
    def test_option_one_start(self, mock_user):
        ctx = {'last_action': 'فاتورة'}
        _result = _run('1', mock_user, ctx)
        assert ctx['option'] == '1'

    def test_back_exit(self, mock_user):
        ctx = {'last_action': 'فاتورة', 'option': '1', 'step': 1, 'data': {}}
        result = _run('عودة', mock_user, ctx)
        assert result

    def test_step_one_no_customers(self, mock_user):
        ctx = {'last_action': 'فاتورة', 'option': '1', 'step': 1, 'data': {}}
        chain = MagicMock()
        chain.limit.return_value.all.return_value = []
        with patch('models.customer.Customer') as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run('اعرض العملاء', mock_user, ctx)
        assert 'لا يوجد عملاء' in result

    def test_step_two_no_products(self, mock_user):
        ctx = {'last_action': 'فاتورة', 'option': '1', 'step': 2, 'data': {'customer_name': 'C'}}
        chain = MagicMock()
        chain.limit.return_value.all.return_value = []
        with patch('models.product.Product') as Product:
            Product.query.filter_by.return_value = chain
            result = _run('list', mock_user, ctx)
        assert 'لا يوجد منتجات' in result

    def test_step_two_product_not_found(self, mock_user):
        ctx = {'last_action': 'فاتورة', 'option': '1', 'step': 2, 'data': {'customer_name': 'C'}}
        chain = MagicMock()
        chain.first.return_value = None
        with patch('models.product.Product') as Product:
            Product.query.filter_by.return_value = chain
            result = _run('Ghost', mock_user, ctx)
        assert 'المنتج غير موجود' in result

    def test_option_two_empty(self, mock_user):
        ctx = {'last_action': 'فاتورة'}
        chain = MagicMock()
        chain.all.return_value = []
        with patch('models.sale.Sale') as Sale:
            Sale.query.filter_by.return_value = chain
            result = _run('2', mock_user, ctx)
        assert 'لا يوجد فواتير' in result

    def test_option_three_search(self, mock_user):
        ctx = {'last_action': 'فاتورة'}
        result = _run('3', mock_user, ctx)
        assert 'البحث عن فاتورة' in result


class TestReceiveWizardWave:
    def test_option_one_start(self, mock_user):
        ctx = {'last_action': 'استلام'}
        _result = _run('1', mock_user, ctx)
        assert ctx['option'] == '1'

    def test_back_exit(self, mock_user):
        ctx = {'last_action': 'استلام', 'option': '1', 'step': 1, 'data': {}}
        result = _run('عودة', mock_user, ctx)
        assert result

    def test_customer_not_found(self, mock_user):
        ctx = {'last_action': 'استلام', 'option': '1', 'step': 1, 'data': {}}
        chain = MagicMock()
        chain.first.return_value = None
        with patch('models.customer.Customer') as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run('Ghost', mock_user, ctx)
        assert 'العميل غير موجود' in result

    def test_step_three_exception(self, mock_user):
        ctx = {'last_action': 'استلام', 'option': '1', 'step': 3,
               'data': {'customer_id': 1, 'customer_name': 'C', 'amount': 100}}
        with patch('models.payment.Payment', side_effect=RuntimeError('db fail')):
            result = _run('cash', mock_user, ctx)
        assert 'خطأ في تسجيل الدفعة' in result


class TestGiveWizardWave:
    def test_option_one_start(self, mock_user):
        ctx = {'last_action': 'إعطاء'}
        _result = _run('1', mock_user, ctx)
        assert ctx['option'] == '1'

    def test_back_exit(self, mock_user):
        ctx = {'last_action': 'إعطاء', 'option': '1', 'step': 1, 'data': {}}
        result = _run('عودة', mock_user, ctx)
        assert result

    def test_customer_not_found(self, mock_user):
        ctx = {'last_action': 'إعطاء', 'option': '1', 'step': 1, 'data': {}}
        chain = MagicMock()
        chain.first.return_value = None
        with patch('models.customer.Customer') as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run('Ghost', mock_user, ctx)
        assert 'العميل غير موجود' in result

    def test_step_two_invalid_amount(self, mock_user):
        ctx = {'last_action': 'إعطاء', 'option': '1', 'step': 2, 'data': {'customer_id': 1}}
        result = _run('not-a-number', mock_user, ctx)
        assert 'خطأ في إدخال المبلغ' in result

    def test_step_three_exception(self, mock_user):
        ctx = {'last_action': 'إعطاء', 'option': '1', 'step': 3,
               'data': {'customer_id': 1, 'customer_name': 'C', 'amount': 50, 'reason': 'r'}}
        with patch('models.payment.Payment', side_effect=RuntimeError('db fail')):
            result = _run('refund', mock_user, ctx)
        assert 'خطأ في تسجيل الدفعة' in result


class TestExpenseWizardWave:
    def test_option_one_start(self, mock_user):
        ctx = {'last_action': 'مصروف'}
        _result = _run('1', mock_user, ctx)
        assert ctx['option'] == '1'

    def test_back_exit(self, mock_user):
        ctx = {'last_action': 'مصروف', 'option': '1', 'step': 1, 'data': {}}
        result = _run('عودة', mock_user, ctx)
        assert result

    def test_step_two_invalid_amount(self, mock_user):
        ctx = {'last_action': 'مصروف', 'option': '1', 'step': 2, 'data': {'description': 'x'}}
        result = _run('bad', mock_user, ctx)
        assert 'خطأ في إدخال المبلغ' in result

    def test_step_three_exception(self, mock_user):
        ctx = {'last_action': 'مصروف', 'option': '1', 'step': 3,
               'data': {'description': 'x', 'amount': 100}}
        with patch('models.expense.Expense', side_effect=RuntimeError('db fail')), \
             patch('utils.helpers.generate_number', return_value='EXP-1'):
            result = _run('cat', mock_user, ctx)
        assert 'خطأ في إنشاء المصروف' in result

    def test_option_three_search_prompt(self, mock_user):
        ctx = {'last_action': 'مصروف'}
        result = _run('3', mock_user, ctx)
        assert 'البحث عن مصروف' in result


class TestSupplierWizardWave:
    def test_option_one_start(self, mock_user):
        ctx = {'last_action': 'مورد'}
        _result = _run('1', mock_user, ctx)
        assert ctx['option'] == '1'

    def test_back_exit(self, mock_user):
        ctx = {'last_action': 'مورد', 'option': '1', 'step': 1, 'data': {}}
        result = _run('عودة', mock_user, ctx)
        assert result

    def test_step_four_valid(self, mock_user):
        ctx = {'last_action': 'مورد', 'option': '1', 'step': 4,
               'data': {'name': 'S', 'phone': '1', 'address': 'A'}}
        _result = _run('5000', mock_user, ctx)
        assert ctx['step'] == 5

    def test_step_four_invalid(self, mock_user):
        ctx = {'last_action': 'مورد', 'option': '1', 'step': 4,
               'data': {'name': 'S', 'phone': '1', 'address': 'A'}}
        result = _run('abc', mock_user, ctx)
        assert 'خطأ في إدخال الرصيد' in result

    def test_step_five_create(self, mock_user):
        ctx = {'last_action': 'مورد', 'option': '1', 'step': 5,
               'data': {'name': 'S', 'phone': '1', 'address': 'A', 'initial_balance': 5000}}
        with patch('models.supplier.Supplier', return_value=_obj(id=2)):
            result = _run('تخطي', mock_user, ctx)
        assert 'تم إنشاء المورد' in result

    def test_step_five_exception(self, mock_user):
        ctx = {'last_action': 'مورد', 'option': '1', 'step': 5,
               'data': {'name': 'S', 'phone': '1', 'address': 'A', 'initial_balance': 0}}
        with patch('models.supplier.Supplier', side_effect=RuntimeError('db fail')):
            result = _run('123', mock_user, ctx)
        assert 'خطأ في إنشاء المورد' in result

    def test_option_two_empty(self, mock_user):
        ctx = {'last_action': 'مورد'}
        chain = MagicMock()
        chain.all.return_value = []
        with patch('models.supplier.Supplier') as Supplier:
            Supplier.query.filter_by.return_value = chain
            result = _run('2', mock_user, ctx)
        assert 'لا يوجد موردين' in result

    def test_option_three_search(self, mock_user):
        ctx = {'last_action': 'مورد'}
        result = _run('3', mock_user, ctx)
        assert 'البحث عن مورد' in result


class TestPurchaseWizardWave:
    def test_option_one_start(self, mock_user):
        ctx = {'last_action': 'مشتريات'}
        _result = _run('1', mock_user, ctx)
        assert ctx['option'] == '1'

    def test_back_exit(self, mock_user):
        ctx = {'last_action': 'مشتريات', 'option': '1', 'step': 1, 'data': {}}
        result = _run('عودة', mock_user, ctx)
        assert result

    def test_supplier_not_found(self, mock_user):
        ctx = {'last_action': 'مشتريات', 'option': '1', 'step': 1, 'data': {}}
        chain = MagicMock()
        chain.first.return_value = None
        with patch('models.supplier.Supplier') as Supplier:
            Supplier.query.filter_by.return_value = chain
            result = _run('Ghost', mock_user, ctx)
        assert 'المورد غير موجود' in result

    def test_product_not_found(self, mock_user):
        ctx = {'last_action': 'مشتريات', 'option': '1', 'step': 2,
               'data': {'supplier_id': 1, 'supplier_name': 'S'}}
        chain = MagicMock()
        chain.first.return_value = None
        with patch('models.product.Product') as Product:
            Product.query.filter_by.return_value = chain
            result = _run('Ghost', mock_user, ctx)
        assert 'المنتج غير موجود' in result

    def test_step_three_invalid_quantity(self, mock_user):
        ctx = {'last_action': 'مشتريات', 'option': '1', 'step': 3,
               'data': {'supplier_id': 1, 'product_id': 2}}
        result = _run('bad', mock_user, ctx)
        assert 'خطأ في إدخال الكمية' in result

    def test_step_four_exception(self, mock_user):
        ctx = {'last_action': 'مشتريات', 'option': '1', 'step': 4,
               'data': {'supplier_id': 1, 'supplier_name': 'S', 'product_id': 2,
                        'product_name': 'P', 'quantity': 5}}
        with patch('models.purchase.Purchase', side_effect=RuntimeError('db fail')):
            result = _run('40', mock_user, ctx)
        assert 'خطأ في إنشاء المشتريات' in result

    def test_option_two_with_items(self, mock_user):
        ctx = {'last_action': 'مشتريات'}
        purchase = _obj(id=1, total_amount=Decimal('500'), supplier=_obj(name='Sup'))
        chain = MagicMock()
        chain.all.return_value = [purchase]
        with patch('models.purchase.Purchase') as Purchase:
            Purchase.query.filter_by.return_value = chain
            result = _run('2', mock_user, ctx)
        assert '#1' in result

    def test_option_three_search(self, mock_user):
        ctx = {'last_action': 'مشتريات'}
        result = _run('3', mock_user, ctx)
        assert 'البحث عن مشتريات' in result


class TestChequeWizardWave:
    def test_option_one_start(self, mock_user):
        ctx = {'last_action': 'شيك'}
        _result = _run('1', mock_user, ctx)
        assert ctx['option'] == '1'

    def test_back_exit(self, mock_user):
        ctx = {'last_action': 'شيك', 'option': '1', 'step': 1, 'data': {}}
        result = _run('عودة', mock_user, ctx)
        assert result

    def test_invalid_type(self, mock_user):
        ctx = {'last_action': 'شيك', 'option': '1', 'step': 1, 'data': {}}
        result = _run('غير معروف', mock_user, ctx)
        assert 'نوع الشيك غير صحيح' in result

    def test_step_three_invalid_amount(self, mock_user):
        ctx = {'last_action': 'شيك', 'option': '1', 'step': 3,
               'data': {'cheque_type': 'incoming', 'cheque_number': 'C1'}}
        result = _run('bad', mock_user, ctx)
        assert 'خطأ في إدخال المبلغ' in result

    def test_step_four_exception(self, mock_user):
        ctx = {'last_action': 'شيك', 'option': '1', 'step': 4,
               'data': {'cheque_type': 'incoming', 'cheque_number': 'C1', 'amount': 5000}}
        with patch('models.cheque.Cheque', side_effect=RuntimeError('db fail')):
            result = _run('2026-12-31', mock_user, ctx)
        assert 'خطأ في إنشاء الشيك' in result

    def test_option_three_search(self, mock_user):
        ctx = {'last_action': 'شيك'}
        result = _run('3', mock_user, ctx)
        assert 'البحث عن شيك' in result


class TestLedgerWizardWave:
    def test_option_one_with_entries(self, mock_user):
        ctx = {'last_action': 'دفتر'}
        entry = _obj(id=1, description='d', debit_amount=Decimal('10'))
        entry.entry_date = _obj(strftime=lambda f: '2026-01-01')
        with patch('models.gl.GLJournalEntry') as GL:
            GL.query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [entry]
            result = _run('1', mock_user, ctx)
        assert 'دفتر الأستاذ' in result

    def test_option_one_empty(self, mock_user):
        ctx = {'last_action': 'دفتر'}
        with patch('models.gl.GLJournalEntry') as GL:
            GL.query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
            result = _run('1', mock_user, ctx)
        assert 'لا يوجد قيود' in result

    def test_option_two_with_entries(self, mock_user):
        ctx = {'last_action': 'دفتر'}
        entry = _obj(id=2, description='d2', debit_amount=Decimal('20'))
        entry.entry_date = _obj(strftime=lambda f: '2026-02-01')
        with patch('models.gl.GLJournalEntry') as GL:
            GL.query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [entry]
            result = _run('2', mock_user, ctx)
        assert 'القيود المحاسبية' in result

    def test_option_two_empty(self, mock_user):
        ctx = {'last_action': 'دفتر'}
        with patch('models.gl.GLJournalEntry') as GL:
            GL.query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
            result = _run('2', mock_user, ctx)
        assert 'لا يوجد قيود' in result

    def test_option_three_search(self, mock_user):
        ctx = {'last_action': 'دفتر'}
        result = _run('3', mock_user, ctx)
        assert 'البحث عن قيد' in result


class TestWarehouseWizardWave:
    def test_option_one_with_warehouses(self, mock_user):
        ctx = {'last_action': 'مستودع'}
        wh = _obj(name='Main', location='Dubai')
        with patch('models.Warehouse') as Warehouse:
            Warehouse.query.filter_by.return_value.all.return_value = [wh]
            result = _run('1', mock_user, ctx)
        assert 'المستودعات' in result

    def test_option_one_empty(self, mock_user):
        ctx = {'last_action': 'مستودع'}
        with patch('models.Warehouse') as Warehouse:
            Warehouse.query.filter_by.return_value.all.return_value = []
            result = _run('1', mock_user, ctx)
        assert 'لا يوجد مستودعات' in result

    def test_option_two_empty(self, mock_user):
        ctx = {'last_action': 'مستودع'}
        with patch('models.product.Product') as Product:
            Product.query.filter_by.return_value.all.return_value = []
            result = _run('2', mock_user, ctx)
        assert 'لا يوجد منتجات في المخزون' in result

    def test_option_three_search(self, mock_user):
        ctx = {'last_action': 'مستودع'}
        result = _run('3', mock_user, ctx)
        assert 'البحث عن مستودع' in result

    def test_option_four_inventory(self, mock_user):
        ctx = {'last_action': 'مستودع'}
        result = _run('4', mock_user, ctx)
        assert 'إدارة المخزون' in result


class TestUserWizardWave:
    def test_step_one_username(self, mock_user):
        ctx = {'last_action': 'مستخدم', 'option': '1', 'step': 1, 'data': {}}
        _result = _run('ahmed', mock_user, ctx)
        assert ctx['step'] == 2

    def test_step_two_password(self, mock_user):
        ctx = {'last_action': 'مستخدم', 'option': '1', 'step': 2, 'data': {'username': 'ahmed'}}
        _result = _run('Pass@123', mock_user, ctx)
        assert ctx['step'] == 3

    def test_back_exit(self, mock_user):
        ctx = {'last_action': 'مستخدم', 'option': '1', 'step': 1, 'data': {}}
        result = _run('عودة', mock_user, ctx)
        assert result

    def test_step_three_invalid_role(self, mock_user):
        ctx = {'last_action': 'مستخدم', 'option': '1', 'step': 3,
               'data': {'username': 'ahmed', 'password': 'p'}}
        result = _run('superhero', mock_user, ctx)
        assert 'الدور غير صحيح' in result

    def test_step_three_valid_role(self, mock_user):
        ctx = {'last_action': 'مستخدم', 'option': '1', 'step': 3,
               'data': {'username': 'ahmed', 'password': 'p'}}
        _result = _run('admin', mock_user, ctx)
        assert ctx['step'] == 4

    def test_step_four_create(self, mock_user):
        ctx = {'last_action': 'مستخدم', 'option': '1', 'step': 4,
               'data': {'username': 'ahmed', 'password': 'Pass@123', 'role': 'admin'}}
        with patch('models.user.User', return_value=_obj(id=3)), \
             patch('utils.password_validator.PasswordValidator.validate', return_value=(True, [])):
            result = _run('تخطي', mock_user, ctx)
        assert 'تم إنشاء المستخدم' in result

    def test_step_four_exception(self, mock_user):
        ctx = {'last_action': 'مستخدم', 'option': '1', 'step': 4,
               'data': {'username': 'ahmed', 'password': 'weak', 'role': 'admin'}}
        with patch('utils.password_validator.PasswordValidator.validate', return_value=(False, ['too weak'])):
            result = _run('a@b.com', mock_user, ctx)
        assert 'خطأ في إنشاء المستخدم' in result

    def test_option_two_empty(self, mock_user):
        ctx = {'last_action': 'مستخدم'}
        chain = MagicMock()
        chain.all.return_value = []
        with patch('utils.tenanting.scoped_user_query', return_value=chain):
            result = _run('2', mock_user, ctx)
        assert 'لا يوجد مستخدمين' in result

    def test_option_three_search(self, mock_user):
        ctx = {'last_action': 'مستخدم'}
        result = _run('3', mock_user, ctx)
        assert 'البحث عن مستخدم' in result

    def test_option_four_permissions(self, mock_user):
        ctx = {'last_action': 'مستخدم'}
        result = _run('4', mock_user, ctx)
        assert 'صلاحيات' in result


class TestColonCommandsWave:
    def test_invoice_colon_product_not_found(self, mock_user):
        ctx = {}
        cust_chain = MagicMock()
        cust_chain.first.return_value = _obj(id=1, name='C')
        prod_chain = MagicMock()
        prod_chain.first.return_value = None
        with patch('models.Customer') as Customer, patch('models.Product') as Product:
            Customer.query.filter_by.return_value = cust_chain
            Product.query.filter_by.return_value = prod_chain
            result = _run('فاتورة: C, Ghost, 1, cash', mock_user, ctx)
        assert 'غير موجود' in result

    def test_payment_colon_success(self, mock_user):
        ctx = {}
        customer = _obj(id=1, name='PayC', balance=Decimal('0'))
        customer.apply_receipt = MagicMock()
        chain = MagicMock()
        chain.first.return_value = customer
        with patch('models.Customer') as Customer, \
             patch('models.Payment', return_value=_obj(id=5)), \
             patch('utils.helpers.generate_number', return_value='PAY-1'):
            Customer.query.filter_by.return_value = chain
            result = _run('دفعة: PayC, 500, cash', mock_user, ctx)
        assert 'تم تسجيل الدفعة' in result

    def test_payment_colon_missing_customer(self, mock_user):
        ctx = {}
        chain = MagicMock()
        chain.first.return_value = None
        with patch('models.Customer') as Customer, \
             patch('models.Payment'), \
             patch('utils.helpers.generate_number', return_value='PAY-1'):
            Customer.query.filter_by.return_value = chain
            result = _run('دفعة: Ghost, 500, cash', mock_user, ctx)
        assert 'غير موجود' in result

    def test_balance_colon_success(self, mock_user):
        ctx = {}
        customer = _obj(id=1, name='Bal', balance=Decimal('100'))
        customer.set_balance = MagicMock()
        chain = MagicMock()
        chain.first.return_value = customer
        with patch('models.Customer') as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run('رصيد: Bal, 1000', mock_user, ctx)
        assert 'تم تعديل رصيد العميل' in result

    def test_balance_colon_missing_customer(self, mock_user):
        ctx = {}
        chain = MagicMock()
        chain.first.return_value = None
        with patch('models.Customer') as Customer:
            Customer.query.filter_by.return_value = chain
            result = _run('رصيد: Ghost, 1000', mock_user, ctx)
        assert 'غير موجود' in result

    def test_show_balance_colon_missing(self, mock_user):
        ctx = {}
        chain = MagicMock()
        chain.first.return_value = None
        with patch('models.Customer') as Customer, patch('models.Payment'):
            Customer.query.filter_by.return_value = chain
            result = _run('عرض رصيد: Ghost', mock_user, ctx)
        assert 'غير موجود' in result

    def test_show_balance_colon_with_payments(self, mock_user):
        ctx = {}
        customer = _obj(id=1, name='ShowC', balance=Decimal('250'), phone='1', address='A')
        cust_chain = MagicMock()
        cust_chain.first.return_value = customer
        payment = _obj(amount_aed=Decimal('100'), payment_method='cash')
        payment.payment_date = _obj(strftime=lambda f: '2026-01-01')
        pay_chain = MagicMock()
        pay_chain.order_by.return_value.limit.return_value.all.return_value = [payment]
        with patch('models.Customer') as Customer, patch('models.Payment') as Payment:
            Customer.query.filter_by.return_value = cust_chain
            Payment.query.filter_by.return_value = pay_chain
            result = _run('عرض رصيد: ShowC', mock_user, ctx)
        assert 'آخر 5 دفعات' in result

    def test_give_colon_missing_customer(self, mock_user):
        ctx = {}
        chain = MagicMock()
        chain.first.return_value = None
        with patch('models.Customer') as Customer, patch('models.Payment'):
            Customer.query.filter_by.return_value = chain
            result = _run('إعطاء: Ghost, 100, refund', mock_user, ctx)
        assert 'غير موجود' in result


class TestProcessUserActionMisc:
    def test_unmatched_returns_none(self, mock_user):
        assert _run('zzz random text here', mock_user, {}) is None

    def test_logging_failure_swallowed(self, mock_user):
        from routes.ai_routes import _process_user_action
        with patch('routes.ai_routes.actions._conversation_ctx', side_effect=RuntimeError('boom')), \
             patch('routes.ai_routes.actions.get_active_tenant_id', return_value=1), \
             patch('routes.ai_routes.actions.LoggingCore.log_error', side_effect=RuntimeError('log fail')):
            result = _process_user_action('x', mock_user)
        assert 'خطأ في التنفيذ' in result


# ===========================================================================
# ai.py - config / upload-excel / excel helpers
# ===========================================================================
class TestConfigUploadWave:
    def test_config_creates_env_when_missing(self, ai_client, tmp_path):
        env_dir = tmp_path / 'routes'
        env_dir.mkdir()
        fake_ai = env_dir / 'ai.py'
        fake_ai.write_text('#', encoding='utf-8')
        with patch('routes.ai_routes.assistant.__file__', str(fake_ai)):
            resp = ai_client.post('/ai/config', data={'api_key': 'k', 'provider': 'groq'})
        assert resp.get_json()['success'] is True
        assert (tmp_path / '.env').exists()

    def test_config_save_exception(self, ai_client, tmp_path):
        env_dir = tmp_path / 'routes'
        env_dir.mkdir()
        fake_ai = env_dir / 'ai.py'
        fake_ai.write_text('#', encoding='utf-8')
        with patch('routes.ai_routes.assistant.__file__', str(fake_ai)), \
             patch('builtins.open', side_effect=OSError('io error')):
            resp = ai_client.post('/ai/config', data={'api_key': 'k', 'provider': 'groq'})
        assert resp.get_json()['success'] is False

    def test_upload_warehouse_fallback(self, ai_client):
        warehouse = MagicMock(id=8)
        data = {'file': (io.BytesIO(b'x'), 'items.xlsx')}
        with patch('models.Warehouse') as Warehouse:
            Warehouse.query.filter_by.return_value.first.side_effect = [None, warehouse]
            with patch('routes.ai_routes.assistant._process_excel_intelligently', return_value={'success': True}) as proc:
                resp = ai_client.post('/ai/upload-excel', data=data, content_type='multipart/form-data')
        assert resp.status_code == 200
        proc.assert_called_once()

    def test_upload_stream_size_exceeds_max(self, ai_client):
        """File stream larger than max while content-length passes -> 413."""
        fake_file = MagicMock()
        fake_file.filename = 'big.xlsx'
        fake_file.stream.tell.return_value = 99_999_999
        fake_req = MagicMock()
        fake_req.content_length = 5
        fake_req.files = {'file': fake_file}
        fake_req.form.get.return_value = 1
        fake_req.endpoint = 'ai.upload_excel'
        fake_req.path = '/ai/upload-excel'
        fake_req.method = 'POST'
        with patch('routes.ai_routes.assistant.request', fake_req):
            resp = ai_client.post('/ai/upload-excel', data={'file': (io.BytesIO(b'x'), 'big.xlsx')},
                                  content_type='multipart/form-data')
        assert resp.status_code == 413


class TestExcelHelpersWave:
    @staticmethod
    def _excel_env(df, mapping, warehouse, existing=None, new_product=None,
                   wh_import=None):
        stack = ExitStack()
        stack.enter_context(patch('routes.ai_routes.assistant.pd.read_excel', return_value=df))
        stack.enter_context(patch('routes.ai_routes.assistant._intelligent_column_detector', return_value=mapping))
        wh = stack.enter_context(patch('models.Warehouse'))
        product = stack.enter_context(patch('models.Product'))
        stack.enter_context(patch('routes.ai_routes.assistant.db'))
        stack.enter_context(patch('routes.ai_routes.assistant.assign_tenant_id'))
        ss = stack.enter_context(patch('routes.ai_routes.assistant.StockService'))
        stack.enter_context(patch('routes.ai_routes.assistant._train_ai_from_excel'))
        wh.query.filter_by.return_value.first.return_value = warehouse if wh_import is None else None
        if wh_import is not None:
            wh.query.filter_by.return_value.first.side_effect = [warehouse, wh_import]
        product.query.filter_by.return_value.first.return_value = existing
        if new_product is not None:
            product.return_value = new_product
        return stack, ss

    def test_create_with_quantity(self, mock_user):
        from routes.ai_routes import _process_excel_intelligently
        df = pd.DataFrame({'name': ['A'], 'part': ['P'], 'price': [10], 'qty': [5]})
        mapping = {'name': 'name', 'part_number': 'part', 'price': 'price', 'quantity': 'qty'}
        stack, ss = TestExcelHelpersWave._excel_env(df, mapping, _obj(name='W'), existing=None, new_product=_obj(id=3))
        with stack:
            result = _process_excel_intelligently(MagicMock(), 1, mock_user)
        assert result['success'] is True
        ss.add_opening_stock.assert_called()

    def test_update_with_quantity(self, mock_user):
        from routes.ai_routes import _process_excel_intelligently
        df = pd.DataFrame({'name': ['A'], 'part': ['P'], 'price': [10], 'qty': [5]})
        mapping = {'name': 'name', 'part_number': 'part', 'price': 'price', 'quantity': 'qty'}
        stack, ss = TestExcelHelpersWave._excel_env(df, mapping, _obj(name='W'),
                                    existing=_obj(id=5), wh_import=_obj(id=2))
        with stack:
            result = _process_excel_intelligently(MagicMock(), 1, mock_user)
        assert result['details']['updated'] == 1
        ss.add_stock.assert_called()

    def test_quantity_nan(self, mock_user):
        from routes.ai_routes import _process_excel_intelligently
        df = pd.DataFrame({'name': ['A'], 'part': ['P'], 'price': [10], 'qty': [np.nan]})
        mapping = {'name': 'name', 'part_number': 'part', 'price': 'price', 'quantity': 'qty'}
        stack, ss = TestExcelHelpersWave._excel_env(df, mapping, _obj(name='W'), existing=None, new_product=_obj(id=3))
        with stack:
            result = _process_excel_intelligently(MagicMock(), 1, mock_user)
        assert result['success'] is True

    def test_skip_nan_name(self, mock_user):
        from routes.ai_routes import _process_excel_intelligently
        df = pd.DataFrame({'name': [np.nan], 'part': ['P'], 'price': [10]})
        mapping = {'name': 'name', 'part_number': 'part', 'price': 'price'}
        stack, ss = TestExcelHelpersWave._excel_env(df, mapping, _obj(name='W'))
        with stack:
            result = _process_excel_intelligently(MagicMock(), 1, mock_user)
        assert result['details']['created'] == 0

    def test_row_error_collected(self, mock_user):
        from routes.ai_routes import _process_excel_intelligently
        df = pd.DataFrame({'name': ['A'], 'part': ['P'], 'price': ['not-a-number']})
        mapping = {'name': 'name', 'part_number': 'part', 'price': 'price'}
        stack, ss = TestExcelHelpersWave._excel_env(df, mapping, _obj(name='W'))
        with stack:
            result = _process_excel_intelligently(MagicMock(), 1, mock_user)
        assert result['success'] is True
        assert 'تفاصيل الأخطاء' in result['message']

    def test_detector_quantity_position_fallback(self):
        from routes.ai_routes import _intelligent_column_detector
        df = pd.DataFrame({'col0': ['a'], 'col1': ['b'], 'col2': [1], 'col3': [2]})
        mapping = _intelligent_column_detector(df)
        assert mapping['quantity'] == 'col3'

    def test_train_ai_from_excel_success(self):
        from routes.ai_routes import _train_ai_from_excel
        df = pd.DataFrame({'name': ['A'], 'part': ['P'], 'price': [10]})
        _train_ai_from_excel(df, 1, 0, 42)

    def test_train_ai_from_excel_handles_error(self):
        from routes.ai_routes import _train_ai_from_excel
        _train_ai_from_excel(None, 1, 0, 42)
