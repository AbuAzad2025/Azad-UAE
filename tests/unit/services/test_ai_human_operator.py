"""Professional Human Operator tests — multi-step sequencing, smart input
validation, Layer-1 RBAC tool filtering in the LLM plan, and persona."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from services.ai_service import AIService


def _user(perms=(), owner=False):
    return SimpleNamespace(
        id=1,
        tenant_id=1,
        role=None,
        is_authenticated=True,
        is_owner=owner,
        has_permission=lambda p: p in perms,
    )


def _pipe(user):
    return {
        "message": "أضف مورد واشترِ منه",
        "context": {},
        "current_user": user,
        "user_id": 1,
        "local_response": "رد محلي",
        "knowledge_context": "",
        "system_context": "",
        "force_local": False,
    }


class _RecordingDispatcher:
    """يحاكي ActionDispatcher ويسجل ترتيب التنفيذ."""

    def __init__(self, order_log):
        self._log = order_log

    def dispatch(self, action_type, args):
        self._log.append((action_type, dict(args)))
        return SimpleNamespace(
            success=True,
            message=f"تم {action_type}",
            data={},
            needs_confirmation=False,
            needs_permission="",
        )


class TestMultiStepWorkflowSequencing:
    def test_supplier_then_purchase_executed_in_order(self):
        order_log = []
        tool_calls = [
            {"function": {"name": "create_supplier", "arguments": json.dumps({"name": "شركة نابلس", "phone": "0599"})}},
            {
                "function": {
                    "name": "create_purchase",
                    "arguments": json.dumps(
                        {"supplier_name": "شركة نابلس", "product_name": "زيت زيتون", "quantity": 50}
                    ),
                }
            },
        ]
        with patch(
            "ai_knowledge.action_dispatcher.ActionDispatcher",
            return_value=_RecordingDispatcher(order_log),
        ):
            out = AIService._execute_native_tool_calls(tool_calls, 1)

        assert [a for a, _ in order_log] == ["create_supplier", "create_purchase"]
        # args validated/coerced by Pydantic before dispatch
        assert order_log[1][1]["quantity"] == 50
        assert "تم create_supplier" in out
        assert "تم create_purchase" in out

    def test_missing_critical_input_rejected_before_dispatch(self):
        """الفحص الذكي: عملية ناقصة بيانات جوهرية تُرفض قبل الوصول للمنفّذ."""
        order_log = []
        tool_calls = [
            {"function": {"name": "create_sale", "arguments": json.dumps({"quantity": 2})}},  # no customer/product
            {"function": {"name": "check_stock", "arguments": "{}"}},
        ]
        with patch(
            "ai_knowledge.action_dispatcher.ActionDispatcher",
            return_value=_RecordingDispatcher(order_log),
        ):
            out = AIService._execute_native_tool_calls(tool_calls, 1)

        # invalid call never reached dispatch; valid one still executed
        assert [a for a, _ in order_log] == ["check_stock"]
        assert "⚠️" in out


class TestLayer1ToolFilteringInPlan:
    def test_owner_plan_contains_all_tools(self):
        with (
            patch.object(AIService, "get_api_key", return_value="k"),
            patch.object(AIService, "get_provider", return_value="groq"),
        ):
            plan = AIService._build_llm_plan(_pipe(_user(owner=True)))
        names = {t["function"]["name"] for t in plan["payload"]["tools"]}
        assert "create_user" in names
        assert "create_sale" in names
        assert "cancel_sale" in names
        assert "transfer_stock" in names

    def test_cashier_plan_excludes_unpermitted_tools(self):
        cashier = _user(perms={"manage_sales"})
        with (
            patch.object(AIService, "get_api_key", return_value="k"),
            patch.object(AIService, "get_provider", return_value="groq"),
        ):
            plan = AIService._build_llm_plan(_pipe(cashier))
        names = {t["function"]["name"] for t in plan["payload"]["tools"]}
        assert "create_sale" in names
        assert "create_user" not in names
        assert "add_expense" not in names
        assert "transfer_stock" not in names

    def test_user_without_permissions_gets_conversational_mode(self):
        viewer = _user(perms=set())
        with (
            patch.object(AIService, "get_api_key", return_value="k"),
            patch.object(AIService, "get_provider", return_value="groq"),
        ):
            plan = AIService._build_llm_plan(_pipe(viewer))
        assert "tools" not in plan["payload"]


class TestProfessionalOperatorPersona:
    def test_persona_injected_into_prompt(self):
        with (
            patch.object(AIService, "get_api_key", return_value="k"),
            patch.object(AIService, "get_provider", return_value="groq"),
        ):
            plan = AIService._build_llm_plan(_pipe(_user(owner=True)))
        prompt = plan["payload"]["messages"][0]["content"]
        assert "مشغّل عمليات تنفيذي" in prompt
        assert "أسئلة توضيحية" in prompt
        assert "التسلسل المنطقي" in prompt

    def test_execution_result_has_executive_format(self):
        order_log = []
        tool_calls = [{"function": {"name": "check_stock", "arguments": "{}"}}]
        with patch(
            "ai_knowledge.action_dispatcher.ActionDispatcher",
            return_value=_RecordingDispatcher(order_log),
        ):
            out = AIService._execute_native_tool_calls(tool_calls, 1)
        assert "تم check_stock" in out
        assert "تم التنفيذ بواسطة أزاد" in out
