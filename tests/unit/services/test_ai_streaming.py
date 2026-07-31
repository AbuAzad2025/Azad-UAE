"""Tests for P3-2 real SSE streaming (chat_response_stream), P3-1 native
tool-call execution, and P4-2 tenant AI privacy opt-out."""

from types import SimpleNamespace
from unittest.mock import patch

from services.ai_service import AIService


def _pipe(**overrides):
    pipe = {
        "message": "سؤال",
        "context": {},
        "current_user": SimpleNamespace(id=1, tenant_id=1, role=None),
        "user_id": 1,
        "local_response": "رد محلي",
        "knowledge_context": "",
        "system_context": "",
        "force_local": False,
    }
    pipe.update(overrides)
    return pipe


def _plan(**overrides):
    plan = {
        "provider": "groq",
        "is_gemini": False,
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "headers": {"Authorization": "Bearer k"},
        "payload": {"model": "llama-3.3-70b-versatile", "messages": []},
    }
    plan.update(overrides)
    return plan


class _FakeStreamResp:
    def __init__(self, lines, status=200):
        self.status_code = status
        self._lines = lines

    def iter_lines(self, decode_unicode=True):
        return iter(self._lines)


class TestChatResponseStream:
    def test_early_exit_yields_final_directly(self):
        with patch.object(AIService, "_chat_stage1_to_3", return_value=("رد مبكر", None)):
            events = list(AIService.chat_response_stream("مرحبا", {}))
        assert events == [("final", "رد مبكر")]

    def test_local_fallback_when_no_plan(self):
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, _pipe())),
            patch.object(AIService, "_build_llm_plan", return_value=None),
            patch.object(AIService, "chat_response", return_value="محلي") as cr,
        ):
            events = list(AIService.chat_response_stream("سؤال", {}))
        assert events == [("final", "محلي")]
        cr.assert_called_once()

    def test_real_token_deltas_then_final(self):
        lines = [
            'data: {"choices": [{"delta": {"content": "مرحبا "}}]}',
            'data: {"choices": [{"delta": {"content": "بالعالم"}}]}',
            ": comment ignored",
            'data: {"choices": [{"delta": {}}]}',
            "data: [DONE]",
        ]
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, _pipe())),
            patch.object(AIService, "_build_llm_plan", return_value=_plan()),
            patch("requests.post", return_value=_FakeStreamResp(lines)) as post,
            patch.object(AIService, "_execute_ai_action", return_value=None),
            patch.object(AIService, "_finalize_llm_response", side_effect=lambda text, plan, pipe: f"FINAL::{text}"),
        ):
            events = list(AIService.chat_response_stream("سؤال", {}))
        assert post.call_args.kwargs.get("stream") is True
        assert post.call_args.kwargs["json"]["stream"] is True
        assert ("delta", "مرحبا ") in events
        assert ("delta", "بالعالم") in events
        assert events[-1] == ("final", "FINAL::مرحبا بالعالم")

    def test_streamed_tool_calls_buffered_and_executed(self):
        lines = [
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "check_"}}]}}]}',
            'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "stock", "arguments": "{}"}}]}}]}',
            "data: [DONE]",
        ]
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, _pipe())),
            patch.object(AIService, "_build_llm_plan", return_value=_plan()),
            patch("requests.post", return_value=_FakeStreamResp(lines)),
            patch.object(AIService, "_execute_native_tool_calls", return_value="نتيجة الأداة") as exec_tools,
            patch.object(AIService, "_finalize_llm_response", side_effect=lambda text, plan, pipe: f"FINAL::{text}"),
        ):
            events = list(AIService.chat_response_stream("افحص المخزون", {}))
        exec_tools.assert_called_once()
        tool_calls = exec_tools.call_args[0][0]
        assert tool_calls == [{"function": {"name": "check_stock", "arguments": "{}"}}]
        assert events[-1] == ("final", "FINAL::نتيجة الأداة")
        assert not [e for e in events if e[0] == "delta"]

    def test_stream_http_error_falls_back_to_local(self):
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, _pipe())),
            patch.object(AIService, "_build_llm_plan", return_value=_plan()),
            patch("requests.post", return_value=_FakeStreamResp([], status=500)),
            patch.object(AIService, "_log_llm_failure"),
        ):
            events = list(AIService.chat_response_stream("سؤال", {}))
        assert events[-1][0] == "final"
        assert "النظام المحلي الذكي" in events[-1][1]

    def test_stream_exception_falls_back_to_local(self):
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, _pipe())),
            patch.object(AIService, "_build_llm_plan", return_value=_plan()),
            patch("requests.post", side_effect=ConnectionError("down")),
            patch.object(AIService, "_log_llm_failure"),
        ):
            events = list(AIService.chat_response_stream("سؤال", {}))
        assert "النظام المحلي الذكي" in events[-1][1]


class TestNativeToolCallExecution:
    def test_valid_tool_call_dispatches(self):
        dispatched = {}

        class _FakeDispatcher:
            def dispatch(self, action_type, args):
                dispatched["action_type"] = action_type
                dispatched["args"] = args
                return SimpleNamespace(
                    success=True,
                    message="تم",
                    needs_confirmation=False,
                    needs_permission="",
                )

        tool_calls = [
            {
                "function": {
                    "name": "list_customers",
                    "arguments": '{"search": "أحمد"}',
                }
            }
        ]
        with patch("ai_knowledge.action_dispatcher.ActionDispatcher", return_value=_FakeDispatcher()):
            out = AIService._execute_native_tool_calls(tool_calls, 1)
        assert dispatched["action_type"] == "list_customers"
        assert dispatched["args"]["search"] == "أحمد"
        assert "تم" in out

    def test_invalid_args_rejected_before_dispatch(self):
        tool_calls = [{"function": {"name": "receive_payment", "arguments": '{"customer_name": "أ", "amount": -3}'}}]
        with patch("ai_knowledge.action_dispatcher.ActionDispatcher") as disp:
            disp.return_value.dispatch.side_effect = AssertionError("must not dispatch")
            out = AIService._execute_native_tool_calls(tool_calls, 1)
        assert "⚠️" in out

    def test_malformed_json_arguments_handled(self):
        tool_calls = [{"function": {"name": "check_stock", "arguments": "{not json"}}]
        out = AIService._execute_native_tool_calls(tool_calls, 1)
        assert "⚠️" in out


class TestTenantAIPrivacyOptOut:
    def test_flag_true_by_default_when_no_tenant(self):
        assert AIService._is_ai_external_sharing_enabled(SimpleNamespace(tenant_id=None)) is True

    def test_flag_false_blocks_sharing(self):
        tenant = SimpleNamespace(ai_external_sharing_enabled=False)
        with patch("services.ai_service.db") as mock_db:
            mock_db.session.get.return_value = tenant
            assert AIService._is_ai_external_sharing_enabled(SimpleNamespace(tenant_id=5)) is False

    def test_flag_true_allows_sharing(self):
        tenant = SimpleNamespace(ai_external_sharing_enabled=True)
        with patch("services.ai_service.db") as mock_db:
            mock_db.session.get.return_value = tenant
            assert AIService._is_ai_external_sharing_enabled(SimpleNamespace(tenant_id=5)) is True

    def test_gather_knowledge_stripped_when_opted_out(self):
        local = {"context": {"current_user": SimpleNamespace(tenant_id=1)}}
        with patch.object(AIService, "_is_ai_external_sharing_enabled", return_value=False):
            out = AIService._gather_relevant_knowledge("stats", local)
        assert "الخصوصية" in out
        assert "درهم" not in out
