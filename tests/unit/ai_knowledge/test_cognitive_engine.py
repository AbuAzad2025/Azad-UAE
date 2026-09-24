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


class TestExpansionRouting:
    ROUTES = [
        ("أنماط المبيعات", CognitiveIntent.PATTERN_ANALYSIS, 0.75),
        ("اتجاه المبيعات", CognitiveIntent.PATTERN_ANALYSIS, 0.40),
        ("هوامش الربح", CognitiveIntent.PROFIT_MARGIN, 0.75),
        ("هامش الربحية", CognitiveIntent.PROFIT_MARGIN, 0.40),
        ("الحركات الراكدة", CognitiveIntent.DEAD_STOCK, 0.75),
        ("منتجات بدون مبيعات", CognitiveIntent.DEAD_STOCK, 0.40),
        ("أعلى المنتجات مبيعاً", CognitiveIntent.TOP_PRODUCTS, 0.75),
        ("الأكثر مبيعا", CognitiveIntent.TOP_PRODUCTS, 0.40),
        ("ديون العملاء", CognitiveIntent.DEBT_OVERVIEW, 0.75),
        ("ذمم العملاء", CognitiveIntent.DEBT_OVERVIEW, 0.40),
        ("ملخص الضرائب", CognitiveIntent.TAX_SUMMARY, 0.30),
        ("ضريبة القيمة", CognitiveIntent.TAX_SUMMARY, 0.40),
        ("كشف الموردين", CognitiveIntent.SUPPLIER_STATUS, 0.75),
        ("مورد أحمد", CognitiveIntent.SUPPLIER_STATUS, 0.30),
        ("فاتورة شراء", CognitiveIntent.PURCHASE_SUMMARY, 0.40),
        ("وين القيود", CognitiveIntent.SYSTEM_GUIDE, 0.40),
        ("كيف أنشئ فاتورة", CognitiveIntent.SYSTEM_GUIDE, 0.30),
        ("تحليل المبيعات", CognitiveIntent.PATTERN_ANALYSIS, 0.40),
        ("ديون أحمد", CognitiveIntent.CUSTOMER_BALANCE, 0.30),
    ]

    def test_expanded_routes(self):
        for message, expected, floor in self.ROUTES:
            result = route(normalize_message(message), None)
            assert result.intent == expected, message
            assert result.confidence >= floor, message
            assert result.evidence, message

    def test_legacy_routes_unchanged(self):
        assert route(normalize_message("هاي"), None).intent == CognitiveIntent.GREETING
        assert route(normalize_message("رصيد"), None).intent == CognitiveIntent.CUSTOMER_BALANCE
        assert route(normalize_message("مصروف"), None).intent == CognitiveIntent.EXPENSE_SUMMARY
        assert route(normalize_message("شيك"), None).intent == CognitiveIntent.CHEQUE_STATUS
        assert route(normalize_message("موظف"), None).intent == CognitiveIntent.HR_SUMMARY
        assert route(normalize_message("xyzq بلا معنى 999"), None).intent == CognitiveIntent.UNKNOWN

    def test_dialect_greetings(self):
        for message in ("كيفك", "شلونك", "شو الأخبار", "هلا والله", "صباح الخير", "hello"):
            result = route(normalize_message(message), None)
            assert result.intent == CognitiveIntent.GREETING, message


class TestExpansionGuards:
    def test_every_data_intent_has_permission(self):
        from ai_knowledge.cognitive.access import required_permission
        from ai_knowledge.cognitive.contracts import DATA_INTENTS

        for intent in DATA_INTENTS:
            assert required_permission(intent), intent.value

    def test_new_intent_permissions(self):
        from ai_knowledge.cognitive.access import check_access

        user = _user()
        user.has_permission.return_value = False
        mapping = {
            CognitiveIntent.PATTERN_ANALYSIS: "view_reports",
            CognitiveIntent.PROFIT_MARGIN: "view_reports",
            CognitiveIntent.DEAD_STOCK: "manage_warehouse",
            CognitiveIntent.TOP_PRODUCTS: "view_reports",
            CognitiveIntent.DEBT_OVERVIEW: "manage_customers",
            CognitiveIntent.TAX_SUMMARY: "view_reports",
            CognitiveIntent.SUPPLIER_STATUS: "manage_suppliers",
        }
        with patch("utils.ai_permissions.user_has_ai_permission", return_value=False):
            for intent, permission in mapping.items():
                allowed, required = check_access(intent, user)
                assert allowed is False
                assert required == permission

    def test_new_planners_fail_closed_without_tenant(self):
        intents = [
            CognitiveIntent.PATTERN_ANALYSIS,
            CognitiveIntent.PROFIT_MARGIN,
            CognitiveIntent.DEAD_STOCK,
            CognitiveIntent.TOP_PRODUCTS,
            CognitiveIntent.DEBT_OVERVIEW,
            CognitiveIntent.TAX_SUMMARY,
            CognitiveIntent.SUPPLIER_STATUS,
        ]
        for intent in intents:
            slots = extract_slots(intent, normalize_message("تقرير"), None)
            status, _trace, provenance, _ = plan_and_execute(intent, slots, None)
            assert status == "no_tenant", intent.value
            assert provenance.tenant_id is None

    def test_supplier_name_extraction(self):
        slots = extract_slots(CognitiveIntent.SUPPLIER_STATUS, normalize_message("حساب المورد أحمد"), None)
        assert slots.values["supplier_name"]
        assert not slots.missing
        carried = extract_slots(
            CognitiveIntent.SUPPLIER_STATUS, normalize_message("وكم حسابه"), {"supplier_name": "أحمد"}
        )
        assert carried.values["supplier_name"] == "أحمد"


class TestGuideAndFallback:
    def test_guide_resolves_feature(self):
        from ai_knowledge.cognitive.composer import compose_guide
        from ai_knowledge.cognitive.guide import resolve_guide_topic

        assert resolve_guide_topic(normalize_message("وين القيود").tokens) in ("قيد", "قيود")
        text = compose_guide("فاتوره")
        assert "فاتورة:" in text
        assert compose_guide("فاتوره") == compose_guide("فاتوره")
        index = compose_guide(None)
        assert "وين القيود" in index or "القيود" in index

    def test_guide_engine_path(self):
        user = _user()
        with patch.object(engine, "_history", return_value=[]):
            result = process_cognitive_message("وين القيود", user)
        assert result.decision == "conversational"
        assert result.intent == CognitiveIntent.SYSTEM_GUIDE.value

    def test_fallback_counts_with_permission(self):
        from types import SimpleNamespace

        from ai_knowledge.cognitive import fallback as fallback_module
        from ai_knowledge.cognitive.fallback import try_dynamic_fallback

        class FakeQuery:
            def __init__(self, rows):
                self._rows = rows

            def order_by(self, *args):
                return self

            def limit(self, *args):
                return self

            def all(self):
                return self._rows

        rows = [SimpleNamespace(id=1, name="أحمد"), SimpleNamespace(id=2, name="سارة")]
        user = _user()
        with patch.object(fallback_module, "tenant_query", return_value=FakeQuery(rows)):
            result = try_dynamic_fallback(normalize_message("كم عدد العملاء"), user)
        assert result is not None
        assert result.decision == "answer"
        assert result.confidence == 0.6
        assert "العملاء" in result.response

    def test_fallback_denied_without_permission(self):
        from ai_knowledge.cognitive.fallback import try_dynamic_fallback

        user = _user()
        user.has_permission.return_value = False
        with patch("utils.ai_permissions.user_has_ai_permission", return_value=False):
            assert try_dynamic_fallback(normalize_message("كم عدد العملاء"), user) is None

    def test_fallback_ignores_anonymous(self):
        from ai_knowledge.cognitive.fallback import try_dynamic_fallback

        assert try_dynamic_fallback(normalize_message("كم عدد العملاء"), None) is None
        assert try_dynamic_fallback(normalize_message("xyzq بلا معنى 999"), _user()) is None

    def test_unknown_flows_to_fallback_then_clarify(self):
        from types import SimpleNamespace

        from ai_knowledge.cognitive import fallback as fallback_module

        class FakeQuery:
            def __init__(self, rows):
                self._rows = rows

            def order_by(self, *args):
                return self

            def limit(self, *args):
                return self

            def all(self):
                return self._rows

        user = _user()
        rows = [SimpleNamespace(id=1, name="أحمد")]
        with (
            patch.object(engine, "_history", return_value=[]),
            patch.object(fallback_module, "tenant_query", return_value=FakeQuery(rows)),
        ):
            counted = process_cognitive_message("كم عدد العملاء", user)
            assert counted.decision == "answer"
            assert "العملاء" in counted.response
        with patch.object(engine, "_history", return_value=[]):
            vague = process_cognitive_message("xyzq بلا معنى 999", None)
            assert vague.decision == "clarify"


class TestNewPlannerExecution:
    def _fake(self, rows):
        from types import SimpleNamespace  # noqa: F401

        class FakeQuery:
            def __init__(self, items):
                self._items = items

            def filter(self, *args, **kwargs):
                return self

            def filter_by(self, *args, **kwargs):
                return self

            def order_by(self, *args):
                return self

            def limit(self, *args):
                return self

            def all(self):
                return self._items

            def first(self):
                return self._items[0] if self._items else None

        return FakeQuery(rows)

    def test_pattern_top_margin_dead(self):
        from datetime import datetime
        from types import SimpleNamespace

        import ai_knowledge.cognitive.planner as planner_module

        now = datetime.now()
        sales = [SimpleNamespace(id=1, sale_date=now, total_amount=100.0)]
        lines = [SimpleNamespace(sale_id=1, product_id=7, line_total=100.0, cost_price=60.0, quantity=2.0)]
        products = [SimpleNamespace(id=7, name="فلتر", is_active=True)]

        def fake_query(model, user=None):
            name = model.__name__
            if name == "Sale":
                return self._fake(sales)
            if name == "SaleLine":
                return self._fake(lines)
            if name == "Product":
                return self._fake(products)
            return self._fake([])

        user = _user()
        with (
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch.object(planner_module, "tenant_query", side_effect=fake_query),
        ):
            for intent in (
                CognitiveIntent.PATTERN_ANALYSIS,
                CognitiveIntent.PROFIT_MARGIN,
                CognitiveIntent.DEAD_STOCK,
                CognitiveIntent.TOP_PRODUCTS,
            ):
                slots = extract_slots(intent, normalize_message("تقرير"), None)
                status, trace, provenance, _ = plan_and_execute(intent, slots, user)
                assert status == "ok", intent.value
                assert trace.conclusion, intent.value
                assert provenance.queries, intent.value

    def test_debt_tax_supplier(self):
        from types import SimpleNamespace

        import ai_knowledge.cognitive.planner as planner_module

        customers = [SimpleNamespace(id=1, name="أحمد", balance=500.0)]
        sales = [SimpleNamespace(id=1, sale_date=None, total_amount=0.0, balance_due=200.0, tax_amount=5.0)]
        purchases = [SimpleNamespace(id=1, tax_amount=2.0)]
        suppliers = [SimpleNamespace(id=9, name="الخليج")]

        def fake_query(model, user=None):
            name = model.__name__
            if name == "Customer":
                return self._fake(customers)
            if name == "Sale":
                return self._fake(sales)
            if name == "Purchase":
                return self._fake(purchases)
            if name == "Supplier":
                return self._fake(suppliers)
            return self._fake([])

        user = _user()
        with (
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch.object(planner_module, "tenant_query", side_effect=fake_query),
        ):
            for intent in (CognitiveIntent.DEBT_OVERVIEW, CognitiveIntent.TAX_SUMMARY):
                slots = extract_slots(intent, normalize_message("تقرير"), None)
                status, trace, provenance, _ = plan_and_execute(intent, slots, user)
                assert status == "ok", intent.value
                assert trace.conclusion, intent.value
            slots = extract_slots(CognitiveIntent.SUPPLIER_STATUS, normalize_message("حساب المورد الخليج"), None)
            status, trace, _prov, _ = plan_and_execute(CognitiveIntent.SUPPLIER_STATUS, slots, user)
            assert status == "ok"
            assert "الخليج" in trace.conclusion


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

    def test_quick_learner_failure_degrades_to_cognitive(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        with (
            patch(
                "ai_knowledge.learning.quick_learner.quick_learner.get_answer",
                side_effect=RuntimeError("db offline"),
            ),
            patch.object(engine, "_history", return_value=[]),
        ):
            result = assistant.process("هاي", user_id=1, context={"use_cognitive": True})
            assert result["method"] == "cognitive"
            assert result["success"] is True

    def test_reasoning_beats_stale_memorized_answer(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        with (
            patch(
                "ai_knowledge.learning.quick_learner.quick_learner.get_answer",
                return_value="رد محفوظ قديم",
            ),
            patch.object(engine, "_history", return_value=[]),
        ):
            result = assistant.process("هاي", user_id=1, context={"use_cognitive": True})
            assert result["method"] == "cognitive"
            assert "رد محفوظ قديم" not in result["response"]


class TestAbstentionPropagation:
    def test_abstained_brain_keeps_local_source(self):
        from ai_knowledge.agents_core import ask_azad_enhanced

        brain = MagicMock()
        brain.ask.return_value = {"answer": "لم أجد شيئا", "confidence": 0.3, "abstained": True}
        with (
            patch("ai_knowledge.system_knowledge.FAQ", {}),
            patch("ai_knowledge.system_knowledge.search_knowledge", return_value=[]),
            patch("ai_knowledge.agents_core._check_llm_availability", return_value=False),
            patch("ai_knowledge.agents_core.get_master_brain", return_value=brain),
            patch("ai_knowledge.trainer.trainer.learn_from_interaction"),
        ):
            result = ask_azad_enhanced("xyz سؤال بلا أساس")
        assert result["source"] == "local"
        assert result["answer"] == ""

    def test_grounded_brain_keeps_master_brain_source(self):
        from ai_knowledge.agents_core import ask_azad_enhanced

        brain = MagicMock()
        brain.ask.return_value = {"answer": "ضريبة القيمة المضافة 5%", "confidence": 0.95}
        with (
            patch("ai_knowledge.system_knowledge.FAQ", {}),
            patch("ai_knowledge.system_knowledge.search_knowledge", return_value=[]),
            patch("ai_knowledge.agents_core._check_llm_availability", return_value=False),
            patch("ai_knowledge.agents_core.get_master_brain", return_value=brain),
            patch("ai_knowledge.trainer.trainer.learn_from_interaction"),
        ):
            result = ask_azad_enhanced("ما ضريبة القيمة المضافة")
        assert result["source"] == "master_brain"
        assert "5%" in result["answer"]


class TestQuickKnowledgeTenantScope:
    def test_quick_lookup_receives_tenant_kwarg(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        with patch(
            "ai_knowledge.learning.quick_learner.quick_learner.get_answer",
            return_value=None,
        ) as get_answer:
            with patch.object(
                assistant,
                "_understand_message",
                return_value={"success": False},
            ):
                assistant.process("سؤال", user_id=1, context={})
        assert get_answer.call_count == 1
        assert "tenant_id" in get_answer.call_args.kwargs
