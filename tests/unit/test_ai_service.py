"""Unit tests for AIService — 100% coverage target."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from extensions import db
from models import Customer, Product, Sale, SaleLine, User
from services.ai_service import AIService

_SINGLETON_ATTRS = (
    '_learning_system', '_context_engine', '_personality', '_dialect_manager',
    '_security_rules', '_neural_engine', '_reasoning_engine', '_memory_system',
    '_code_generator', '_agent_coordinator', '_reflection_engine',
    '_conversation_manager', '_vision_processor', '_master_brain', '_transformers_brain',
)


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    yield
    db_session.rollback()


@pytest.fixture(autouse=True)
def _reset_ai_singletons():
    saved = {a: getattr(AIService, a) for a in _SINGLETON_ATTRS}
    for a in _SINGLETON_ATTRS:
        setattr(AIService, a, None)
    yield
    for a, v in saved.items():
        setattr(AIService, a, v)


@pytest.fixture(autouse=True)
def _clear_api_keys(monkeypatch):
    for key in ('GROQ_API_KEY', 'GEMINI_API_KEY', 'OPENAI_API_KEY'):
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Configuration & security
# ---------------------------------------------------------------------------

class TestConfig:
    def test_is_enabled(self):
        assert AIService.is_enabled() is True

    def test_get_api_key_priority(self, monkeypatch):
        monkeypatch.setenv('GROQ_API_KEY', 'g')
        monkeypatch.setenv('GEMINI_API_KEY', 'gem')
        monkeypatch.setenv('OPENAI_API_KEY', 'o')
        assert AIService.get_api_key() == 'g'

    def test_get_provider_chain(self, monkeypatch):
        assert AIService.get_provider() == 'local'
        monkeypatch.setenv('OPENAI_API_KEY', 'o')
        assert AIService.get_provider() == 'openai'
        monkeypatch.setenv('GEMINI_API_KEY', 'g')
        assert AIService.get_provider() == 'gemini'
        monkeypatch.setenv('GROQ_API_KEY', 'groq')
        assert AIService.get_provider() == 'groq'


class TestSensitiveRequest:
    def test_non_sensitive_message(self):
        user = SimpleNamespace(is_owner=False)
        assert AIService.is_sensitive_request('ما سعر المنتج؟', user) == (False, False, None)

    def test_password_request_denied_for_non_owner(self):
        user = SimpleNamespace(is_owner=False)
        sensitive, requires_owner, resp = AIService.is_sensitive_request('كلمة المرور', user)
        assert sensitive is True
        assert requires_owner is False
        assert resp['type'] == 'warning'

    def test_password_request_allowed_for_owner(self):
        user = SimpleNamespace(is_owner=True)
        sensitive, requires_owner, resp = AIService.is_sensitive_request('password', user)
        assert sensitive is True
        assert requires_owner is True
        assert resp is None

    def test_short_user_info_request_sensitive(self):
        user = SimpleNamespace(is_owner=False)
        sensitive, _, _ = AIService.is_sensitive_request('بيانات مستخدم', user)
        assert sensitive is True

    def test_security_permissions_keyword(self):
        user = SimpleNamespace(is_owner=False)
        sensitive, _, _ = AIService.is_sensitive_request('صلاحيات النظام', user)
        assert sensitive is True

    def test_owner_without_is_owner_attr(self):
        user = SimpleNamespace()
        sensitive, requires_owner, _ = AIService.is_sensitive_request('password', user)
        assert sensitive is True
        assert requires_owner is False


class TestUserInfoForOwner:
    def test_escape_ilike(self):
        assert AIService._escape_ilike('a%b_c') == r'a\%b\_c'

    def test_user_not_found(self, db_session):
        result = AIService.get_user_info_for_owner('nobody-here-xyz')
        assert result['success'] is False

    def test_user_found_no_password_hash(self, db_session, sample_user):
        result = AIService.get_user_info_for_owner(sample_user.username)
        assert result['success'] is True
        assert 'password_hash' not in result['user']

    def test_list_all_users(self, db_session, sample_user):
        result = AIService.get_user_info_for_owner()
        assert result['success'] is True
        assert result['count'] >= 1
        assert 'password_hash' not in result['users'][0]


# ---------------------------------------------------------------------------
# Pricing, stock, customer analytics
# ---------------------------------------------------------------------------

class TestRecommendPrice:
    def test_missing_entities(self):
        assert AIService.recommend_price(999999, 999999) is None

    def test_merchant_with_history(
        self, db_session, sample_product, sample_customer, sample_user, sample_tenant,
    ):
        sample_customer.customer_type = 'merchant'
        sample_product.get_price_for_customer = MagicMock(return_value=Decimal('90'))
        db_session.commit()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f'S-{uuid.uuid4().hex[:6]}',
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            subtotal=Decimal('100'),
            total_amount=Decimal('100'),
            amount=Decimal('100'),
            amount_aed=Decimal('100'),
            status='confirmed',
        )
        db_session.add(sale)
        db_session.flush()
        db_session.add(SaleLine(
            tenant_id=sample_tenant.id,
            sale_id=sale.id,
            product_id=sample_product.id,
            quantity=Decimal('1'),
            unit_price=Decimal('120'),
            line_total=Decimal('120'),
            cost_price=Decimal('50'),
        ))
        db_session.commit()
        result = AIService.recommend_price(sample_product.id, sample_customer.id)
        assert result is not None
        assert 'recommended_price' in result

    def test_partner_customer(self, db_session, sample_product, sample_customer):
        sample_customer.customer_type = 'partner'
        sample_product.get_price_for_customer = MagicMock(return_value=Decimal('80'))
        db_session.commit()
        result = AIService.recommend_price(sample_product.id, sample_customer.id)
        assert result is not None


class TestStockAlert:
    def test_missing_product(self):
        assert AIService.check_stock_alert(999999, 1) is None

    def test_insufficient_stock(self, sample_product):
        sample_product.current_stock = Decimal('2')
        result = AIService.check_stock_alert(sample_product.id, 5)
        assert result['type'] == 'error'

    def test_low_stock_warning(self, sample_product, db_session):
        sample_product.current_stock = Decimal('10')
        sample_product.min_stock_alert = Decimal('5')
        db_session.commit()
        result = AIService.check_stock_alert(sample_product.id, 6)
        assert result['type'] == 'warning'

    def test_sufficient_stock(self, sample_product):
        sample_product.current_stock = Decimal('100')
        sample_product.min_stock_alert = Decimal('5')
        assert AIService.check_stock_alert(sample_product.id, 1) is None


class TestCustomerAnalysis:
    def test_missing_customer(self):
        assert AIService.analyze_customer_behavior(999999) is None

    def test_risk_levels(self, mocker):
        customer = MagicMock()
        customer.id = 1
        customer.get_balance_aed.return_value = Decimal('1000')
        mocker.patch.object(Customer, 'query')
        Customer.query.get.return_value = customer
        sale = MagicMock(
            total_amount=Decimal('100'),
            created_at=datetime.now(timezone.utc),
            customer=customer,
            lines=[],
        )
        payment = MagicMock(
            amount=Decimal('50'),
            created_at=datetime.now(timezone.utc) + timedelta(days=2),
            customer_id=1,
        )
        mocker.patch.object(Sale, 'query')
        Sale.query.options.return_value.filter.return_value.all.return_value = [sale]
        from models import Payment
        mocker.patch.object(Payment, 'query')
        Payment.query.filter.return_value.all.return_value = [payment]
        result = AIService.analyze_customer_behavior(1)
        assert result['risk_level'] == 'high'

    def test_get_risk_recommendation_unknown(self):
        assert 'غير متوفر' in AIService._get_risk_recommendation('unknown')

    def test_perform_analysis_no_sales(self, sample_customer):
        result = AIService._perform_analysis(sample_customer)
        assert result['risk_level'] == 'low'

    def test_perform_analysis_type_error_on_delay(self, mocker, sample_customer):
        sale_dt = datetime.now(timezone.utc)
        sale = MagicMock(total_amount=Decimal('100'), created_at=sale_dt, customer=sample_customer, lines=[])
        pay_dt = MagicMock()
        pay_dt.__sub__ = MagicMock(side_effect=TypeError('bad'))
        pay_dt.__ge__ = MagicMock(return_value=True)
        payment = MagicMock(amount=Decimal('50'), created_at=pay_dt)
        mocker.patch.object(Sale, 'query')
        Sale.query.options.return_value.filter.return_value.all.return_value = [sale]
        from models import Payment
        mocker.patch.object(Payment, 'query')
        Payment.query.filter.return_value.all.return_value = [payment]
        sample_customer.get_balance_aed = MagicMock(return_value=Decimal('0'))
        result = AIService._perform_analysis(sample_customer)
        assert result['avg_payment_delay_days'] == 0


class TestExchangeRate:
    def test_from_recent_sales(self, db_session, sample_tenant, sample_customer, sample_user):
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f'USD-{uuid.uuid4().hex[:6]}',
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            subtotal=Decimal('100'),
            total_amount=Decimal('100'),
            amount=Decimal('100'),
            amount_aed=Decimal('367'),
            currency='USD',
            exchange_rate=Decimal('3.67'),
            status='confirmed',
        )
        db_session.add(sale)
        db_session.commit()
        result = AIService.get_exchange_rate_suggestion('USD')
        assert result['source'] == 'نظام داخلي - متوسط آخر 7 أيام'

    def test_default_rate(self):
        result = AIService.get_exchange_rate_suggestion('GBP', target_date=datetime.now())
        assert result['source'] == 'سعر افتراضي'


# ---------------------------------------------------------------------------
# Sales analytics
# ---------------------------------------------------------------------------

def _confirmed_sale(db_session, sample_tenant, sample_customer, sample_user, **kwargs):
    day = kwargs.get('sale_date', datetime.now(timezone.utc))
    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number=f'S-{uuid.uuid4().hex[:6]}',
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        sale_date=day,
        subtotal=Decimal('100'),
        total_amount=Decimal('100'),
        amount=Decimal('100'),
        amount_aed=Decimal(kwargs.get('amount_aed', '100')),
        status='confirmed',
    )
    db_session.add(sale)
    db_session.commit()
    return sale


class TestSalesTrend:
    def test_no_data(self, mocker):
        mocker.patch.object(Sale, 'query')
        Sale.query.filter.return_value.all.return_value = []
        result = AIService.predict_sales_trend()
        assert result['prediction'] is None

    def test_insufficient_days(self, mocker):
        sales = []
        for i in range(3):
            sales.append(MagicMock(
                sale_date=datetime.now(timezone.utc) - timedelta(days=i),
                amount_aed=Decimal('100'),
                status='confirmed',
            ))
        mocker.patch.object(Sale, 'query')
        Sale.query.filter.return_value.all.return_value = sales
        result = AIService.predict_sales_trend()
        assert '7 أيام' in result['message']

    def test_full_prediction(self, mocker):
        sales = []
        for i in range(10):
            sales.append(MagicMock(
                sale_date=datetime.now(timezone.utc) - timedelta(days=i),
                amount_aed=Decimal(str(100 + i * 5)),
                status='confirmed',
            ))
        mocker.patch.object(Sale, 'query')
        Sale.query.filter.return_value.all.return_value = sales
        result = AIService.predict_sales_trend(days_ahead=3)
        assert result['prediction'] is not None
        assert result['confidence'] >= 0


class TestProfitMargins:
    def test_no_sales(self, mocker):
        mocker.patch.object(Sale, 'query')
        Sale.query.filter.return_value.all.return_value = []
        assert AIService.analyze_profit_margins()['success'] is False

    def test_with_lines(self, mocker, sample_product):
        line = MagicMock(
            product_id=sample_product.id,
            quantity=Decimal('2'),
            unit_price=Decimal('50'),
            line_total=Decimal('100'),
            cost_price=Decimal('30'),
            product=sample_product,
        )
        sale = MagicMock(
            amount_aed=Decimal('100'),
            exchange_rate=Decimal('1'),
            lines=[line],
        )
        mocker.patch.object(Sale, 'query')
        Sale.query.filter.return_value.all.return_value = [sale]
        result = AIService.analyze_profit_margins()
        assert result['success'] is True


class TestSalesPatterns:
    def test_insufficient_data(self, mocker):
        mocker.patch.object(Sale, 'query')
        Sale.query.filter.return_value.all.return_value = []
        assert AIService.detect_sales_patterns()['success'] is False

    def test_patterns(self, db_session, sample_tenant, sample_customer, sample_user):
        base = datetime.now(timezone.utc)
        for i in range(12):
            _confirmed_sale(
                db_session, sample_tenant, sample_customer, sample_user,
                sale_date=base - timedelta(days=i),
            )
        result = AIService.detect_sales_patterns()
        assert result['success'] is True


class TestInventoryHealth:
    def test_no_products(self, db_session, sample_tenant):
        Product.query.filter_by(tenant_id=sample_tenant.id).delete()
        db_session.commit()
        assert AIService.analyze_inventory_health(tenant_id=sample_tenant.id)['success'] is False

    def test_health_ratings(self, sample_product, db_session):
        sample_product.min_stock_alert = Decimal('5')
        sample_product.current_stock = Decimal('0')
        db_session.commit()
        weak = AIService.analyze_inventory_health(tenant_id=sample_product.tenant_id)
        assert weak['rating'] == 'ضعيف'
        sample_product.current_stock = Decimal('3')
        db_session.commit()
        low = AIService.analyze_inventory_health(tenant_id=sample_product.tenant_id)
        assert low['summary']['low'] >= 1
        sample_product.current_stock = Decimal('100')
        db_session.commit()
        good = AIService.analyze_inventory_health(tenant_id=sample_product.tenant_id)
        assert good['health_score'] >= 60


# ---------------------------------------------------------------------------
# Chat & actions
# ---------------------------------------------------------------------------

class TestChatResponse:
    def test_local_fallback(self, mocker):
        mocker.patch(
            'ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process',
            return_value={'response': 'محلي'},
        )
        mocker.patch('ai_knowledge.system_knowledge.search_knowledge', return_value=None)
        mocker.patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', return_value=None)
        mocker.patch('ai_knowledge.agents_core.ask_azad_enhanced', return_value=None)
        out = AIService.chat_response('مرحبا', {'force_local': True})
        assert 'محلي' in out

    def test_action_dispatcher_path(self, mocker):
        mocker.patch(
            'ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process',
            return_value={'response': 'x'},
        )
        mocker.patch('ai_knowledge.system_knowledge.search_knowledge', return_value='ctx')
        parsed = ('create_customer', {})
        dispatch_result = SimpleNamespace(success=True, message='تم')
        mocker.patch(
            'ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action',
            return_value=parsed,
        )
        mocker.patch(
            'ai_knowledge.action_dispatcher.action_dispatcher.dispatch',
            return_value=dispatch_result,
        )
        out = AIService.chat_response('أنشئ عميل')
        assert 'تم' in out

    def test_fast_path_enhanced(self, mocker):
        mocker.patch(
            'ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process',
            return_value={'response': 'x'},
        )
        mocker.patch('ai_knowledge.system_knowledge.search_knowledge', side_effect=RuntimeError())
        mocker.patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', return_value=None)
        mocker.patch(
            'ai_knowledge.agents_core.ask_azad_enhanced',
            return_value={'answer': 'من GROQ', 'source': 'groq'},
        )
        out = AIService.chat_response(
            'سؤال',
            {'current_user': SimpleNamespace(id=1, role=SimpleNamespace(slug='admin'))},
        )
        assert 'من GROQ' in out

    def test_groq_success(self, mocker, monkeypatch):
        monkeypatch.setenv('GROQ_API_KEY', 'key')
        mocker.patch(
            'ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process',
            return_value={'response': 'local'},
        )
        mocker.patch('ai_knowledge.system_knowledge.search_knowledge', return_value=None)
        mocker.patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', return_value=None)
        mocker.patch('ai_knowledge.agents_core.ask_azad_enhanced', return_value=None)
        mocker.patch('services.ai_service.AIService._gather_relevant_knowledge', return_value='stats')
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {'choices': [{'message': {'content': 'إجابة Groq'}}]}
        mocker.patch('requests.post', return_value=resp)
        mocker.patch('services.ai_service.AIService._execute_ai_action', return_value=None)
        mocker.patch('services.ai_service.AIService._train_local_from_groq')
        out = AIService.chat_response('سؤال')
        assert 'إجابة Groq' in out

    def test_groq_failure_logs(self, mocker, monkeypatch):
        monkeypatch.setenv('GROQ_API_KEY', 'key')
        mocker.patch(
            'ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process',
            return_value={'response': 'fallback'},
        )
        mocker.patch('ai_knowledge.system_knowledge.search_knowledge', return_value=None)
        mocker.patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', return_value=None)
        mocker.patch('ai_knowledge.agents_core.ask_azad_enhanced', return_value=None)
        mocker.patch('requests.post', side_effect=RuntimeError('net'))
        mocker.patch('services.logging_core.LoggingCore.log_error')
        out = AIService.chat_response('سؤال')
        assert 'fallback' in out


class TestExecuteAiAction:
    def _groq_json(self, action, data=None, message='msg'):
        return json.dumps({'action': action, 'data': data or {}, 'message': message})

    def test_no_json(self):
        assert AIService._execute_ai_action('plain text', 1) is None

    def test_create_customer_success(self, mocker):
        user = SimpleNamespace(is_authenticated=True)
        mocker.patch('flask_login.current_user', user)
        ex = MagicMock()
        ex.create_customer.return_value = {'success': True, 'message': 'عميل'}
        mocker.patch('services.ai_executor.AIExecutor', return_value=ex)
        out = AIService._execute_ai_action(
            self._groq_json('create_customer', {'name': 'Ali', 'phone': '05'}),
            1,
        )
        assert 'عميل' in out

    def test_all_action_types(self, mocker):
        user = SimpleNamespace(is_authenticated=False)
        mocker.patch('flask_login.current_user', user)
        ex = MagicMock()
        ex.create_customer.return_value = {'success': True, 'message': 'ok'}
        ex.create_product.return_value = {'success': True, 'message': 'ok'}
        ex.create_sale.return_value = {'success': True, 'message': 'ok'}
        ex.receive_payment.return_value = {'success': True, 'message': 'ok'}
        ex.add_expense.return_value = {'success': True, 'message': 'ok'}
        ex.create_supplier.return_value = {'success': True, 'message': 'ok'}
        ex.create_employee.return_value = {'success': True, 'message': 'ok'}
        mocker.patch('services.ai_executor.AIExecutor', return_value=ex)
        actions = [
            ('create_customer', {'الاسم': 'x', 'الهاتف': '1'}),
            ('create_product', {'الاسم': 'p', 'سعر': 10, 'الكمية': 2}),
            ('create_sale', {'products': [{'name': 'p', 'quantity': 1}], 'اسم_العميل': 'c'}),
            ('receive_payment', {'اسم_العميل': 'c', 'المبلغ': 50}),
            ('add_expense', {'الوصف': 'x', 'المبلغ': 20}),
            ('create_supplier', {'الاسم': 's', 'الهاتف': '1'}),
            ('create_employee', {'الاسم': 'e', 'الراتب': 1000}),
        ]
        for action, data in actions:
            out = AIService._execute_ai_action(self._groq_json(action, data), 1)
            assert out is not None

    def test_action_failure_message(self, mocker):
        mocker.patch('flask_login.current_user', SimpleNamespace(is_authenticated=False))
        ex = MagicMock()
        ex.create_customer.return_value = {'success': False, 'message': 'فشل'}
        mocker.patch('services.ai_executor.AIExecutor', return_value=ex)
        out = AIService._execute_ai_action(
            self._groq_json('create_customer', {'name': 'x'}),
            1,
        )
        assert 'فشل' in out

    def test_invalid_json_returns_error(self, mocker):
        mocker.patch('flask_login.current_user', SimpleNamespace(is_authenticated=False))
        out = AIService._execute_ai_action('{"action": bad}', 1)
        assert 'خطأ' in out


class TestGatherKnowledge:
    def test_success(self, app, mocker):
        mocker.patch('utils.tenanting.scoped_user_query', return_value=MagicMock(count=MagicMock(return_value=1)))
        from models import Customer, Supplier, Product, Sale, Purchase, Expense, Payment, Cheque
        for model in (Customer, Supplier, Product, Sale, Purchase, Expense, Payment, Cheque):
            mocker.patch.object(model, 'query', MagicMock())
        Customer.query.filter_by.return_value.count.return_value = 2
        Supplier.query.filter_by.return_value.count.return_value = 1
        Product.query.filter_by.return_value.count.return_value = 3
        Sale.query.filter.return_value.count.return_value = 4
        Purchase.query.filter.return_value.count.return_value = 1
        Expense.query.filter.return_value.count.return_value = 1
        Payment.query.filter.return_value.count.return_value = 1
        Cheque.query.filter_by.return_value.count.return_value = 0
        sum_query = MagicMock()
        sum_query.filter.return_value.scalar.return_value = 100
        mocker.patch.object(db.session, 'query', return_value=sum_query)
        user = MagicMock(tenant_id=1, username='admin', is_owner=False)
        user.role = SimpleNamespace(name_ar='مدير')
        local = {'context': {'current_user': user}}
        out = AIService._gather_relevant_knowledge('stats', local)
        assert 'بيانات النظام' in out

    def test_error_path(self, mocker):
        mocker.patch('utils.tenanting.scoped_user_query', side_effect=RuntimeError('db'))
        out = AIService._gather_relevant_knowledge('x', {})
        assert 'خطأ' in out


class TestBusinessInsights:
    def test_generate_insights(self, mocker):
        mocker.patch.object(Product, 'query')
        Product.query.filter.return_value.count.return_value = 2
        cust = MagicMock(get_balance_aed=MagicMock(return_value=Decimal('2000')))
        mocker.patch.object(Customer, 'query')
        Customer.query.filter.return_value.all.return_value = [cust]
        mocker.patch.object(Sale, 'query')
        Sale.query.filter.return_value.count.return_value = 0
        insights = AIService.generate_business_insights()
        assert len(insights) >= 2

    def test_insights_error(self, mocker):
        mocker.patch.object(Product, 'query', side_effect=RuntimeError('x'))
        insights = AIService.generate_business_insights()
        assert insights[0]['type'] == 'error'

    def test_optimize_inventory(self, mocker):
        prod = MagicMock(
            id=1, name='P', current_stock=Decimal('1'),
            min_stock_alert=Decimal('5'), cost_price=Decimal('10'),
        )
        mocker.patch.object(Product, 'query')
        Product.query.filter.return_value.all.return_value = [prod]
        result = AIService.optimize_inventory_levels()
        assert result['success'] is True
        assert result['total_products'] == 1

    def test_optimize_inventory_error(self, mocker):
        q = MagicMock()
        q.filter.side_effect = RuntimeError('x')
        mocker.patch.object(Product, 'query', q)
        assert AIService.optimize_inventory_levels()['success'] is False


class TestMiscHelpers:
    def test_contextual_help(self):
        result = AIService.contextual_help('dashboard', 'admin')
        assert result['page'] == 'dashboard'
        result2 = AIService.contextual_help('unknown', 'user')
        assert 'لا توجد' in result2['help']

    def test_deep_business_analysis(self, mocker):
        mocker.patch('services.ai_service.AIService.generate_business_insights', return_value=[{'a': 1}])
        assert AIService.deep_business_analysis()['success'] is True

    def test_deep_business_analysis_error(self, mocker):
        mocker.patch('services.ai_service.AIService.generate_business_insights', side_effect=RuntimeError())
        assert AIService.deep_business_analysis()['success'] is False

    def test_predict_cash_flow(self, mocker):
        mocker.patch('services.ai_service.AIService.predict_cash_flow_neural', return_value={'ok': True})
        assert AIService.predict_cash_flow(30)['ok'] is True

    def test_predict_cash_flow_error(self, mocker):
        mocker.patch('services.ai_service.AIService.predict_cash_flow_neural', side_effect=RuntimeError())
        assert AIService.predict_cash_flow(30)['success'] is False

    def test_smart_pricing_tiers(self, sample_product):
        assert AIService.smart_pricing_engine(999999, None) is None
        r5 = AIService.smart_pricing_engine(sample_product.id, None, quantity=5)
        assert r5['discount_percentage'] == 5.0
        r10 = AIService.smart_pricing_engine(sample_product.id, None, quantity=10)
        assert r10['discount_percentage'] == 10.0

    def test_smart_pricing_error(self, mocker):
        q = MagicMock()
        q.get.side_effect = RuntimeError()
        mocker.patch.object(Product, 'query', q)
        assert AIService.smart_pricing_engine(999999, 1) is None

    def test_predict_churn(self, db_session, sample_customer, sample_tenant, sample_user):
        old = datetime.now() - timedelta(days=200)
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f'OLD-{uuid.uuid4().hex[:6]}',
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=old,
            subtotal=Decimal('50'),
            total_amount=Decimal('50'),
            amount=Decimal('50'),
            amount_aed=Decimal('50'),
            status='confirmed',
        )
        db_session.add(sale)
        db_session.commit()
        result = AIService.predict_customer_churn()
        assert result['success'] is True

    def test_predict_churn_error(self, mocker):
        q = MagicMock()
        q.filter_by.side_effect = RuntimeError()
        mocker.patch.object(Customer, 'query', q)
        assert AIService.predict_customer_churn()['success'] is False

    def test_train_local_from_groq(self, mocker):
        ls = MagicMock()
        mocker.patch('ai_knowledge.core.learning_system.learning_system', ls)
        AIService._train_local_from_groq('q', 'l', 'g', 1)
        ls.learn_from_groq_feedback.assert_called_once()

    def test_train_local_skipped(self, mocker):
        ls = MagicMock()
        ls.learn_from_groq_feedback.side_effect = RuntimeError('fail')
        mocker.patch('ai_knowledge.core.learning_system.learning_system', ls)
        AIService._train_local_from_groq('q', 'l', 'g', 1)


# ---------------------------------------------------------------------------
# Lazy singleton getters
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('method,path,cls_name', [
    ('get_learning_system', 'ai_knowledge.core.learning_system', 'AzadLearningSystem'),
    ('get_context_engine', 'ai_knowledge.core.context_engine', 'ContextEngine'),
    ('get_personality', 'ai_knowledge.personality.azad_personality', 'AzadPersonality'),
    ('get_dialect_manager', 'ai_knowledge.personality.dialects', 'DialectManager'),
    ('get_security_rules', 'ai_knowledge.specialized.security_rules', 'SecurityRules'),
    ('get_neural_engine', 'ai_knowledge.neural.neural_engine', 'get_neural_engine'),
    ('get_reasoning_engine', 'ai_knowledge.core.reasoning_engine', 'get_reasoning_engine'),
    ('get_memory_system', 'ai_knowledge.core.memory_system', 'get_memory_system'),
    ('get_code_generator', 'ai_knowledge.generation.code_generator', 'get_code_generator'),
    ('get_agent_coordinator', 'ai_knowledge.agents.multi_agent_system', 'get_agent_coordinator'),
    ('get_reflection_engine', 'ai_knowledge.improvement.self_reflection', 'get_reflection_engine'),
    ('get_conversation_manager', 'ai_knowledge.core.conversation_manager', 'get_conversation_manager'),
    ('get_vision_processor', 'ai_knowledge.neural.vision_processor', 'get_vision_processor'),
    ('get_master_brain', 'ai_knowledge.agents.master_brain', 'get_master_brain'),
    ('get_transformers_brain', 'ai_knowledge.neural.transformers_brain', 'get_transformers_brain'),
])
def test_singleton_getters(method, path, cls_name, mocker):
    inst = MagicMock()
    if cls_name.startswith('get_'):
        mocker.patch(f'{path}.{cls_name}', return_value=inst)
    else:
        mocker.patch(f'{path}.{cls_name}', return_value=inst)
    first = getattr(AIService, method)()
    second = getattr(AIService, method)()
    assert first is inst
    assert second is inst


# ---------------------------------------------------------------------------
# Contextual response & integration wrappers
# ---------------------------------------------------------------------------

class TestContextualResponse:
    def test_success(self, mocker):
        ctx_eng = MagicMock(build_context=MagicMock(return_value={}))
        dial = MagicMock(detect_dialect=MagicMock(return_value='msa'))
        pers = MagicMock(generate_response=MagicMock(return_value='رد'))
        learn = MagicMock()
        mocker.patch('services.ai_service.AIService.get_context_engine', return_value=ctx_eng)
        mocker.patch('services.ai_service.AIService.get_dialect_manager', return_value=dial)
        mocker.patch('services.ai_service.AIService.get_personality', return_value=pers)
        mocker.patch('services.ai_service.AIService.get_learning_system', return_value=learn)
        assert AIService.get_contextual_response('مرحبا') == 'رد'

    def test_fallback_azad_responses(self, mocker):
        mocker.patch('services.ai_service.AIService.get_context_engine', side_effect=RuntimeError())
        mocker.patch(
            'ai_knowledge.personality.azad_responses.AzadResponses.get_error_response',
            return_value='خطأ لطيف',
        )
        assert AIService.get_contextual_response('x') == 'خطأ لطيف'

    def test_fallback_plain(self, mocker):
        mocker.patch('services.ai_service.AIService.get_context_engine', side_effect=RuntimeError())
        mocker.patch(
            'ai_knowledge.personality.azad_responses.AzadResponses.get_error_response',
            side_effect=RuntimeError(),
        )
        assert 'عذراً' in AIService.get_contextual_response('x')

    def test_local_response(self, mocker):
        mocker.patch(
            'ai_knowledge.personality.azad_responses.AzadResponses.smart_response',
            return_value='smart',
        )
        assert AIService._local_response('hi') == 'smart'


class TestIntegrationWrappers:
    def test_analyze_sales_with_predictions(self, mocker):
        mocker.patch('services.ai_service.AIService.predict_sales_trend', return_value={'t': 1})
        mocker.patch.object(Sale, 'query')
        Sale.query.filter.return_value.all.return_value = []
        analyzer = MagicMock(analyze_sales_performance=MagicMock(return_value={}))
        mocker.patch('ai_knowledge.analytics.data_analyzer.DataAnalyzer', return_value=analyzer)
        mocker.patch(
            'ai_knowledge.analytics.analytics_predictions.SalesAnalytics.predict_next_month_sales',
            return_value={'prediction': 0},
        )
        mocker.patch(
            'ai_knowledge.analytics.analytics_predictions.SalesAnalytics.analyze_sales_pattern',
            return_value={},
        )
        result = AIService.analyze_sales_with_predictions()
        assert 'trend' in result

    def test_wrapper_delegates(self, mocker):
        mocker.patch('services.ai_service.AIService.optimize_inventory_levels', return_value={'success': True})
        mocker.patch('services.ai_service.AIService.analyze_profit_margins', return_value={'success': True})
        assert AIService.optimize_inventory_with_ai()['success'] is True
        assert AIService.analyze_profitability()['success'] is True

    def test_knowledge_wrappers(self):
        assert AIService.get_tax_and_customs_info('ضريبة VAT')
        assert AIService.get_tax_and_customs_info('customs جمارك')
        assert AIService.get_parts_information('filter')
        assert AIService.get_market_insights_report()
        assert AIService.get_customer_service_response('شكوى')
        assert AIService.get_system_guide('sales')
        assert AIService.get_company_information()
        assert AIService.get_system_knowledge('users')
        assert AIService.get_advanced_law_info('customs')
        assert AIService.get_advanced_law_info('shipping')
        assert AIService.get_advanced_law_info('vat')

    def test_wrapper_errors_return_empty(self, mocker):
        mocker.patch('services.ai_service.get_tax_advice', side_effect=RuntimeError())
        assert AIService.get_tax_and_customs_info('x') == {}


# ---------------------------------------------------------------------------
# Neural & advanced capabilities (mocked)
# ---------------------------------------------------------------------------

class TestNeuralAndAdvanced:
    def _neural(self, mocker):
        neural = MagicMock()
        mocker.patch('services.ai_service.AIService.get_neural_engine', return_value=neural)
        return neural

    def test_predict_price_neural(self, mocker, sample_product, sample_customer):
        neural = self._neural(mocker)
        neural.predict_optimal_price.return_value = {'price': 99}
        result = AIService.predict_price_with_neural(sample_product.id, sample_customer.id)
        assert result['price'] == 99

    def test_predict_price_fallback(self, mocker):
        mocker.patch('services.ai_service.AIService.get_neural_engine', side_effect=RuntimeError())
        mocker.patch('services.ai_service.AIService.recommend_price', return_value={'recommended_price': 1})
        assert AIService.predict_price_with_neural(1, 1)['recommended_price'] == 1

    def test_neural_forecast_and_fraud(self, mocker):
        neural = self._neural(mocker)
        neural.forecast_sales.return_value = {'days': 7}
        neural.detect_fraud.return_value = {'is_fraud': False}
        assert AIService.forecast_sales_neural()['days'] == 7
        assert AIService.detect_fraud_neural({})['is_fraud'] is False

    def test_neural_customer_inventory_maintenance_cashflow(self, mocker):
        neural = self._neural(mocker)
        neural.classify_customer_intelligence.return_value = {'segment': 'vip'}
        neural.optimize_stock_level.return_value = {'qty': 10}
        neural.predict_maintenance_needs.return_value = {'due': True}
        neural.predict_cash_flow.return_value = {'months': 3}
        neural.train_all_models.return_value = {'success': True}
        neural.get_status.return_value = {'trained_models': 5}
        assert AIService.classify_customer_neural(1)['segment'] == 'vip'
        assert AIService.optimize_inventory_neural(1)['qty'] == 10
        assert AIService.predict_maintenance_neural(1)['due'] is True
        assert AIService.predict_cash_flow_neural()['months'] == 3
        assert AIService.train_all_neural_models()['success'] is True
        assert AIService.get_neural_status()['trained_models'] == 5

    def test_neural_errors(self, mocker):
        mocker.patch('services.ai_service.AIService.get_neural_engine', side_effect=RuntimeError())
        assert AIService.forecast_sales_neural() == {}
        assert AIService.detect_fraud_neural({})['is_fraud'] is False
        assert AIService.get_neural_status()['trained_models'] == 0

    def test_reasoning_delegate_code_memory_chat_reflect_vision(self, mocker):
        reasoning = MagicMock(think=MagicMock(return_value={'thought': 1}))
        coord = MagicMock(delegate_task=MagicMock(return_value={'task': 1}))
        codegen = MagicMock(
            generate_sql_query=MagicMock(return_value='SELECT 1'),
            generate_python_function=MagicMock(return_value='def f(): pass'),
        )
        memory = MagicMock()
        memory.recall_conversations.return_value = [{'m': 1}]
        conv = MagicMock(process_message=MagicMock(return_value={'response': 'hi'}))
        reflect = MagicMock(reflect_on_performance=MagicMock(return_value={'score': 9}))
        vision = MagicMock(read_invoice_image=MagicMock(return_value={'total': 100}))
        mocker.patch('services.ai_service.AIService.get_reasoning_engine', return_value=reasoning)
        mocker.patch('services.ai_service.AIService.get_agent_coordinator', return_value=coord)
        mocker.patch('services.ai_service.AIService.get_code_generator', return_value=codegen)
        mocker.patch('services.ai_service.AIService.get_memory_system', return_value=memory)
        mocker.patch('services.ai_service.AIService.get_conversation_manager', return_value=conv)
        mocker.patch('services.ai_service.AIService.get_reflection_engine', return_value=reflect)
        mocker.patch('services.ai_service.AIService.get_vision_processor', return_value=vision)
        assert AIService.think_deeply('problem')['thought'] == 1
        assert AIService.delegate_to_expert('task')['task'] == 1
        assert 'SELECT' in AIService.generate_code('sql', 'report', {'intent': 'select', 'table': 'sales'})['code']
        assert AIService.generate_code('python', 'fn', {'name': 'fn', 'params': []})['type'] == 'python'
        assert AIService.generate_code('js', 'x', {})['code'].startswith('#')
        assert AIService.remember_conversation(1, 'a', 'b')['status'] == 'remembered'
        assert AIService.recall_conversations(1) == [{'m': 1}]
        assert AIService.chat(1, 'hi')['response'] == 'hi'
        assert AIService.self_reflect()['score'] == 9
        assert AIService.read_invoice_image('/tmp/x.png')['total'] == 100

    def test_advanced_errors(self, mocker):
        mocker.patch('services.ai_service.AIService.get_reasoning_engine', side_effect=RuntimeError())
        mocker.patch('services.ai_service.AIService.get_memory_system', side_effect=RuntimeError())
        assert AIService.think_deeply('x') == {}
        assert AIService.recall_conversations(1) == []

    def test_master_brain_methods(self, mocker):
        brain = MagicMock()
        brain.ask.return_value = {'answer': 'نعم', 'confidence': 90}
        brain.quick_calc.return_value = {'result': 50, 'success': True}
        brain.explain.return_value = 'شرح'
        brain.validate_accounting_entry.return_value = {'is_balanced': True}
        mocker.patch('services.ai_service.AIService.get_master_brain', return_value=brain)
        assert AIService.ask_genius('سؤال')['answer'] == 'نعم'
        assert AIService.quick_calculate('vat', amount=1000)['success'] is True
        assert AIService.explain_anything('مفهوم') == 'شرح'
        assert AIService.validate_entry(100, 100)['is_balanced'] is True

    def test_master_brain_errors(self, mocker):
        mocker.patch('services.ai_service.AIService.get_master_brain', side_effect=RuntimeError())
        assert AIService.ask_genius('x')['confidence'] == 0
        assert AIService.quick_calculate('vat')['success'] is False
        assert 'عذراً' in AIService.explain_anything('x')
        assert AIService.validate_entry(1, 2)['is_balanced'] is False

    def test_transformers(self, mocker):
        tf = MagicMock()
        tf.understand.return_value = {'attention_map': {}, 'tokens': ['a']}
        tf.generate_response.return_value = 'generated'
        mocker.patch('services.ai_service.AIService.get_transformers_brain', return_value=tf)
        assert AIService.understand_with_transformers('نص')
        assert AIService.generate_with_transformers('prompt') == 'generated'
        assert AIService.analyze_attention('نص')['visualization']

    def test_transformers_errors(self, mocker):
        mocker.patch('services.ai_service.AIService.get_transformers_brain', side_effect=RuntimeError())
        assert AIService.understand_with_transformers('x') == {}
        assert 'عذراً' in AIService.generate_with_transformers('x')
        assert AIService.analyze_attention('x') == {}

    def test_ecu_and_external(self, mocker):
        ecu = MagicMock()
        ecu.diagnose_code.return_value = {'code': 'P0420'}
        ecu.get_sensor_info.return_value = {'name': 'MAF'}
        ecu.get_ecu_info.return_value = {'type': 'engine'}
        mocker.patch('services.ai_service.get_automotive_ecu_knowledge', return_value=ecu)
        assert AIService.diagnose_obd_code('P0420')['code'] == 'P0420'
        assert AIService.get_sensor_info('MAF')['name'] == 'MAF'
        assert AIService.get_ecu_knowledge('engine_ecu')['type'] == 'engine'

        learning = MagicMock()
        learning.get_knowledge_sources_list.return_value = ['wiki']
        learning.get_statistics.return_value = {'count': 1}
        learning.learn_from_source.return_value = {'success': True}
        mocker.patch('ai_knowledge.learning.external_learning.get_external_learning', return_value=learning)
        sources = AIService.get_learning_sources()
        assert sources['total_sources'] == 1
        assert AIService.learn_from_external('wiki', 't', 'c')['success'] is True

    def test_security_compliance(self, mocker):
        sec = MagicMock(check_compliance=MagicMock(return_value=(True, [])))
        mocker.patch('services.ai_service.AIService.get_security_rules', return_value=sec)
        assert AIService.check_security_compliance('read')['compliant'] is True

    def test_get_system_capabilities(self):
        caps = AIService.get_system_capabilities()
        assert caps['neural_networks']['available'] is True

    def test_expand_and_integrate_mocked(self, mocker):
        expander = MagicMock(search_knowledge=MagicMock(return_value={'ok': True}))
        mocker.patch('ai_knowledge.expansion.knowledge_expansion.KnowledgeExpander', return_value=expander)
        self_imp = MagicMock(analyze_performance=MagicMock(return_value={'improved': True}))
        mocker.patch('ai_knowledge.improvement.self_improvement.AzadSelfImprovement', return_value=self_imp)
        integrator = MagicMock(
            get_system_summary=MagicMock(return_value={'integrated': True}),
            search_data=MagicMock(return_value={'hits': []}),
        )
        mocker.patch('ai_knowledge.core.system_integration.SystemIntegrator', return_value=integrator)
        connector = MagicMock(fetch_knowledge=MagicMock(return_value={'data': 1}))
        mocker.patch('ai_knowledge.expansion.global_knowledge.GlobalKnowledgeConnector', return_value=connector)
        beginners = MagicMock(get_help=MagicMock(return_value='help'))
        mocker.patch('ai_knowledge.personality.beginners_mode.BeginnersGuide', return_value=beginners)
        doc_gen = MagicMock(generate=MagicMock(return_value='doc'))
        mocker.patch('ai_knowledge.generation.document_generator.DocumentGenerator', return_value=doc_gen)
        assert AIService.expand_knowledge_base('topic')['ok'] is True
        assert AIService.perform_self_improvement()['improved'] is True
        assert AIService.integrate_with_system('summary', {})['integrated'] is True
        assert AIService.get_global_knowledge('q')['data'] == 1
        assert AIService.get_beginners_help('start') == 'help'
        assert AIService.generate_document_with_ai('invoice', {}) == 'doc'


# ---------------------------------------------------------------------------
# Additional branches for full coverage
# ---------------------------------------------------------------------------

class TestCoverageGaps:
    def test_perform_analysis_naive_datetime_and_medium_risk(self, mocker, sample_customer):
        naive_sale_dt = datetime.now() - timedelta(days=5)
        sale = MagicMock(
            total_amount=Decimal('1000'),
            created_at=naive_sale_dt,
            customer=sample_customer,
            lines=[],
        )
        payment = MagicMock(
            amount=Decimal('200'),
            created_at=datetime.now(timezone.utc),
        )
        mocker.patch.object(Sale, 'query')
        Sale.query.options.return_value.filter.return_value.all.return_value = [sale]
        from models import Payment
        mocker.patch.object(Payment, 'query')
        Payment.query.filter.return_value.all.return_value = [payment]
        sample_customer.get_balance_aed = MagicMock(return_value=Decimal('300'))
        result = AIService._perform_analysis(sample_customer)
        assert result['risk_level'] == 'medium'

    def test_perform_analysis_skip_sale_without_created_at(self, mocker, sample_customer):
        sale = MagicMock(total_amount=Decimal('100'), created_at=None, customer=sample_customer, lines=[])
        payment = MagicMock(amount=Decimal('10'), created_at=datetime.now(timezone.utc))
        mocker.patch.object(Sale, 'query')
        Sale.query.options.return_value.filter.return_value.all.return_value = [sale]
        from models import Payment
        mocker.patch.object(Payment, 'query')
        Payment.query.filter.return_value.all.return_value = [payment]
        sample_customer.get_balance_aed = MagicMock(return_value=Decimal('0'))
        assert AIService._perform_analysis(sample_customer)['avg_payment_delay_days'] == 0

    def test_perform_analysis_payment_without_created_at(self, mocker, sample_customer):
        sale = MagicMock(
            total_amount=Decimal('100'),
            created_at=datetime.now(timezone.utc),
            customer=sample_customer,
            lines=[],
        )
        payment = MagicMock(amount=Decimal('10'), created_at=None)
        mocker.patch.object(Sale, 'query')
        Sale.query.options.return_value.filter.return_value.all.return_value = [sale]
        from models import Payment
        mocker.patch.object(Payment, 'query')
        Payment.query.filter.return_value.all.return_value = [payment]
        sample_customer.get_balance_aed = MagicMock(return_value=Decimal('0'))
        AIService._perform_analysis(sample_customer)

    def test_chat_action_dispatcher_exception(self, mocker):
        mocker.patch(
            'ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process',
            return_value={'response': 'local'},
        )
        mocker.patch('ai_knowledge.system_knowledge.search_knowledge', return_value=None)
        mocker.patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', side_effect=RuntimeError())
        mocker.patch('ai_knowledge.agents_core.ask_azad_enhanced', return_value=None)
        out = AIService.chat_response('x')
        assert 'local' in out

    def test_chat_enhanced_exception(self, mocker):
        mocker.patch(
            'ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process',
            return_value={'response': 'local'},
        )
        mocker.patch('ai_knowledge.system_knowledge.search_knowledge', return_value=None)
        mocker.patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', return_value=None)
        mocker.patch('ai_knowledge.agents_core.ask_azad_enhanced', side_effect=RuntimeError())
        out = AIService.chat_response('x')
        assert 'local' in out

    def test_chat_openai_provider(self, mocker, monkeypatch):
        monkeypatch.setenv('OPENAI_API_KEY', 'key')
        mocker.patch(
            'ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process',
            return_value={'response': 'local'},
        )
        mocker.patch('ai_knowledge.system_knowledge.search_knowledge', return_value=None)
        mocker.patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', return_value=None)
        mocker.patch('ai_knowledge.agents_core.ask_azad_enhanced', return_value=None)
        mocker.patch('services.ai_service.AIService._gather_relevant_knowledge', return_value='')
        resp = MagicMock(status_code=200)
        resp.json.return_value = {'choices': [{'message': {'content': 'OpenAI'}}]}
        mocker.patch('requests.post', return_value=resp)
        mocker.patch('services.ai_service.AIService._execute_ai_action', return_value=None)
        mocker.patch('services.ai_service.AIService._train_local_from_groq')
        out = AIService.chat_response('q')
        assert 'OpenAI' in out

    def test_chat_gemini_provider(self, mocker, monkeypatch):
        monkeypatch.setenv('GEMINI_API_KEY', 'key')
        mocker.patch(
            'ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process',
            return_value={'response': 'local'},
        )
        mocker.patch('ai_knowledge.system_knowledge.search_knowledge', return_value=None)
        mocker.patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', return_value=None)
        mocker.patch('ai_knowledge.agents_core.ask_azad_enhanced', return_value=None)
        mocker.patch('services.ai_service.AIService._gather_relevant_knowledge', return_value='')
        resp = MagicMock(status_code=200)
        resp.json.return_value = {'choices': [{'message': {'content': 'Gemini'}}]}
        mocker.patch('requests.post', return_value=resp)
        mocker.patch('services.ai_service.AIService._execute_ai_action', return_value='تنفيذ')
        mocker.patch('services.ai_service.AIService._train_local_from_groq', side_effect=RuntimeError())
        out = AIService.chat_response('q')
        assert 'تنفيذ' in out

    def test_chat_groq_logging_core_failure(self, mocker, monkeypatch):
        monkeypatch.setenv('GROQ_API_KEY', 'key')
        mocker.patch(
            'ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process',
            return_value={'response': 'local'},
        )
        mocker.patch('ai_knowledge.system_knowledge.search_knowledge', return_value=None)
        mocker.patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', return_value=None)
        mocker.patch('ai_knowledge.agents_core.ask_azad_enhanced', return_value=None)
        mocker.patch('requests.post', side_effect=RuntimeError('api'))
        mocker.patch('services.logging_core.LoggingCore.log_error', side_effect=RuntimeError())
        out = AIService.chat_response('q')
        assert 'local' in out

    def test_execute_action_sale_lines_fallback_and_empty_action(self, mocker):
        mocker.patch('flask_login.current_user', SimpleNamespace(is_authenticated=False))
        ex = MagicMock()
        ex.create_sale.return_value = {'success': True, 'message': 'sale'}
        mocker.patch('services.ai_executor.AIExecutor', return_value=ex)
        payload = json.dumps({
            'action': 'create_sale',
            'data': {'customer_name': 'c', 'product_name': 'p', 'quantity': 2},
            'message': 'm',
        })
        assert 'sale' in AIService._execute_ai_action(payload, 1)
        assert AIService._execute_ai_action('{"action": "", "data": {}}', 1) is None

    def test_execute_action_logs_error(self, mocker):
        mocker.patch('flask_login.current_user', SimpleNamespace(is_authenticated=False))
        mocker.patch('services.ai_executor.AIExecutor', side_effect=RuntimeError('boom'))
        mocker.patch('services.logging_core.LoggingCore.log_error')
        out = AIService._execute_ai_action('{"action": "create_customer", "data": {"name": "x"}}', 1)
        assert 'خطأ' in out

    def test_gather_flask_current_user(self, app, mocker):
        user = MagicMock(tenant_id=1, username='u', is_owner=False)
        user.role = SimpleNamespace(name_ar='مدير')
        mocker.patch('flask_login.current_user', user)
        mocker.patch('utils.tenanting.scoped_user_query', return_value=MagicMock(count=MagicMock(return_value=1)))
        from models import Customer, Supplier, Product, Sale, Purchase, Expense, Payment, Cheque
        for model in (Customer, Supplier, Product, Sale, Purchase, Expense, Payment, Cheque):
            mocker.patch.object(model, 'query', MagicMock())
        Customer.query.filter_by.return_value.count.return_value = 1
        Supplier.query.filter_by.return_value.count.return_value = 1
        Product.query.filter_by.return_value.count.return_value = 1
        Sale.query.filter.return_value.count.return_value = 1
        Purchase.query.filter.return_value.count.return_value = 1
        Expense.query.filter.return_value.count.return_value = 1
        Payment.query.filter.return_value.count.return_value = 1
        Cheque.query.filter_by.return_value.count.return_value = 0
        sum_query = MagicMock()
        sum_query.filter.return_value.scalar.return_value = 50
        mocker.patch.object(db.session, 'query', return_value=sum_query)
        out = AIService._gather_relevant_knowledge('x', {})
        assert 'بيانات النظام' in out

    def test_contextual_response_logging_failure(self, mocker):
        mocker.patch('services.ai_service.AIService.get_context_engine', side_effect=RuntimeError('x'))
        mocker.patch('services.logging_core.LoggingCore.log_error', side_effect=RuntimeError())
        assert 'عذراً' in AIService.get_contextual_response('msg')

    def test_wrapper_error_paths(self, mocker):
        mocker.patch('services.ai_service.AIService.predict_sales_trend', side_effect=RuntimeError())
        assert AIService.analyze_sales_with_predictions() == {}
        mocker.patch('services.ai_service.AIService.optimize_inventory_levels', side_effect=RuntimeError())
        assert AIService.optimize_inventory_with_ai() == {}
        mocker.patch('services.ai_service.AIService.analyze_profit_margins', side_effect=RuntimeError())
        assert AIService.analyze_profitability() == {}
        mocker.patch('services.ai_service.get_part_info', side_effect=RuntimeError())
        assert AIService.get_parts_information('x') == {}
        mocker.patch('services.ai_service.get_market_insights', side_effect=RuntimeError())
        assert AIService.get_market_insights_report() == {}
        mocker.patch('services.ai_service.get_customer_service_tip', side_effect=RuntimeError())
        assert 'عذراً' in AIService.get_customer_service_response('x')
        mocker.patch('services.ai_service.lookup_system_guide', side_effect=RuntimeError())
        assert AIService.get_system_guide('x') == {}
        mocker.patch('services.ai_service.search_knowledge', side_effect=RuntimeError())
        assert AIService.get_system_knowledge('x') == {}
        mocker.patch('services.ai_service.advanced_laws.get_customs_info', side_effect=RuntimeError())
        assert AIService.get_advanced_law_info('customs') == {}

    def test_neural_product_not_found(self, mocker):
        mocker.patch('extensions.db.session.get', return_value=None)
        assert AIService.predict_price_with_neural(1, 1)['error'] == 'Product not found'

    def test_neural_extra_errors(self, mocker):
        mocker.patch('services.ai_service.AIService.get_neural_engine', side_effect=RuntimeError())
        assert AIService.classify_customer_neural(1) == {}
        assert AIService.optimize_inventory_neural(1) == {}
        assert AIService.predict_maintenance_neural(1) == {}
        assert AIService.predict_cash_flow_neural() == {}
        assert AIService.train_all_neural_models()['success'] is False

    def test_advanced_memory_chat_errors(self, mocker):
        mocker.patch('services.ai_service.AIService.get_memory_system', side_effect=RuntimeError())
        mocker.patch('services.ai_service.AIService.get_conversation_manager', side_effect=RuntimeError())
        mocker.patch('services.ai_service.AIService.get_reflection_engine', side_effect=RuntimeError())
        mocker.patch('services.ai_service.AIService.get_vision_processor', side_effect=RuntimeError())
        mocker.patch('services.ai_service.AIService.get_code_generator', side_effect=RuntimeError())
        assert AIService.remember_conversation(1, 'a', 'b') == {}
        assert AIService.chat(1, 'hi')['response'] == 'عذراً، حدث خطأ'
        assert AIService.self_reflect() == {}
        assert AIService.read_invoice_image('x') == {'error': ''}
        assert AIService.generate_code('sql', 'x', {}) == {}

    def test_security_compliance_error(self, mocker):
        mocker.patch('services.ai_service.AIService.get_security_rules', side_effect=RuntimeError())
        assert AIService.check_security_compliance('x')['compliant'] is True

    def test_ecu_errors(self, mocker):
        mocker.patch('services.ai_service.get_automotive_ecu_knowledge', side_effect=RuntimeError('x'))
        assert AIService.diagnose_obd_code('P0')['found'] is False
        assert 'error' in AIService.get_sensor_info('MAF')
        assert AIService.get_ecu_knowledge('x') == {}

    def test_external_learning_errors(self, mocker):
        mocker.patch('ai_knowledge.learning.external_learning.get_external_learning', side_effect=RuntimeError('x'))
        assert AIService.get_learning_sources()['sources'] == []
        assert AIService.learn_from_external('w', 't', 'c')['success'] is False

    def test_integrate_search_data_path(self, mocker):
        integrator = MagicMock(search_data=MagicMock(return_value={'hits': [1]}))
        mocker.patch('ai_knowledge.core.system_integration.SystemIntegrator', return_value=integrator)
        assert AIService.integrate_with_system('customers', 'ali')['hits'] == [1]

    def test_action_unsuccessful_result(self, mocker):
        mocker.patch('flask_login.current_user', SimpleNamespace(is_authenticated=False))
        ex = MagicMock()
        ex.create_product.return_value = {'success': False, 'message': 'no'}
        mocker.patch('services.ai_executor.AIExecutor', return_value=ex)
        out = AIService._execute_ai_action(
            json.dumps({'action': 'create_product', 'data': {'name': 'p'}}),
            1,
        )
        assert 'no' in out

    def test_recommendations_low_medium_high(self):
        assert 'ممتاز' in AIService._get_risk_recommendation('low')
        assert 'جيد' in AIService._get_risk_recommendation('medium')
        assert 'عالي' in AIService._get_risk_recommendation('high')

    def test_normalize_timezone_aware_datetime(self, mocker, sample_customer):
        aware = datetime.now(timezone.utc)
        sale = MagicMock(total_amount=Decimal('100'), created_at=aware, customer=sample_customer, lines=[])
        mocker.patch.object(Sale, 'query')
        Sale.query.options.return_value.filter.return_value.all.return_value = [sale]
        from models import Payment
        mocker.patch.object(Payment, 'query')
        Payment.query.filter.return_value.all.return_value = []
        sample_customer.get_balance_aed = MagicMock(return_value=Decimal('0'))
        AIService._perform_analysis(sample_customer)

    def test_execute_unknown_action_returns_none(self, mocker):
        mocker.patch('flask_login.current_user', SimpleNamespace(is_authenticated=False))
        ex = MagicMock()
        mocker.patch('services.ai_executor.AIExecutor', return_value=ex)
        assert AIService._execute_ai_action('{"action": "unknown", "data": {}}', 1) is None

    def test_execute_logging_core_failure(self, mocker):
        mocker.patch('flask_login.current_user', SimpleNamespace(is_authenticated=False))
        mocker.patch('services.ai_executor.AIExecutor', side_effect=RuntimeError('x'))
        mocker.patch('services.logging_core.LoggingCore.log_error', side_effect=RuntimeError())
        assert 'خطأ' in AIService._execute_ai_action('{"action": "create_customer", "data": {}}', 1)

    def test_train_from_groq_failure(self, mocker):
        ls = MagicMock()
        ls.learn_from_groq_feedback.side_effect = RuntimeError('x')
        mocker.patch('ai_knowledge.core.learning_system.learning_system', ls)
        AIService._train_local_from_groq('q', 'l', 'g', 1)

    def test_customer_service_without_query(self):
        out = AIService.get_customer_service_response('')
        assert out
        assert 'استفسار' not in out

    def test_remaining_wrapper_errors(self, mocker):
        mocker.patch('services.ai_service.get_customer_service_tip', side_effect=RuntimeError('x'))
        assert 'عذراً' in AIService.get_customer_service_response('complaint')
        mocker.patch('services.ai_service.get_tax_info', side_effect=RuntimeError())
        mocker.patch('services.ai_service.get_tax_advice', side_effect=RuntimeError())
        assert AIService.get_tax_and_customs_info('vat') == {}
        mocker.patch('ai_knowledge.generation.document_generator.DocumentGenerator', side_effect=RuntimeError())
        assert AIService.generate_document_with_ai('x', {}) is None
        mocker.patch('ai_knowledge.expansion.knowledge_expansion.KnowledgeExpander', side_effect=RuntimeError())
        assert AIService.expand_knowledge_base('t') == {}
        mocker.patch('ai_knowledge.improvement.self_improvement.AzadSelfImprovement', side_effect=RuntimeError())
        assert AIService.perform_self_improvement() == {}
        mocker.patch('ai_knowledge.core.system_integration.SystemIntegrator', side_effect=RuntimeError())
        assert AIService.integrate_with_system('x', {}) == {}
        mocker.patch('ai_knowledge.expansion.global_knowledge.GlobalKnowledgeConnector', side_effect=RuntimeError())
        assert AIService.get_global_knowledge('q') == {}
        mocker.patch('ai_knowledge.personality.beginners_mode.BeginnersGuide', side_effect=RuntimeError())
        assert AIService.get_beginners_help('t') == {}

    def test_delegate_and_codegen_errors(self, mocker):
        mocker.patch('services.ai_service.AIService.get_agent_coordinator', side_effect=RuntimeError())
        assert AIService.delegate_to_expert('t') == {}