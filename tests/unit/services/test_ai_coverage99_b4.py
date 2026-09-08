"""Coverage-99 boost for services/ai_service.py — batch 4 (execute, stream, actions)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.ai_service import AIService


def _pipe(**over):
    base = {
        "message": "m",
        "context": {},
        "current_user": MagicMock(id=1, tenant_id=5),
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


def _plan(gemini=False):
    return {
        "provider": "gemini" if gemini else "groq",
        "is_gemini": gemini,
        "url": "http://x",
        "model": "m",
        "headers": {},
        "payload": {},
    }


class TestExecuteLlm:
    def test_non_200(self):
        with patch("requests.post", return_value=MagicMock(status_code=500)):
            assert AIService._execute_llm_request(_plan(), _pipe()) is None

    def test_gemini_texts(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "hi"}, {"text": "yo"}]}}]}
        with (
            patch("requests.post", return_value=resp),
            patch.object(AIService, "_execute_ai_action", return_value=None),
            patch.object(AIService, "_dispatch_parsed_hint", return_value=None),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            assert AIService._execute_llm_request(_plan(gemini=True), _pipe()) == "F"

    def test_gemini_calls_and_empty(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "f", "args": {"a": 1}}}]}}]
        }
        with (
            patch("requests.post", return_value=resp),
            patch.object(AIService, "_execute_native_tool_calls", return_value="N"),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            assert AIService._execute_llm_request(_plan(gemini=True), _pipe()) == "F"
        resp2 = MagicMock(status_code=200)
        resp2.json.return_value = {"candidates": []}
        with (
            patch("requests.post", return_value=resp2),
            patch.object(AIService, "_dispatch_parsed_hint", return_value="H"),
        ):
            assert AIService._execute_llm_request(_plan(gemini=True), _pipe()) == "H"
        with (
            patch("requests.post", return_value=resp2),
            patch.object(AIService, "_dispatch_parsed_hint", return_value=None),
        ):
            try:
                AIService._execute_llm_request(_plan(gemini=True), _pipe())
                raised = False
            except ValueError:
                raised = True
            assert raised

    def test_openai_tools_and_content(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"choices": [{"message": {"tool_calls": [{"function": {"name": "f"}}]}}]}
        with (
            patch("requests.post", return_value=resp),
            patch.object(AIService, "_execute_native_tool_calls", return_value="N"),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            assert AIService._execute_llm_request(_plan(), _pipe()) == "F"
        resp2 = MagicMock(status_code=200)
        resp2.json.return_value = {"choices": [{"message": {"content": "C"}}]}
        with (
            patch("requests.post", return_value=resp2),
            patch.object(AIService, "_execute_ai_action", return_value="A"),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            assert AIService._execute_llm_request(_plan(), _pipe()) == "F"
        with (
            patch("requests.post", return_value=resp2),
            patch.object(AIService, "_execute_ai_action", return_value=None),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            assert AIService._execute_llm_request(_plan(), _pipe()) == "F"


class TestStream:
    def _sse(self, lines, status=200):
        resp = MagicMock(status_code=status)
        resp.iter_lines.return_value = iter(lines)
        return resp

    def test_early_and_local(self):
        with patch.object(AIService, "_chat_stage1_to_3", return_value=("E", None)):
            assert list(AIService.chat_response_stream("hi")) == [("final", "E")]
        pipe = _pipe()
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value=None),
            patch.object(AIService, "chat_response", return_value="L"),
        ):
            assert list(AIService.chat_response_stream("hi")) == [("final", "L")]

    def test_gemini_passthrough(self):
        pipe = _pipe()
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value=_plan(gemini=True)),
            patch.object(AIService, "_stream_gemini_response", return_value=iter([("final", "G")])),
        ):
            assert list(AIService.chat_response_stream("hi")) == [("final", "G")]

    def test_sse_deltas_tools(self):
        import json as _json

        pipe = _pipe()
        lines = [
            "",
            "note",
            "data: not-json{",
            "data: " + _json.dumps({"choices": []}),
            "data: "
            + _json.dumps(
                {
                    "choices": [
                        {
                            "delta": {
                                "content": "ab",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"name": "fn", "arguments": "{}"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
            "data: [DONE]",
        ]
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value=_plan()),
            patch("requests.post", return_value=self._sse(lines)),
            patch.object(AIService, "_execute_native_tool_calls", return_value="N"),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            out = list(AIService.chat_response_stream("hi"))
        assert ("delta", "ab") in out and out[-1] == ("final", "F")

    def test_sse_conversational_and_error(self):
        import json as _json

        pipe = _pipe()
        lines = ["data: " + _json.dumps({"choices": [{"delta": {"content": "z"}}]})]
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value=_plan()),
            patch("requests.post", return_value=self._sse(lines)),
            patch.object(AIService, "_execute_ai_action", return_value=None),
            patch.object(AIService, "_dispatch_parsed_hint", return_value=None),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            assert list(AIService.chat_response_stream("hi"))[-1] == ("final", "F")
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value=_plan()),
            patch("requests.post", side_effect=RuntimeError("net")),
        ):
            out = list(AIService.chat_response_stream("hi"))
        assert "المحلي" in out[-1][1]

    def test_sse_bad_status(self):
        pipe = _pipe()
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value=_plan()),
            patch("requests.post", return_value=self._sse([], status=500)),
        ):
            out = list(AIService.chat_response_stream("hi"))
        assert "المحلي" in out[-1][1]

    def test_sse_legacy_action(self):
        import json as _json

        pipe = _pipe()
        lines = ["data: " + _json.dumps({"choices": [{"delta": {"content": "z"}}]})]
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value=_plan()),
            patch("requests.post", return_value=self._sse(lines)),
            patch.object(AIService, "_execute_ai_action", return_value="ACT"),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            assert list(AIService.chat_response_stream("hi"))[-1] == ("final", "F")


class TestGeminiStream:
    def _resp(self, lines, status=200):
        resp = MagicMock(status_code=status)
        resp.iter_lines.return_value = iter(lines)
        return resp

    def test_text_and_fncall(self):
        import json as _json

        pipe = _pipe()
        lines = [
            "x",
            "data: bad{",
            "data: "
            + _json.dumps(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    "not-a-dict",
                                    {"text": "t1"},
                                    {
                                        "functionCall": {
                                            "name": "ff",
                                            "args": {"a": 1},
                                        }
                                    },
                                    {"functionCall": {"name": "gg", "args": "s"}},
                                ]
                            }
                        }
                    ]
                }
            ),
            "data: [DONE]",
        ]
        with (
            patch("requests.post", return_value=self._resp(lines)),
            patch.object(AIService, "_execute_native_tool_calls", return_value="N"),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            out = list(AIService._stream_gemini_response(_plan(gemini=True), pipe))
        assert ("delta", "t1") in out and out[-1] == ("final", "F")

    def test_no_fncall_paths(self):
        pipe = _pipe()
        with (
            patch("requests.post", return_value=self._resp([], status=500)),
        ):
            out = list(AIService._stream_gemini_response(_plan(gemini=True), pipe))
        assert "المحلي" in out[-1][1]
        with (
            patch("requests.post", return_value=self._resp([])),
            patch.object(AIService, "_execute_ai_action", return_value="A"),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            assert list(AIService._stream_gemini_response(_plan(gemini=True), pipe))[-1] == (
                "final",
                "F",
            )
        with (
            patch("requests.post", return_value=self._resp([])),
            patch.object(AIService, "_execute_ai_action", return_value=None),
            patch.object(AIService, "_dispatch_parsed_hint", return_value="H"),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            assert list(AIService._stream_gemini_response(_plan(gemini=True), pipe))[-1] == (
                "final",
                "F",
            )


class TestSpansPayloads:
    def test_spans_variants(self):
        assert list(AIService._iter_action_spans("no markers")) == []
        assert list(AIService._iter_action_spans('"action":1')) == []
        spans = list(AIService._iter_action_spans('x {"action": "a", "data": {}} y'))
        assert len(spans) == 1
        nested = '{"action": "a", "data": {"x": {"y": 1}}}'
        assert len(list(AIService._iter_action_spans(nested))) == 1
        s = '{"action": "a \\"q\\" { }", "data": {}}'
        assert len(list(AIService._iter_action_spans(s))) == 1
        unclosed = '{"action": "a"'
        assert list(AIService._iter_action_spans(unclosed)) == []

    def test_payloads(self):
        out = AIService._extract_action_payloads('{"action": "create_customer", "data": {"n": 1}}')
        assert out == [("create_customer", {"n": 1})]
        out = AIService._extract_action_payloads('{"action": "x", "data": [1]}')
        assert out == [("x", {})]
        assert AIService._extract_action_payloads('{"action": oops}') == []
        assert AIService._extract_action_payloads("hello") == []


class TestExecuteAction:
    def test_plain_and_malformed(self):
        assert AIService._execute_ai_action("hello world", 1) is None
        single = '{"action": oops'
        out = AIService._execute_ai_action(single, 1)
        assert out is None or "خطأ" in out
        two = '{"action": oops} {"action": also-bad}'
        assert AIService._execute_ai_action(two, 1) is None
        empty = '{"action": ""}'
        assert AIService._execute_ai_action(empty, 1) is None

    def test_dispatch_results(self):
        from ai_knowledge.action_dispatcher import ActionDispatcher

        payload = '{"action": "help", "data": {}}'
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
                assert needle in AIService._execute_ai_action(payload, 1)

    def test_outer_exception_paths(self):
        with patch.object(AIService, "_extract_action_payloads", side_effect=RuntimeError("x")):
            with patch("services.logging_core.LoggingCore.log_error", return_value=None):
                assert "خطأ" in AIService._execute_ai_action("{}", 1)
            with patch(
                "services.logging_core.LoggingCore.log_error",
                side_effect=RuntimeError("y"),
            ):
                assert "خطأ" in AIService._execute_ai_action("{}", 1)
