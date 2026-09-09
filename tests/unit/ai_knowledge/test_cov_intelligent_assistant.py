"""Coverage tests for ai_knowledge/agents/intelligent_assistant.py uncovered arcs."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant


class TestCovIntelligentAssistantCachedProps:
    def test_reasoning_engine_cached_path_69_73(self):
        assistant = IntelligentAssistant()
        sentinel = object()
        assistant._reasoning_engine = sentinel
        assert assistant.reasoning_engine is sentinel

    def test_context_engine_cached_path_96_100(self):
        assistant = IntelligentAssistant()
        sentinel = object()
        assistant._context_engine = sentinel
        assert assistant.context_engine is sentinel


class TestCovIntelligentAssistantCollect:
    def test_collect_no_request_context_264_273(self):
        assistant = IntelligentAssistant()
        with patch("flask.has_request_context", return_value=False):
            result = assistant._collect_real_data("sales_analysis", {}, 1)
        assert result == {}

    def test_collect_customer_not_found_323_328(self):
        assistant = IntelligentAssistant()
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.count.return_value = 0
        mock_q.all.return_value = []
        mock_q.first.return_value = None
        with (
            patch("flask.has_request_context", return_value=True),
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch("extensions.db.session.query", return_value=mock_q),
        ):
            result = assistant._collect_real_data("customer_balance", {"names": ["Ahmed"]}, 1)
        assert isinstance(result, dict)
        assert "customer_data" not in result
        assert result.get("system_stats", {}).get("total_customers") == 0


class TestCovIntelligentAssistantAnalyze:
    def test_customer_balance_unsuccessful_414_433(self):
        assistant = IntelligentAssistant()
        data = {"customer_data": {"success": False}}
        result = assistant._analyze_and_reason("customer_balance", data, {})
        assert result["insights"] == []
        assert result["warnings"] == []


class TestCovIntelligentAssistantGenerate:
    def test_customer_balance_no_overdue_516_518(self):
        assistant = IntelligentAssistant()
        data = {
            "customer_data": {
                "success": True,
                "customer": {"name": "Ahmed"},
                "debt_analysis": {
                    "total_debt": 100.0,
                    "unpaid_sales_count": 1,
                    "overdue_count": 0,
                },
            }
        }
        response = assistant._generate_dynamic_response("customer_balance", {}, {}, data)
        assert "Ahmed" in response
        assert "متأخرة" not in response

    def test_inventory_check_missing_key_520_538(self):
        assistant = IntelligentAssistant()
        response = assistant._generate_dynamic_response("inventory_check", {"insights": ["i"]}, {}, {})
        assert "لا يوجد سياق منشأة نشط" in response
        assert "i" in response

    def test_unknown_intent_skips_all_branches_520_538(self):
        assistant = IntelligentAssistant()
        response = assistant._generate_dynamic_response("unknown_intent_xyz", {"insights": ["hello-insight"]}, {}, {})
        assert "hello-insight" in response

    def test_generate_exception_563_565(self):
        assistant = IntelligentAssistant()
        response = assistant._generate_dynamic_response("greeting", None, {}, {})
        assert response == "عذراً، حدث خطأ في توليد الرد"


class TestCovIntelligentAssistantLearn:
    def test_learn_no_request_context_577_582(self):
        assistant = IntelligentAssistant()
        assistant._memory_system = MagicMock()
        with (
            patch("flask.has_request_context", return_value=False),
            patch("ai_knowledge.core.learning_system.learning_system") as mock_ls,
        ):
            mock_ls.learn_from_interaction = MagicMock()
            assistant._learn_from_interaction("hi", "hello", 1)
        assistant._memory_system.remember_conversation.assert_called_once_with(1, "hi", "hello")
        mock_ls.learn_from_interaction.assert_called_once()
