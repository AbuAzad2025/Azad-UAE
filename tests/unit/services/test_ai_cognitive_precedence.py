"""Stage-3 precedence: grounded cognitive verdicts beat MasterBrain fallbacks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.ai_service import AIService


def _user():
    user = MagicMock()
    user.id = 1
    user.is_owner = False
    user.tenant_id = 5
    user.role = MagicMock(slug="admin")
    return user


class TestCognitivePrecedence:
    def test_cognitive_answer_short_circuits_fast_path(self):
        cognitive = {
            "success": True,
            "response": "ملخص المبيعات: 3 فواتير",
            "intent": "sales_summary",
            "confidence": 0.9,
            "method": "cognitive",
            "needs_escalation": False,
        }
        with (
            patch("ai_knowledge.agents.intelligent_assistant.intelligent_assistant") as intel,
            patch("ai_knowledge.action_dispatcher.action_dispatcher") as disp,
            patch("ai_knowledge.agents_core.ask_azad_enhanced") as fast,
            patch("ai_knowledge.system_knowledge.search_knowledge", return_value=None),
            patch.object(AIService, "_get_recent_history", return_value=[]),
        ):
            intel.process.return_value = cognitive
            disp.parse_chat_action.return_value = None
            fast.return_value = {"answer": "قالب قديم", "source": "master_brain"}
            early, pipe = AIService._chat_stage1_to_3("ملخص المبيعات", {"current_user": _user()})
        assert pipe is None
        assert "3 فواتير" in early
        assert "قالب قديم" not in early

    def test_escalated_cognitive_flows_to_fast_path(self):
        cognitive = {
            "success": True,
            "response": "غير متأكد",
            "intent": "unknown",
            "confidence": 0.2,
            "method": "cognitive",
            "needs_escalation": True,
        }
        with (
            patch("ai_knowledge.agents.intelligent_assistant.intelligent_assistant") as intel,
            patch("ai_knowledge.action_dispatcher.action_dispatcher") as disp,
            patch("ai_knowledge.agents_core.ask_azad_enhanced") as fast,
            patch("ai_knowledge.system_knowledge.search_knowledge", return_value=None),
            patch.object(AIService, "_get_recent_history", return_value=[]),
        ):
            intel.process.return_value = cognitive
            disp.parse_chat_action.return_value = None
            fast.return_value = {"answer": "إجابة غنية", "source": "llm"}
            early, pipe = AIService._chat_stage1_to_3("سؤال غامض", {"current_user": _user()})
        assert pipe is None
        assert "إجابة غنية" in early
