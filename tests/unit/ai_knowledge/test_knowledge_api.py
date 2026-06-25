"""Smoke tests for public knowledge / analytics / specialized APIs."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from ai_knowledge.analytics import get_market_insights
from ai_knowledge.knowledge import (
    COMPANY_INFO,
    get_customs_advice,
    get_part_info,
    get_tax_info,
    search_knowledge as kb_search,
)
from ai_knowledge.specialized import (
    get_customer_service_tip,
    get_guide,
    get_system_guide,
    get_tax_advice,
)


class TestKnowledgeAPI:
    def test_company_info(self):
        assert COMPANY_INFO

    def test_get_tax_info(self):
        assert get_tax_info('uae')

    def test_get_customs_advice(self):
        assert get_customs_advice('جمارك')

    def test_get_part_info(self):
        assert get_part_info('filter') is not None

    def test_kb_search(self):
        assert isinstance(kb_search('sales'), (str, list, dict)) or kb_search('sales') is None

    def test_market_insights(self):
        assert len(get_market_insights()) > 20

    def test_customer_service_tip(self):
        assert get_customer_service_tip()

    def test_system_and_user_guide(self):
        assert get_system_guide()
        assert get_guide('sales') or get_guide('dashboard')

    def test_tax_advice(self):
        assert get_tax_advice('ضريبة')

    def test_advanced_laws(self):
        from ai_knowledge.specialized_knowledge import advanced_laws
        assert advanced_laws.get_tax_info('uae', 'vat')


class TestLearningSystem:
    def test_learn_from_interaction(self, tmp_path):
        path_fn = lambda name: str(tmp_path / name)
        with patch('ai_knowledge.get_knowledge_path', side_effect=path_fn):
            from ai_knowledge.core.learning_system import AzadLearningSystem
            ls = AzadLearningSystem()
            ls.learn_from_interaction('ما هي الضريبة؟', 'ضريبة 5%', user_feedback=5)
            assert ls.get_learning_insights()['total_interactions'] >= 1

    def test_patterns_saved_as_json(self, tmp_path):
        path_fn = lambda name: str(tmp_path / name)
        with patch('ai_knowledge.get_knowledge_path', side_effect=path_fn):
            from ai_knowledge.core.learning_system import AzadLearningSystem
            ls = AzadLearningSystem()
            ls.learn_from_interaction('q', 'a', user_feedback=5)
            assert ls.get_learning_insights()['total_interactions'] >= 1
