"""Tests for agents_core entry points."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_knowledge.agents_core import (
    _build_system_prompt,
    _check_llm_availability,
    ask_azad_enhanced,
    intelligent_response,
)


class TestAgentsCore:
    def test_check_llm_availability_false(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        import ai_knowledge.agents_core as core

        core._llm_available = None
        with patch("dotenv.load_dotenv"):
            assert _check_llm_availability() is False

    def test_build_system_prompt(self):
        prompt = _build_system_prompt("ما هي الصلاحيات؟", "manager")
        assert "مدير" in prompt
        assert len(prompt) > 50

    def test_intelligent_response_help(self):
        with patch("ai_knowledge.trainer.trainer.seed"):
            out = intelligent_response("مساعدة")
            assert "الأوامر" in out

    def test_intelligent_response_greeting(self):
        with (
            patch("ai_knowledge.trainer.trainer.seed"),
            patch(
                "ai_knowledge.action_dispatcher.current_user",
                MagicMock(full_name="Ali"),
            ),
        ):
            out = intelligent_response("مرحبا")
            assert "أزاد" in out

    def test_intelligent_response_fallback(self):
        with (
            patch("ai_knowledge.trainer.trainer.seed"),
            patch(
                "ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process",
                return_value={"response": "رد محلي"},
            ),
        ):
            out = intelligent_response("سؤال عام")
            assert out == "رد محلي"

    def test_intelligent_response_error(self):
        with (
            patch("ai_knowledge.trainer.trainer.seed", side_effect=RuntimeError()),
            patch(
                "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
                side_effect=RuntimeError("x"),
            ),
            patch("ai_knowledge.action_dispatcher._log_ai_error"),
        ):
            out = intelligent_response("x")
            assert "عذراً" in out

    def test_ask_azad_enhanced_local(self):
        brain = MagicMock()
        brain.ask.return_value = {"answer": "من العقل", "confidence": 0.8}
        with (
            patch(
                "ai_knowledge.agents_core._check_llm_availability", return_value=False
            ),
            patch("ai_knowledge.agents_core.get_master_brain", return_value=brain),
            patch("ai_knowledge.trainer.trainer.learn_from_interaction"),
        ):
            result = ask_azad_enhanced("ما هو النظام؟")
            assert result["answer"]

    def test_ask_azad_enhanced_faq(self):
        with (
            patch(
                "ai_knowledge.agents_core._check_llm_availability", return_value=False
            ),
            patch(
                "ai_knowledge.system_knowledge.search_knowledge",
                return_value=[{"type": "faq", "answer": "إجابة"}],
            ),
        ):
            result = ask_azad_enhanced("كيف أعمل فاتورة؟")
            assert result.get("answer") or result.get("source")
