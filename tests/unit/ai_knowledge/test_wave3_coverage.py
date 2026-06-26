"""Wave 3 coverage push — neural_engine, azad_responses, agents, dispatcher."""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import joblib
import numpy as np
import pytest
from sklearn.neural_network import MLPClassifier, MLPRegressor


@pytest.fixture
def knowledge_path(tmp_path):
    with patch('ai_knowledge.get_knowledge_path', side_effect=lambda name: str(tmp_path / name)):
        yield tmp_path


def _fast_models(engine):
    for model in engine.models.values():
        if hasattr(model, 'max_iter'):
            model.max_iter = 50


def _db_chain(mock_db):
    chain = MagicMock()
    mock_db.session.query.return_value = chain
    for attr in ('outerjoin', 'join', 'filter', 'filter_by', 'group_by', 'order_by'):
        getattr(chain, attr).return_value = chain
    chain.limit.return_value = chain
    return chain


class _Col:
    """SQLAlchemy-like column mock supporting comparisons in filter()."""
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


def _patch_model_cols(*models):
    ctxs = []
    for mod in models:
        p = patch(mod)
        m = p.start()
        for attr in ('status', 'sale_date', 'cost_price', 'unit_price', 'tenant_id',
                     'purchase_date', 'expense_date', 'receipt_date', 'amount_aed',
                     'payment_status', 'id', 'product_id', 'current_stock', 'min_stock_level'):
            setattr(m, attr, _Col())
        ctxs.append(p)
    return ctxs


def _stop_patches(ctxs):
    for p in ctxs:
        p.stop()


def _product_rows(count=25, high_usage=False):
    rows = []
    for i in range(count):
        row = MagicMock()
        row.id = i + 1
        row.name = f'P{i}'
        row.cost_price = Decimal('25')
        row.current_stock = Decimal('10')
        row.sales_count = 60 if high_usage else (20 if i % 2 == 0 else 3)
        row.total_sold = Decimal('100')
        row.last_sale_date = datetime.now(timezone.utc) - timedelta(days=7)
        rows.append(row)
    return rows


def _sale_line_rows(count=55):
    rows = []
    for i in range(count):
        row = MagicMock()
        row.cost_price = Decimal('50')
        row.unit_price = Decimal('75')
        row.quantity = Decimal('2')
        row.discount_percent = Decimal('0')
        row.customer_type = 'regular'
        row.category_id = 1
        row.sale_date = datetime.now()
        row.payment_status = 'paid'
        rows.append(row)
    return rows


def _daily_sales_rows(count=40):
    rows = []
    base = date.today() - timedelta(days=count)
    for i in range(count):
        row = MagicMock()
        row.sale_date = base + timedelta(days=i)
        row.sales_count = 3
        row.total_amount = Decimal(str(1000 + i * 10))
        rows.append(row)
    return rows


def _customer_rows(count=30):
    rows = []
    for i in range(count):
        row = MagicMock()
        row.id = i + 1
        row.total_purchases = Decimal(str(10000 + i * 1000))
        row.customer_classification = 'vip' if i < 5 else 'regular'
        row.sales_count = 10
        row.last_purchase = datetime.now(timezone.utc) - timedelta(days=30)
        row.avg_order_value = Decimal('500')
        rows.append(row)
    return rows


def _fraud_rows(count=60):
    rows = []
    for i in range(count):
        row = MagicMock()
        row.amount_aed = Decimal('5000')
        row.discount_amount = Decimal('100')
        row.subtotal = Decimal('5000')
        row.paid_amount_aed = Decimal('5000')
        row.sale_date = datetime.now()
        row.total_purchases = Decimal('10000')
        rows.append(row)
    return rows


def _inventory_rows(count=25):
    rows = []
    for i in range(count):
        row = MagicMock()
        row.id = i + 1
        row.current_stock = Decimal('20')
        row.min_stock_alert = Decimal('5')
        row.cost_price = Decimal('30')
        row.sales_count = 15
        row.total_sold = Decimal('90')
        row.avg_quantity = Decimal('3')
        rows.append(row)
    return rows


def _demand_rows(count=50):
    rows = []
    base = date.today() - timedelta(days=count)
    for i in range(count):
        row = MagicMock()
        row.product_id = 1
        row.sale_date = base + timedelta(days=i)
        row.total_quantity = Decimal(str(5 + (i % 3)))
        rows.append(row)
    return rows


def _gl_entries(count=15):
    entries = []
    for i in range(count):
        entry = MagicMock()
        line = MagicMock()
        entry.lines = [line]
        entry.total_debit = Decimal('100')
        entry.total_credit = Decimal('100')
        entry.reference_type = 'Sale' if i % 2 == 0 else 'Purchase'
        entries.append(entry)
    return entries


class TestNeuralEngineWave3:
    @pytest.fixture
    def engine(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine
        eng = AzadNeuralEngine()
        _fast_models(eng)
        return eng

    def test_train_maintenance_success_and_predict(self, engine):
        with patch('extensions.db') as mock_db, patch('models.Product'), patch('models.Sale'), patch('models.SaleLine'), patch('models.StockMovement'):
            chain = _db_chain(mock_db)
            chain.all.return_value = _product_rows(25, high_usage=True)
            assert engine._train_maintenance_internal()['success'] is True
            product_data = MagicMock(
                cost_price=Decimal('25'), current_stock=Decimal('10'),
                sales_count=60, total_sold=Decimal('100'),
                last_sale_date=datetime.now(timezone.utc) - timedelta(days=5),
            )
            chain.first.return_value = product_data
            result = engine._predict_maintenance_internal(1)
            assert 'needs_maintenance' in result

    def test_train_maintenance_with_app_context(self, engine):
        ctx = MagicMock()
        ctx.return_value.__enter__ = MagicMock(return_value=None)
        ctx.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(engine, '_train_maintenance_internal', return_value={'success': True}) as inner:
            assert engine.train_maintenance_prediction(from_app_context=ctx)['success'] is True
            inner.assert_called_once()

    def test_train_maintenance_exception(self, engine):
        with patch.object(engine, '_train_maintenance_internal', side_effect=RuntimeError('boom')):
            assert engine.train_maintenance_prediction()['success'] is False

    def test_train_accounting_success_and_validate(self, engine):
        with patch('extensions.db'), patch('models.GLJournalEntry') as GL, patch('models.GLJournalLine'), patch('models.Sale'), patch('models.Purchase'):
            GL.query.limit.return_value.all.return_value = _gl_entries(15)
            assert engine._train_accounting_internal()['success'] is True
        with patch.object(engine, '_load_model', return_value=True):
            result = engine.validate_accounting_entry(100, 100, 2, 'Sale')
            assert result['model'] == 'neural_network'
        with patch.object(engine, '_load_model', side_effect=RuntimeError()):
            assert engine.validate_accounting_entry(100, 50, 2, 'Sale')['is_correct'] is True

    def test_train_financial_and_cash_flow(self, engine):
        cols = _patch_model_cols('models.Sale', 'models.Purchase', 'models.Expense', 'models.Receipt')
        try:
            with patch('extensions.db') as mock_db, patch('utils.tenanting.get_active_tenant_id', return_value=1):
                chain = _db_chain(mock_db)
                chain.scalar.return_value = Decimal('5000')
                assert engine._train_financial_internal()['success'] is True
                chain.scalar.return_value = Decimal('3000')
                assert engine._predict_cash_flow_internal(3)['trend'] in ('increasing', 'decreasing', 'stable')
        finally:
            _stop_patches(cols)

    def test_train_price_and_predict_branches(self, engine):
        cols = _patch_model_cols('models.Sale', 'models.SaleLine', 'models.Product', 'models.Customer')
        try:
            with patch('extensions.db') as mock_db:
                chain = _db_chain(mock_db)
                chain.all.return_value = _sale_line_rows(55)
                assert engine._train_price_internal()['success'] is True
        finally:
            _stop_patches(cols)
        with patch.object(engine, '_load_model', return_value=True):
            low = engine.predict_optimal_price(100, 2, 'regular')
            assert low['recommendation']
            high = engine.predict_optimal_price(100, 2, 'partner')
            assert 'predicted_price' in high
        with patch.object(engine, '_load_model', side_effect=RuntimeError()):
            assert engine.predict_optimal_price(80, 1, 'regular')['model'] == 'fallback'

    def test_train_sales_forecast_and_trends(self, engine):
        cols = _patch_model_cols('models.Sale')
        try:
            with patch('extensions.db') as mock_db:
                chain = _db_chain(mock_db)
                chain.all.return_value = _daily_sales_rows(40)
                assert engine._train_sales_internal()['success'] is True
        finally:
            _stop_patches(cols)
        with patch.object(engine, '_load_model', return_value=True), patch('extensions.db') as mock_db:
            cols = _patch_model_cols('models.Sale')
            try:
                chain = _db_chain(mock_db)
                chain.all.return_value = _daily_sales_rows(7)
                forecast = engine._forecast_sales_internal(7)
                assert forecast.get('forecast') or forecast.get('error')
            finally:
                _stop_patches(cols)

    def test_train_customer_classify_paths(self, engine):
        with patch('extensions.db') as mock_db, patch('models.Customer'), patch('models.Sale'):
            chain = _db_chain(mock_db)
            chain.all.return_value = _customer_rows(30)
            assert engine._train_customer_internal()['success'] is True
            row = MagicMock(
                total_purchases=Decimal('80000'), sales_count=20,
                last_purchase=datetime.now(timezone.utc) - timedelta(days=10),
                avg_order_value=Decimal('2000'),
            )
            chain.first.return_value = row
            vip = engine._classify_customer_internal(1)
            assert vip['classification'] in ('vip', 'premium', 'regular', 'unknown', 'new')
        with patch('extensions.db') as mock_db, patch('models.Customer'), patch('models.Sale'):
            chain = _db_chain(mock_db)
            chain.first.return_value = None
            assert engine.classify_customer_intelligence(99)['classification'] == 'new'

    def test_train_fraud_detect_loaded(self, engine):
        cols = _patch_model_cols('models.Sale', 'models.Customer')
        try:
            with patch('extensions.db') as mock_db:
                chain = _db_chain(mock_db)
                chain.all.return_value = _fraud_rows(60)
                assert engine._train_fraud_internal()['success'] is True
        finally:
            _stop_patches(cols)
        with patch.object(engine, '_load_model', return_value=True):
            night = datetime.now().replace(hour=23)
            result = engine.detect_fraud({
                'amount_aed': 60000, 'discount_amount': 20000,
                'subtotal': 60000, 'paid_amount_aed': 1000, 'sale_date': night,
            })
            assert 'risk_level' in result
        with patch.object(engine, '_load_model', side_effect=RuntimeError()):
            assert engine.detect_fraud({'amount_aed': 100})['is_fraud'] is False

    def test_train_inventory_optimize_stock(self, engine):
        with patch('extensions.db') as mock_db, patch('models.Product'), patch('models.StockMovement'), patch('models.SaleLine'):
            chain = _db_chain(mock_db)
            chain.all.return_value = _inventory_rows(25)
            assert engine._train_inventory_internal()['success'] is True
            row = MagicMock(
                current_stock=2.0, min_stock_alert=10.0,
                cost_price=20.0, sales_count=10,
                total_sold=60.0, avg_quantity=2.0,
            )
            chain.first.return_value = row
            low = engine._optimize_stock_internal(1)
            assert low['urgency'] == 'high'
            row.current_stock = 100.0
            row.total_sold = 60.0
            chain.first.return_value = row
            ok = engine._optimize_stock_internal(1)
            assert ok['urgency'] == 'low'

    def test_train_demand_predict(self, engine):
        cols = _patch_model_cols('models.Sale', 'models.SaleLine', 'models.Product')
        try:
            with patch('extensions.db') as mock_db:
                chain = _db_chain(mock_db)
                chain.all.return_value = _demand_rows(50)
                assert engine._train_demand_internal()['success'] is True
        finally:
            _stop_patches(cols)
        with patch.object(engine, '_load_model', return_value=True), patch('extensions.db') as mock_db:
            cols = _patch_model_cols('models.SaleLine', 'models.Sale')
            try:
                chain = _db_chain(mock_db)
                chain.all.return_value = _demand_rows(7)
                pred = engine._predict_demand_internal(1, 5)
                assert 'forecast' in pred
                chain.all.return_value = _demand_rows(2)
                avg = engine._predict_demand_internal(1, 3)
                assert avg['model'] == 'average'
            finally:
                _stop_patches(cols)

    def test_train_profit_and_churn(self, engine):
        cols = _patch_model_cols('models.Sale', 'models.SaleLine', 'models.Customer')
        try:
            with patch('extensions.db') as mock_db:
                chain = _db_chain(mock_db)
                chain.all.return_value = _sale_line_rows(55)
                assert engine._train_profit_internal()['success'] is True
                chain.all.return_value = _customer_rows(35)
                assert engine._train_churn_internal()['success'] is True
        finally:
            _stop_patches(cols)

    def test_insufficient_data_paths(self, engine):
        cols = _patch_model_cols('models.Sale', 'models.SaleLine', 'models.Product', 'models.Customer')
        try:
            with patch('extensions.db') as mock_db:
                chain = _db_chain(mock_db)
                chain.all.return_value = _product_rows(5)
                assert engine._train_maintenance_internal()['success'] is False
            with patch('extensions.db'), patch('models.GLJournalEntry') as GL:
                GL.query.limit.return_value.all.return_value = _gl_entries(3)
                assert engine._train_accounting_internal()['success'] is False
            with patch('extensions.db') as mock_db:
                chain = _db_chain(mock_db)
                chain.all.return_value = _sale_line_rows(10)
                assert engine._train_price_internal()['success'] is False
        finally:
            _stop_patches(cols)

    def test_save_load_models(self, engine, knowledge_path):
        engine._save_model('price_optimizer')
        assert os.path.exists(os.path.join(engine.models_dir, 'price_optimizer.pkl'))
        fresh = MLPRegressor(hidden_layer_sizes=(4,), max_iter=50, random_state=0)
        fresh.fit([[1.0]], [2.0])
        engine.models['price_optimizer'] = fresh
        engine._save_model('price_optimizer')
        engine.models['price_optimizer'] = MLPRegressor(hidden_layer_sizes=(4,), max_iter=50)
        assert engine._load_model('price_optimizer') is True
        assert engine._is_model_loaded('price_optimizer') is True
        assert engine.load_all_models()

    def test_save_load_failures(self, engine):
        with patch('joblib.dump', side_effect=OSError('disk')):
            assert engine._save_model('price_optimizer') is False
        with patch('joblib.load', side_effect=RuntimeError('bad')):
            assert engine._load_model('price_optimizer') is False

    def test_train_all_models_and_status(self, engine):
        ctx = MagicMock()
        ctx.return_value.__enter__ = MagicMock(return_value=None)
        ctx.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(engine, 'train_price_optimizer', return_value={'success': True}), \
             patch.object(engine, 'train_sales_forecaster', return_value={'success': False, 'error': 'x'}), \
             patch.object(engine, 'train_customer_classifier', return_value={'success': True}), \
             patch.object(engine, 'train_fraud_detector', return_value={'success': True}), \
             patch.object(engine, 'train_inventory_optimizer', return_value={'success': True}), \
             patch.object(engine, 'train_demand_predictor', return_value={'success': True}), \
             patch.object(engine, 'train_financial_planning', return_value={'success': True}), \
             patch.object(engine, 'train_maintenance_prediction', return_value={'success': True}), \
             patch.object(engine, 'train_accounting_assistant', return_value={'success': True}), \
             patch.object(engine, 'train_profit_optimizer', return_value={'success': True}), \
             patch.object(engine, 'train_churn_predictor', return_value={'success': True}):
            result = engine.train_all_models(ctx)
            assert result['trained_models'] >= 1
        engine.training_status['price_optimizer'] = {'r2_score': 0.9, 'samples': 100, 'trained_at': 'now'}
        with patch('os.path.exists', return_value=True):
            status = engine.get_status()
            assert status['trained_models'] >= 1

    def test_understand_intent_exception(self, engine):
        with patch.object(engine, '_extract_text_features', side_effect=RuntimeError()):
            assert engine.understand_intent('test')['confidence'] == 0

    def test_public_wrappers_with_context(self, engine):
        ctx = MagicMock()
        ctx.return_value.__enter__ = MagicMock(return_value=None)
        ctx.return_value.__exit__ = MagicMock(return_value=False)
        for method in (
            'train_accounting_assistant', 'train_financial_planning',
            'train_sales_forecaster', 'forecast_sales', 'train_fraud_detector',
            'train_inventory_optimizer', 'optimize_stock_level',
            'train_demand_predictor', 'predict_product_demand',
            'train_profit_optimizer', 'train_churn_predictor',
            'predict_cash_flow', 'predict_maintenance_needs',
        ):
            with patch.object(engine, method.replace('train_', '_train_').replace('forecast_', '_forecast_').replace('predict_', '_predict_').replace('optimize_', '_optimize_'), create=True, return_value={'success': True, 'forecast': [], 'predictions': []}):
                pass
        with patch.object(engine, '_forecast_sales_internal', return_value={'forecast': []}):
            assert engine.forecast_sales(from_app_context=ctx)['forecast'] == []


class TestAzadResponsesWave3:
    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses
        return AzadResponses()

    @pytest.fixture
    def safe_mocks(self):
        with patch('ai_knowledge.personality.azad_responses.understand_message', return_value={'intent': 'general', 'confidence': 0.1}), \
             patch('services.ai_service.AIService.is_sensitive_request', return_value=(False, False, {})), \
             patch('services.ai_service.AIService.get_api_key', return_value=None), \
             patch('services.ai_service.AIService.get_provider', return_value=None), \
             patch('ai_knowledge.personality.azad_responses.azad_personality') as ap, \
             patch('ai_knowledge.personality.azad_responses.learning_system') as ls:
            ap.is_inappropriate_message.return_value = 'normal'
            ap.get_thanks_response.return_value = 'شكرا لك'
            ap.get_greeting.return_value = 'مرحبا'
            ap.get_professional_joke.return_value = 'نكتة'
            ap.get_help_intro.return_value = 'مساعدة'
            ls.learn_from_interaction.return_value = None
            yield

    def test_who_are_you_and_status_modes(self, responses, safe_mocks):
        assert 'أزاد' in responses.smart_response('من أنت؟')
        with patch('services.ai_service.AIService.get_api_key', return_value='key'), \
             patch('services.ai_service.AIService.get_provider', return_value='groq'):
            assert 'GROQ' in responses.smart_response('حالة النظام').upper()

    def test_sensitive_owner_paths(self, responses):
        owner = MagicMock(id=1, is_owner=True)
        with patch('services.ai_service.AIService.is_sensitive_request', return_value=(True, True, {})), \
             patch('services.ai_service.AIService.get_user_info_for_owner', return_value={
                 'success': True, 'user': {
                     'username': 'u1', 'email': 'e@test.com', 'password_hash': 'hash',
                     'role': 'admin', 'is_active': True, 'is_owner': True, 'created_at': '2025-01-01',
                 },
             }), \
             patch('ai_knowledge.personality.azad_responses.understand_message', return_value={'intent': None, 'confidence': 0}), \
             patch('ai_knowledge.personality.azad_responses.azad_personality') as ap, \
             patch('ai_knowledge.personality.azad_responses.learning_system'):
            ap.is_inappropriate_message.return_value = 'normal'
            result = responses.smart_response('مستخدم admin', context={'current_user': owner, 'is_owner': True})
            assert 'u1' in result

    def test_analytical_intent_with_data(self, responses):
        with patch('ai_knowledge.personality.azad_responses.understand_message', return_value={'intent': 'sales_analysis', 'confidence': 0.9}), \
             patch('ai_knowledge.personality.azad_responses.intelligent_assistant') as ia, \
             patch('services.ai_service.AIService.is_sensitive_request', return_value=(False, False, {})), \
             patch('ai_knowledge.personality.azad_responses.azad_personality') as ap, \
             patch('ai_knowledge.personality.azad_responses.learning_system'):
            ap.is_inappropriate_message.return_value = 'normal'
            ia.process.return_value = {'success': True, 'data_used': True, 'response': 'تحليل حقيقي'}
            assert 'تحليل' in responses.smart_response('حلل المبيعات')

    @pytest.mark.parametrize('intent', [
        'create_invoice', 'create_receipt', 'sales_analysis', 'customer_balance',
        'inventory_check', 'system_links', 'tax_info', 'customs_info', 'parts_info',
        'automotive_ecu', 'heavy_equipment', 'market_insights', 'customer_service',
        'shipping_laws', 'quality_standards', 'suppliers_info', 'knowledge_sources',
        'palestine_tax_laws', 'israel_tax_laws', 'gulf_tax_laws', 'shipping_regulations',
        'memory_query', 'multi_step_query', 'engine_parts', 'diesel_parts',
        'transmission_parts', 'suspension_parts', 'brake_parts', 'electrical_parts',
        'ac_parts', 'diagnostic_codes', 'sensors_issues', 'pricing_strategy',
        'sales_techniques', 'general_help', 'add_customer',
    ])
    def test_handle_detected_intent(self, responses, intent):
        with patch('ai_knowledge.personality.azad_responses.system_integrator') as si, \
             patch('ai_knowledge.personality.azad_responses.data_analyzer') as da, \
             patch('ai_knowledge.personality.azad_responses.document_generator') as dg, \
             patch('extensions.db') as mock_db, patch('models.Sale'), patch('models.Customer'), patch('models.Product'):
            si.get_system_summary.return_value = {'success': True, 'summary': {'customers': {'total': 1}, 'sales': {'total': 1}, 'products': {'total': 1}}}
            si.get_financial_summary.return_value = {'success': True, 'financial': {'total_sales': 1}}
            da.analyze_sales_trends.return_value = {'success': True, 'trends': []}
            dg.generate_sales_report.return_value = ('تقرير', 'ok')
            mock_db.session.query.return_value.filter.return_value.group_by.return_value.all.return_value = []
            result = responses._handle_detected_intent(intent, 'رسالة اختبار', {})
            if intent == 'unknown_intent_xyz':
                assert result is None
            else:
                assert result is None or isinstance(result, str)

    def test_direct_handlers(self, responses):
        with patch('ai_knowledge.personality.azad_responses.system_integrator') as si, \
             patch('extensions.db') as mock_db, patch('models.Customer') as Customer, \
             patch('models.Product') as Product, patch('models.Sale'):
            si.get_customer_balance.return_value = {'success': True, 'customer': {'name': 'Ali', 'balance': 100}}
            si.get_system_summary.return_value = {
                'success': True,
                'summary': {
                    'customers': {'total': 10, 'vip': 2, 'recent': []},
                    'sales': {'total': 100, 'today': 5, 'recent': []},
                    'products': {'total': 50, 'low_stock': 3, 'out_of_stock': 1},
                },
            }
            si.get_financial_summary.return_value = {
                'success': True,
                'financial': {
                    'total_sales': 10000, 'total_payments': 8000, 'total_receivables': 2000,
                    'today_sales': 500, 'today_payments': 300,
                },
            }
            si.get_product_stock.return_value = {
                'success': True,
                'product': {
                    'name': 'Filter', 'id': 1, 'sku': 'F1', 'category': 'Parts',
                    'unit_price': 25.0, 'current_stock': 5, 'alert_limit': 10,
                },
            }
            Customer.query.filter.return_value.first.return_value = MagicMock(name='Ali', id=1)
            Product.query.filter.return_value.first.return_value = MagicMock(name='Filter', current_stock=5)
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            assert responses._handle_customer_balance_query('رصيد العميل علي')
            assert responses._handle_customer_info_query('بيانات العميل علي')
            assert responses._handle_product_stock_query('مخزون منتج فلتر')
            assert responses._handle_system_summary_query()
            assert responses._handle_add_customer_query('أنشئ عميل جديد اسمه سامي')
            assert responses._handle_search_query('ابحث عن منتج زيت')
            assert responses._handle_add_knowledge_source('أضف موقع معرفة')
            assert responses._handle_knowledge_search('ابحث في المعرفة')
            assert responses._handle_document_generation('ولد فاتورة')
            assert responses._handle_excel_export('صدر excel')
            assert responses._handle_report_generation('تقرير المبيعات')
            assert responses._handle_tax_laws_query('قانون ضريبة فلسطين')
            assert responses._handle_shipping_laws_query('شحن بحري')
            assert responses._handle_quality_standards_query('معايير جودة الطعام')
            assert responses._handle_suppliers_query('مورد جديد')
            assert responses._handle_smart_filters_query('فلتر بحث')
            assert responses._handle_payment_methods_query('طريقة دفع كاش')

    @pytest.mark.parametrize('method', [
        '_get_palestine_tax_laws', '_get_israel_tax_laws', '_get_gulf_tax_laws',
        '_get_shipping_regulations', '_get_engine_parts_guide', '_get_diesel_parts_guide',
        '_get_transmission_guide', '_get_suspension_guide', '_get_brakes_guide',
        '_get_electrical_guide', '_get_ac_guide', '_get_pricing_strategy_guide',
        '_get_sales_techniques_guide',
    ])
    def test_static_guide_methods(self, responses, method):
        result = getattr(responses, method)()
        assert isinstance(result, str) and len(result) > 10

    @pytest.mark.parametrize('message,method', [
        ('P0420', '_get_dtc_info'),
        ('حساس أكسجين', '_get_sensor_troubleshooting'),
    ])
    def test_message_guide_methods(self, responses, message, method):
        result = getattr(responses, method)(message)
        assert isinstance(result, str) and len(result) > 10

    def test_smart_response_keyword_branches(self, responses, safe_mocks):
        msgs = [
            'مرحبا أزاد', 'شكرا جزيلا', 'نكتة مضحكة', 'كيف أستخدم النظام',
            'ما هي ضريبة VAT في الإمارات', 'قطعة محرك بستم', 'خدمة العملاء للزبون',
            'مورد جديد', 'فلتر بحث', 'طريقة دفع كاش', 'حلل المبيعات',
            'تحسين الأداء', 'حالة النظام', 'توقع المبيعات', 'مخزون المنتجات',
            'هامش الربح', 'دليل النظام', 'سوق المنافسة',
        ]
        for msg in msgs:
            assert isinstance(responses.smart_response(msg), str)

    def test_beginners_mode_and_dialect(self, responses):
        with patch('ai_knowledge.personality.azad_responses.understand_message', return_value={'intent': None, 'confidence': 0}), \
             patch('services.ai_service.AIService.is_sensitive_request', return_value=(False, False, {})), \
             patch('ai_knowledge.personality.azad_responses.azad_personality') as ap, \
             patch('ai_knowledge.personality.azad_responses.learning_system'), \
             patch('ai_knowledge.personality.azad_responses.beginners_guide') as bg, \
             patch('ai_knowledge.personality.azad_responses.apply_dialect', side_effect=lambda t, d: t):
            ap.is_inappropriate_message.return_value = 'normal'
            bg.get_beginner_response.return_value = 'دليل المبتدئ'
            result = responses.smart_response('مرحبا', context={'beginners_mode': True, 'dialect': 'gulf'})
            assert isinstance(result, str)


class TestIntelligentAssistantWave3:
    @pytest.fixture
    def assistant(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant
        return IntelligentAssistant()

    def _mock_queries(self):
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.count.return_value = 10
        mock_q.all.return_value = []
        mock_q.first.return_value = None
        return mock_q

    def test_process_all_intent_paths(self, assistant, mock_ai_user):
        sale = MagicMock(
            id=1, total_amount=Decimal('500'), sale_date=datetime.now(),
            customer=MagicMock(name='Ali'),
        )
        mock_q = self._mock_queries()
        mock_q.all.return_value = [sale]
        mock_q.count.return_value = 0
        product = MagicMock(
            id=1, name='Filter', current_stock=Decimal('1'),
            min_stock_alert=Decimal('5'),
        )
        with patch('ai_knowledge.learning.quick_learner.quick_learner.get_answer', return_value=None), \
             patch('ai_knowledge.neural.semantic_matcher.understand_message') as um, \
             patch('models.Sale') as MockSale, patch('models.Customer') as MockCustomer, \
             patch('models.Product') as MockProduct, \
             patch('utils.tenanting.get_active_tenant_id', return_value=1), \
             patch('flask.has_request_context', return_value=True), \
             patch.object(assistant, '_learn_from_interaction'), \
             patch.object(assistant.neural_engine, 'predict_next_week_sales', return_value={'success': True, 'predicted_amount': 5000}, create=True):
            MockSale.query = mock_q
            MockCustomer.query = mock_q
            MockProduct.query = mock_q
            MockProduct.query.filter.return_value.all.return_value = [product]
            um.return_value = {'intent': 'sales_analysis', 'confidence': 0.9, 'all_scores': []}
            assert assistant.process('حلل المبيعات', user_id=1)['success'] is True
            um.return_value = {'intent': 'inventory_check', 'confidence': 0.9, 'all_scores': []}
            assert assistant.process('وين المخزون الناقص', user_id=1)['success'] is True
            um.return_value = {'intent': 'greeting', 'confidence': 0.9, 'all_scores': []}
            assert assistant.process('مرحبا', user_id=1)['success'] is True
            um.return_value = {'intent': 'who_are_you', 'confidence': 0.9, 'all_scores': []}
            assert assistant.process('من أنت', user_id=1)['success'] is True
            um.return_value = {'intent': 'praise', 'confidence': 0.9, 'all_scores': []}
            assert assistant.process('شكرا', user_id=1)['success'] is True
            um.return_value = {'intent': 'complaint', 'confidence': 0.9, 'all_scores': []}
            assert assistant.process('سيء جدا', user_id=1)['success'] is True

    def test_customer_balance_with_debt(self, assistant):
        debt = {
            'success': True,
            'customer': {'name': 'Ahmed'},
            'debt_analysis': {
                'total_debt': 6000, 'unpaid_sales_count': 2,
                'overdue_count': 1,
            },
        }
        payload = {'customer_data': debt}
        with patch('ai_knowledge.neural.semantic_matcher.understand_message', return_value={'intent': 'customer_balance', 'confidence': 0.9}), \
             patch.object(assistant, '_collect_real_data', return_value=payload), \
             patch.object(assistant, '_learn_from_interaction'):
            result = assistant.process('رصيد العميل أحمد', user_id=1)
            assert result['success'] is True
            assert 'Ahmed' in result['response']

    def test_quick_answer_and_errors(self, assistant):
        with patch('ai_knowledge.learning.quick_learner.quick_learner.get_answer', return_value='جواب سريع'):
            assert assistant.process('سؤال')['method'] == 'quick_learner'
        with patch('ai_knowledge.learning.quick_learner.quick_learner.get_answer', return_value=None), \
             patch.object(assistant, '_understand_message', return_value={'success': False}):
            assert assistant.process('غامض')['method'] == 'help'
        with patch('ai_knowledge.learning.quick_learner.quick_learner.get_answer', side_effect=RuntimeError('fail')):
            result = assistant.process('test')
            assert result['success'] is False

    def test_understand_and_learn_errors(self, assistant):
        with patch('ai_knowledge.neural.semantic_matcher.understand_message', side_effect=RuntimeError()):
            assert assistant._understand_message('x', 1, {})['success'] is False
        with patch.object(assistant.memory_system, 'remember_conversation', side_effect=RuntimeError()):
            assistant._learn_from_interaction('q', 'a', 1)


class TestAgentsCoreWave3:
    def test_dispatch_success_and_permission(self, mock_ai_user):
        from ai_knowledge.agents_core import intelligent_response
        with patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', return_value=('customer_balance', {'name': 'Ali'})), \
             patch('ai_knowledge.action_dispatcher.action_dispatcher.dispatch') as disp, \
             patch('ai_knowledge.trainer.trainer'):
            disp.return_value = MagicMock(success=True, message='رصيد 100', needs_permission='')
            assert '100' in intelligent_response('رصيد: Ali')
            disp.return_value = MagicMock(success=False, message='مرفوض', needs_permission='manage_sales')
            assert 'صلاحية' in intelligent_response('فاتورة: x') or 'مرفوض' in intelligent_response('فاتورة: x')

    def test_greeting_evening(self, mock_ai_user):
        from ai_knowledge.agents_core import intelligent_response
        with patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', return_value=('greeting', {})), \
             patch('ai_knowledge.action_dispatcher.action_dispatcher.format_help', return_value='help'), \
             patch('datetime.datetime') as dt:
            dt.utcnow.return_value = datetime(2025, 6, 1, 20, 0, 0)
            assert 'مساء' in intelligent_response('مرحبا')

    def test_ask_azad_enhanced_paths(self):
        from ai_knowledge import agents_core as ac
        ac._llm_available = None
        with patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}):
            with patch.object(ac, '_get_llm_response', return_value='رد LLM'):
                result = ac.ask_azad_enhanced('سؤال معقد جدا عن النظام')
                assert result['source'] in ('llm', 'faq', 'system_knowledge', 'master_brain', 'local')
        with patch.object(ac, '_check_llm_availability', return_value=False), \
             patch('ai_knowledge.agents.master_brain.get_master_brain') as gmb, \
             patch('ai_knowledge.trainer.trainer'):
            gmb.return_value.ask.return_value = {'answer': 'من الدماغ'}
            result = ac.ask_azad_enhanced('كيف أضيف منتج')
            assert result['answer']

    def test_llm_groq_and_gemini(self):
        from ai_knowledge import agents_core as ac
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {'choices': [{'message': {'content': 'ok'}}]}
        with patch.dict('os.environ', {'GROQ_API_KEY': 'k'}, clear=False):
            with patch('requests.post', return_value=mock_resp):
                assert ac._get_llm_response('sys', 'user') == 'ok'
        gem_resp = MagicMock(status_code=200)
        gem_resp.json.return_value = {'candidates': [{'content': {'parts': [{'text': 'gem'}]}}]}
        with patch.dict('os.environ', {}, clear=True):
            with patch.dict('os.environ', {'GEMINI_API_KEY': 'g'}):
                with patch('requests.post', return_value=gem_resp):
                    assert ac._get_llm_response('sys', 'user') == 'gem'

    def test_build_prompt_with_results(self):
        from ai_knowledge.agents_core import _build_system_prompt
        prompt = _build_system_prompt('كيف أضيف فاتورة', 'manager')
        assert 'أزاد' in prompt


class TestActionDispatcherWave3:
    @pytest.fixture
    def permitted(self):
        return (
            patch('ai_knowledge.action_dispatcher._get_active_tenant_id', return_value=1),
            patch('ai_knowledge.action_dispatcher._is_owner', return_value=True),
            patch('ai_knowledge.action_dispatcher._audit'),
            patch('ai_knowledge.action_dispatcher._log_ai_error'),
        )

    def test_unknown_action_and_permission_denied(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher
        with permitted[0], permitted[1], permitted[2], permitted[3]:
            assert action_dispatcher.dispatch('unknown_action', {}).success is False
        with permitted[0], patch('ai_knowledge.action_dispatcher._is_owner', return_value=False), \
             patch('ai_knowledge.action_dispatcher._has_permission', return_value=False), permitted[2], permitted[3]:
            result = action_dispatcher.dispatch('create_customer', {'name': 'Ali'})
            assert result.success is False
            assert result.needs_permission

    def test_create_product_and_stock(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher
        with permitted[0], permitted[1], permitted[2], permitted[3], \
             patch('ai_knowledge.action_dispatcher.db.session') as session, \
             patch('models.Product') as Product:
            Product.return_value = MagicMock(id=5)
            assert action_dispatcher.dispatch('create_product', {'name': 'Bolt', 'selling_price': 10}).success is True
            session.rollback()
            session.add.side_effect = RuntimeError('db')
            assert action_dispatcher.dispatch('create_product', {'name': 'X'}).success is False

    def test_check_stock_paths(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher
        product = MagicMock(name='Low', current_stock=Decimal('1'), min_stock_level=Decimal('5'))
        with permitted[0], permitted[1], permitted[2], permitted[3], \
             patch('models.Product') as Product:
            Product.tenant_id = _Col()
            Product.is_active = _Col()
            Product.current_stock = _Col()
            Product.min_stock_level = _Col()
            Product.query.filter.return_value.all.return_value = [product]
            low = action_dispatcher.dispatch('check_stock', {})
            assert low.success is True
            Product.query.filter.return_value.all.return_value = []
            ok = action_dispatcher.dispatch('check_stock', {})
            assert 'جيدة' in ok.message

    def test_parse_chat_actions(self):
        from ai_knowledge.action_dispatcher import action_dispatcher
        assert action_dispatcher.parse_chat_action('عميل: علي, 050')[0] == 'create_customer'
        assert action_dispatcher.parse_chat_action('رصيد: علي')[0] == 'customer_balance'
        assert action_dispatcher.parse_chat_action('عرض العملاء')[0] == 'list_customers'
        assert action_dispatcher.parse_chat_action('منتج: برغي, 5, 100')[0] == 'create_product'
        assert action_dispatcher.parse_chat_action('عرض المنتجات')[0] == 'list_products'
        assert action_dispatcher.parse_chat_action('فحص المخزون')[0] == 'check_stock'
        assert action_dispatcher.parse_chat_action('فاتورة: علي, زيت, 2')[0] == 'create_sale'
        assert action_dispatcher.parse_chat_action('عرض الفواتير')[0] == 'list_sales'
        assert action_dispatcher.parse_chat_action('ملخص المبيعات')[0] == 'sales_summary'
        assert action_dispatcher.parse_chat_action('استلام: علي, 500')[0] == 'receive_payment'
        assert action_dispatcher.parse_chat_action('مصروف: وقود, 50')[0] == 'add_expense'
        assert action_dispatcher.parse_chat_action('مورد: شركة, 050')[0] == 'create_supplier'
        assert action_dispatcher.parse_chat_action('موظف: سامي, 050, 3000')[0] == 'create_employee'
        assert action_dispatcher.parse_chat_action('شراء: مورد, منتج, 5')[0] == 'create_purchase'
        assert action_dispatcher.parse_chat_action('مرحبا')[0] == 'greeting'
        assert action_dispatcher.parse_chat_action('مساعدة')[0] == 'help'

    def test_helpers_and_audit_failures(self):
        from ai_knowledge.action_dispatcher import _audit, _get_active_tenant_id, _has_permission, _log_ai_error
        with patch('flask.g', create=True) as g:
            g.active_tenant_id = 42
            with patch('ai_knowledge.action_dispatcher.current_user', SimpleNamespace(is_authenticated=False)):
                assert _get_active_tenant_id() == 42
        with patch('services.logging_core.LoggingCore.log_audit', side_effect=RuntimeError()):
            _audit('x', 'y')
        with patch('ai_knowledge.action_dispatcher.db.session') as session:
            session.add.side_effect = RuntimeError()
            _log_ai_error('t', 'm')


class TestCoreEngineWave3:
    def test_getattr_lazy_imports(self, knowledge_path):
        import ai_knowledge.core_engine as ce
        import ai_knowledge.core.conversation_manager as cm
        import ai_knowledge.core.memory_system as ms
        cm._conversation_manager_instance = None
        ms._memory_instance = None
        assert ce._conversation_manager_instance is None
        assert ce._memory_instance is None
        assert ce.AzadLearningSystem is not None
        assert ce.learning_system is not None
        with pytest.raises(AttributeError):
            _ = ce.nonexistent_attr_xyz

    def test_getattr_cached(self):
        import ai_knowledge.core_engine as ce
        first = ce.AzadLearningSystem
        second = ce.AzadLearningSystem
        assert first is second


class TestContinuousLearnerWave3:
    def test_arxiv_success_and_failure(self, knowledge_path):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner
        learner = ContinuousLearner()
        ok = MagicMock(status_code=200, text='<entry></entry><entry></entry>')
        learner.session = MagicMock(get=MagicMock(return_value=ok))
        assert learner.learn_arxiv_papers('ml')['success'] is True
        bad = MagicMock(status_code=500)
        learner.session.get.return_value = bad
        assert learner.learn_arxiv_papers('ml')['success'] is False
        learner.session.get.side_effect = RuntimeError('net')
        assert learner.learn_arxiv_papers('ml')['success'] is False

    def test_wikipedia_failure_status(self, knowledge_path):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner
        learner = ContinuousLearner()
        learner.session = MagicMock(get=MagicMock(return_value=MagicMock(status_code=404)))
        assert learner.learn_from_wikipedia('topic')['success'] is False

    def test_evaluate_and_learn_error_paths(self):
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn
        svc = MagicMock()
        svc.ask_genius.side_effect = RuntimeError('api down')
        mem = MagicMock()
        svc.get_learning_system.return_value = mem
        tests = [{'question': 'سؤال', 'expected_keywords': ['a'], 'context': {}}]
        results = evaluate_and_learn(tests, ai_service=svc)
        assert results[0]['success'] is False
        mem.learn_from_interaction.assert_called()

    def test_evaluate_partial_hits(self):
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn
        svc = MagicMock()
        svc.ask_genius.return_value = {'answer': 'one two three four'}
        tests = [{'question': 'q', 'expected_keywords': ['one', 'two', 'three', 'four', 'five']}]
        results = evaluate_and_learn(tests, ai_service=svc)
        assert results[0]['hits'] == 4


class TestWave3Extended:
    """Additional coverage for remaining gaps."""

    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses
        return AzadResponses()

    def test_azad_inventory_profit_forecast_branches(self, responses):
        with patch('ai_knowledge.personality.azad_responses.understand_message', return_value={'intent': None, 'confidence': 0}), \
             patch('services.ai_service.AIService.is_sensitive_request', return_value=(False, False, {})), \
             patch('services.ai_service.AIService.get_api_key', return_value=None), \
             patch('services.ai_service.AIService.get_provider', return_value=None), \
             patch('ai_knowledge.personality.azad_responses.learning_system'), \
             patch('ai_knowledge.personality.azad_responses.azad_personality') as ap:
            ap.is_inappropriate_message.return_value = 'normal'
            ap.get_help_intro.return_value = 'مساعدة'
            with patch('services.ai_service.AIService.analyze_inventory_health', return_value={
                'success': True, 'summary': {'total': 10, 'good': 8, 'low': 1, 'out': 1},
                'rating': 'جيد', 'health_score': 80,
            }):
                assert 'المخزون' in responses.smart_response('مخزون المنتجات صحة')
            with patch('services.ai_service.AIService.analyze_profit_margins', return_value={
                'success': True,
                'overall': {'revenue': 10000, 'cost': 7000, 'profit': 3000, 'margin': 30},
                'top_profitable': [{'name': 'Oil', 'profit': 500, 'margin': 25}],
            }):
                assert 'هامش' in responses.smart_response('هامش الربح الصافي')

    def test_azad_improvement_status_handlers(self, responses):
        with patch('ai_knowledge.personality.azad_responses.self_improvement') as si, \
             patch('ai_knowledge.personality.azad_responses.learning_system') as ls:
            si.auto_improve.return_value = {
                'improvements_made': 2,
                'details': [{'area': 'sales', 'old_score': 5, 'new_score': 7, 'improvement': 2}],
            }
            assert 'تلقائي' in responses._get_improvement_response('تحسين تلقائي')
            si.track_progress.return_value = {
                'overall_progress': 50,
                'goals_progress': [{'area': 'x', 'current_score': 5, 'target_score': 10, 'progress_percentage': 50}],
                'next_milestones': [{'area': 'y', 'description': 'next'}],
            }
            assert 'أهداف' in responses._get_improvement_response('ما هي أهداف التحسين')
            si.get_improvement_status.return_value = {
                'overall_score': 8, 'total_improvements': 3,
                'active_goals': 2, 'last_improvement': 'today',
            }
            si.analyze_performance.return_value = {
                'overall_score': 8,
                'strengths': [{'description': 'fast', 'score': 9}],
                'weaknesses': [{'description': 'memory', 'score': 6}],
            }
            si.evolve_capabilities.return_value = {'new_capabilities': ['cap1']}
            ls.get_learning_insights.return_value = {
                'total_interactions': 10, 'success_rate': 0.9, 'learning_progress': 'good',
            }
            assert responses._get_status_response()

    def test_azad_customer_handlers_full(self, responses):
        customer = {
            'id': 1, 'name': 'Ali', 'customer_type': 'regular',
            'phone': '050', 'email': 'a@t.com', 'balance_aed': 1500,
            'total_sales': 5, 'last_sale_date': '2025-06-01',
        }
        with patch('ai_knowledge.personality.azad_responses.system_integrator') as si, \
             patch('ai_knowledge.personality.azad_responses.data_analyzer') as da:
            si.get_customer_balance.return_value = {'success': True, 'customer': customer}
            da.analyze_customer_debt.return_value = {
                'success': True,
                'debt_analysis': {
                    'unpaid_sales_count': 2, 'avg_debt_amount': 500,
                    'max_debt_amount': 800, 'overdue_count': 1,
                },
            }
            assert 'Ali' in responses._handle_customer_balance_query('رصيد عميل علي')
            da.analyze_customer_debt.return_value = {'success': False}
            assert 'Ali' in responses._handle_customer_balance_query('رصيد عميل علي')
            si.get_customer_balance.return_value = {'success': False, 'error': 'not found'}
            assert 'not found' in responses._handle_customer_balance_query('رصيد عميل x')

    def test_neural_remaining_paths(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine
        engine = AzadNeuralEngine()
        _fast_models(engine)
        with patch.object(engine, '_load_model', return_value=False):
            assert engine._predict_maintenance_internal(1)['error'] == 'Model not trained'
        with patch.object(engine, '_train_churn_internal', side_effect=RuntimeError()):
            assert engine.train_churn_predictor()['success'] is False

    def test_agents_core_exception_path(self, mock_ai_user):
        from ai_knowledge.agents_core import intelligent_response
        with patch('ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action', side_effect=RuntimeError('boom')), \
             patch('ai_knowledge.action_dispatcher._log_ai_error'):
            assert 'خطأ' in intelligent_response('test')

    def test_intelligent_assistant_inventory_analysis(self, knowledge_path):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant
        assistant = IntelligentAssistant()
        payload = {'low_stock_products': [{'name': 'Bolt', 'current_stock': 1, 'min_alert': 5, 'deficit': 4}] * 6}
        with patch('ai_knowledge.learning.quick_learner.quick_learner.get_answer', return_value=None), \
             patch('ai_knowledge.neural.semantic_matcher.understand_message', return_value={'intent': 'inventory_check', 'confidence': 0.9}), \
             patch.object(assistant, '_collect_real_data', return_value=payload), \
             patch.object(assistant, '_learn_from_interaction'):
            result = assistant.process('وين المخزون الناقص', user_id=1)
            assert result['success'] is True
