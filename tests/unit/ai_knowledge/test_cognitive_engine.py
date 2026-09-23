"""Unit tests for the native cognitive engine (deterministic, no canned data)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_knowledge.cognitive import engine, process_cognitive_message
from ai_knowledge.cognitive.access import check_access
from ai_knowledge.cognitive.composer import (
    compose_conversational,
    compose_data,
    compose_denied,
    compose_unknown,
)
from ai_knowledge.cognitive.contracts import CognitiveIntent, Provenance, ReasoningTrace
from ai_knowledge.cognitive.intent_router import route
from ai_knowledge.cognitive.normalizer import normalize_message
from ai_knowledge.cognitive.planner import plan_and_execute
from ai_knowledge.cognitive.slots import extract_slots


def _user(**overrides):
    user = MagicMock()
    user.is_authenticated = True
    user.is_owner = False
    user.id = 7
    user.tenant_id = 1
    user.has_permission.return_value = True
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


class TestNormalizer:
    def test_arabic_variants_collapse(self):
        assert normalize_message("أهلا").tokens == normalize_message("اهلا").tokens
        assert "مساعده" in normalize_message("مساعدة").tokens

    def test_numbers_and_currency(self):
        result = normalize_message("ادفع 1500 درهم")
        assert 1500.0 in result.numbers
        assert "درهم" in result.currency_hints


class TestRouter:
    def test_greeting_with_evidence(self):
        result = route(normalize_message("هاي هلا"))
        assert result.intent == CognitiveIntent.GREETING
        assert result.evidence
        assert result.confidence >= 0.4

    def test_customer_balance_compound(self):
        result = route(normalize_message("رصيد العميل أحمد"))
        assert result.intent == CognitiveIntent.CUSTOMER_BALANCE
        assert any(e.startswith("compound:") for e in result.evidence)

    def test_unknown_has_no_signal(self):
        result = route(normalize_message("xyzq بلا معنى تماما 999"))
        assert result.intent == CognitiveIntent.UNKNOWN
        assert result.confidence <= 0.2


class TestAccess:
    def test_conversational_needs_no_user(self):
        allowed, _ = check_access(CognitiveIntent.GREETING, None)
        assert allowed is True

    def test_data_denied_without_user(self):
        allowed, required = check_access(CognitiveIntent.SALES_SUMMARY, None)
        assert allowed is False
        assert required == "view_reports"

    def test_data_denied_without_permission(self):
        user = _user()
        user.has_permission.return_value = False
        with patch("utils.ai_permissions.user_has_ai_permission", return_value=False):
            allowed, required = check_access(CognitiveIntent.GL_BALANCE, user)
        assert allowed is False
        assert required == "view_ledger"

    def test_owner_passes(self):
        user = _user(is_owner=True)
        user.has_permission.return_value = True
        allowed, _ = check_access(CognitiveIntent.HR_SUMMARY, user)
        assert allowed is True


class TestSlots:
    def test_customer_name_markers(self):
        slots = extract_slots(CognitiveIntent.CUSTOMER_BALANCE, normalize_message("رصيد العميل أحمد"))
        assert slots.values["customer_name"]
        assert not slots.missing

    def test_customer_missing_without_name(self):
        slots = extract_slots(CognitiveIntent.CUSTOMER_BALANCE, normalize_message("رصيد"))
        assert slots.missing == ("customer_name",)

    def test_history_carryover(self):
        slots = extract_slots(
            CognitiveIntent.CUSTOMER_BALANCE,
            normalize_message("وكم المتبقي"),
            {"customer_name": "أحمد"},
        )
        assert slots.values["customer_name"] == "أحمد"


class TestComposer:
    def test_deterministic_conversational(self):
        assert compose_conversational(CognitiveIntent.GREETING) == compose_conversational(CognitiveIntent.GREETING)

    def test_denied_names_permission_without_data(self):
        text = compose_denied(CognitiveIntent.GL_BALANCE, "view_ledger")
        assert "view_ledger" in text
        assert "12345" not in text

    def test_data_cites_provenance(self):
        trace = ReasoningTrace(plan=("q",), steps=(), conclusion="Found 2 sales.", confidence=0.9)
        text = compose_data(
            CognitiveIntent.SALES_SUMMARY, trace, Provenance(tenant_id=1, queries=("Sale[x]",), row_counts=(2,))
        )
        assert "Found 2 sales." in text
        assert "1" in text

    def test_unknown_lists_capabilities(self):
        hypothesis = route(normalize_message("xyzq بلا معنى تماما 999"))
        assert "المبيعات" in compose_unknown(hypothesis)


class TestPlannerGuards:
    def test_no_tenant_fail_closed(self):
        status, trace, provenance, _ = plan_and_execute(
            CognitiveIntent.SALES_SUMMARY, extract_slots(CognitiveIntent.SALES_SUMMARY, normalize_message("ملخص")), None
        )
        assert status == "no_tenant"
        assert provenance.tenant_id is None
        assert trace.conclusion

    def test_missing_slot_never_queries(self):
        user = _user()
        slots = extract_slots(CognitiveIntent.CUSTOMER_BALANCE, normalize_message("رصيد"))
        with patch("utils.tenanting.get_active_tenant_id", return_value=1):
            status, trace, _, _ = plan_and_execute(CognitiveIntent.CUSTOMER_BALANCE, slots, user)
        assert status == "need_slots"
        assert "customer_name" in trace.conclusion or "Missing" in trace.steps[1].observation


class TestEngine:
    def test_conversational_answer(self):
        with patch.object(engine, "_history", return_value=[]):
            result = process_cognitive_message("هاي", None)
        assert result.success is True
        assert result.intent == CognitiveIntent.GREETING.value
        assert result.decision == "conversational"

    def test_denied_before_query(self):
        with patch.object(engine, "_history", return_value=[]):
            result = process_cognitive_message("ملخص المبيعات", None)
        assert result.decision == "denied"
        assert "view_reports" in result.response

    def test_clarify_missing_customer(self):
        user = _user()
        with patch.object(engine, "_history", return_value=[]):
            result = process_cognitive_message("رصيد", user)
        assert result.decision == "clarify"
        assert "العميل" in result.response

    def test_answer_path_uses_trace(self):
        from ai_knowledge.cognitive.contracts import ReasoningStep

        user = _user()
        trace = ReasoningTrace(
            plan=("intent-decoded", "query"),
            steps=(ReasoningStep("query", "Found 3 sales.", 0.9, provenance="Sale[x]"),),
            conclusion="Found 3 sales.",
            confidence=0.9,
        )
        provenance = Provenance(tenant_id=1, queries=("Sale[x]",), row_counts=(3,))
        with (
            patch.object(engine, "_history", return_value=[]),
            patch("ai_knowledge.cognitive.engine.plan_and_execute", return_value=("ok", trace, provenance, {})),
        ):
            result = process_cognitive_message("ملخص المبيعات لآخر 30 يوم", user)
        assert result.decision == "answer"
        assert "Found 3 sales." in result.response


class TestAssistantOptIn:
    def test_process_uses_cognitive_only_with_flag(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        with patch.object(engine, "_history", return_value=[]):
            flagged = assistant.process("هاي", user_id=1, context={"use_cognitive": True})
            assert flagged["method"] == "cognitive"
            assert flagged["intent"] == CognitiveIntent.GREETING.value

    def test_process_legacy_default_without_flag(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        with patch(
            "ai_knowledge.learning.quick_learner.quick_learner.get_answer",
            return_value="إجابة سريعة",
        ):
            result = assistant.process("سؤال", user_id=1, context={})
            assert result["method"] == "quick_learner"
