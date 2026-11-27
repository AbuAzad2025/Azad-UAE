"""Stage 1 provider governance: API keys never travel in URL query strings."""

from __future__ import annotations

from unittest.mock import patch

from services.ai_service import AIService


def _pipe():
    return {
        "message": "hello",
        "knowledge_context": "",
        "system_context": "",
        "current_user": None,
        "history": [],
        "force_local": False,
        "parsed_hint": None,
    }


def _clear_other_providers(monkeypatch):
    for name in ("GROQ_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_gemini_plan_uses_header_instead_of_query_string(monkeypatch):
    _clear_other_providers(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret-not-in-url")
    with patch.object(AIService, "get_provider", return_value="gemini"):
        plan = AIService._build_llm_plan(_pipe())

    assert plan is not None
    assert "?key=" not in plan["url"]
    assert "gemini-secret-not-in-url" not in plan["url"]
    assert plan["headers"]["x-goog-api-key"] == "gemini-secret-not-in-url"
    assert "contents" in plan["payload"]


def test_openai_style_provider_keeps_bearer_header(monkeypatch):
    _clear_other_providers(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "groq-secret-not-in-url")
    with patch.object(AIService, "get_provider", return_value="groq"):
        plan = AIService._build_llm_plan(_pipe())

    assert plan is not None
    assert "groq-secret-not-in-url" not in plan["url"]
    assert plan["headers"]["Authorization"] == "Bearer groq-secret-not-in-url"


def test_local_mode_still_short_circuits_without_provider(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert AIService._build_llm_plan(_pipe()) is None


def test_agents_core_gemini_request_uses_header():
    import inspect

    import ai_knowledge.agents_core as agents_core

    source = inspect.getsource(agents_core._get_llm_response)

    assert "?key=" not in source
    assert "x-goog-api-key" in source
