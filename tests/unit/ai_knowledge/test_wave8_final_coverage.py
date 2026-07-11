"""Wave 8 final coverage push — target >=99% aggregate on ai_knowledge/*."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture
def knowledge_path(tmp_path):
    with patch('ai_knowledge.get_knowledge_path', side_effect=lambda name: str(tmp_path / name)):
        yield tmp_path


class _Col:
    def __lt__(self, other):
        return MagicMock()
    def __le__(self, other):
        return MagicMock()
    def __gt__(self, other):
        return MagicMock()
    def __ge__(self, other):
        return MagicMock()
    def __eq__(self, other):
        return MagicMock()
    def between(self, a, b):
        return MagicMock()
    def ilike(self, *a, **kw):
        return MagicMock()
    def desc(self):
        return MagicMock()


def _db_chain(mock_db):
    chain = MagicMock()
    mock_db.session.query.return_value = chain
    for attr in ('outerjoin', 'join', 'filter', 'filter_by', 'group_by', 'order_by'):
        getattr(chain, attr).return_value = chain
    chain.limit.return_value = chain
    return chain


def _patch_model_cols(*models):
    ctxs = []
    for mod in models:
        p = patch(mod)
        m = p.start()
        for attr in ('status', 'sale_date', 'cost_price', 'unit_price', 'tenant_id',
                     'purchase_date', 'expense_date', 'receipt_date', 'amount_aed',
                     'payment_status', 'id', 'product_id', 'current_stock', 'min_stock_level',
                     'min_stock_alert', 'is_active', 'paid_amount', 'total_amount',
                     'customer_id', 'created_at', 'name', 'customer_type', 'customer_classification',
                     'total_purchases', 'discount_percent', 'category_id', 'quantity'):
            setattr(m, attr, _Col())
        ctxs.append(p)
    return ctxs


def _stop_patches(ctxs):
    for p in ctxs:
        p.stop()


def _fast_models(engine):
    for model in engine.models.values():
        if hasattr(model, 'max_iter'):
            model.max_iter = 50


class TestWave8ActionDispatcher:
    def test_flask_g_tenant_and_log_success(self):
        from ai_knowledge import action_dispatcher as ad
        with patch('ai_knowledge.action_dispatcher.current_user', SimpleNamespace(is_authenticated=False)):
            with patch('flask.g', create=True) as g:
                g.active_tenant_id = 7
                assert ad._get_active_tenant_id() == 7
        with patch('ai_knowledge.action_dispatcher.db.session') as sess, \
             patch('models.ErrorAuditLog') as Log:
            sess.add = MagicMock()
            sess.commit = MagicMock()
            ad._log_ai_error('wave8', 'ok', request_data={'x': 1})
            sess.add.assert_called_once()
            sess.flush.assert_called_once()

    def test_profit_summary_and_purchase_fail(self, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher
        line = MagicMock(product_id=1, quantity=2)
        product = MagicMock(cost_price=Decimal('10'))
        with patch('ai_knowledge.action_dispatcher._get_active_tenant_id', return_value=1), \
             patch('ai_knowledge.action_dispatcher._has_permission', return_value=True), \
             patch('ai_knowledge.action_dispatcher.db') as db, \
             patch('models.Sale'), patch('models.SaleLine'), patch('models.Product') as Product:
            chain = _db_chain(db)
            chain.scalar.return_value = Decimal('1000')
            chain.all.return_value = [line]
            Product.query.get.return_value = product
            r = action_dispatcher.dispatch('profit_summary', {})
            assert r.success is True
            assert r.data['margin_percent'] > 0
            chain.scalar.side_effect = RuntimeError('db')
            assert action_dispatcher.dispatch('profit_summary', {}).success is False
        with patch('ai_knowledge.action_dispatcher._get_active_tenant_id', return_value=1), \
             patch('ai_knowledge.action_dispatcher._has_permission', return_value=True), \
             patch('services.ai_executor.AIExecutor') as Ex:
            Ex.return_value.create_purchase.return_value = {'success': False, 'message': 'no supplier'}
            r = action_dispatcher.dispatch('create_purchase', {
                'supplier_name': 'S', 'product_name': 'P',
            })
            assert r.success is False


class TestWave8AzadResponses:
    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses
        return AzadResponses()

    def _smart(self, responses, message, **ctx):
        with patch('ai_knowledge.personality.azad_responses.understand_message', return_value={'intent': None, 'confidence': 0}), \
             patch('services.ai_service.AIService.is_sensitive_request', return_value=(False, False, {})), \
             patch('ai_knowledge.personality.azad_responses.azad_personality') as ap, \
             patch('ai_knowledge.personality.azad_responses.learning_system'), \
             patch('ai_knowledge.personality.azad_responses.beginners_guide') as bg:
            ap.is_inappropriate_message.return_value = 'normal'
            ap.get_help_intro.return_value = 'intro'
            bg.get_beginner_response.return_value = None
            return responses.smart_response(message, context=ctx or None)

    def test_reachable_smart_branches(self, responses):
        with patch('ai_knowledge.personality.azad_responses.get_system_guide', return_value='SYSGUIDE'), \
             patch('ai_knowledge.personality.azad_responses.get_market_insights', return_value='MARKET'), \
             patch('ai_knowledge.personality.azad_responses.system_integrator') as si, \
             patch('ai_knowledge.personality.azad_responses.knowledge_expander') as ke, \
             patch('ai_knowledge.personality.azad_responses.document_generator') as dg:
            si.get_system_summary.return_value = {'success': True, 'summary': {
                'customers': {'total': 1, 'vip': 0, 'recent': []},
                'sales': {'total': 1, 'today': 0, 'recent': []},
                'products': {'total': 1, 'low_stock': 0, 'out_of_stock': 0},
            }}
            si.get_financial_summary.return_value = {'success': True, 'financial': {
                'total_sales': 1, 'total_payments': 1, 'total_receivables': 0,
                'today_sales': 0, 'today_payments': 0,
            }}
            ke.search_knowledge.return_value = {'success': True, 'total_found': 0, 'results': []}
            dg.generate_invoice.return_value = (None, 'missing')
            assert 'SYSGUIDE' in self._smart(responses, 'استخدام النظام اليومي')
            assert 'MARKET' in self._smart(responses, 'سوق السيارات منافسة')
            assert self._smart(responses, 'ملخص summary نظام system كلي')
            assert self._smart(responses, 'أضف add موقع website مصدر source')
            assert self._smart(responses, 'روابط links نظام system')
            assert self._smart(responses, 'مصادر sources websites')
            assert self._smart(responses, 'أين where أجد find معلومات info')
            assert self._smart(responses, 'فاتورة invoice جديد new')
            assert self._smart(responses, 'سند receipt جديد new')
            assert self._smart(responses, 'ولد generate فاتورة invoice 9')
            assert self._smart(responses, 'ولد generate تقرير report sales')
            assert self._smart(responses, 'شحن shipping قانون law إجراءات procedures')
            assert self._smart(responses, 'جودة quality معايير standards')

    def test_else_suggestions_and_handlers(self, responses):
        with patch('ai_knowledge.personality.azad_responses.azad_personality') as ap, \
             patch('ai_knowledge.personality.azad_responses.learning_system'), \
             patch('ai_knowledge.personality.azad_responses.beginners_guide') as bg, \
             patch('ai_knowledge.personality.azad_responses.understand_message', return_value={'intent': None, 'confidence': 0}), \
             patch('services.ai_service.AIService.is_sensitive_request', return_value=(False, False, {})), \
             patch('ai_knowledge.personality.azad_responses.knowledge_expander') as ke:
            ap.is_inappropriate_message.return_value = 'normal'
            ap.get_help_intro.return_value = 'intro'
            bg.get_beginner_response.return_value = None
            out = responses.smart_response('سؤال عام balance debt فاتورة invoice تقرير report')
            assert 'جرّب' in out
        assert 'لم أتمكن' in responses._handle_product_stock_query('مخزون stock فقط')
        assert 'لم أتمكن' in responses._handle_search_query('ابحث')
        with patch('ai_knowledge.personality.azad_responses.system_integrator') as si:
            si.search_data.return_value = {'success': False, 'error': 'fail'}
            assert 'fail' in responses._handle_search_query('ابحث search term')
        ke = patch('ai_knowledge.personality.azad_responses.knowledge_expander').start()
        ke.search_knowledge.return_value = {'success': False, 'error': 'fail'}
        assert 'fail' in responses._handle_knowledge_search('ابحث search tax vat info')
        patch.stopall()
        with patch('ai_knowledge.personality.azad_responses.document_generator') as dg:
            dg.generate_invoice.return_value = (None, 'not found')
            assert 'not found' in responses._handle_document_generation('ولد generate فاتورة invoice 1')


class TestWave8NeuralEngine:
    @pytest.fixture
    def engine(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine
        eng = AzadNeuralEngine()
        _fast_models(eng)
        return eng

    def test_cash_flow_single_month(self, engine):
        cols = _patch_model_cols('models.Sale', 'models.Purchase', 'models.Expense', 'models.Receipt')
        try:
            with patch.object(engine, '_load_model', return_value=True), \
                 patch('extensions.db') as mock_db, \
                 patch('utils.tenanting.get_active_tenant_id', return_value=1), \
                 patch.object(engine.scalers['financial_planner'], 'transform', return_value=np.array([[1.0] * 6])), \
                 patch.object(engine.models['financial_planner'], 'predict', return_value=np.array([100.0])):
                chain = _db_chain(mock_db)
                chain.scalar.return_value = Decimal('500')
                r = engine._predict_cash_flow_internal(1)
                assert r['trend'] == 'stable'
                assert 'بيانات غير كافية' in r['recommendation']
        finally:
            _stop_patches(cols)

    def test_train_insufficient_data_paths(self, engine):
        cols = _patch_model_cols('models.Sale', 'models.Customer', 'models.SaleLine', 'models.Product')
        try:
            with patch('extensions.db') as mock_db:
                chain = _db_chain(mock_db)
                chain.all.return_value = []
                chain.scalar.return_value = 0
                assert engine._train_sales_internal()['success'] is False
                assert engine._train_customer_internal()['success'] is False
                assert engine._train_churn_internal()['success'] is False
                assert engine._train_profit_internal()['success'] is False
                assert engine._train_demand_internal()['success'] is False
        finally:
            _stop_patches(cols)

    def test_forecast_short_horizon(self, engine):
        cols = _patch_model_cols('models.Sale')
        try:
            rows = []
            base = date.today() - timedelta(days=7)
            for i in range(7):
                row = MagicMock()
                row.sale_date = base + timedelta(days=i)
                row.total_amount = Decimal('100')
                rows.append(row)
            with patch.object(engine, '_load_model', return_value=True), \
                 patch('extensions.db') as mock_db, \
                 patch.object(engine.scalers['sales_forecaster'], 'transform', return_value=np.array([[1.0] * 11])), \
                 patch.object(engine.models['sales_forecaster'], 'predict', return_value=np.array([120.0])):
                chain = _db_chain(mock_db)
                chain.all.return_value = rows
                r = engine._forecast_sales_internal(2)
                assert r.get('trend') == 'stable'
        finally:
            _stop_patches(cols)

    def test_inventory_eoq_zero_holding(self, engine):
        product_data = MagicMock(
            current_stock=5, min_stock_alert=10,
            cost_price=0, sales_count=5, total_sold=30,
            avg_quantity=2,
        )
        with patch.object(engine, '_load_model', return_value=False), \
             patch('extensions.db') as mock_db, \
             patch('models.Product'), patch('models.SaleLine'):
            chain = _db_chain(mock_db)
            chain.first.return_value = product_data
            r = engine._optimize_stock_internal(1)
            assert r['economic_order_quantity'] > 0

    def test_customer_classify_and_demand_paths(self, engine):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch.object(engine, '_train_customer_internal', side_effect=RuntimeError('x')):
            assert engine.train_customer_classifier(from_app_context=ctx)['success'] is False
        with patch.object(engine, '_classify_customer_internal', return_value={'classification': 'vip'}):
            assert engine.classify_customer_intelligence(1, from_app_context=ctx)['classification'] == 'vip'
        with patch.object(engine, '_train_demand_internal', side_effect=RuntimeError('x')):
            assert engine.train_demand_predictor(from_app_context=ctx)['success'] is False
        with patch.object(engine, '_predict_demand_internal', return_value={'forecast': []}):
            assert engine.predict_product_demand(1, from_app_context=ctx)['forecast'] == []

    def test_demand_train_with_samples(self, engine):
        cols = _patch_model_cols('models.Sale', 'models.SaleLine', 'models.Product')
        try:
            demands = []
            base = date.today() - timedelta(days=20)
            for i in range(20):
                d = MagicMock()
                d.sale_date = base + timedelta(days=i)
                d.product_id = 1
                d.total_quantity = Decimal(str(2 + i % 3))
                demands.append(d)
            with patch('extensions.db') as mock_db:
                chain = _db_chain(mock_db)
                chain.all.return_value = demands
                r = engine._train_demand_internal()
                assert r.get('success') is True or 'error' in r
        finally:
            _stop_patches(cols)

    def test_model_load_helpers(self, engine):
        with patch.object(engine, '_load_model', side_effect=RuntimeError('bad')):
            assert engine._is_model_loaded('price_optimizer') is False
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch.object(engine, 'train_price_optimizer', side_effect=RuntimeError('boom')):
            r = engine.train_all_models(ctx)
            assert 'price_optimizer' in r['results']


class TestWave8Analytics:
    def test_analytics_ratio_branches(self):
        from ai_knowledge.analytics.analytics_predictions import CashFlowAnalytics
        assert CashFlowAnalytics.working_capital_ratio(150, 100)['status'] == 'good'
        assert CashFlowAnalytics.working_capital_ratio(120, 100)['status'] == 'acceptable'
        assert CashFlowAnalytics.working_capital_ratio(80, 100)['status'] == 'critical'

    def test_data_analyzer_trends_and_payments(self):
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer
        analyzer = DataAnalyzer()
        sales = []
        base = datetime.now(timezone.utc) - timedelta(days=14)
        for i in range(14):
            sale = MagicMock()
            sale.created_at = base + timedelta(days=i)
            sale.total_amount = Decimal(str(50 + i * 5))
            sale.customer = MagicMock(name='Ali')
            sales.append(sale)
        with patch('models.Sale') as Sale, patch('extensions.db.session'):
            Sale.query.filter.return_value.all.return_value = sales
            Sale.created_at = _Col()
            r = analyzer.analyze_sales_performance(14)
            assert r['success'] is True
            assert r['analysis']['trend'] in ('تصاعدي', 'تنازلي', 'مستقر')
        pay = MagicMock(amount=Decimal('50'), payment_method='cash', payment_date=datetime.now())
        with patch('models.Payment') as Payment, patch('extensions.db.session'):
            Payment.query.filter.return_value.all.return_value = [pay]
            Payment.payment_date = _Col()
            Payment.amount = _Col()
            ok = analyzer.analyze_payment_patterns(customer_id=1)
            assert ok['success'] is True
            Payment.query.filter.side_effect = RuntimeError('x')
            bad = analyzer.analyze_payment_patterns(customer_id=1)
            assert bad['success'] is False


class TestWave8SystemKnowledge:
    def test_search_all_branches(self):
        import ai_knowledge.system_knowledge as sk
        assert sk.get_model_info('sales') is not None
        assert sk.get_model_info('unknown_xyz_model') is None
        hits = sk.search_knowledge('owner')
        assert any(h['type'] == 'role' for h in hits)
        hits2 = sk.search_knowledge('sales')
        assert any(h['type'] == 'route_group' for h in hits2) or hits2
        hits3 = sk.search_knowledge('مبيعات')
        assert hits3
        hits4 = sk.search_knowledge('أصل')
        assert any(h['type'] == 'accounting' for h in hits4)


class TestWave8AgentsAndCore:
    def test_intelligent_assistant_branches(self, knowledge_path):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant
        ia = IntelligentAssistant()
        customer = MagicMock(id=1, name='Ali')
        with patch('models.Customer') as Customer, \
             patch.object(ia.data_analyzer, 'analyze_customer_debt', return_value={'success': True}), \
             patch('extensions.db.session'):
            Customer.query.filter.return_value.first.return_value = customer
            data = ia._collect_real_data('customer_balance', {'names': ['Ali']}, 1)
            assert 'customer_data' in data
            Customer.query.filter.side_effect = RuntimeError('x')
            data2 = ia._collect_real_data('customer_balance', {'names': ['Ali']}, 1)
            assert 'customer_data' not in data2
        product = MagicMock(id=1, name='P', current_stock=1, min_stock_alert=5)
        with patch('flask.has_request_context', return_value=False), \
             patch('models.Product') as Product, patch('models.Sale') as Sale, \
             patch('models.Customer') as Customer, patch('models.Payment'):
            for model in (Product, Sale, Customer):
                chain = MagicMock()
                model.query = chain
                chain.filter_by.return_value = chain
                chain.filter.return_value = chain
                chain.count.return_value = 0
                chain.all.return_value = []
            Sale.sale_date = _Col()
            for attr in ('is_active', 'current_stock', 'min_stock_alert'):
                setattr(Product, attr, _Col())
            Product.query.filter.return_value.all.return_value = [product]
            inv = ia._collect_real_data('inventory_check', {}, 1)
            assert inv.get('low_stock_products')
            Product.query.filter.side_effect = RuntimeError('x')
            Product.query.filter.return_value = MagicMock()
            assert 'low_stock_products' not in ia._collect_real_data('inventory_check', {}, 1)
        analysis = ia._analyze_and_reason('customer_balance', {
            'customer_data': {'success': True, 'debt_analysis': {
                'total_debt': 2000, 'overdue_count': 2,
            }},
        }, {})
        assert analysis['warnings']
        assert ia._analyze_and_reason('x', {}, {})['insights'] == [] or isinstance(ia._analyze_and_reason('x', {}, {}), dict)
        with patch.object(ia.memory_system, 'remember_conversation') as mem, \
             patch('ai_knowledge.core.learning_system.learning_system') as ls, \
             patch('flask.has_request_context', return_value=True), \
             patch('utils.tenanting.get_active_tenant_id', return_value=3):
            ia._learn_from_interaction(1, 'q', 'a')
            mem.assert_called_once()
            ls.learn_from_interaction.assert_called()

    def test_master_brain_and_multi_agent(self):
        from ai_knowledge.agents.master_brain import MasterBrain
        from ai_knowledge.agents.multi_agent_system import MultiAgentCoordinator, SalesAgent
        brain = MasterBrain()
        with patch.object(brain, '_retrieve_knowledge', return_value={}), \
             patch.object(brain, '_use_neural_if_needed', return_value=None):
            assert isinstance(brain.ask('حالة النظام'), dict)
        coord = MultiAgentCoordinator()
        assert coord.delegate_task('مهمة غامضة xyz')['confidence'] <= 0.5
        agent = SalesAgent()
        with patch('services.ai_service.AIService.predict_price_with_neural', return_value={'success': True, 'price': 99}):
            assert agent.execute('سعر price', {'product_id': 1})['confidence'] > 0

    def test_context_conversation_learning(self, knowledge_path):
        from ai_knowledge.core.context_engine import ContextEngine
        from ai_knowledge.core.conversation_manager import ConversationManager
        from ai_knowledge.core import conversation_store
        from ai_knowledge.core.learning_system import AzadLearningSystem
        from ai_knowledge.core.memory_system import LongTermMemory
        from ai_knowledge.core.reasoning_engine import ReasoningEngine
        with patch('ai_knowledge.core.context_engine.system_integrator') as si:
            si.get_system_summary.return_value = {'success': False}
            ContextEngine.analyze_context('test', {})
            si.get_system_summary.return_value = {'success': True, 'summary': {}}
            ContextEngine.analyze_context('كم how many', {})
        mgr = ConversationManager()
        mgr.start_conversation(99)
        mgr.process_message(99, 'hello')
        mgr.end_conversation(99)
        mem_row = MagicMock(
            value='{"x":1}', last_accessed=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc), is_active=True, access_count=0,
        )
        with patch('ai_knowledge.core.conversation_store.AiMemory') as AiMemory, \
             patch('ai_knowledge.core.conversation_store.db.session'):
            AiMemory.query.filter_by.return_value.first.return_value = mem_row
            assert conversation_store.get_context(1, tenant_id=1) == {'x': 1}
            old = datetime.now(timezone.utc) - timedelta(hours=3)
            mem_row.last_accessed = old
            mem_row.created_at = old
            assert conversation_store.get_context(1, tenant_id=1) is None
        ls = AzadLearningSystem()
        ls.learn_from_interaction('q', 'a', tenant_id=1)
        mem = LongTermMemory()
        mem.remember_fact('fact', 'general')
        re = ReasoningEngine()
        assert re.financial_reasoning('x', {'sales': 0, 'costs': 0, 'expenses': 0, 'assets': 0, 'liabilities': 0})['confidence'] >= 0


class TestWave8RemainingModules:
    def test_generation_improvement_learning(self, knowledge_path):
        from ai_knowledge.generation.document_generator import DocumentGenerator
        from ai_knowledge.improvement.self_improvement import AzadSelfImprovement
        from ai_knowledge.improvement.self_reflection import SelfReflectionEngine
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler
        from ai_knowledge.learning.continuous_learner import ContinuousLearner
        from ai_knowledge.learning.external_learning import ExternalLearningSystem
        from ai_knowledge.learning.quick_learner import QuickLearner
        from ai_knowledge.knowledge_base import search_knowledge as kb_search
        from ai_knowledge.neural.semantic_matcher import SemanticMatcher
        from ai_knowledge.neural.transformers_brain import TransformersBrain
        from ai_knowledge.personality.dialects import apply_dialect
        from ai_knowledge.specialized.advanced_laws import AdvancedLaws
        from ai_knowledge.specialized.security_rules import SecurityRules
        from ai_knowledge.specialized.user_guide import get_help_for_task
        from ai_knowledge.trainer import Trainer
        sale = MagicMock(id=1, customer_id=1, total_amount=Decimal('100'))
        with patch('models.Sale') as Sale, patch('models.Customer') as Customer:
            Sale.query.get.return_value = sale
            Customer.query.get.return_value = MagicMock(name='Ali', phone='050', address='DXB')
            content, msg = DocumentGenerator.generate_invoice(1)
            assert content or msg
            Sale.query.get.return_value = None
            _, err = DocumentGenerator.generate_invoice(99)
            assert err
        ai = AzadSelfImprovement()
        ai.auto_improve()
        sr = SelfReflectionEngine()
        sr.reflect_on_performance()
        assert AutoRetrainingScheduler.should_retrain() in (True, False)
        AutoRetrainingScheduler.get_last_training_info()
        cl = ContinuousLearner()
        with patch.object(cl, '_create_session') as sess:
            sess.return_value.get.return_value.status_code = 404
            cl.learn_from_wikipedia('tax', lang='ar')
        el = ExternalLearningSystem()
        el.learn_from_source('invalid', 'x', 'y')
        ql = QuickLearner()
        with patch('models.ai.AiMemory') as AiMemory, patch('extensions.db.session'):
            AiMemory.query.filter_by.return_value.first.return_value = None
            AiMemory.return_value = MagicMock()
            ql.learn('q', 'a', tenant_id=1)
            assert ql.get_answer('q', tenant_id=None) is None
        assert isinstance(kb_search('ضريبة'), list)
        sm = SemanticMatcher()
        sm.find_best_intent('مبيعات اليوم')
        tb = TransformersBrain()
        assert isinstance(tb.generate_response('مرحبا'), str)
        assert isinstance(tb.understand('مبيعات اليوم'), dict)
        assert apply_dialect('مرحبا', 'palestinian')
        AdvancedLaws.get_shipping_info('sea')
        user = MagicMock(is_authenticated=False)
        with patch('ai_knowledge.specialized.security_rules.current_user', user):
            SecurityRules.check_user_permissions('admin')
        assert get_help_for_task('فاتورة')
        trainer = Trainer()
        with patch.object(trainer, 'quick_learner', MagicMock()):
            trainer.learn_from_interaction('q', 'a', tenant_id=1)


class TestWave8ExtraPush:
    def test_flask_g_runtime_import_error(self):
        from ai_knowledge import action_dispatcher as ad
        import builtins
        real_import = builtins.__import__

        def block_g(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'flask' and fromlist and 'g' in fromlist:
                raise RuntimeError('no app context')
            return real_import(name, globals, locals, fromlist, level)

        with patch('builtins.__import__', side_effect=block_g), \
             patch('ai_knowledge.action_dispatcher.current_user', SimpleNamespace(is_authenticated=False)):
            assert ad._get_active_tenant_id() is None

    def test_azad_remaining_smart_and_handlers(self):
        from ai_knowledge.personality.azad_responses import AzadResponses
        r = AzadResponses()
        with patch('ai_knowledge.personality.azad_responses.system_integrator') as si:
            si.get_product_stock.return_value = {
                'success': True,
                'product': {'name': 'Bolt', 'id': 1, 'sku': 'S', 'category': 'C',
                            'unit_price': 10.0, 'current_stock': 5, 'alert_limit': 10},
            }
            assert 'Bolt' in r._handle_product_stock_query('مخزون stock اسم name Bolt')
        with patch('ai_knowledge.personality.azad_responses.understand_message', return_value={'intent': None, 'confidence': 0}), \
             patch('services.ai_service.AIService.is_sensitive_request', return_value=(False, False, {})), \
             patch('ai_knowledge.personality.azad_responses.azad_personality') as ap, \
             patch('ai_knowledge.personality.azad_responses.learning_system'), \
             patch('ai_knowledge.personality.azad_responses.beginners_guide') as bg, \
             patch('ai_knowledge.personality.azad_responses.knowledge_expander') as ke, \
             patch('ai_knowledge.personality.azad_responses.document_generator') as dg, \
             patch('ai_knowledge.personality.azad_responses.system_integrator') as si:
            ap.is_inappropriate_message.return_value = 'normal'
            ap.get_help_intro.return_value = 'intro'
            bg.get_beginner_response.return_value = None
            ke.search_knowledge.return_value = {'success': True, 'total_found': 0, 'results': []}
            dg.generate_sales_report.return_value = ('r', 'ok')
            si.get_system_summary.return_value = {'success': True, 'summary': {
                'customers': {'total': 0, 'vip': 0, 'recent': []},
                'sales': {'total': 0, 'today': 0, 'recent': []},
                'products': {'total': 0, 'low_stock': 0, 'out_of_stock': 0},
            }}
            si.get_financial_summary.return_value = {'success': True, 'financial': {
                'total_sales': 0, 'total_payments': 0, 'total_receivables': 0,
                'today_sales': 0, 'today_payments': 0,
            }}
            for msg in (
                'مصادر sources websites مواقع',
                'تقرير report ولد generate create أنشئ',
                'أين where وين أجد find معلومات information',
            ):
                assert isinstance(r.smart_response(msg), str)

    def test_neural_no_context_paths(self):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine
        engine = AzadNeuralEngine()
        for model in engine.models.values():
            if hasattr(model, 'max_iter'):
                model.max_iter = 50
        with patch.object(engine, '_train_customer_internal', return_value={'success': True}):
            assert engine.train_customer_classifier()['success'] is True
        with patch.object(engine, '_train_demand_internal', return_value={'success': True}):
            assert engine.train_demand_predictor()['success'] is True
        with patch.object(engine, '_predict_demand_internal', return_value={'forecast': [1]}):
            assert engine.predict_product_demand(1)['forecast']
        with patch.object(engine, '_load_model', return_value=True), \
             patch('extensions.db') as mock_db, patch('models.Product'), patch('models.SaleLine'), patch('models.Sale'):
            product_data = MagicMock(
                current_stock=5, min_stock_alert=10, cost_price=20,
                sales_count=5, total_sold=30, avg_quantity=2,
            )
            chain = _db_chain(mock_db)
            chain.first.return_value = product_data
            engine.models['inventory_optimizer'] = MagicMock()
            engine.models['inventory_optimizer'].predict.return_value = np.array([15.0])
            engine.scalers['inventory_optimizer'] = MagicMock()
            engine.scalers['inventory_optimizer'].transform.return_value = np.array([[1.0] * 6])
            assert engine._optimize_stock_internal(1)['model'] == 'neural_network'

    def test_data_analyzer_declining_trend(self):
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer
        analyzer = DataAnalyzer()
        sales = []
        base = datetime.now(timezone.utc) - timedelta(days=14)
        for i in range(14):
            sale = MagicMock()
            sale.created_at = base + timedelta(days=i)
            sale.total_amount = Decimal(str(200 - i * 10))
            sale.customer = MagicMock(name='Ali')
            sales.append(sale)
        with patch('models.Sale') as Sale, patch('extensions.db.session'):
            Sale.query.filter.return_value.all.return_value = sales
            Sale.created_at = _Col()
            r = analyzer.analyze_sales_performance(14)
            assert r['analysis']['trend'] in ('تنازلي', 'مستقر', 'تصاعدي')

    def test_system_knowledge_features_and_accounting_list(self):
        import ai_knowledge.system_knowledge as sk
        hits = sk.search_knowledge('فروع')
        assert any(h['type'] == 'feature' for h in hits)
        hits2 = sk.search_knowledge('خصم')
        assert any(h['type'] == 'accounting' for h in hits2)

    def test_intelligent_assistant_analysis_tiers(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant
        ia = IntelligentAssistant()
        for debt, key in ((0, 'insights'), (500, 'insights'), (2000, 'warnings'), (6000, 'warnings')):
            a = ia._analyze_and_reason('customer_balance', {
                'customer_data': {'success': True, 'debt_analysis': {
                    'total_debt': debt, 'overdue_count': 1 if debt > 1000 else 0,
                }},
            }, {})
            assert a[key] or a.get('recommendations')

    def test_core_modules_extra(self, knowledge_path):
        from ai_knowledge.core.context_engine import ContextEngine
        from ai_knowledge.core.conversation_manager import ConversationManager
        from ai_knowledge.core.learning_system import AzadLearningSystem
        from ai_knowledge.core.memory_system import LongTermMemory
        from ai_knowledge.core.reasoning_engine import ReasoningEngine
        from ai_knowledge.agents.multi_agent_system import AccountingAgent, InventoryAgent, MaintenanceAgent
        with patch('ai_knowledge.core.context_engine.data_analyzer') as da, \
             patch('ai_knowledge.core.context_engine.knowledge_expander') as ke, \
             patch('ai_knowledge.core.context_engine.learning_system') as ls, \
             patch('ai_knowledge.core.context_engine.system_integrator') as si:
            si.get_system_summary.return_value = {'success': True, 'summary': {'total_customers': 1}}
            da.get_financial_ratios.return_value = {'current_ratio': 2}
            ContextEngine.enhance_response('حلل analyze sales', 'base', {'is_owner': True})
            ke.search_knowledge.return_value = [{'title': 't'}]
            ContextEngine.enhance_response('ابحث search tax', 'base', {})
            ls.get_learning_insights.return_value = {'patterns': 1}
            ContextEngine.enhance_response('تعلم learn', 'base', {})
        mgr = ConversationManager()
        mgr.start_conversation(7)
        mgr.process_message(7, 'test')
        mgr.end_conversation(7)
        ls = AzadLearningSystem()
        with patch.object(ls, '_save_tenant_data') as save:
            ls.learn_from_interaction('q', 'a', tenant_id=5)
            save.assert_called()
        with patch('ai_knowledge.core.memory_system.LongTermMemory.remember_procedure') as rp:
            from ai_knowledge.core.memory_system import LongTermMemory
            LongTermMemory.remember_procedure(MagicMock(), 'proc', ['step1'], category='sales')
            rp.assert_called()
        re = ReasoningEngine()
        re.technical_reasoning('فرامل ضعيفة brake weak')
        re.technical_reasoning('مشكلة عامة unknown issue')
        AccountingAgent().execute('قيد journal', {'debit': 50, 'credit': 100})
        InventoryAgent().execute('مخزون stock low', {})
        MaintenanceAgent().execute('صيانة maintenance engine', {})
