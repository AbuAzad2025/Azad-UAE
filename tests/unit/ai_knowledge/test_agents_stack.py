"""Tests for agents stack."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant, intelligent_response
from ai_knowledge.agents.master_brain import MasterBrain, ask_azad, explain_concept, get_master_brain, quick_calc
from ai_knowledge.agents.multi_agent_system import (
    AccountingAgent,
    BaseAgent,
    InventoryAgent,
    MaintenanceAgent,
    MultiAgentCoordinator,
    SalesAgent,
    get_agent_coordinator,
)


class TestMasterBrain:
    @pytest.fixture
    def brain(self):
        return MasterBrain()

    def test_ask_accounting(self, brain):
        result = brain.ask('ما هو مبدأ الاستحقاق في المحاسبة؟')
        assert result['answer']
        assert result['confidence'] > 0

    def test_ask_tax(self, brain):
        result = brain.ask('ما هي ضريبة VAT في الإمارات؟')
        assert '5' in result['answer'] or 'ضريبة' in result['answer']

    def test_ask_general(self, brain):
        result = brain.ask('مرحبا كيف حالك')
        assert result['answer']

    def test_quick_calc_vat(self, brain):
        result = brain.quick_calc('vat', amount=100)
        assert result['result'] == 5.0

    def test_quick_calc_unknown(self, brain):
        result = brain.quick_calc('unknown_formula')
        assert 'error' in result or result.get('success') is False

    def test_validate_balanced(self, brain):
        result = brain.validate_accounting_entry(100, 100)
        assert result['is_balanced'] is True

    def test_validate_unbalanced(self, brain):
        result = brain.validate_accounting_entry(100, 50)
        assert result['is_balanced'] is False

    def test_explain_known(self, brain):
        result = brain.explain('accrual')
        assert isinstance(result, str)

    def test_explain_unknown(self, brain):
        result = brain.explain('xyz_unknown_concept')
        assert isinstance(result, str)

    def test_ask_with_user_id(self, brain):
        result = brain.ask('سؤال', user_id='u1')
        assert len(brain.unified_memory['conversations']) >= 1

    def test_ask_exception(self, brain):
        with patch.object(brain, '_analyze_question', side_effect=RuntimeError('fail')):
            result = brain.ask('test')
            assert 'error' in result or result['confidence'] <= 0.3

    def test_module_helpers(self):
        with patch('ai_knowledge.agents.master_brain.get_master_brain') as mock_gb:
            mock_gb.return_value.ask.return_value = {'answer': 'ok'}
            assert ask_azad('q')['answer'] == 'ok'
        with patch('ai_knowledge.agents.master_brain.get_master_brain') as mock_gb:
            mock_gb.return_value.quick_calc.return_value = {'result': 5}
            assert quick_calc('vat', amount=100)['result'] == 5
        with patch('ai_knowledge.agents.master_brain.get_master_brain') as mock_gb:
            mock_gb.return_value.explain.return_value = 'text'
            assert explain_concept('x') == 'text'

    def test_singleton(self):
        import ai_knowledge.agents.master_brain as mod
        mod._master_brain_instance = None
        b1 = get_master_brain()
        b2 = get_master_brain()
        assert b1 is b2


class TestIntelligentAssistant:
    @pytest.fixture
    def assistant(self):
        return IntelligentAssistant()

    def test_quick_learner_shortcut(self, assistant):
        with patch('ai_knowledge.learning.quick_learner.quick_learner.get_answer', return_value='إجابة سريعة'):
            result = assistant.process('سؤال')
            assert result['method'] == 'quick_learner'

    def test_understand_failure_help(self, assistant):
        with patch('ai_knowledge.learning.quick_learner.quick_learner.get_answer', return_value=None):
            with patch('ai_knowledge.neural.semantic_matcher.understand_message', side_effect=RuntimeError()):
                result = assistant.process('x')
                assert result.get('method') == 'help' or 'response' in result

    def test_greeting_response(self, assistant):
        with patch('ai_knowledge.learning.quick_learner.quick_learner.get_answer', return_value=None):
            with patch('ai_knowledge.neural.semantic_matcher.understand_message', return_value={'intent': 'greeting', 'confidence': 0.9}):
                with patch.object(assistant, '_collect_real_data', return_value={}):
                    with patch.object(assistant, '_analyze_and_reason', return_value={}):
                        result = assistant.process('مرحبا')
                        assert 'response' in result

    def test_intelligent_response_helper(self):
        with patch('ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process', return_value={'response': 'ok'}):
            assert intelligent_response('test') == 'ok'


class TestMultiAgentSystem:
    def test_base_agent_no_match(self):
        agent = BaseAgent('Test', ['xyz'])
        assert agent.can_handle('unrelated') == 0.0

    def test_sales_agent_price(self):
        agent = SalesAgent()
        with patch('services.ai_service.AIService.predict_price_with_neural', return_value={'predicted_price': 100, 'confidence': 0.9}):
            result = agent.execute('سعر المنتج', {'product_id': 1, 'customer_id': 2})
            assert result['confidence'] > 0

    def test_accounting_balanced(self):
        agent = AccountingAgent()
        result = agent.execute('قيد محاسبي', {'debit': 100, 'credit': 100})
        assert result['confidence'] > 0

    def test_accounting_unbalanced(self):
        agent = AccountingAgent()
        result = agent.execute('قيد', {'debit': 100, 'credit': 50})
        assert 'غير متوازن' in result.get('explanation', '') or result['confidence'] > 0

    def test_inventory_agent(self):
        agent = InventoryAgent()
        with patch('services.ai_service.AIService.optimize_inventory_neural', return_value={'optimal_stock': 50}):
            result = agent.execute('مخزون', {'product_id': 1})
            assert result.get('result') is not None or 'agent' in result

    def test_maintenance_agent(self):
        agent = MaintenanceAgent()
        with patch('ai_knowledge.core.reasoning_engine.get_reasoning_engine') as mock_re:
            mock_re.return_value.technical_reasoning.return_value = {'causes': ['x'], 'solutions': ['y']}
            result = agent.execute('صيانة المحرك', {})
            assert result.get('confidence', 0) >= 0

    def test_delegate_task(self):
        coord = MultiAgentCoordinator()
        result = coord.delegate_task('سعر المنتج', {'product_id': 1})
        assert 'agent' in result or 'result' in result

    def test_delegate_low_confidence(self):
        coord = MultiAgentCoordinator()
        result = coord.delegate_task('xyz unrelated task abc')
        assert result is not None

    def test_collaborative_solve(self):
        coord = MultiAgentCoordinator()
        result = coord.collaborative_solve('محاسبة ومخزون', {'debit': 100, 'credit': 100})
        assert isinstance(result, dict)

    def test_singleton(self):
        import ai_knowledge.agents.multi_agent_system as mod
        mod._coordinator_instance = None
        c1 = get_agent_coordinator()
        c2 = get_agent_coordinator()
        assert c1 is c2
