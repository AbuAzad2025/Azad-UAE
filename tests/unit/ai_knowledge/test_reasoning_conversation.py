"""Tests for reasoning_engine and conversation modules."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_knowledge.core.conversation_manager import (
    ConversationManager,
    get_conversation_manager,
)
from ai_knowledge.core.conversation_store import clear_context, get_context, set_context
from ai_knowledge.core.reasoning_engine import ReasoningEngine, get_reasoning_engine


class TestReasoningEngine:
    @pytest.fixture
    def engine(self):
        return ReasoningEngine()

    def test_think_pricing(self, engine):
        result = engine.think(
            "تسعير المنتج",
            {"cost_price": 100, "customer_type": "regular", "quantity": 1},
        )
        assert "solution" in result

    def test_mathematical_addition(self, engine):
        assert engine.mathematical_reasoning("10 + 5")["result"] == 15

    def test_mathematical_division_by_zero(self, engine):
        assert engine.mathematical_reasoning("10 / 0")["result"] == 0

    def test_financial_reasoning(self, engine):
        result = engine.financial_reasoning("تحليل الربح", {"sales": 10000, "costs": 6000, "expenses": 1000})
        assert "reasoning_steps" in result

    def test_technical_brakes(self, engine):
        result = engine.technical_reasoning("مشكلة في الفرامل")
        assert "diagnosis_steps" in result

    def test_chain_of_thought(self, engine):
        result = engine.chain_of_thought("كيف أحسن المبيعات؟")
        assert "thought_chain" in result

    def test_explain_decision(self, engine):
        explanation = engine.explain_decision("زيادة السعر", {"cost": 100, "demand": "high"})
        assert "زيادة السعر" in explanation

    def test_singleton(self):
        import ai_knowledge.core.reasoning_engine as mod

        mod._reasoning_engine_instance = None
        assert get_reasoning_engine() is get_reasoning_engine()


class TestConversationManager:
    @pytest.fixture
    def manager(self):
        return ConversationManager()

    def test_start_conversation(self, manager):
        result = manager.start_conversation(1)
        assert "conversation_id" in result

    def test_process_auto_start(self, manager):
        with patch("ai_knowledge.core.memory_system.get_memory_system") as mock_mem:
            mock_mem.return_value.remember_conversation = MagicMock()
            result = manager.process_message(2, "مرحبا")
            assert "response" in result

    def test_process_pricing(self, manager):
        with patch("ai_knowledge.core.memory_system.get_memory_system"):
            manager.start_conversation(3)
            result = manager.process_message(3, "كم السعر")
            assert "response" in result

    def test_end_conversation(self, manager):
        manager.start_conversation(5)
        result = manager.end_conversation(5)
        assert result.get("success") is True or "summary" in result

    def test_singleton(self):
        import ai_knowledge.core.conversation_manager as mod

        mod._conversation_manager_instance = None
        assert get_conversation_manager() is get_conversation_manager()


class TestConversationStore:
    def test_get_context_no_record(self):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        with patch("ai_knowledge.core.conversation_store.AiMemory") as MockMem:
            MockMem.query = mock_q
            assert get_context(1) is None

    def test_set_context_new(self):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        with (
            patch("ai_knowledge.core.conversation_store.AiMemory") as MockMem,
            patch("ai_knowledge.core.conversation_store.db") as mock_db,
        ):
            MockMem.query = mock_q
            set_context(1, {"msg": "hi"}, tenant_id=1)
            mock_db.session.add.assert_called_once()

    def test_clear_context(self):
        mem = MagicMock()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = mem
        with (
            patch("ai_knowledge.core.conversation_store.AiMemory") as MockMem,
            patch("ai_knowledge.core.conversation_store.db"),
        ):
            MockMem.query = mock_q
            clear_context(1)
            assert mem.is_active is False
