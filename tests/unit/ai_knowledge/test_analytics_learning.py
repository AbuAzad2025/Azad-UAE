"""Tests for analytics, generation, learning, and improvement modules."""

from __future__ import annotations

from unittest.mock import patch

from ai_knowledge.analytics.analytics_predictions import (
    CashFlowAnalytics,
    InventoryAnalytics,
    ProfitAnalytics,
    SalesAnalytics,
    get_analytics,
)
from ai_knowledge.analytics.data_analyzer import DataAnalyzer, data_analyzer
from ai_knowledge.generation.code_generator import CodeGenerator, get_code_generator
from ai_knowledge.improvement.self_improvement import AzadSelfImprovement
from ai_knowledge.improvement.self_reflection import (
    SelfReflectionEngine,
    get_reflection_engine,
)
from ai_knowledge.learning.auto_retraining import (
    AutoRetrainingScheduler,
    auto_retraining,
)
from ai_knowledge.learning.external_learning import (
    ExternalLearningSystem,
    get_external_learning,
)
from ai_knowledge.learning.quick_learner import QuickLearner, quick_learner


class TestSalesAnalytics:
    def test_predict_insufficient(self):
        assert (
            SalesAnalytics.predict_next_month_sales([100])["method"]
            == "insufficient_data"
        )

    def test_predict_trend_up(self):
        result = SalesAnalytics.predict_next_month_sales([100, 110, 120, 130, 140, 150])
        assert result["prediction"] > 0

    def test_inventory_eoq(self):
        result = InventoryAnalytics.calculate_eoq(
            {"annual_sales": 1200, "cost_price": 10, "ordering_cost": 50}
        )
        assert result["eoq"] > 0

    def test_profit_break_even(self):
        result = ProfitAnalytics.break_even_analysis(10000, 60, 100)
        assert result["break_even_units"] == 250

    def test_cash_flow_forecast(self):
        result = CashFlowAnalytics.forecast_cash_flow(
            [{"amount": 1000}], [{"amount": 800}]
        )
        assert result["net_cash_flow"] == 200

    def test_get_analytics(self):
        assert get_analytics("sales") == SalesAnalytics


class TestDataAnalyzer:
    def test_customer_not_found(self):
        with (
            patch("extensions.db") as mock_db,
            patch("models.Customer"),
            patch("models.Sale"),
        ):
            mock_db.session.get.return_value = None
            assert DataAnalyzer().analyze_customer_debt(999)["success"] is False

    def test_singleton(self):
        assert data_analyzer is not None


class TestCodeGenerator:
    def test_sql_select(self):
        sql = CodeGenerator().generate_sql_query(
            "select", "sales", {"where": {"id": 1}}
        )
        assert "SELECT" in sql

    def test_python_function(self):
        code = CodeGenerator().generate_python_function("calc_total", "حساب", ["items"])
        assert "def calc_total" in code

    def test_singleton(self):
        import ai_knowledge.generation.code_generator as mod

        mod._code_generator_instance = None
        assert get_code_generator() is get_code_generator()


class TestSelfReflection:
    def test_empty_reflection(self):
        assert "overall_score" in SelfReflectionEngine().reflect_on_performance()

    def test_log_and_reflect(self):
        engine = SelfReflectionEngine()
        engine.log_performance("task", 0.95)
        assert engine.reflect_on_performance()["overall_score"] > 0

    def test_log_error(self):
        engine = SelfReflectionEngine()
        engine.log_error("timeout", "slow response")
        assert isinstance(engine.suggest_improvements(), list)

    def test_singleton(self):
        import ai_knowledge.improvement.self_reflection as mod

        mod._reflection_engine_instance = None
        assert get_reflection_engine() is get_reflection_engine()


class TestSelfImprovement:
    def test_analyze_performance(self, tmp_path):
        with patch("ai_knowledge.get_knowledge_path", return_value=str(tmp_path)):
            assert isinstance(AzadSelfImprovement().analyze_performance(), dict)

    def test_get_status(self, tmp_path):
        with patch("ai_knowledge.get_knowledge_path", return_value=str(tmp_path)):
            assert isinstance(AzadSelfImprovement().get_improvement_status(), dict)


class TestQuickLearner:
    def test_learn_new(self):
        with patch("models.ai.AiMemory") as MockMem, patch("extensions.db") as mock_db:
            MockMem.query.filter_by.return_value.first.return_value = None
            assert QuickLearner().learn("سؤال", "جواب") is True
            mock_db.session.flush.assert_called()

    def test_singleton(self):
        assert quick_learner is not None


class TestExternalLearning:
    def test_learn_from_source(self, tmp_path):
        with patch("ai_knowledge.get_knowledge_path", return_value=str(tmp_path)):
            sys = ExternalLearningSystem()
            result = sys.learn_from_source("wikipedia", "VAT", "content")
            assert isinstance(result, dict)

    def test_singleton(self, tmp_path):
        with patch("ai_knowledge.get_knowledge_path", return_value=str(tmp_path)):
            import ai_knowledge.learning.external_learning as mod

            mod._external_learning_instance = None
            assert get_external_learning() is get_external_learning()


class TestAutoRetraining:
    def test_should_retrain(self):
        with (
            patch(
                "ai_knowledge.learning.auto_retraining.os.path.exists",
                return_value=False,
            ),
            patch("models.Sale") as MockSale,
        ):
            MockSale.query.filter_by.return_value.count.return_value = 150
            assert AutoRetrainingScheduler().should_retrain() is True

    def test_singleton(self):
        assert auto_retraining is not None
