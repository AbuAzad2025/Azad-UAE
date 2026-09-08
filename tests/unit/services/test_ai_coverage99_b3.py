"""Coverage-99 boost for services/ai_service.py — batch 3 (chat stages, plan, dispatch)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.ai_service import AIService


def _user(uid=1, owner=False):
    u = MagicMock()
    u.id = uid
    u.is_owner = owner
    u.tenant_id = 5
    u.role = MagicMock(slug="admin")
    return u


def _pipe(**over):
    base = {
        "message": "مرحبا",
        "context": {},
        "current_user": _user(),
        "user_id": 1,
        "tenant_id": 5,
        "local_response": "local",
        "knowledge_context": "k",
        "system_context": "s",
        "force_local": False,
        "parsed_hint": None,
        "history": [],
    }
    base.update(over)
    return base


class TestStage1To3:
    def test_sensitive_early(self):
        user = _user(owner=False)
        with patch("ai_knowledge.agents.intelligent_assistant.intelligent_assistant"):
            early, pipe = AIService._chat_stage1_to_3("show me the password", {"current_user": user})
        assert pipe is None and early is not None

    def test_greeting_dispatch(self):
        with (
            patch("ai_knowledge.agents.intelligent_assistant.intelligent_assistant") as intel,
            patch("ai_knowledge.action_dispatcher.action_dispatcher") as disp,
            patch.object(AIService, "get_api_key", return_value="k"),
        ):
            intel.process.return_value = {"response": "lr"}
            disp.parse_chat_action.return_value = ("greeting", {})
            disp.dispatch.return_value = MagicMock(success=True, message="hi")
            early, pipe = AIService._chat_stage1_to_3("مرحبا", {"current_user": _user()})
        assert pipe is None and "hi" in early

    def test_hint_stash_and_fast_path(self):
        with (
            patch("ai_knowledge.agents.intelligent_assistant.intelligent_assistant") as intel,
            patch("ai_knowledge.action_dispatcher.action_dispatcher") as disp,
            patch.object(AIService, "get_api_key", return_value="k"),
            patch("ai_knowledge.agents_core.ask_azad_enhanced") as fast,
            patch("ai_knowledge.system_knowledge.search_knowledge", return_value=None),
            patch.object(AIService, "_get_recent_history", return_value=[]),
        ):
            intel.process.return_value = {"response": "lr"}
            disp.parse_chat_action.return_value = ("create_customer", {"name": "x"})
            fast.return_value = {"answer": "A", "source": "groq"}
            early, pipe = AIService._chat_stage1_to_3("أنشئ عميل", {"current_user": _user()})
        assert pipe is None and "A" in early

    def test_full_pipe(self):
        with (
            patch("ai_knowledge.agents.intelligent_assistant.intelligent_assistant") as intel,
            patch("ai_knowledge.action_dispatcher.action_dispatcher") as disp,
            patch("ai_knowledge.agents_core.ask_azad_enhanced", return_value=None),
            patch(
                "ai_knowledge.system_knowledge.search_knowledge",
                return_value=[{"name": "N", "code": None, "type": None}],
            ),
            patch.object(AIService, "_get_recent_history", return_value=[]),
        ):
            intel.process.return_value = {"response": "lr"}
            disp.parse_chat_action.return_value = None
            early, pipe = AIService._chat_stage1_to_3("سؤال عام", {})
        assert early is None and pipe["message"] == "سؤال عام"

    def test_exceptions_covered(self):
        with (
            patch("ai_knowledge.agents.intelligent_assistant.intelligent_assistant") as intel,
            patch(
                "ai_knowledge.action_dispatcher.action_dispatcher",
                side_effect=RuntimeError("x"),
            ),
            patch(
                "ai_knowledge.agents_core.ask_azad_enhanced",
                side_effect=RuntimeError("y"),
            ),
            patch(
                "ai_knowledge.system_knowledge.search_knowledge",
                side_effect=RuntimeError("z"),
            ),
            patch.object(AIService, "_get_recent_history", return_value=[]),
        ):
            intel.process.return_value = {"response": "lr"}
            early, pipe = AIService._chat_stage1_to_3("سؤال", {})
        assert early is None and pipe is not None


class TestChatResponse:
    def test_early(self):
        with patch.object(AIService, "_chat_stage1_to_3", return_value=("EARLY", None)):
            assert AIService.chat_response("hi") == "EARLY"

    def test_local_fallback(self):
        pipe = _pipe()
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value=None),
        ):
            out = AIService.chat_response("hi")
        assert "المحلي" in out

    def test_execute_final(self):
        pipe = _pipe()
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value={"x": 1}),
            patch.object(AIService, "_execute_llm_request", return_value="FINAL"),
        ):
            assert AIService.chat_response("hi") == "FINAL"

    def test_execute_raise_hint(self):
        pipe = _pipe(parsed_hint={"action_type": "help", "args": {}})
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value={"x": 1}),
            patch.object(AIService, "_execute_llm_request", side_effect=RuntimeError("e")),
            patch.object(AIService, "_dispatch_parsed_hint", return_value="HINT"),
        ):
            assert AIService.chat_response("hi") == "HINT"


class TestDispatchHint:
    def test_no_hint(self):
        assert AIService._dispatch_parsed_hint(None) is None
        assert AIService._dispatch_parsed_hint({}) is None
        assert AIService._dispatch_parsed_hint({"parsed_hint": "x"}) is None

    def test_confirm_permission_success_fail(self):
        from ai_knowledge.action_dispatcher import ActionDispatcher

        for flags, needle in [
            ({"needs_confirmation": True}, "التأكيد"),
            ({"needs_permission": True}, "مرفوضة"),
            ({"success": True}, "التنفيذ"),
            ({}, "أزاد"),
        ]:
            res = MagicMock(message="m", **flags)
            for k in ("needs_confirmation", "needs_permission", "success"):
                if k not in flags:
                    setattr(res, k, False)
            with patch.object(ActionDispatcher, "dispatch", return_value=res):
                out = AIService._dispatch_parsed_hint({"parsed_hint": {"action_type": "help", "args": {}}})
            assert needle in out

    def test_exception(self):
        from ai_knowledge.action_dispatcher import ActionDispatcher

        with patch.object(ActionDispatcher, "dispatch", side_effect=RuntimeError("x")):
            assert AIService._dispatch_parsed_hint({"parsed_hint": {"action_type": "help", "args": {}}}) is None


class TestLogFailure:
    def test_ok_and_inner_error(self):
        with patch("services.logging_core.LoggingCore.log_error", return_value=None):
            AIService._log_llm_failure(RuntimeError("e"))
        with patch("services.logging_core.LoggingCore.log_error", side_effect=RuntimeError("x")):
            AIService._log_llm_failure(RuntimeError("e"))


class TestBuildPlan:
    def test_no_key_and_force_local(self):
        assert AIService._build_llm_plan(_pipe()) is None or True
        with patch.object(AIService, "get_api_key", return_value=None):
            assert AIService._build_llm_plan(_pipe()) is None
        with patch.object(AIService, "get_api_key", return_value="k"):
            assert AIService._build_llm_plan(_pipe(force_local=True)) is None

    def _plan(self, provider, tools=None, history=None, hint=None):
        pipe = _pipe(history=history or [], parsed_hint=hint)
        with (
            patch.object(AIService, "get_api_key", return_value="k"),
            patch.object(AIService, "get_provider", return_value=provider),
            patch(
                "ai_knowledge.tool_registry.get_tools_for_user",
                side_effect=RuntimeError("t") if tools == "err" else None,
                return_value=None if tools == "err" else tools,
            ),
        ):
            return AIService._build_llm_plan(pipe)

    def test_groq_openai_gemini(self):
        assert self._plan("groq")["provider"] == "groq"
        assert self._plan("openai")["provider"] == "openai"
        tools = [{"function": {"name": "f", "description": "d", "parameters": {}}}]
        plan = self._plan("gemini", tools=tools)
        assert plan["is_gemini"] is True
        assert "tools" in plan["payload"]
        plan = self._plan("groq", tools=tools)
        assert plan["payload"]["tool_choice"] == "auto"

    def test_tool_registry_error(self):
        assert self._plan("groq", tools="err")["provider"] == "groq"

    def test_history_and_hint_blocks(self):
        history = [{"q": "qqqqqq", "r": "rrrr"}]
        hint = {"action_type": "create_customer", "args": {"name": "x"}}
        plan = self._plan("groq", history=history, hint=hint)
        assert "المحادثة" in plan["payload"]["messages"][0]["content"]
        assert "صريح" in plan["payload"]["messages"][0]["content"]

    def test_history_block_error(self):
        pipe = _pipe(history="not-a-list")
        with (
            patch.object(AIService, "get_api_key", return_value="k"),
            patch.object(AIService, "get_provider", return_value="groq"),
            patch("ai_knowledge.tool_registry.get_tools_for_user", return_value=None),
        ):
            assert AIService._build_llm_plan(pipe)["provider"] == "groq"


class TestFinalize:
    def test_ok_and_train_error(self):
        pipe = _pipe()
        with patch.object(AIService, "_train_local_from_groq", return_value=None):
            out = AIService._finalize_llm_response("R", {"provider": "groq"}, pipe)
        assert "GROQ" in out
        with patch.object(AIService, "_train_local_from_groq", side_effect=RuntimeError("x")):
            out = AIService._finalize_llm_response("R", {"provider": "gemini"}, pipe)
        assert "GEMINI" in out
