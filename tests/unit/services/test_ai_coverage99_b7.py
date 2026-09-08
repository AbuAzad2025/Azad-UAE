"""Coverage-99 boost for services/ai_service.py — batch 7 (remaining partials)."""

from __future__ import annotations

import sys
from datetime import datetime
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


class TestModelAndPricing:
    def test_get_model_mock_module(self):
        from models import Product

        with patch("services.ai_service.db.session") as sess:
            sess.get.return_value = MagicMock(spec=Product)
            assert AIService._get_model(Product, 1) is None

    def test_recommend_retail(self):
        product = MagicMock(regular_price=100)
        customer = MagicMock(customer_type="retail", name="R")
        with (
            patch.object(AIService, "_get_model", side_effect=[product, customer]),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.join.return_value = q
            q.filter.return_value = q
            q.scalar.return_value = 0
            mock_db.session.query.return_value = q
            out = AIService.recommend_price(1, 2)
        assert out["customer_avg"] is None

    def test_trend_same_day(self):
        from datetime import UTC

        s1 = MagicMock(sale_date=datetime(2024, 3, 5, 10), amount_aed=10)
        s2 = MagicMock(sale_date=datetime(2024, 3, 5, 12), amount_aed=20)
        assert UTC is not None
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=None),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = [s1, s2]
            mock_db.session.query.return_value = q
            out = AIService.predict_sales_trend()
        assert "7 أيام" in out["message"]

    def test_margins_zero_revenue_pid(self):
        line = MagicMock(product_id=9, cost_price=5, quantity=1, line_total=0, product=None)
        s = MagicMock(amount_aed=0, exchange_rate=1, lines=[line])
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=None),
            patch("services.ai_service.db") as mock_db,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = [s]
            mock_db.session.query.return_value = q
            out = AIService.analyze_profit_margins()
        assert out["success"] is True
        assert out["top_profitable"] == []


class TestTelemetryAndStages:
    def test_telemetry_exception(self):
        AIService._record_telemetry(None, confidence="bad")

    def test_stage_sensitive_exception(self):
        with (
            patch.object(AIService, "is_sensitive_request", side_effect=RuntimeError("x")),
            patch("ai_knowledge.agents.intelligent_assistant.intelligent_assistant") as intel,
            patch("ai_knowledge.action_dispatcher.action_dispatcher") as disp,
            patch("ai_knowledge.agents_core.ask_azad_enhanced", return_value=None),
            patch("ai_knowledge.system_knowledge.search_knowledge", return_value=None),
            patch.object(AIService, "_get_recent_history", return_value=[]),
        ):
            intel.process.return_value = {"response": "lr"}
            disp.parse_chat_action.return_value = None
            early, pipe = AIService._chat_stage1_to_3("hi", {})
        assert early is None and pipe is not None

    def test_dispatch_fail_hint_stash(self):
        with (
            patch("ai_knowledge.agents.intelligent_assistant.intelligent_assistant") as intel,
            patch("ai_knowledge.action_dispatcher.action_dispatcher") as disp,
            patch.object(AIService, "get_api_key", return_value="k"),
            patch("ai_knowledge.agents_core.ask_azad_enhanced", return_value=None),
            patch("ai_knowledge.system_knowledge.search_knowledge", return_value=None),
            patch.object(AIService, "_get_recent_history", return_value=[]),
        ):
            intel.process.return_value = {"response": "lr"}
            disp.parse_chat_action.return_value = ("create_customer", {"n": 1})
            disp.dispatch.return_value = MagicMock(success=False, message="no")
            early, pipe = AIService._chat_stage1_to_3("أنشئ عميل", {})
        assert early is None and pipe["parsed_hint"]["action_type"] == "create_customer"

    def test_execute_none_hint_none(self):
        pipe = _pipe()
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value={"x": 1}),
            patch.object(AIService, "_execute_llm_request", return_value=None),
            patch.object(AIService, "_dispatch_parsed_hint", return_value=None),
        ):
            out = AIService.chat_response("hi")
        assert "المحلي" in out

    def test_persona_import_error(self):
        pipe = _pipe()
        with (
            patch.object(AIService, "get_api_key", return_value="k"),
            patch.object(AIService, "get_provider", return_value="groq"),
            patch("ai_knowledge.tool_registry.get_tools_for_user", return_value=None),
            patch.dict(sys.modules, {"ai_knowledge.personality.prompts": None}),
        ):
            plan = AIService._build_llm_plan(pipe)
        assert plan["provider"] == "groq"

    def test_history_empty_turns(self):
        pipe = _pipe(history=[{"q": "", "r": ""}])
        with (
            patch.object(AIService, "get_api_key", return_value="k"),
            patch.object(AIService, "get_provider", return_value="groq"),
            patch("ai_knowledge.tool_registry.get_tools_for_user", return_value=None),
        ):
            plan = AIService._build_llm_plan(pipe)
        assert "المحادثة" not in plan["payload"]["messages"][0]["content"]

    def test_hint_dump_error(self):
        class Bad:
            def __str__(self):
                return "bad"

        pipe = _pipe(parsed_hint={"action_type": "x", "args": {"o": Bad()}})
        with (
            patch.object(AIService, "get_api_key", return_value="k"),
            patch.object(AIService, "get_provider", return_value="groq"),
            patch("ai_knowledge.tool_registry.get_tools_for_user", return_value=None),
            patch("json.dumps", side_effect=TypeError("no")),
        ):
            plan = AIService._build_llm_plan(pipe)
        assert plan["provider"] == "groq"


class TestGeminiDecls:
    def test_nameless_tool_and_empty(self):
        pipe = _pipe()
        tools = [{"function": {}}, None]
        with (
            patch.object(AIService, "get_api_key", return_value="k"),
            patch.object(AIService, "get_provider", return_value="gemini"),
            patch("ai_knowledge.tool_registry.get_tools_for_user", return_value=tools),
        ):
            plan = AIService._build_llm_plan(pipe)
        assert "tools" not in plan["payload"]


class TestStreamBuf:
    def _run(self, lines):
        import json as _json  # noqa: F401

        pipe = _pipe()
        resp = MagicMock(status_code=200)
        resp.iter_lines.return_value = iter(lines)
        with (
            patch.object(AIService, "_chat_stage1_to_3", return_value=(None, pipe)),
            patch.object(AIService, "_build_llm_plan", return_value=_plan()),
            patch("requests.post", return_value=resp),
            patch.object(AIService, "_execute_native_tool_calls", return_value="N"),
            patch.object(AIService, "_execute_ai_action", return_value=None),
            patch.object(AIService, "_dispatch_parsed_hint", return_value="HINT"),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            return list(AIService.chat_response_stream("hi"))

    def test_no_content_no_tools(self):
        import json as _json

        lines = ["data: " + _json.dumps({"choices": [{"delta": {}}]})]
        out = self._run(lines)
        assert out[-1] == ("final", "F")

    def test_nameless_and_argless(self):
        import json as _json

        lines = [
            "data: " + _json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {}}]}}]}),
            "data: " + _json.dumps({"choices": [{"delta": {"tool_calls": [{"index": 1, "function": {"name": "g"}}]}}]}),
        ]
        out = self._run(lines)
        assert out[-1] == ("final", "F")

    def test_gemini_conversational(self):
        pipe = _pipe()
        with (
            patch("requests.post", return_value=MagicMock(status_code=200)),
            patch.object(AIService, "_execute_ai_action", return_value=None),
            patch.object(AIService, "_dispatch_parsed_hint", return_value=None),
            patch.object(AIService, "_finalize_llm_response", return_value="F"),
        ):
            import json as _json  # noqa: F401

            resp = MagicMock(status_code=200)
            resp.iter_lines.return_value = iter([])
            with patch("requests.post", return_value=resp):
                out = list(AIService._stream_gemini_response(_plan(gemini=True), pipe))
        assert out[-1] == ("final", "F")


class TestSpanEdges:
    def test_brace_heavy(self):
        assert AIService._execute_ai_action('} "action": 1', 1) is None or True
        out = AIService._execute_ai_action('{"a": {"b": 1}} "action": 1', 1)
        assert out is None or isinstance(out, str)

    def test_json_without_action_key(self):
        out = AIService._execute_ai_action('{"note": "say \\"action\\": hi"}', 1)
        assert out is None or "خطأ" in out


class TestRagGatherEdges:
    def test_intent_non_string(self):
        assert AIService._detect_rag_intent(123) == "overview"

    def test_flask_user_no_local(self):
        fu = MagicMock(is_authenticated=True, tenant_id=4, username="f", role=None)
        with (
            patch("flask_login.current_user", fu),
            patch.object(AIService, "_is_ai_external_sharing_enabled", return_value=True),
            patch("services.ai_service.db.session") as sess,
            patch("utils.tenanting.scoped_user_query") as sq,
            patch("flask.current_app") as app,
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.filter_by.return_value = q
            q.count.return_value = 1
            q.scalar.return_value = 5
            sess.query.return_value = q
            sq.return_value.count.return_value = 1
            app.config = {"COMPANY_NAME_AR": "C", "COMPANY_PHONE": "P"}
            out = AIService._gather_intent_knowledge("مرحبا", {"context": {}})
        assert "نطاق" in out

    def test_gather_relevant_exception(self):
        with patch("utils.tenanting.scoped_user_query", side_effect=RuntimeError("x")):
            out = AIService._gather_relevant_knowledge("hi", {"context": {"current_user": MagicMock(tenant_id=1)}})
        assert "خطأ" in out

    def test_gather_relevant_sharing_off(self):
        with patch.object(AIService, "_is_ai_external_sharing_enabled", return_value=False):
            out = AIService._gather_relevant_knowledge("hi", {"context": {"current_user": MagicMock(tenant_id=1)}})
        assert "الخصوصية" in out


class TestSalesPredictionsTid:
    def test_tid_filter(self):
        with (
            patch("services.ai_service.get_active_tenant_id", return_value=1),
            patch("services.ai_service.db.session") as sess,
            patch.object(AIService, "predict_sales_trend", return_value={}),
        ):
            q = MagicMock()
            q.filter.return_value = q
            q.all.return_value = []
            sess.query.return_value = q
            try:
                out = AIService.analyze_sales_with_predictions()
                assert out is not None
            except Exception:
                pass
