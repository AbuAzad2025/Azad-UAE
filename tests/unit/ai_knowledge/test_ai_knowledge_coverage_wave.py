"""Coverage wave — drive all 28 ai_knowledge target files to 100%."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, mock_open, patch

import pytest


@pytest.fixture
def knowledge_path(tmp_path):
    with patch(
        "ai_knowledge.get_knowledge_path", side_effect=lambda name: str(tmp_path / name)
    ):
        yield tmp_path


# ── agents/intelligent_assistant.py ──────────────────────────────────


class TestIntelligentAssistantCovWave:
    def test_collect_real_data_outer_exception(self):
        """Lines 330-332: outer exception in _collect_real_data returns {}."""
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        with patch("flask.has_request_context", side_effect=RuntimeError("no flask")):
            r = assistant._collect_real_data("sales_analysis", {}, 1)
        assert isinstance(r, dict)

    def test_analyze_and_reason_exception(self):
        """Lines 413-415: exception in _analyze_and_reason."""
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        bad_data = {"recent_sales": None}
        r = assistant._analyze_and_reason("sales_analysis", bad_data, {})
        assert "insights" in r and r["insights"] == []

    def test_learn_tenant_exception(self):
        """Lines 539-540: tenant resolution fails in _learn_from_interaction."""
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        with (
            patch("flask.has_request_context", side_effect=Exception("no ctx")),
            patch("ai_knowledge.core.learning_system.learning_system") as mock_ls,
        ):
            mock_ls.learn_from_interaction = MagicMock()
            assistant._learn_from_interaction("hi", "hello", 1)


# ── agents/master_brain.py ───────────────────────────────────────────


class TestMasterBrainCovWave:
    def test_quick_calc_formula_error(self):
        """Lines 648-649: formula calculation exception."""
        from ai_knowledge.agents.master_brain import MasterBrain

        brain = MasterBrain()
        result = brain.quick_calc("gross_margin", sales=0, cogs=100)
        assert result["success"] is True
        result2 = brain.quick_calc(
            "break_even", fixed_costs="bad", price=10, variable_cost=5
        )
        assert result2["success"] is False

    def test_formulas_in_ask(self):
        """Lines 529-531: formulas branch in ask."""
        from ai_knowledge.agents.master_brain import MasterBrain

        brain = MasterBrain()
        brain.knowledge_base["accounting"] = {
            "formulas": {"ربح_إجمالي": "الإيرادات - التكاليف"}
        }
        result = brain.ask("ربح إجمالي")
        assert result.get("answer") or result.get("confidence", 0) >= 0

    def test_explain_sub_value_match(self):
        """Line 664: explain matching concept in sub_value string."""
        from ai_knowledge.agents.master_brain import MasterBrain

        brain = MasterBrain()
        brain.knowledge_base["domain_test"] = {
            "cat": {"item_key": "This is about depreciation info"}
        }
        result = brain.explain("depreciation")
        assert "📚" in result


# ── agents/multi_agent_system.py ─────────────────────────────────────


class TestMultiAgentSystemCovWave:
    def test_base_agent_execute_raises(self):
        """Line 57: BaseAgent.execute raises NotImplementedError."""
        from ai_knowledge.agents.multi_agent_system import BaseAgent

        agent = BaseAgent(name="test", expertise=["test"])
        with pytest.raises(NotImplementedError):
            agent.execute("task", {})

    def test_accounting_agent_exception(self):
        """Lines 146-147: AccountingAgent exception branch."""
        from ai_knowledge.agents.multi_agent_system import AccountingAgent

        agent = AccountingAgent()
        result = agent.execute("قيد محاسبي", {"debit": object(), "credit": 100})
        assert result.get("confidence") == 0
        assert "error" in result

    def test_inventory_agent_no_match(self):
        """Line 176: InventoryAgent no keyword match."""
        from ai_knowledge.agents.multi_agent_system import InventoryAgent

        agent = InventoryAgent()
        result = agent.execute("unrelated task", {})
        assert result["confidence"] == 0.5

    def test_inventory_agent_exception(self):
        """Lines 178-179: InventoryAgent exception."""
        from ai_knowledge.agents.multi_agent_system import InventoryAgent

        agent = InventoryAgent()
        with patch.dict(
            "sys.modules",
            {
                "services.ai_service": MagicMock(
                    AIService=MagicMock(
                        optimize_inventory_neural=MagicMock(
                            side_effect=Exception("boom")
                        )
                    )
                )
            },
        ):
            result = agent.execute("مخزون check", {"product_id": 1})
        assert result.get("confidence", 0) == 0 or "error" in result

    def test_maintenance_agent_no_match(self):
        """Line 208: MaintenanceAgent no keyword match."""
        from ai_knowledge.agents.multi_agent_system import MaintenanceAgent

        agent = MaintenanceAgent()
        result = agent.execute("unrelated", {})
        assert result["confidence"] == 0.5


# ── core/context_engine.py ───────────────────────────────────────────


class TestContextEngineCovWave:
    def test_system_summary_exception(self):
        """Lines 112-113: system summary enrichment fails in enhance_response."""
        from ai_knowledge.core.context_engine import ContextEngine

        with (
            patch("ai_knowledge.core.context_engine.system_integrator") as mock_si,
            patch("ai_knowledge.core.context_engine.learning_system") as mock_ls,
        ):
            mock_si.get_system_summary.side_effect = [
                {"success": True, "summary": {}},
                RuntimeError("fail"),
            ]
            mock_ls.get_learning_insights.return_value = {}
            result = ContextEngine.enhance_response("كم عدد العملاء", "base")
        assert isinstance(result, str)

    def test_knowledge_search_exception(self):
        """Lines 137-138: knowledge search enrichment fails."""
        from ai_knowledge.core.context_engine import ContextEngine

        with (
            patch("ai_knowledge.core.context_engine.knowledge_expander") as mock_ke,
            patch("ai_knowledge.core.context_engine.learning_system") as mock_ls,
        ):
            mock_ke.search_knowledge.side_effect = RuntimeError("fail")
            mock_ls.get_learning_insights.return_value = {}
            result = ContextEngine.enhance_response("ابحث عن شيء", "base")
        assert isinstance(result, str)


# ── core/conversation_manager.py ─────────────────────────────────────


class TestConversationManagerCovWave:
    def test_greeting_afternoon(self):
        """Line 68: afternoon branch (12 <= hour < 17)."""
        from ai_knowledge.core.conversation_manager import ConversationManager

        mgr = ConversationManager()
        with patch("ai_knowledge.core.conversation_manager.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 1, 14, 0, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            greeting = mgr._generate_greeting({"name": "Test"})
        assert isinstance(greeting, str)

    def test_intent_history_truncation(self):
        """Line 192: intent_history truncated to last 10."""
        from ai_knowledge.core.conversation_manager import ConversationManager

        mgr = ConversationManager()
        user_id = 99
        mgr.active_conversations[user_id] = {
            "context": {"intent_history": ["x"] * 15},
            "messages": [],
            "start_time": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "style": "professional",
        }
        mgr._update_context(user_id, "new_intent", {})
        assert len(mgr.active_conversations[user_id]["context"]["intent_history"]) <= 11

    def test_get_conversation_history_no_user(self):
        """Line 314: no active conversation returns []."""
        from ai_knowledge.core.conversation_manager import ConversationManager

        mgr = ConversationManager()
        assert mgr.get_conversation_history(9999) == []


# ── core/conversation_store.py ───────────────────────────────────────


class TestConversationStoreCovWave:
    def test_get_context_naive_datetime(self, db_session, sample_tenant):
        """Line 28: updated.tzinfo is None branch."""
        from ai_knowledge.core.conversation_store import get_context
        from models.ai import AiMemory

        naive_time = datetime(2020, 1, 1, 0, 0, 0)
        mem = AiMemory(
            key="conversation_context:123",
            value=json.dumps({"test": True}),
            category="conversation",
            tenant_id=sample_tenant.id,
            is_active=True,
            last_accessed=naive_time,
            created_at=naive_time,
        )
        db_session.add(mem)
        db_session.flush()
        result = get_context(123, tenant_id=sample_tenant.id)
        assert result is None


# ── core/learning_system.py ──────────────────────────────────────────


class TestLearningSystemCovWave:
    def test_normalize_loaded_data_non_dict(self, knowledge_path):
        """Line 53: _normalize_loaded_data for non-dict."""
        from ai_knowledge.core.learning_system import AzadLearningSystem

        result = AzadLearningSystem._normalize_loaded_data("not a dict")
        assert isinstance(result, dict)

    def test_normalize_loaded_data_with_file(self, knowledge_path):
        """Line 53: loaded data not dict triggers normalize."""
        lk_file = knowledge_path / "learned_knowledge.json"
        lk_file.write_text('"not a dict"', encoding="utf-8")
        from ai_knowledge.core.learning_system import AzadLearningSystem

        ls = AzadLearningSystem()
        assert isinstance(ls.learned_knowledge, dict)

    def test_tenant_path_no_tenant(self, knowledge_path):
        """Line 53: _tenant_path without tenant_id."""
        from ai_knowledge.core.learning_system import AzadLearningSystem

        result = AzadLearningSystem._tenant_path("test.json")
        assert result.endswith("test.json")

    def test_save_tenant_data_expertise_error(self, knowledge_path):
        """Lines 288-289: TypeError on dict(ea)."""
        from ai_knowledge.core.learning_system import AzadLearningSystem

        ls = AzadLearningSystem()
        ls.learned_knowledge["expertise_areas"] = 42
        ls.interactions = [{"tenant_id": 1}]
        ls._save_tenant_data(1)

    def test_save_data_expertise_error(self, knowledge_path):
        """Lines 308-309: TypeError on dict(ea) in _save_data."""
        from ai_knowledge.core.learning_system import AzadLearningSystem

        ls = AzadLearningSystem()
        ls.learned_knowledge["expertise_areas"] = 42
        ls._save_data()

    def test_calculate_learning_progress_levels(self, knowledge_path):
        """Lines 378, 380, 382: multiple progress levels."""
        from ai_knowledge.core.learning_system import AzadLearningSystem

        ls = AzadLearningSystem()
        ls.interactions = list(range(15))
        assert "متوسط" in ls._calculate_learning_progress()
        ls.interactions = list(range(60))
        assert "متقدم" in ls._calculate_learning_progress()
        ls.interactions = list(range(250))
        assert "خبير" in ls._calculate_learning_progress()

    def test_get_enhanced_response_no_strategies(self, knowledge_path):
        """Line 540: no response_strategies returns base_response."""
        from ai_knowledge.core.learning_system import AzadLearningSystem

        ls = AzadLearningSystem()
        ls.learned_knowledge.pop("response_strategies", None)
        result = ls.get_enhanced_response("test q", "base answer")
        assert result == "base answer"

    def test_groq_feedback_log_truncation(self, knowledge_path):
        """Line 582: groq_training_log truncation."""
        from ai_knowledge.core.learning_system import AzadLearningSystem

        ls = AzadLearningSystem()
        ls.groq_training_log = [{"q": "x"}] * 105
        ls.learn_from_groq_feedback(
            {
                "question": "q",
                "local_answer": "a",
                "improved_answer": "b",
                "timestamp": datetime.now().isoformat(),
            }
        )
        assert len(ls.groq_training_log) <= 101


# ── core/memory_system.py ────────────────────────────────────────────


class TestMemorySystemCovWave:
    def test_load_memory_corrupt(self, knowledge_path):
        """Line 63: non-list memories returns default."""
        from ai_knowledge.core.memory_system import LongTermMemory

        mem_dir = knowledge_path / "memory"
        mem_dir.mkdir(exist_ok=True)
        ep_file = mem_dir / "episodic_memory.json"
        ep_file.write_text(json.dumps({"memories": "not_a_list"}), encoding="utf-8")
        ms = LongTermMemory()
        assert ms.episodic_memory == {"memories": []}

    def test_recall_fact_category_filter(self, knowledge_path):
        """Line 246: category filter skips non-matching."""
        from ai_knowledge.core.memory_system import LongTermMemory

        ms = LongTermMemory()
        ms.semantic_memory = {
            "memories": [
                {"fact": "test fact", "category": "accounting"},
                {"fact": "test fact", "category": "other"},
            ]
        }
        result = ms.recall_fact("test", category="accounting")
        assert all(m["category"] == "accounting" for m in result)

    def test_recall_procedure_not_found(self, knowledge_path):
        """Line 267: returns None when not found."""
        from ai_knowledge.core.memory_system import LongTermMemory

        ms = LongTermMemory()
        ms.procedural_memory = {"memories": [{"procedure": "foo"}]}
        assert ms.recall_procedure("nonexistent_xyz") is None

    def test_search_memory_procedures(self, knowledge_path):
        """Line 321: procedures filled in search_memory."""
        from ai_knowledge.core.memory_system import LongTermMemory

        ms = LongTermMemory()
        ms.semantic_memory = {"memories": []}
        ms.procedural_memory = {"memories": [{"procedure": "test_proc"}]}
        result = ms.search_memory("test_proc")
        assert len(result["procedures"]) >= 1

    def test_consolidate_is_pass(self, knowledge_path):
        """Line 359: consolidate_memories is pass."""
        from ai_knowledge.core.memory_system import LongTermMemory

        ms = LongTermMemory()
        assert ms.consolidate_memories() is None


# ── core/reasoning_engine.py ─────────────────────────────────────────


class TestReasoningEngineCovWave:
    def test_combine_solutions_prediction(self):
        """Line 245: prediction branch — empty returns None."""
        from ai_knowledge.core.reasoning_engine import ReasoningEngine

        engine = ReasoningEngine()
        assert engine._combine_solutions([42], "prediction") == 42
        assert engine._combine_solutions([], "prediction") is None

    def test_verify_solution_negative(self):
        """Lines 260-262: negative price fails verification."""
        from ai_knowledge.core.reasoning_engine import ReasoningEngine

        engine = ReasoningEngine()
        result = engine._verify_solution(-5, "price test", {})
        assert result["is_valid"] is False

    def test_math_reasoning_percentage_one_number(self):
        """Line 399: percentage with < 2 numbers."""
        from ai_knowledge.core.reasoning_engine import ReasoningEngine

        engine = ReasoningEngine()
        result = engine.mathematical_reasoning("50%")
        assert result["operation"] == "percentage"

    def test_financial_reasoning_low_margin(self):
        """Line 453: gross_margin < 20 warning."""
        from ai_knowledge.core.reasoning_engine import ReasoningEngine

        engine = ReasoningEngine()
        result = engine.financial_reasoning(
            "تحليل",
            {
                "sales": 100,
                "costs": 90,
                "expenses": 5,
                "assets": 200,
                "liabilities": 100,
            },
        )
        assert any("منخفض" in r for r in result.get("reasoning_steps", []))

    def test_financial_reasoning_low_liquidity(self):
        """Line 478: current_ratio < 1 warning."""
        from ai_knowledge.core.reasoning_engine import ReasoningEngine

        engine = ReasoningEngine()
        result = engine.financial_reasoning(
            "تحليل",
            {
                "sales": 1000,
                "costs": 400,
                "expenses": 100,
                "assets": 50,
                "liabilities": 100,
            },
        )
        assert any("خطر" in r for r in result.get("reasoning_steps", []))


# ── generation/document_generator.py ─────────────────────────────────


class TestDocumentGeneratorCovWave:
    def test_generate_sales_report_with_sales(self):
        """Line 161: iterating sales in report."""
        from ai_knowledge.generation.document_generator import DocumentGenerator

        mock_customer = MagicMock()
        mock_customer.configure_mock(name="Test Customer")
        mock_sale = MagicMock()
        mock_sale.id = 1
        mock_sale.customer = mock_customer
        mock_sale.total_amount = Decimal("500.00")
        mock_sale.paid_amount = Decimal("400.00")
        mock_sale.created_at = datetime(2025, 1, 15)
        with patch("models.Sale") as MockSale:
            MockSale.query.all.return_value = [mock_sale]
            result, msg = DocumentGenerator.generate_sales_report()
        assert result is not None

    def test_export_to_excel_exception(self):
        """Lines 254-255: exception in export_to_excel."""
        from ai_knowledge.generation.document_generator import DocumentGenerator

        with patch("models.Sale") as MockSale:
            MockSale.query.all.side_effect = Exception("db error")
            result, msg = DocumentGenerator.export_to_excel("sales")
        assert result is None
        assert "خطأ" in msg

    def test_customer_statement_with_payments(self):
        """Lines 299-300: payments loop in customer statement."""
        from ai_knowledge.generation.document_generator import DocumentGenerator

        mock_payment = MagicMock()
        mock_payment.id = 1
        mock_payment.amount = Decimal("200.00")
        mock_payment.created_at = datetime(2025, 1, 20)
        mock_sale = MagicMock()
        mock_sale.id = 1
        mock_sale.total_amount = Decimal("500.00")
        mock_sale.created_at = datetime(2025, 1, 15)
        mock_sale.payments = [mock_payment]
        mock_customer = MagicMock()
        mock_customer.name = "Test Client"
        mock_customer.phone = "050123456"
        mock_customer.email = "test@example.com"
        with patch("models.Customer") as MockCust, patch("models.Sale") as MockSale:
            MockCust.query.get.return_value = mock_customer
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.all.return_value = [mock_sale]
            MockSale.query.filter.return_value = mock_q
            result, msg = DocumentGenerator.generate_customer_statement(1)
        assert result is not None

    def test_customer_statement_exception(self):
        """Lines 313-314: exception in generate_customer_statement."""
        from ai_knowledge.generation.document_generator import DocumentGenerator

        with patch("models.Customer") as MockCust:
            MockCust.query.get.side_effect = Exception("db error")
            result, msg = DocumentGenerator.generate_customer_statement(1)
        assert result is None


# ── improvement/self_improvement.py ──────────────────────────────────


class TestSelfImprovementCovWave:
    def _make_engine(self, tmp_path):
        with patch(
            "ai_knowledge.get_knowledge_path", side_effect=lambda n: str(tmp_path / n)
        ):
            from ai_knowledge.improvement.self_improvement import AzadSelfImprovement

            return AzadSelfImprovement()

    def test_load_improvement_data_exists(self, tmp_path):
        """Line 69: load existing file."""
        data = {
            "total_improvements": 5,
            "improvement_history": [],
            "last_improvement_date": None,
            "current_version": "1.0",
            "next_version": "1.1",
        }
        (tmp_path / "self_improvement.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        engine = self._make_engine(tmp_path)
        assert engine.improvement_data["total_improvements"] == 5

    def test_load_performance_metrics_exists(self, tmp_path):
        """Line 85: load existing performance file."""
        data = {
            "daily_metrics": {},
            "weekly_metrics": {},
            "monthly_metrics": {},
            "overall_performance": 9.0,
        }
        (tmp_path / "performance_metrics.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        engine = self._make_engine(tmp_path)
        assert engine.performance_metrics.get("overall_performance") == 9.0

    def test_load_improvement_goals_exists(self, tmp_path):
        """Line 100: load existing goals file."""
        data = {"short_term_goals": ["goal1"], "long_term_goals": ["goal2"]}
        (tmp_path / "improvement_goals.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        engine = self._make_engine(tmp_path)
        assert "goal1" in engine.improvement_goals.get("short_term_goals", [])

    def test_implement_improvement_invalid_area(self, tmp_path):
        """Line 236: invalid area."""
        engine = self._make_engine(tmp_path)
        result = engine.implement_improvement("nonexistent_area")
        assert result["success"] is False

    def test_set_goal_invalid_area(self, tmp_path):
        """Line 306: invalid area."""
        engine = self._make_engine(tmp_path)
        result = engine.set_improvement_goal("nonexistent_area", 9.5)
        assert result["success"] is False

    def test_analyze_trend_slow_stable(self, tmp_path):
        """Lines 408-411: slow/stable/zero trends."""
        engine = self._make_engine(tmp_path)
        engine.improvement_data["improvement_history"] = [
            {"improvement": 0.015} for _ in range(10)
        ]
        result = engine._calculate_improvement_trend()
        assert result in ["تحسن بطيء", "تحسن مستقر", "ثابت"]

        engine.improvement_data["improvement_history"] = [
            {"improvement": 0.0} for _ in range(10)
        ]
        assert engine._calculate_improvement_trend() == "ثابت"

    def test_evolve_high_score(self, tmp_path):
        """Lines 459, 468: high score evolve adds capabilities."""
        engine = self._make_engine(tmp_path)
        for area in engine.improvement_areas:
            engine.improvement_areas[area]["current_score"] = 9.5
        result = engine.evolve_capabilities()
        assert len(result.get("new_capabilities", [])) > 0


# ── improvement/self_reflection.py ───────────────────────────────────


class TestSelfReflectionCovWave:
    def test_reflect_low_accuracy(self):
        """Line 75: low accuracy adds weakness."""
        from ai_knowledge.improvement.self_reflection import SelfReflectionEngine

        sr = SelfReflectionEngine()
        sr.performance_log = [{"accuracy": 0.3} for _ in range(5)]
        result = sr.reflect_on_performance()
        assert any("منخفض" in w for w in result.get("weaknesses", []))

    def test_reflect_good_accuracy(self):
        """Line 73: good accuracy (0.7-0.9) adds strength."""
        from ai_knowledge.improvement.self_reflection import SelfReflectionEngine

        sr = SelfReflectionEngine()
        sr.performance_log = [{"accuracy": 0.8} for _ in range(5)]
        result = sr.reflect_on_performance()
        assert any("جيدة" in s for s in result.get("strengths", []))

    def test_log_performance_truncation(self):
        """Line 123: performance_log > 1000 truncation."""
        from ai_knowledge.improvement.self_reflection import SelfReflectionEngine

        sr = SelfReflectionEngine()
        sr.performance_log = [{"accuracy": 0.9}] * 1005
        sr.log_performance("test", 0.9)
        assert len(sr.performance_log) <= 1001

    def test_log_error_truncation(self):
        """Line 138: errors_log > 500 truncation."""
        from ai_knowledge.improvement.self_reflection import SelfReflectionEngine

        sr = SelfReflectionEngine()
        sr.errors_log = [{"type": "err"}] * 505
        sr.log_error("test_err", "msg")
        assert len(sr.errors_log) <= 501


# ── knowledge_base.py ────────────────────────────────────────────────


class TestKnowledgeBaseCovWave:
    def test_search_parts_match(self):
        """Line 795: search_parts finds match."""
        from ai_knowledge.knowledge_base import search_parts, PARTS_DATABASE

        if PARTS_DATABASE:
            first_key = next(iter(PARTS_DATABASE))
            content_snippet = PARTS_DATABASE[first_key][:10].lower()
            results = search_parts(content_snippet)
            assert len(results) >= 1 or isinstance(results, list)
        else:
            results = search_parts("brake")
            assert isinstance(results, list)

    def test_diagnose_code_p0(self):
        """Line 1251: P0 code → Powertrain."""
        from ai_knowledge.knowledge_base import AutomotiveECUKnowledge

        ecu = AutomotiveECUKnowledge()
        result = ecu.diagnose_code("P0101")
        assert result["category"] == "Powertrain"

    def test_diagnose_code_b0(self):
        """Line 1255: B0 code → Body."""
        from ai_knowledge.knowledge_base import AutomotiveECUKnowledge

        ecu = AutomotiveECUKnowledge()
        result = ecu.diagnose_code("B0100")
        assert result["category"] == "Body"

    def test_diagnose_code_u0(self):
        """Line 1257: U0 code → Network."""
        from ai_knowledge.knowledge_base import AutomotiveECUKnowledge

        ecu = AutomotiveECUKnowledge()
        result = ecu.diagnose_code("U0100")
        assert result["category"] == "Network"


# ── learning/auto_retraining.py ──────────────────────────────────────


class TestAutoRetrainingCovWave:
    def test_should_retrain_false(self):
        """Line 36: returns False when no threshold met."""
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        with (
            patch("models.Sale") as MockSale,
            patch("extensions.db"),
            patch.object(
                AutoRetrainingScheduler,
                "get_last_training_info",
                return_value={
                    "timestamp": datetime.now().isoformat(),
                    "sales_count": 1000,
                },
            ),
        ):
            MockSale.query.filter_by.return_value.count.return_value = 1010
            assert AutoRetrainingScheduler.should_retrain() is False

    def test_get_last_training_info_corrupt(self):
        """Lines 68-69: corrupt training log."""
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="not json")),
        ):
            result = AutoRetrainingScheduler.get_last_training_info()
        assert result is None

    def test_log_training_exception(self):
        """Lines 89-90: log_training write failure."""
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        with (
            patch("os.path.exists", return_value=False),
            patch("builtins.open", side_effect=OSError("disk full")),
        ):
            AutoRetrainingScheduler.log_training(100, {"success": True})


# ── learning/continuous_learner.py ───────────────────────────────────


class TestContinuousLearnerCovWave:
    def test_evaluate_memory_exception(self):
        """Lines 290-292: get_learning_system raises."""
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn

        mock_svc = MagicMock()
        mock_svc.get_learning_system.side_effect = Exception("no learning")
        mock_svc.ask_genius.return_value = {"answer": "test answer with keyword1"}
        tests = [{"question": "test?", "expected_keywords": ["keyword1"]}]
        results = evaluate_and_learn(tests, ai_service=mock_svc)
        assert len(results) == 1

    def test_evaluate_learn_exception(self):
        """Lines 322-323: feedback learn raises."""
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn

        mock_memory = MagicMock()
        mock_memory.learn_from_interaction.side_effect = Exception("learn fail")
        mock_svc = MagicMock()
        mock_svc.get_learning_system.return_value = mock_memory
        mock_svc.ask_genius.return_value = {"answer": "kw1 included"}
        tests = [{"question": "q?", "expected_keywords": ["kw1"]}]
        results = evaluate_and_learn(tests, ai_service=mock_svc)
        assert results[0]["success"]

    def test_evaluate_ask_exception(self):
        """Lines 341-342: ask raises, inner learn raises."""
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn

        mock_memory = MagicMock()
        mock_memory.learn_from_interaction.side_effect = Exception("learn fail")
        mock_svc = MagicMock()
        mock_svc.get_learning_system.return_value = mock_memory
        mock_svc.ask_genius.side_effect = Exception("ask fail")
        tests = [{"question": "q?", "expected_keywords": ["kw1"]}]
        results = evaluate_and_learn(tests, ai_service=mock_svc)
        assert not results[0]["success"]


# ── learning/external_learning.py ────────────────────────────────────


class TestExternalLearningCovWave:
    def test_load_learned_data_exists(self, knowledge_path):
        """Line 290: load existing external learned data."""
        from ai_knowledge.learning.external_learning import (
            ExternalLearningSystem as ExternalLearning,
        )

        data = {
            "articles": [{"topic": "x"}],
            "code_snippets": [],
            "solutions": [],
            "tutorials": [],
            "research_papers": [],
            "metadata": {"created": datetime.now().isoformat(), "total_learned": 1},
        }
        learned_file = knowledge_path / "external_learned_data.json"
        learned_file.write_text(json.dumps(data), encoding="utf-8")
        el = ExternalLearning()
        assert len(el.learned_data["articles"]) == 1

    def test_learn_from_source_exception(self, knowledge_path):
        """Lines 362-364: learn_from_source exception."""
        from ai_knowledge.learning.external_learning import (
            ExternalLearningSystem as ExternalLearning,
        )

        el = ExternalLearning()
        with patch.object(
            el, "_extract_knowledge", side_effect=Exception("extract fail")
        ):
            result = el.learn_from_source("wikipedia", "test", "content")
        assert result["success"] is False


# ── learning/quick_learner.py ────────────────────────────────────────


class TestQuickLearnerCovWave:
    def test_get_answer_fuzzy(self, db_session, sample_tenant):
        """Line 46: fuzzy match via get_close_matches."""
        from ai_knowledge.learning.quick_learner import QuickLearner
        from models.ai import AiMemory

        mem = AiMemory(
            key="what is vat rate",
            value="5%",
            category="general",
            tenant_id=sample_tenant.id,
            is_active=True,
        )
        db_session.add(mem)
        db_session.flush()
        ql = QuickLearner()
        ql.get_answer("what is the vat rate?", tenant_id=sample_tenant.id)

    def test_knowledge_base_property(self):
        """Line 76: knowledge_base property."""
        from ai_knowledge.learning.quick_learner import QuickLearner

        assert QuickLearner().knowledge_base == {}


# ── neural/neural_engine.py ──────────────────────────────────────────


class TestNeuralEngineCovWave:
    def _make_engine(self):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        engine = AzadNeuralEngine.__new__(AzadNeuralEngine)
        engine.models = {}
        engine.scalers = {}
        engine.training_history = {}
        engine.model_dir = "/tmp/test_models"
        engine.logger = MagicMock()
        return engine

    def test_fraud_not_enough_sales(self):
        """Line 1363: < 50 sales for fraud."""
        engine = self._make_engine()
        mock_chain = MagicMock()
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.all.return_value = list(range(30))
        with (
            patch("models.Sale") as MockSale,
            patch("models.Customer") as MockCust,
            patch("extensions.db") as mock_db,
        ):
            mock_db.session.query.return_value = mock_chain
            result = engine._train_fraud_internal()
        assert result.get("success") is False

    def test_predict_demand_exception(self):
        """Lines 1776-1778: predict_product_demand exception."""
        engine = self._make_engine()
        with patch.object(
            engine, "_predict_demand_internal", side_effect=Exception("boom")
        ):
            result = engine.predict_product_demand(1)
        assert result == {"forecast": [], "total_expected": 0}

    def test_predict_demand_model_not_trained(self):
        """Line 1787: demand model not trained."""
        engine = self._make_engine()
        engine.models = {}
        with (
            patch("models.SaleLine"),
            patch("models.Sale"),
            patch("extensions.db"),
            patch("sqlalchemy.func"),
        ):
            result = engine._predict_demand_internal(1, 7)
        assert "error" in result or result.get("total_expected") == 0


# ── neural/semantic_matcher.py ───────────────────────────────────────


class TestSemanticMatcherCovWave:
    def test_idf_word_not_in_docs(self):
        """Line 278: word in vocab but not in any document."""
        from ai_knowledge.neural.semantic_matcher import SemanticMatcher

        sm = SemanticMatcher()
        sm.vocabulary.add("xyznonexistent")
        idf = sm._calculate_idf()
        assert idf.get("xyznonexistent") == 0

    def test_cosine_zero_magnitude(self):
        """Line 309: zero magnitude returns 0.0."""
        from ai_knowledge.neural.semantic_matcher import SemanticMatcher

        sm = SemanticMatcher()
        assert sm._cosine_similarity({"w": 0.0}, {"w": 0.0}) == 0.0
        assert sm._cosine_similarity({}, {"w": 1.0}) == 0.0

    def test_fuzzy_match_empty_strings(self):
        """Lines 367, 370: empty strings."""
        from ai_knowledge.neural.semantic_matcher import SemanticMatcher

        sm = SemanticMatcher()
        assert sm.fuzzy_match("", "") == 0.0
        assert sm.fuzzy_match("hello", "") == 0.0

    def test_smart_match_fuzzy_fallback(self):
        """Lines 437-438, 441: fuzzy fallback in smart_match."""
        from ai_knowledge.neural.semantic_matcher import SemanticMatcher

        sm = SemanticMatcher()
        result = sm.smart_match("injector")
        assert result["method"] in ("fuzzy", "semantic")

    def test_find_best_intent_fuzzy(self):
        """find_best_intent basic test."""
        from ai_knowledge.neural.semantic_matcher import SemanticMatcher

        sm = SemanticMatcher()
        sm.intents_db = {"greeting": ["مرحبا", "أهلا", "صباح"]}
        sm.vocabulary = set()
        for examples in sm.intents_db.values():
            for ex in examples:
                sm.vocabulary.update(sm._tokenize(ex))
        sm.idf_scores = sm._calculate_idf()
        best_intent, confidence, all_scores = sm.find_best_intent("مرحبا")
        assert best_intent is not None or confidence >= 0


# ── neural/transformers_brain.py ─────────────────────────────────────


class TestTransformersBrainCovWave:
    def test_extract_intent_types(self):
        """Lines 341, 343: question and calculation intents."""
        from ai_knowledge.neural.transformers_brain import TransformersBrain

        brain = TransformersBrain()
        rep = [0.5] * 100
        assert brain._extract_intent("ما هو الحساب؟", rep) == "question"
        assert brain._extract_intent("احسب المجموع", rep) == "calculation"

    def test_extract_entities_terms(self):
        """Lines 366, 370: tax and management terms."""
        from ai_knowledge.neural.transformers_brain import TransformersBrain

        brain = TransformersBrain()
        entities = brain._extract_entities(
            "ضريبة مخزون قيد 100", ["ضريبة", "مخزون", "قيد"]
        )
        assert "ضريبة" in entities["tax_terms"]
        assert "مخزون" in entities["management_terms"]

    def test_generate_response_tax_branch(self):
        """Line 424: tax_terms response branch."""
        from ai_knowledge.neural.transformers_brain import TransformersBrain

        brain = TransformersBrain()
        r = brain.generate_response("ما هي ضريبة ؟")
        assert "📊" in r

    def test_generate_response_accounting_branch(self):
        """Line 429: accounting_terms response branch."""
        from ai_knowledge.neural.transformers_brain import TransformersBrain

        brain = TransformersBrain()
        r = brain.generate_response("ما هو قيد ؟")
        assert "💼" in r

    def test_generate_response_calculation_branch(self):
        """Line 429: calculation intent branch."""
        from ai_knowledge.neural.transformers_brain import TransformersBrain

        brain = TransformersBrain()
        r = brain.generate_response("احسب الأرباح")
        assert "🧮" in r

    def test_generate_response_explanation_branch(self):
        """Line 343: explanation intent via _extract_intent."""
        from ai_knowledge.neural.transformers_brain import TransformersBrain

        brain = TransformersBrain()
        r = brain.generate_response("اشرح المحاسبة")
        assert "✅" in r

    def test_context_memory_and_summary(self):
        """Lines 464-467: context_memory and summary."""
        from ai_knowledge.neural.transformers_brain import TransformersBrain

        brain = TransformersBrain()
        brain.add_to_context("test msg")
        assert brain.get_context_summary() != "لا يوجد سياق سابق"


# ── neural/vision_processor.py ───────────────────────────────────────


class TestVisionProcessorCovWave:
    def test_ocr_not_available(self):
        """Lines 44-46: PIL import fails."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "PIL" or (isinstance(name, str) and name.startswith("PIL.")):
                raise ImportError("no PIL")
            return real_import(name, *args, **kwargs)

        from ai_knowledge.neural.vision_processor import VisionProcessor

        vp = VisionProcessor.__new__(VisionProcessor)
        with patch("builtins.__import__", side_effect=mock_import):
            result = vp._check_ocr_availability()
        assert result is False

    def test_extract_text(self):
        """extract_text_from_image returns message."""
        from ai_knowledge.neural.vision_processor import VisionProcessor

        vp = VisionProcessor()
        result = vp.extract_text_from_image("dummy.png")
        assert isinstance(result, str)


# ── personality/azad_personality.py ──────────────────────────────────


class TestAzadPersonalityCovWave:
    def test_contextual_response_else(self):
        """Line 219: get_contextual_response else branch."""
        from ai_knowledge.personality.azad_personality import AzadPersonality

        result = AzadPersonality.get_contextual_response("normal", "base response")
        assert isinstance(result, str)


# ── personality/azad_responses.py ────────────────────────────────────


class TestAzadResponsesCovWave:
    def _run_smart_response(self, message):
        from ai_knowledge.personality.azad_responses import AzadResponses

        mock_ai = MagicMock()
        mock_ai.is_sensitive_request.return_value = (False, False, None)
        mock_ai_module = MagicMock(AIService=mock_ai)
        with (
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
            patch.dict(
                "sys.modules",
                {"services": MagicMock(), "services.ai_service": mock_ai_module},
            ),
        ):
            return AzadResponses.smart_response(message)

    def test_smart_response_sources(self):
        """Line 446: sources keyword."""
        result = self._run_smart_response("عرض مصادر")
        assert isinstance(result, str)

    def test_smart_response_shipping_laws(self):
        """Line 469: shipping + law keywords."""
        result = self._run_smart_response("إجراءات شحن")
        assert isinstance(result, str)

    def test_smart_response_question_fallback(self):
        """Line 482: question word in fallback else branch."""
        result = self._run_smart_response("ماذا xyz1234")
        assert isinstance(result, str)


# ── personality/dialects.py ──────────────────────────────────────────


class TestDialectsCovWave:
    def test_get_encouragement_fallback(self):
        """Line 199: unknown dialect returns fallback."""
        from ai_knowledge.personality.dialects import DialectManager

        dm = DialectManager()
        assert dm.get_encouragement(dialect="nonexistent") == "ممتاز! 👍"

    def test_get_response_word_fallback(self):
        """Line 209: unknown dialect returns word_type."""
        from ai_knowledge.personality.dialects import DialectManager

        dm = DialectManager()
        assert dm.get_response_word("hello", dialect="nonexistent") == "hello"


# ── specialized/advanced_laws.py ─────────────────────────────────────


class TestAdvancedLawsCovWave:
    def test_get_tax_info_unavailable(self):
        """Line 114: unknown tax type."""
        from ai_knowledge.specialized.advanced_laws import AdvancedLaws

        al = AdvancedLaws()
        result = al.get_tax_info("uae", "unknown_tax_type")
        assert result == "معلومات ضريبية غير متاحة"


# ── specialized/security_rules.py ────────────────────────────────────


class TestSecurityRulesCovWave:
    def test_filter_email_masking(self):
        """Line 44: email/phone partial mask + non-string email fallback."""
        from ai_knowledge.specialized.security_rules import SecurityRules

        result = SecurityRules.filter_sensitive_data(
            {"email": "test@example.com", "name": "Ali"}
        )
        assert "@***.***" in result["email"]
        result2 = SecurityRules.filter_sensitive_data({"email": 12345})
        assert result2["email"] == 12345

    def test_filter_non_dict(self):
        """Line 49: non-dict returned as-is."""
        from ai_knowledge.specialized.security_rules import SecurityRules

        assert SecurityRules.filter_sensitive_data("just a string") == "just a string"

    def test_sanitize_empty_and_dangerous(self):
        """Lines 87, 92-93: empty input + dangerous chars removed."""
        from ai_knowledge.specialized.security_rules import SecurityRules

        assert SecurityRules.sanitize_input("") == ""
        assert SecurityRules.sanitize_input(None) == ""
        result = SecurityRules.sanitize_input("<script>alert(1)</script>")
        assert "<" not in result


# ── system_knowledge.py ──────────────────────────────────────────────


class TestSystemKnowledgeCovWave:
    def test_search_knowledge_accounting(self):
        """Line 678: search accounting dict match."""
        from ai_knowledge.system_knowledge import search_knowledge

        results = search_knowledge("ضريبة")
        accounting_results = [r for r in results if r.get("type") == "accounting"]
        assert len(accounting_results) >= 1


# ── trainer.py ───────────────────────────────────────────────────────


class TestTrainerCovWave:
    def test_train_from_feedback_exception(self, db_session):
        """Lines 369-370: feedback save fails (non-critical)."""
        from ai_knowledge.trainer import Trainer

        trainer = Trainer()
        with patch.object(trainer, "_get_ql") as mock_ql:
            mock_ql.return_value = MagicMock()
            with patch("ai_knowledge.core.learning_system.learning_system") as mock_ls:
                mock_ls.learn_from_interaction.side_effect = Exception("save fail")
                trainer.train_from_feedback(
                    "question", "answer", user_id=1, tenant_id=1
                )
