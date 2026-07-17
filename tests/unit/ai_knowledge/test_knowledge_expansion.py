"""Tests for knowledge expansion and learning system modules."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from ai_knowledge.core.learning_system import AzadLearningSystem
from ai_knowledge.expansion.global_knowledge import (
    GlobalExpertiseUpdater,
    GlobalKnowledgeConnector,
)
from ai_knowledge.expansion.knowledge_expansion import (
    KnowledgeExpander,
    knowledge_expander,
)
from ai_knowledge.expansion.knowledge_sources import (
    KnowledgeSourceManager,
    get_learning_resources,
)
from ai_knowledge.knowledge_base import (
    get_customs_info,
    get_tax_info,
    get_welcome_message,
    search_knowledge,
)


class TestGlobalKnowledge:
    def test_fetch_automotive_news(self):
        assert (
            GlobalKnowledgeConnector().fetch_global_automotive_news()["success"] is True
        )

    def test_global_insights(self):
        assert isinstance(GlobalKnowledgeConnector().get_global_insights(), dict)

    def test_update_expertise(self):
        assert isinstance(GlobalExpertiseUpdater().update_expertise(), dict)


class TestKnowledgeExpansion:
    def test_add_website_invalid(self):
        assert KnowledgeExpander().add_website("not-a-url")["success"] is False

    def test_add_document(self, tmp_path):
        with patch("ai_knowledge.get_knowledge_path", return_value=str(tmp_path)):
            result = KnowledgeExpander().add_document("content", "Title", "general")
            assert isinstance(result, dict)

    def test_search_knowledge(self, tmp_path):
        def path_fn(name):
            return str(tmp_path / name)

        with patch("ai_knowledge.get_knowledge_path", side_effect=path_fn):
            result = KnowledgeExpander().search_knowledge("test")
            assert result["success"] is True

    def test_singleton(self):
        assert knowledge_expander is not None


class TestKnowledgeSources:
    def test_sources_by_topic(self):
        assert isinstance(KnowledgeSourceManager().get_sources_by_topic("parts"), list)

    def test_exchange_rates_cached(self):
        mgr = KnowledgeSourceManager()
        mgr.cache["exchange_rates"] = ({"rates": {"USD": 3.67}}, datetime.now())
        assert mgr.fetch_exchange_rates() is not None

    def test_learning_resources(self):
        assert isinstance(get_learning_resources("accounting"), (list, dict))


class TestLearningSystem:
    def test_learn_from_interaction(self, tmp_path):
        def path_fn(name):
            return str(tmp_path / name)

        with patch("ai_knowledge.get_knowledge_path", side_effect=path_fn):
            sys = AzadLearningSystem()
            result = sys.learn_from_interaction("سؤال", "جواب", user_feedback=5)
            assert result is None or isinstance(result, dict)

    def test_get_insights(self, tmp_path):
        def path_fn(name):
            return str(tmp_path / name)

        with patch("ai_knowledge.get_knowledge_path", side_effect=path_fn):
            assert isinstance(AzadLearningSystem().get_learning_insights(), dict)


class TestKnowledgeBase:
    def test_welcome_message(self):
        assert isinstance(get_welcome_message(), str)

    def test_tax_info_uae(self):
        assert isinstance(get_tax_info("uae"), str)

    def test_customs_info(self):
        assert isinstance(get_customs_info("import"), str)

    def test_search_knowledge(self):
        assert isinstance(search_knowledge("مورد"), list)
