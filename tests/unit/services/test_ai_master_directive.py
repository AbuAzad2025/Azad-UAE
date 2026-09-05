"""Master Directive acceptance tests — AI native tools, RBAC, tenant guard, model cache.

Covers:
- Phase 1: neural model cache (version hash, drift gate, skip-fresh, background guard).
- Phase 2: native function-calling first (OpenAI/Groq tool_calls, Gemini
  functionCall, parsed-hint fallback, structured-command determinism).
- Phase 3: explicit tenant warning for data intents (fail-closed, non-silent).
- Phase 4: telemetry recording on the pipe/context channel.
"""

from __future__ import annotations

import os
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.ai_service import AIService


@pytest.fixture
def knowledge_path(tmp_path):
    with patch("ai_knowledge.get_knowledge_path", side_effect=lambda name: str(tmp_path / name)):
        yield tmp_path


def _groq_plan(**overrides):
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


def _pipe(**overrides):
    ctx: dict = {}
    pipe = {
        "message": "افحص المخزون",
        "context": ctx,
        "current_user": SimpleNamespace(id=1, tenant_id=1, role=None),
        "user_id": 1,
        "tenant_id": 1,
        "local_response": "رد محلي",
        "knowledge_context": "",
        "system_context": "",
        "force_local": False,
        "parsed_hint": None,
        "history": [],
    }
    pipe.update(overrides)
    return pipe


class TestNativeToolCalling:
    def test_openai_tool_calls_execute_natively(self):
        calls = [{"function": {"name": "check_stock", "arguments": "{}"}}]
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"choices": [{"message": {"tool_calls": calls, "content": None}}]}
        pipe = _pipe()
        with (
            patch("requests.post", return_value=resp),
            patch.object(AIService, "_execute_native_tool_calls", return_value="نتيجة الأداة") as exec_tools,
            patch.object(AIService, "_execute_ai_action") as legacy,
            patch.object(
                AIService,
                "_finalize_llm_response",
                side_effect=lambda text, plan, pipe: f"FINAL::{text}",
            ),
        ):
            out = AIService._execute_llm_request(_groq_plan(), pipe)
        exec_tools.assert_called_once_with(calls, 1)
        legacy.assert_not_called()
        assert out == "FINAL::نتيجة الأداة"
        telemetry = pipe["context"].get("ai_telemetry") or {}
        assert telemetry.get("fallback_path") == "native_tools"
        assert "check_stock" in (telemetry.get("tool_names") or "")

    def test_gemini_function_call_executes_natively(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "list_sales", "args": {}}}]}}]
        }
        plan = _groq_plan(provider="gemini", is_gemini=True, url="https://x/models/m:generateContent?key=k")
        pipe = _pipe()
        with (
            patch("requests.post", return_value=resp),
            patch.object(AIService, "_execute_native_tool_calls", return_value="تم") as exec_tools,
            patch.object(AIService, "_execute_ai_action") as legacy,
            patch.object(
                AIService,
                "_finalize_llm_response",
                side_effect=lambda text, plan, pipe: f"FINAL::{text}",
            ),
        ):
            out = AIService._execute_llm_request(plan, pipe)
        exec_tools.assert_called_once()
        sent = exec_tools.call_args[0][0]
        assert sent[0]["function"]["name"] == "list_sales"
        legacy.assert_not_called()
        assert out == "FINAL::تم"
        assert (pipe["context"].get("ai_telemetry") or {}).get("fallback_path") == "native_tools"

    def test_gemini_plan_carries_function_declarations(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "key")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        tool = {
            "type": "function",
            "function": {
                "name": "check_stock",
                "description": "فحص المخزون",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        pipe = _pipe()
        with patch("ai_knowledge.tool_registry.get_tools_for_user", return_value=[tool]):
            plan = AIService._build_llm_plan(pipe)
        assert plan["is_gemini"] is True
        assert "contents" in plan["payload"]
        assert "messages" not in plan["payload"]
        decls = (plan["payload"].get("tools") or [{}])[0].get("functionDeclarations") or []
        assert [d["name"] for d in decls] == ["check_stock"]

    def test_loose_nl_match_stashes_hint_without_dispatch(self, mocker, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "key")
        mocker.patch(
            "ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process",
            return_value={"response": "x"},
        )
        mocker.patch("ai_knowledge.system_knowledge.search_knowledge", return_value=None)
        mocker.patch(
            "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
            return_value=("list_sales", {}),
        )
        dispatch = mocker.patch("ai_knowledge.action_dispatcher.action_dispatcher.dispatch")
        mocker.patch("ai_knowledge.agents_core.ask_azad_enhanced", return_value=None)
        user = SimpleNamespace(id=1, tenant_id=1, role=None)
        early, pipe = AIService._chat_stage1_to_3("عرض الفواتير", {"current_user": user})
        assert early is None
        assert pipe["parsed_hint"] == {"action_type": "list_sales", "args": {}}
        dispatch.assert_not_called()

    def test_structured_command_dispatches_immediately(self, mocker, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "key")
        mocker.patch(
            "ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process",
            return_value={"response": "x"},
        )
        mocker.patch("ai_knowledge.system_knowledge.search_knowledge", return_value=None)
        mocker.patch(
            "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
            return_value=("create_customer", {"name": "X"}),
        )
        dispatch = mocker.patch(
            "ai_knowledge.action_dispatcher.action_dispatcher.dispatch",
            return_value=SimpleNamespace(success=True, message="تم الإنشاء"),
        )
        user = SimpleNamespace(id=1, tenant_id=1, role=None)
        early, _pipe_out = AIService._chat_stage1_to_3("عميل: X", {"current_user": user})
        dispatch.assert_called_once()
        assert early is not None and "تم الإنشاء" in early

    def test_hint_fallback_executes_through_dispatcher(self, mocker):
        pipe = _pipe(parsed_hint={"action_type": "list_sales", "args": {}})
        result = SimpleNamespace(success=True, message="القائمة", needs_permission="", needs_confirmation=False)
        dispatch = mocker.patch(
            "ai_knowledge.action_dispatcher.ActionDispatcher.dispatch",
            return_value=result,
        )
        out = AIService._dispatch_parsed_hint(pipe)
        dispatch.assert_called_once_with("list_sales", {})
        assert out is not None and "القائمة" in out
        assert (pipe["context"].get("ai_telemetry") or {}).get("fallback_path") == "legacy_action"

    def test_hint_fallback_none_without_hint(self):
        assert AIService._dispatch_parsed_hint(_pipe()) is None
        assert AIService._dispatch_parsed_hint(None) is None


class TestDispatcherRbac:
    @staticmethod
    def _user(**overrides):
        base = {
            "is_authenticated": True,
            "is_owner": False,
            "tenant_id": 1,
            "has_permission": lambda code: False,
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_unpermitted_tool_rejected_before_schema(self, mocker):
        from ai_knowledge.action_dispatcher import ActionDispatcher

        mocker.patch("ai_knowledge.action_dispatcher.current_user", self._user())
        result = ActionDispatcher().dispatch(
            "create_sale",
            {"customer_name": "a", "product_name": "b", "quantity": 1},
        )
        assert result.success is False
        assert result.needs_permission == "manage_sales"

    def test_owner_passes_permission_gate_to_validation(self, mocker):
        from ai_knowledge.action_dispatcher import ActionDispatcher

        mocker.patch(
            "ai_knowledge.action_dispatcher.current_user",
            self._user(is_owner=True, has_permission=lambda code: True),
        )
        result = ActionDispatcher().dispatch("create_sale", {})
        assert not result.needs_permission
        assert result.success is False


class TestTenantGuardExplicit:
    def test_collect_empty_without_tenant(self, app):
        from ai_knowledge.agents.intelligent_assistant import intelligent_assistant

        with app.app_context():
            assert intelligent_assistant._collect_real_data("sales_analysis", {}, None) == {}

    def test_data_intent_warns_explicitly(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        out = IntelligentAssistant._generate_dynamic_response("sales_analysis", {"insights": []}, {}, {})
        assert "لا يوجد سياق منشأة" in out

    def test_conversational_intent_has_no_warning(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        out = IntelligentAssistant._generate_dynamic_response("greeting", {}, {}, {})
        assert "سياق منشأة" not in out


class TestNeuralModelCache:
    @staticmethod
    def _engine(knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        return AzadNeuralEngine()

    def test_version_hash_stable_and_sized(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        h1 = AzadNeuralEngine._version_hash("price_optimizer", 100)
        h2 = AzadNeuralEngine._version_hash("price_optimizer", 100)
        h3 = AzadNeuralEngine._version_hash("price_optimizer", 130)
        assert h1 == h2
        assert len(h1) == 12
        assert h1 != h3

    def test_should_retrain_missing_file(self, knowledge_path):
        engine = self._engine(knowledge_path)
        assert engine.should_retrain("price_optimizer") is True

    def test_cache_fresh_then_stale(self, knowledge_path):
        engine = self._engine(knowledge_path)
        open(os.path.join(engine.models_dir, "price_optimizer.pkl"), "w").close()
        engine._persist_metadata("price_optimizer", 100)
        assert engine.should_retrain("price_optimizer", current_samples=105) is False
        assert engine.should_retrain("price_optimizer", current_samples=130) is True
        assert engine.should_retrain("price_optimizer", current_samples=None) in (True, False)

    def test_save_model_writes_sidecar(self, knowledge_path):
        engine = self._engine(knowledge_path)
        engine.training_status["price_optimizer"] = {"samples": 42}
        assert engine._save_model("price_optimizer") is True
        meta_path = os.path.join(engine.models_dir, "price_optimizer.meta.json")
        assert os.path.exists(meta_path)
        import json as _json

        with open(meta_path, encoding="utf-8") as fh:
            meta = _json.load(fh)
        assert meta["samples"] == 42
        assert meta["model_version_hash"] == engine._version_hash("price_optimizer", 42)

    def test_train_all_models_skips_fresh_cache(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import NEURAL_TRAIN_METHODS

        engine = self._engine(knowledge_path)
        for model in NEURAL_TRAIN_METHODS:
            open(os.path.join(engine.models_dir, f"{model}.pkl"), "w").close()
            engine._persist_metadata(model, 100)
        trains = {}
        for model, attr in NEURAL_TRAIN_METHODS.items():
            mock = MagicMock(return_value={"success": True})
            patcher = patch.object(engine, attr, mock)
            patcher.start()
            trains[attr] = (mock, patcher)
        try:
            with patch.object(engine, "_dataset_volume", return_value=100):
                result = engine.train_all_models(None)
        finally:
            for _, patcher in trains.values():
                patcher.stop()
        for mock, _ in trains.values():
            mock.assert_not_called()
        assert result["success"] is True
        assert all(r.get("skipped") is True for r in result["results"].values())

    def test_train_all_models_retrains_on_drift(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import NEURAL_TRAIN_METHODS

        engine = self._engine(knowledge_path)
        for model in NEURAL_TRAIN_METHODS:
            open(os.path.join(engine.models_dir, f"{model}.pkl"), "w").close()
            engine._persist_metadata(model, 100)
        trains = {}
        for model, attr in NEURAL_TRAIN_METHODS.items():
            mock = MagicMock(return_value={"success": True})
            patcher = patch.object(engine, attr, mock)
            patcher.start()
            trains[attr] = (mock, patcher)
        try:
            with patch.object(engine, "_dataset_volume", return_value=200):
                result = engine.train_all_models(None)
        finally:
            for _, patcher in trains.values():
                patcher.stop()
        for mock, _ in trains.values():
            mock.assert_called_once()
        assert result["trained_models"] == len(NEURAL_TRAIN_METHODS)

    def test_background_retrain_inflight_guard(self, knowledge_path):
        engine = self._engine(knowledge_path)
        started = threading.Event()
        release = threading.Event()

        def _slow(_ctx=None):
            started.set()
            release.wait(timeout=10)
            return {"success": True}

        with patch.object(engine, "train_price_optimizer", side_effect=_slow):
            assert engine.schedule_background_retrain("price_optimizer") is True
            assert started.wait(timeout=10)
            assert engine.schedule_background_retrain("price_optimizer") is False
            release.set()
        deadline = threading.Event()
        for _ in range(100):
            if "price_optimizer" not in engine._retrain_inflight:
                deadline.set()
                break
            deadline.wait(timeout=0.1)
        assert "price_optimizer" not in engine._retrain_inflight
        assert engine.schedule_background_retrain("unknown_model") is False

    def test_predict_next_week_sales_shape(self, knowledge_path):
        engine = self._engine(knowledge_path)
        payload = {
            "forecast": [{"date": "2026-09-06", "amount": 100.0, "confidence": 0.8}] * 7,
            "total_expected": 700.0,
            "trend": "stable",
            "confidence": 0.8,
        }
        with patch.object(engine, "forecast_sales", return_value=payload):
            result = engine.predict_next_week_sales()
        assert result["success"] is True
        assert result["predicted_amount"] == 700.0
        with patch.object(engine, "forecast_sales", return_value={"forecast": []}):
            assert engine.predict_next_week_sales()["success"] is False
