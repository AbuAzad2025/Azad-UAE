from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestContextEngineIntents:
    def test_enhance_analysis_intent(self):
        from ai_knowledge.core.context_engine import ContextEngine

        with patch('ai_knowledge.core.context_engine.data_analyzer') as da:
            da.get_financial_ratios.return_value = {'success': True, 'ratios': {'gross_profit_margin': 10, 'net_profit_margin': 5}}
            result = ContextEngine.enhance_response('حلل الأرباح', 'base', {})
        assert '10.0%' in result

    def test_enhance_data_query(self):
        from ai_knowledge.core.context_engine import ContextEngine

        with patch('ai_knowledge.core.context_engine.system_integrator') as si:
            si.get_system_summary.return_value = {'success': True, 'summary': {'total_customers': 5, 'total_products': 10, 'today_sales': 1000}}
            result = ContextEngine.enhance_response('كم عدد العملاء', 'base', {})
        assert '5' in result

    def test_enhance_prediction_intent(self):
        from ai_knowledge.core.context_engine import ContextEngine

        result = ContextEngine.enhance_response('توقع المبيعات', 'base', {})
        assert 'توقع' in result

    def test_enhance_create_intent(self):
        from ai_knowledge.core.context_engine import ContextEngine

        result = ContextEngine.enhance_response('أنشئ وثيقة جديدة', 'base', {})
        assert 'وثائق' in result or 'إنشاء' in result

    def test_enhance_search_intent(self):
        from ai_knowledge.core.context_engine import ContextEngine

        with patch('ai_knowledge.core.context_engine.knowledge_expander') as ke:
            ke.search_knowledge.return_value = {'success': True, 'results': [{'title': 'Doc'}]}
            result = ContextEngine.enhance_response('ابحث في النظام', 'base', {})
        assert 'Doc' in result

    def test_enhance_financial_exception(self):
        from ai_knowledge.core.context_engine import ContextEngine

        with patch('ai_knowledge.core.context_engine.data_analyzer') as da:
            da.get_financial_ratios.side_effect = RuntimeError('fail')
            result = ContextEngine.enhance_response('حلل', 'base', {})
        assert result.startswith('base')

    def test_get_smart_suggestions(self):
        from ai_knowledge.core.context_engine import ContextEngine

        suggestions = ContextEngine.get_smart_suggestions('حلل المبيعات', {})
        assert len(suggestions) >= 1

    def test_detect_intent_general(self):
        from ai_knowledge.core.context_engine import ContextEngine

        assert ContextEngine._detect_intent('xyz unknown') == 'general'


class TestContinuousLearnerPush:
    def test_learn_arxiv_success(self):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner

        learner = ContinuousLearner()
        resp = MagicMock(status_code=200, text='<entry></entry><entry></entry>')
        with patch.object(learner.session, 'get', return_value=resp):
            result = learner.learn_arxiv_papers('ml', max_results=2)
        assert result['success'] is True

    def test_learn_arxiv_non_200(self):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner

        learner = ContinuousLearner()
        with patch.object(learner.session, 'get', return_value=MagicMock(status_code=500)):
            result = learner.learn_arxiv_papers('ml')
        assert result['success'] is False

    def test_daily_learning_routine(self):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner

        learner = ContinuousLearner()
        with patch.object(learner, 'learn_from_wikipedia', return_value={'success': True}), \
             patch.object(learner, 'learn_arxiv_papers', return_value={'success': True, 'papers': 2}):
            result = learner.daily_learning_routine()
        assert result['items_learned'] >= 0

    def test_get_continuous_learner_singleton(self):
        import importlib

        cl = importlib.import_module('ai_knowledge.learning.continuous_learner')
        cl._continuous_learner_instance = None
        a = cl.get_continuous_learner()
        b = cl.get_continuous_learner()
        assert a is b

    def test_evaluate_and_learn_skips_empty_question(self):
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn

        svc = MagicMock()
        assert evaluate_and_learn([{'question': '', 'expected_keywords': ['a']}], ai_service=svc) == []

    def test_evaluate_and_learn_success(self):
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn

        svc = MagicMock()
        svc.ask_genius.return_value = {'answer': 'sales revenue profit'}
        memory = MagicMock()
        svc.get_learning_system.return_value = memory
        tests = [{'question': 'sales?', 'expected_keywords': ['sales', 'revenue'], 'context': {}}]
        results = evaluate_and_learn(tests, ai_service=svc)
        assert results[0]['success'] is True

    def test_evaluate_and_learn_exception_path(self):
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn

        svc = MagicMock()
        svc.ask_genius.side_effect = RuntimeError('api fail')
        memory = MagicMock()
        svc.get_learning_system.return_value = memory
        results = evaluate_and_learn([{'question': 'x', 'expected_keywords': ['a']}], ai_service=svc)
        assert results[0]['success'] is False


class TestMultiAgentSystemPush:
    def test_sales_agent_price_task(self):
        from ai_knowledge.agents.multi_agent_system import SalesAgent

        agent = SalesAgent()
        assert agent.can_handle('سعر المنتج') > 0
        with patch('services.ai_service.AIService.predict_price_with_neural', return_value={'predicted_price': 99, 'confidence': 0.9}):
            result = agent.execute('سعر المنتج', {'product_id': 1, 'customer_id': 2})
        assert result['confidence'] == 0.9

    def test_sales_agent_generic_task(self):
        from ai_knowledge.agents.multi_agent_system import SalesAgent

        agent = SalesAgent()
        result = agent.execute('بيع عام', {})
        assert result['confidence'] == 0.5

    def test_sales_agent_exception(self):
        from ai_knowledge.agents.multi_agent_system import SalesAgent

        agent = SalesAgent()
        with patch('services.ai_service.AIService.predict_price_with_neural', side_effect=RuntimeError('fail')):
            result = agent.execute('price check', {})
        assert result['confidence'] == 0

    def test_accounting_agent_balanced_entry(self):
        from ai_knowledge.agents.multi_agent_system import AccountingAgent

        agent = AccountingAgent()
        result = agent.execute('قيد محاسبي', {'debit': 100, 'credit': 100})
        assert result['result']['is_balanced'] is True

    def test_coordinator_delegates_task(self):
        from ai_knowledge.agents.multi_agent_system import MultiAgentCoordinator, get_agent_coordinator

        coord = MultiAgentCoordinator()
        with patch('services.ai_service.AIService.predict_price_with_neural', return_value={'predicted_price': 50, 'confidence': 0.8}):
            result = coord.delegate_task('سعر منتج', {'product_id': 1})
        assert result['assigned_agent'] == 'sales'
        collab = coord.collaborative_solve('سعر ومخزون', {'product_id': 1})
        assert 'agents_involved' in collab

        import ai_knowledge.agents.multi_agent_system as mas
        mas._coordinator_instance = None
        assert get_agent_coordinator() is not None


class TestConversationManagerPush:
    def test_full_conversation_lifecycle(self):
        from ai_knowledge.core.conversation_manager import ConversationManager, get_conversation_manager

        mgr = ConversationManager()
        start = mgr.start_conversation(99, {'name': 'Ali'})
        assert start['status'] == 'active'
        for msg, intent in (
            ('كم سعر المنتج 100', 'pricing_query'),
            ('توقع المبيعات', 'prediction_query'),
            ('قيد محاسبي', 'accounting_query'),
            ('صيانة الجهاز', 'maintenance_query'),
            ('مخزون المنتج', 'inventory_query'),
            ('بيانات عميل', 'customer_query'),
            ('كيف أستخدم النظام', 'howto_query'),
            ('سؤال عام', 'general_query'),
        ):
            out = mgr.process_message(99, msg)
            assert out['intent'] == intent
        assert mgr.get_conversation_history(99)
        end = mgr.end_conversation(99)
        assert 'farewell' in end
        assert mgr.end_conversation(99) == {'error': 'No active conversation'}

        import ai_knowledge.core.conversation_manager as cm
        cm._conversation_manager_instance = None
        assert get_conversation_manager() is not None

    def test_greeting_morning_and_evening(self):
        from ai_knowledge.core.conversation_manager import ConversationManager
        from datetime import datetime

        mgr = ConversationManager()
        with patch('ai_knowledge.core.conversation_manager.datetime') as dt:
            dt.now.return_value = datetime(2025, 1, 1, 9, 0, 0)
            morning = mgr._generate_greeting({'name': 'Sara'})
            dt.now.return_value = datetime(2025, 1, 1, 20, 0, 0)
            evening = mgr._generate_greeting({'name': 'Sara'})
        assert 'صباح' in morning
        assert 'مساء' in evening

    def test_memory_save_failure_logged(self):
        from ai_knowledge.core.conversation_manager import ConversationManager

        mgr = ConversationManager()
        mgr.start_conversation(1)
        with patch('ai_knowledge.core.memory_system.get_memory_system', side_effect=RuntimeError('mem fail')):
            mgr.process_message(1, 'test message')


class TestContinuousLearnerExtended:
    def test_learn_wikipedia_success(self, tmp_path, monkeypatch):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner

        learner = ContinuousLearner()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {'extract': 'Accounting basics', 'content_urls': {'desktop': {'page': 'http://wiki'}}}
        with patch.object(learner.session, 'get', return_value=resp), \
             patch.object(learner, '_save_history'):
            result = learner.learn_from_wikipedia('Accounting', 'en')
        assert result['success'] is True

    def test_learn_wikipedia_non_200(self):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner

        learner = ContinuousLearner()
        with patch.object(learner.session, 'get', return_value=MagicMock(status_code=404)):
            result = learner.learn_from_wikipedia('Missing')
        assert result['success'] is False

    def test_get_learning_stats(self):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner

        learner = ContinuousLearner()
        stats = learner.get_learning_stats()
        assert 'total_items_learned' in stats

    def test_evaluate_and_learn_no_service(self):
        import builtins
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn

        real_import = builtins.__import__

        def selective_import(name, *args, **kwargs):
            if name == 'services.ai_service':
                raise ImportError('no ai service')
            return real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=selective_import):
            assert evaluate_and_learn([{'question': 'q', 'expected_keywords': ['a']}], ai_service=None) == []


class TestContextEngineExtended:
    def test_enhance_learning_intent(self):
        from ai_knowledge.core.context_engine import ContextEngine

        with patch('ai_knowledge.core.context_engine.learning_system') as ls:
            ls.get_learning_insights.return_value = {'insights': ['tip1']}
            result = ContextEngine.enhance_response('تعلم من البيانات', 'base', {})
        assert 'tip1' in result or 'base' in result

    def test_enhance_search_failure(self):
        from ai_knowledge.core.context_engine import ContextEngine

        with patch('ai_knowledge.core.context_engine.knowledge_expander') as ke:
            ke.search_knowledge.side_effect = RuntimeError('search fail')
            result = ContextEngine.enhance_response('ابحث عن tax', 'base', {})
        assert result.startswith('base')

    def test_smart_suggestions_all_intents(self):
        from ai_knowledge.core.context_engine import ContextEngine

        for msg in ('حلل الأرباح', 'كم عدد', 'توقع', 'أنشئ', 'ابحث', 'unknown'):
            assert ContextEngine.get_smart_suggestions(msg, {})
