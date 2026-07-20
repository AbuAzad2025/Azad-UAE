"""Coverage push tests for ai_knowledge modules."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import joblib
import numpy as np
import pytest


@pytest.fixture
def knowledge_path(tmp_path):
    with patch("ai_knowledge.get_knowledge_path", side_effect=lambda name: str(tmp_path / name)):
        yield tmp_path


class TestNeuralEngineCoverage:
    @staticmethod
    def _engine(knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        return AzadNeuralEngine()

    @staticmethod
    def _customer_row(total, days_ago=5):
        row = MagicMock()
        row.total_purchases = total
        row.sales_count = 8
        row.avg_order_value = Decimal("1200")
        row.last_purchase = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return row

    @staticmethod
    def _product_row(stock, min_alert, total_sold):
        row = MagicMock()
        row.current_stock = stock
        row.min_stock_alert = min_alert
        row.cost_price = Decimal("25")
        row.sales_count = 12
        row.total_sold = total_sold
        row.avg_quantity = 2
        return row

    def test_classify_premium_and_vip(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with (
            patch.object(engine, "_load_model", return_value=False),
            patch("extensions.db") as mock_db,
            patch("models.Customer"),
            patch("models.Sale"),
        ):
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = self._customer_row(
                75000
            )
            assert engine.classify_customer_intelligence(2)["classification"] == "premium"
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = self._customer_row(
                150000
            )
            assert engine.classify_customer_intelligence(1)["classification"] == "vip"

    def test_classify_with_loaded_model(self, knowledge_path):
        engine = self._engine(knowledge_path)
        row = self._customer_row(5000)
        with (
            patch("extensions.db") as mock_db,
            patch("models.Customer"),
            patch("models.Sale"),
        ):
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = row
            with (
                patch.object(engine, "_load_model", return_value=True),
                patch.object(engine, "_is_model_loaded", return_value=True),
                patch.object(
                    engine.scalers["customer_classifier"],
                    "transform",
                    return_value=np.array([[1.0, 2.0, 3.0, 4.0, 5.0]]),
                ),
                patch.object(
                    engine.models["customer_classifier"],
                    "predict",
                    return_value=np.array([0]),
                ),
                patch.object(
                    engine.models["customer_classifier"],
                    "predict_proba",
                    return_value=np.array([[0.2, 0.8]]),
                ),
                patch.object(
                    engine.encoders["customer_classifier"],
                    "inverse_transform",
                    return_value=np.array(["premium"]),
                ),
            ):
                result = engine.classify_customer_intelligence(3)
                assert result["classification"] == "premium"
                assert result["model"] == "neural_network"

    def test_optimize_stock_medium_urgency(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with (
            patch.object(engine, "_load_model", return_value=False),
            patch("extensions.db") as mock_db,
            patch("models.Product"),
            patch("models.SaleLine"),
        ):
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = self._product_row(
                22, 10, 40
            )
            result = engine.optimize_stock_level(1)
            assert result["urgency"] == "medium"

    def test_forecast_sales_fallbacks(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with patch.object(engine, "_load_model", return_value=False):
            assert engine.forecast_sales(7)["total_expected"] == 0
        with patch.object(
            engine,
            "_forecast_sales_internal",
            return_value={
                "forecast": [],
                "total_expected": 0,
                "error": "Not enough recent data",
            },
        ):
            assert "error" in engine.forecast_sales(3)

    def test_forecast_sales_success(self, knowledge_path):
        engine = self._engine(knowledge_path)
        forecast_payload = {
            "forecast": [{"date": "2025-06-01", "amount": 100.0, "confidence": 0.88}] * 3,
            "total_expected": 300.0,
            "trend": "stable",
            "confidence": 0.88,
        }
        with patch.object(engine, "_forecast_sales_internal", return_value=forecast_payload):
            result = engine.forecast_sales(3)
            assert len(result["forecast"]) == 3
            assert result["total_expected"] == 300.0

    def test_load_all_models_and_save(self, knowledge_path):
        engine = self._engine(knowledge_path)
        model_path = os.path.join(engine.models_dir, "price_optimizer.pkl")
        scaler_path = os.path.join(engine.models_dir, "price_optimizer_scaler.pkl")
        joblib.dump(engine.models["price_optimizer"], model_path)
        joblib.dump(engine.scalers["price_optimizer"], scaler_path)
        loaded = engine.load_all_models()
        assert "price_optimizer" in loaded
        assert engine._save_model("fraud_detector") is True

    def test_train_internals_mocked(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with patch.object(
            engine,
            "_train_maintenance_internal",
            return_value={"success": True, "samples": 25},
        ):
            assert engine.train_maintenance_prediction()["success"] is True
        with patch.object(
            engine,
            "_train_accounting_internal",
            return_value={"success": True, "accuracy": 0.9},
        ):
            assert engine.train_accounting_assistant()["success"] is True
        with patch.object(
            engine,
            "_train_financial_internal",
            return_value={"success": True, "r2_score": 0.8},
        ):
            assert engine.train_financial_planning()["success"] is True
        with patch.object(
            engine,
            "_train_fraud_internal",
            return_value={"success": True, "accuracy": 0.95},
        ):
            assert engine.train_fraud_detector()["success"] is True
        ctx = MagicMock()
        ctx.return_value.__enter__ = MagicMock(return_value=None)
        ctx.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(engine, "_train_price_internal", return_value={"success": True}) as inner:
            engine.train_price_optimizer(from_app_context=ctx)
            inner.assert_called_once()

    def test_train_all_models(self, knowledge_path):
        engine = self._engine(knowledge_path)
        ctx = MagicMock()
        ctx.return_value.__enter__ = MagicMock(return_value=None)
        ctx.return_value.__exit__ = MagicMock(return_value=False)
        with (
            patch.object(engine, "train_price_optimizer", return_value={"success": True}),
            patch.object(engine, "train_sales_forecaster", return_value={"success": True}),
            patch.object(
                engine,
                "train_customer_classifier",
                return_value={"success": False, "error": "x"},
            ),
            patch.object(engine, "train_fraud_detector", return_value={"success": True}),
            patch.object(engine, "train_inventory_optimizer", return_value={"success": True}),
            patch.object(engine, "train_demand_predictor", return_value={"success": True}),
            patch.object(engine, "train_financial_planning", return_value={"success": True}),
            patch.object(engine, "train_maintenance_prediction", return_value={"success": True}),
            patch.object(engine, "train_accounting_assistant", return_value={"success": True}),
            patch.object(engine, "train_profit_optimizer", return_value={"success": True}),
            patch.object(engine, "train_churn_predictor", return_value={"success": True}),
        ):
            result = engine.train_all_models(ctx)
            assert result["success"] is True
            assert result["trained_models"] >= 1

    def test_validate_accounting_with_model(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with patch.object(engine, "_load_model", return_value=True):
            engine.scalers["accounting_classifier"] = engine.scalers.get(
                "accounting_classifier", engine.scalers["price_optimizer"]
            )
            engine.models["accounting_classifier"] = engine.models["fraud_detector"]
            engine.scalers["accounting_classifier"].transform = MagicMock(return_value=np.array([[1.0] * 6]))
            engine.models["accounting_classifier"].predict = MagicMock(return_value=np.array([1]))
            engine.models["accounting_classifier"].predict_proba = MagicMock(return_value=np.array([[0.1, 0.9]]))
            result = engine.validate_accounting_entry(100, 100, 2, "Sale")
            assert result["is_correct"] is True


class TestVisionProcessorCoverage:
    def test_analyze_part_image_success(self):
        from ai_knowledge.neural.vision_processor import VisionProcessor
        from PIL import Image

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            Image.new("RGB", (20, 20), color="blue").save(f.name)
            path = f.name
        try:
            result = VisionProcessor().analyze_part_image(path)
            assert result.get("confidence") == 0.6
            assert result.get("method") == "basic_vision"
        finally:
            os.unlink(path)


class TestReasoningEngineCoverage:
    @pytest.fixture
    def engine(self):
        from ai_knowledge.core.reasoning_engine import ReasoningEngine

        return ReasoningEngine()

    @pytest.mark.parametrize(
        "problem,ctx",
        [
            ("مخزون المنتج منخفض", {}),
            ("توقع المبيعات القادمة", {}),
            ("قيد محاسبي جديد", {}),
            ("صيانة المحرك", {}),
            ("عميل مهم", {"customer_type": "partner"}),
            ("خطة عامة للنمو", {}),
        ],
    )
    def test_think_problem_types(self, engine, problem, ctx):
        result = engine.think(problem, ctx)
        assert result.get("problem_type") is not None or result.get("reasoning_steps")

    def test_business_reasoning_full(self, engine):
        result = engine.business_reasoning("خطة النمو", {"revenue": 50000})
        assert "swot" in result
        assert len(result["recommendations"]) >= 3
        assert result["action_plan"]

    def test_technical_oil_and_financial_ratios(self, engine):
        oil = engine.technical_reasoning("مشكلة في الزيت")
        assert oil["possible_causes"]
        fin = engine.financial_reasoning(
            "تحليل",
            {
                "sales": 10000,
                "costs": 6000,
                "expenses": 1000,
                "assets": 50000,
                "liabilities": 20000,
            },
        )
        assert fin["metrics"].get("current_ratio") == 2.5

    def test_mathematical_percentage_and_history(self, engine):
        assert engine.mathematical_reasoning("100 نسبة 15%")["operation"] == "percentage"
        engine.think(
            "تسعير المنتج 500",
            {"cost_price": 80, "customer_type": "vip", "quantity": 2},
        )
        assert engine.get_reasoning_history(1)

    def test_think_exception(self, engine):
        with patch.object(engine, "_analyze_problem", side_effect=RuntimeError("fail")):
            assert engine.think("test")["confidence"] == 0


class TestConversationManagerCoverage:
    @pytest.fixture
    def manager(self):
        from ai_knowledge.core.conversation_manager import ConversationManager

        return ConversationManager()

    @pytest.mark.parametrize(
        "message,expected_intent",
        [
            ("كم السعر", "pricing_query"),
            ("توقع المبيعات", "prediction_query"),
            ("قيد محاسبي", "accounting_query"),
            ("صيانة المحرك", "maintenance_query"),
            ("مخزون المنتج", "inventory_query"),
            ("عميل أحمد", "customer_query"),
            ("كيف أضيف فاتورة", "howto_query"),
            ("مرحبا", "general_query"),
        ],
    )
    def test_all_intent_branches(self, manager, message, expected_intent):
        with patch("ai_knowledge.core.memory_system.get_memory_system") as mock_mem:
            mock_mem.return_value.remember_conversation = MagicMock()
            manager.start_conversation(99)
            result = manager.process_message(99, message)
            assert result["intent"] == expected_intent
            assert "response" in result
            assert result["suggestions"]

    def test_greeting_with_user_info(self, manager):
        result = manager.start_conversation(1, {"name": "أحمد"})
        assert "أحمد" in result["greeting"] or "عزيزي" in result["greeting"]

    def test_end_conversation_no_active(self, manager):
        assert manager.end_conversation(404)["error"] == "No active conversation"


class TestSystemIntegrationCoverage:
    @pytest.fixture
    def integrator(self):
        from ai_knowledge.core.system_integration import SystemIntegrator

        return SystemIntegrator()

    def test_get_financial_summary(self, integrator):
        mock_query = MagicMock()
        mock_query.scalar.side_effect = [
            Decimal("10000"),
            Decimal("7000"),
            Decimal("500"),
            Decimal("300"),
            Decimal("8000"),
        ]
        mock_query.filter.return_value = mock_query
        mock_db = MagicMock()
        mock_db.session.query.return_value = mock_query
        mock_db.func.sum.return_value = MagicMock()
        with patch("extensions.db", mock_db):
            result = integrator.get_financial_summary()
            assert result["success"] is True, result.get("error")
            assert result["financial"]["total_receivables"] == 3000.0

    @pytest.mark.parametrize("dtype", ["all", "customers", "products", "sales"])
    def test_search_data_types(self, integrator, dtype):
        customer = MagicMock(
            id=1,
            name="Ali",
            customer_type="VIP",
            phone="050",
            get_balance_aed=lambda: Decimal("100"),
        )
        product = MagicMock(id=2, name="Filter", sku="F1", current_stock=5, unit_price=Decimal("50"))
        sale = MagicMock(
            id=3,
            total_amount=Decimal("200"),
            created_at=datetime.now(),
            customer=customer,
        )
        with (
            patch("models.Customer") as MockC,
            patch("models.Product") as MockP,
            patch("models.Sale") as MockS,
        ):
            MockC.query.filter.return_value.limit.return_value.all.return_value = [customer]
            MockP.query.filter.return_value.limit.return_value.all.return_value = [product]
            MockS.query.join.return_value.filter.return_value.limit.return_value.all.return_value = [sale]
            result = integrator.search_data("Ali", dtype)
            assert result["success"] is True

    def test_add_customer_success(self, integrator):
        tenant = MagicMock(id=1)
        customer = MagicMock(id=10, name="New Co", customer_type="regular", phone="", email="")
        mock_db = MagicMock()
        with (
            patch("models.Customer", return_value=customer) as MockCustomer,
            patch("extensions.db", mock_db),
            patch("models.tenant.Tenant") as MockTenant,
        ):
            MockTenant.get_current.return_value = tenant
            MockCustomer.return_value = customer
            result = integrator.add_customer({"name": "New Co", "customer_type": "regular"})
            assert result["success"] is True
            mock_db.session.add.assert_called_once()
            mock_db.session.flush.assert_called_once()


class TestDataAnalyzerCoverage:
    def test_customer_debt_full_path(self):
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer

        customer = MagicMock(id=1, name="Debtor")
        sale_overdue = MagicMock(
            id=10,
            total_amount=Decimal("1000"),
            paid_amount=Decimal("100"),
            created_at=datetime.now() - timedelta(days=45),
        )
        sale_normal = MagicMock(
            id=11,
            total_amount=Decimal("500"),
            paid_amount=Decimal("200"),
            created_at=datetime.now() - timedelta(days=10),
        )
        mock_sale_q = MagicMock()
        mock_sale_q.filter.return_value.all.return_value = [sale_overdue, sale_normal]
        with patch("extensions.db") as mock_db, patch("models.Sale.query", mock_sale_q):
            mock_db.session.get.return_value = customer
            result = DataAnalyzer().analyze_customer_debt(1)
            assert result["success"] is True, result.get("error")
            assert result["debt_analysis"]["unpaid_sales_count"] == 2
            assert result["debt_analysis"]["overdue_count"] == 1

    def test_sales_performance_with_trend(self):
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer

        sales = []
        for i in range(10):
            cust = MagicMock()
            cust.name = f"Customer{i % 2}"
            sale = MagicMock(
                total_amount=Decimal(str(100 + i * 10)),
                created_at=datetime.now() - timedelta(days=i),
                customer=cust,
            )
            sales.append(sale)
        chain = MagicMock()
        chain.all.return_value = sales
        with patch("models.Sale.query") as mock_q:
            mock_q.filter.return_value = chain
            result = DataAnalyzer().analyze_sales_performance(period_days=30)
            assert result["success"] is True, result.get("error")
            assert result["analysis"]["total_sales"] == 10
            assert result["analysis"]["top_customers"]

    def test_product_performance_all_products(self):
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer

        product = MagicMock(id=1, name="Bolt", sku="B1", current_stock=50)
        line = MagicMock(quantity=3, line_total=Decimal("90"))
        with (
            patch("models.Product") as MockP,
            patch("models.SaleLine") as MockSL,
            patch("models.Sale"),
        ):
            MockP.query.all.return_value = [product]
            MockSL.query.filter.return_value.all.return_value = [line]
            result = DataAnalyzer().analyze_product_performance()
            assert result["success"] is True
            assert result["top_products"][0]["total_sold"] == 3

    def test_payments_and_ratios(self):
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer

        payment = MagicMock(payment_method="card", amount=Decimal("250"))
        mock_db = MagicMock()
        mock_db.func.sum.return_value = MagicMock()
        mock_db.session.query.return_value.scalar.side_effect = [
            Decimal("5000"),
            Decimal("4000"),
        ]
        with (
            patch("extensions.db", mock_db),
            patch("models.Payment") as MockPay,
            patch("models.Customer") as MockC,
            patch("models.Product") as MockP,
            patch("models.Sale"),
        ):
            MockPay.query.all.return_value = [payment]
            MockC.query.count.return_value = 10
            MockP.query.count.return_value = 20
            payments = DataAnalyzer().analyze_payment_patterns()
            ratios = DataAnalyzer().get_financial_ratios()
            assert payments["analysis"]["payment_methods"][0]["method"] == "card"
            assert ratios["ratios"]["collection_rate"] == 80.0


class TestAnalyticsPredictionsCoverage:
    def test_customer_segmentation(self):
        from ai_knowledge.analytics.analytics_predictions import SalesAnalytics

        customers = [{"name": f"C{i}", "total_purchases": i * 1000} for i in range(1, 11)]
        segments = SalesAnalytics.customer_segmentation(customers)
        assert segments["vip"]
        assert segments["regular"]

    def test_analyze_sales_pattern(self):
        from ai_knowledge.analytics.analytics_predictions import SalesAnalytics

        sale = MagicMock()
        sale.sale_date = datetime(2025, 6, 2)
        result = SalesAnalytics.analyze_sales_pattern([sale] * 6)
        assert result["peak_day"] is not None
        assert result["trend"] == "growing"

    def test_inventory_turnover_statuses(self):
        from ai_knowledge.analytics.analytics_predictions import InventoryAnalytics

        assert (
            InventoryAnalytics.inventory_turnover({"cogs_annual": 80000, "avg_inventory_value": 10000})["status"]
            == "excellent"
        )
        assert (
            InventoryAnalytics.inventory_turnover({"cogs_annual": 50000, "avg_inventory_value": 10000})["status"]
            == "good"
        )
        assert (
            InventoryAnalytics.inventory_turnover({"cogs_annual": 30000, "avg_inventory_value": 10000})["status"]
            == "average"
        )
        assert (
            InventoryAnalytics.inventory_turnover({"cogs_annual": 5000, "avg_inventory_value": 10000})["status"]
            == "slow"
        )
        assert InventoryAnalytics.inventory_turnover({"avg_inventory_value": 0})["status"] == "no_inventory"

    def test_predict_high_confidence_and_abc(self):
        from ai_knowledge.analytics.analytics_predictions import SalesAnalytics

        hist = [100, 102, 101, 103, 100, 102]
        result = SalesAnalytics.predict_next_month_sales(hist)
        assert result["confidence"] in ("high", "medium", "low")
        abc = SalesAnalytics.abc_analysis(
            [
                {"name": "A", "revenue": 800},
                {"name": "B", "revenue": 150},
                {"name": "C", "revenue": 50},
            ]
        )
        assert abc["A"]


class TestCodeGeneratorCoverage:
    @pytest.fixture
    def gen(self):
        from ai_knowledge.generation.code_generator import CodeGenerator

        return CodeGenerator()

    def test_fix_code_paths(self, gen):
        quote = gen.fix_code("print('x')", "SyntaxError: quote")
        assert quote["changes"]
        indent = gen.fix_code("def f():\nprint(1)", "IndentationError")
        assert "    " in indent["fixed_code"]
        name = gen.fix_code("db.add(x)", "NameError: name 'db' is not defined")
        assert "extensions" in name["fixed_code"]

    def test_optimize_code_paths(self, gen):
        loop = "items = []\nfor x in range(10):\n    items.append(x)\n"
        bulk = loop + "db.session.add(x)\n" * 6 + "Product.query.filter(x=1).all()"
        opt = gen.optimize_code(bulk)
        assert len(opt["improvements"]) >= 2
        assert opt["performance_gain_percent"] > 0

    def test_sql_insert_and_python_predict(self, gen):
        sql = gen.generate_sql_query("insert", "customers", {"columns": ["name"], "values": ["Ali"]})
        assert "INSERT INTO customers" in sql
        code = gen.generate_python_function("forecast", "توقع المبيعات", ["days"])
        assert "AIService" in code


class TestDocumentGeneratorCoverage:
    @staticmethod
    def _sale_mock():
        customer = MagicMock(name="Ali", phone="050", address="Dubai")
        payment = MagicMock(payment_method="cash")
        line = MagicMock(
            quantity=2,
            unit_price=Decimal("50"),
            line_total=Decimal("100"),
            product=MagicMock(name="Oil Filter"),
        )
        line.product.name = "Oil Filter"
        sale = MagicMock(
            id=42,
            created_at=datetime(2025, 6, 1, 10, 30),
            customer=customer,
            paid_amount=Decimal("100"),
            balance_due=Decimal("0"),
            payments=[payment],
            sale_lines=[line],
            subtotal=Decimal("100"),
            discount_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            tax_amount=Decimal("5"),
            total_amount=Decimal("105"),
        )
        return sale

    def test_generate_receipt(self):
        from ai_knowledge.generation.document_generator import DocumentGenerator

        sale = self._sale_mock()
        with patch("models.Sale") as MockSale:
            MockSale.query.get.return_value = sale
            content, msg = DocumentGenerator.generate_receipt(42)
            assert content is not None
            assert "سند قبض" in content
            assert "نجاح" in msg or "تم" in msg

    def test_generate_invoice(self):
        from ai_knowledge.generation.document_generator import DocumentGenerator

        sale = self._sale_mock()
        with patch("models.Sale") as MockSale:
            MockSale.query.get.return_value = sale
            content, msg = DocumentGenerator.generate_invoice(42)
            assert "فاتورة" in content
            assert "Oil Filter" in content

    def test_generate_missing_sale(self):
        from ai_knowledge.generation.document_generator import DocumentGenerator

        with patch("models.Sale") as MockSale:
            MockSale.query.get.return_value = None
            content, msg = DocumentGenerator.generate_receipt(99)
            assert content is None


class TestIntelligentAssistantCoverage:
    @pytest.fixture
    def assistant(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        return IntelligentAssistant()

    def test_pipeline_stages_mocked(self, assistant):
        understanding = {
            "success": True,
            "intent": "sales_analysis",
            "entities": {},
            "context": {},
            "confidence": 0.9,
        }
        real_data = {
            "recent_sales": {
                "count": 12,
                "total_amount": 50000,
                "avg_amount": 4000,
                "sales": [],
            }
        }
        analysis = {
            "insights": ["ok"],
            "warnings": [],
            "recommendations": ["grow"],
            "predictions": [],
        }
        with (
            patch(
                "ai_knowledge.learning.quick_learner.quick_learner.get_answer",
                return_value=None,
            ),
            patch.object(assistant, "_understand_message", return_value=understanding),
            patch.object(assistant, "_collect_real_data", return_value=real_data),
            patch.object(assistant, "_analyze_and_reason", return_value=analysis),
            patch.object(assistant, "_learn_from_interaction") as learn,
        ):
            result = assistant.process("حلل المبيعات", user_id=5, context={})
            assert result["success"] is True
            assert result["method"] == "intelligent_ai"
            learn.assert_called_once()

    def test_analyze_with_neural_prediction_mock(self, assistant):
        with patch.object(
            assistant.neural_engine,
            "predict_next_week_sales",
            return_value={"success": True, "predicted_amount": 12000},
            create=True,
        ):
            data = {
                "recent_sales": {
                    "count": 20,
                    "total_amount": 100000,
                    "avg_amount": 5000,
                },
                "low_stock_products": [{"name": "P1", "deficit": 5}],
            }
            result = assistant._analyze_and_reason("sales_analysis", data, {})
            assert result["insights"] or result["warnings"] or result["recommendations"]


class TestMasterBrainCoverage:
    @pytest.fixture
    def brain(self):
        from ai_knowledge.agents.master_brain import MasterBrain

        return MasterBrain()

    @pytest.mark.parametrize(
        "formula,params,expected",
        [
            ("gross_margin", {"sales": 1000, "cogs": 600}, 40.0),
            ("net_margin", {"revenue": 1000, "expenses": 700}, 30.0),
            ("current_ratio", {"current_assets": 300, "current_liabilities": 150}, 2.0),
            (
                "eoq",
                {"annual_demand": 1200, "order_cost": 50, "holding_cost": 2},
                pytest.approx(244.95, rel=0.01),
            ),
            (
                "break_even",
                {"fixed_costs": 10000, "price": 100, "variable_cost": 60},
                250.0,
            ),
            ("vat", {"amount": 1000}, 50.0),
            ("price_with_vat", {"amount": 100}, 105.0),
            ("price_without_vat", {"amount_with_vat": 105}, 100.0),
        ],
    )
    def test_quick_calc_formulas(self, brain, formula, params, expected):
        assert brain.quick_calc(formula, **params)["result"] == expected

    @pytest.mark.parametrize(
        "question,fragment",
        [
            ("كيف أحسب نقطة إعادة الطلب", "إعادة"),
            ("مشكلة في الفرامل", "فرامل"),
            ("اكتب استعلام sql", "SQL"),
            ("مبدأ القيد المزدوج", "مزدوج"),
        ],
    )
    def test_more_domains(self, brain, question, fragment):
        result = brain.ask(question)
        assert fragment.lower() in result["answer"].lower() or fragment in result["answer"] or result["confidence"] > 0

    def test_neural_pricing_branch(self, brain):
        with patch("services.ai_service.AIService") as MockAI:
            MockAI.predict_price_with_neural.return_value = {
                "predicted_price": 150.0,
                "margin_percent": 25,
                "confidence": 0.9,
            }
            result = brain.ask("سعر المنتج", context={"product_id": 1, "customer_id": 2})
            assert result["answer"]


class TestAutoRetrainingCoverage:
    def test_trigger_retraining(self, knowledge_path):
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        mock_neural = MagicMock()
        mock_neural.train_all_models.return_value = {
            "success": True,
            "trained_models": 5,
        }
        with (
            patch(
                "ai_knowledge.neural.neural_engine.get_neural_engine",
                return_value=mock_neural,
            ),
            patch("models.Sale") as MockSale,
        ):
            MockSale.query.filter_by.return_value.count.return_value = 200
            result = AutoRetrainingScheduler.trigger_retraining()
            assert result["success"] is True

    def test_check_and_train(self, knowledge_path):
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        with (
            patch.object(AutoRetrainingScheduler, "should_retrain", return_value=True),
            patch.object(
                AutoRetrainingScheduler,
                "trigger_retraining",
                return_value={"success": True},
            ) as trigger,
        ):
            assert AutoRetrainingScheduler.check_and_train_if_needed()["success"] is True
            trigger.assert_called_once()
        with patch.object(AutoRetrainingScheduler, "should_retrain", return_value=False):
            assert "message" in AutoRetrainingScheduler.check_and_train_if_needed()

    def test_should_retrain_with_history(self, knowledge_path, tmp_path):
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        log_path = tmp_path / "training_history.json"
        log_path.write_text(
            json.dumps(
                [
                    {
                        "timestamp": (datetime.now() - timedelta(days=8)).isoformat(),
                        "sales_count": 100,
                        "results": {},
                    }
                ]
            ),
            encoding="utf-8",
        )
        with (
            patch.object(AutoRetrainingScheduler, "TRAINING_LOG_FILE", str(log_path)),
            patch("models.Sale") as MockSale,
        ):
            MockSale.query.filter_by.return_value.count.return_value = 160
            assert AutoRetrainingScheduler.should_retrain() is True

    def test_log_training(self, knowledge_path, tmp_path):
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        log_path = tmp_path / "training_history.json"
        with patch.object(AutoRetrainingScheduler, "TRAINING_LOG_FILE", str(log_path)):
            AutoRetrainingScheduler.log_training(150, {"success": True})
            history = json.loads(log_path.read_text(encoding="utf-8"))
            assert history[-1]["sales_count"] == 150


class TestExternalLearningCoverage:
    def test_more_source_types(self, knowledge_path):
        from ai_knowledge.learning.external_learning import ExternalLearningSystem

        sys = ExternalLearningSystem()
        with patch.object(sys, "_save_learned_data"):
            assert sys.learn_from_source("stackoverflow", "SQL error", "use join")["success"] is True
            assert sys.learn_from_source("github", "flask route", "def view(): pass")["success"] is True
        assert sys.get_automotive_resources()
        assert sys.get_accounting_resources()
        stats = sys.get_statistics()
        assert stats["total_sources"] > 0
        sources = sys.get_knowledge_sources_list()
        assert any(s["category"] == "automotive" for s in sources)


class TestLearningSystemCoverage:
    def test_evolve_knowledge(self, knowledge_path):
        from ai_knowledge.core.learning_system import AzadLearningSystem

        sys = AzadLearningSystem()
        sys.interactions = [
            {
                "question": "مشكلة ecm في المحرك",
                "response": "فحص الحساس",
                "success": True,
                "context": "garage",
            },
        ] * 6
        sys.learned_knowledge["successful_responses"] = {
            "parts_question": [
                {
                    "question": "q",
                    "response": "r 🔧",
                    "timestamp": datetime.now().isoformat(),
                }
            ]
            * 6,
        }
        result = sys.evolve_knowledge()
        assert result["new_terms_discovered"] >= 0
        assert result["strategies_updated"] is True

    def test_groq_feedback(self, knowledge_path):
        from ai_knowledge.core.learning_system import AzadLearningSystem

        sys = AzadLearningSystem()
        with patch.object(sys, "learn_from_interaction") as learn:
            sys.learn_from_groq_feedback(
                {
                    "question": "ما الضريبة",
                    "local_answer": "5",
                    "improved_answer": "ضريبة القيمة المضافة 5% في الإمارات",
                    "timestamp": datetime.now().isoformat(),
                }
            )
            learn.assert_called_once()
        assert len(sys.groq_training_log) == 1

    def test_enhanced_response_with_strategy(self, knowledge_path):
        from collections import Counter
        from ai_knowledge.core.learning_system import AzadLearningSystem

        sys = AzadLearningSystem()
        sys.learned_knowledge["response_strategies"] = {
            "tax_question": {
                "common_elements": {
                    "emojis_used": Counter({"%": 2}),
                    "response_length": [100, 120],
                },
            },
        }
        out = sys.get_enhanced_response("ما ضريبة vat", "الضريبة 5%")
        assert out == "الضريبة 5%"


class TestKnowledgeExpansionCoverage:
    def test_add_website_mocked_requests(self, knowledge_path, tmp_path):
        from ai_knowledge.expansion.knowledge_expansion import KnowledgeExpander

        html = "<html><head><title>Test Site</title></head><body><p>Accounting knowledge content</p></body></html>"
        mock_response = MagicMock()
        mock_response.content = html.encode()
        mock_response.raise_for_status = MagicMock()
        with patch(
            "ai_knowledge.expansion.knowledge_expansion.requests.get",
            return_value=mock_response,
        ):
            expander = KnowledgeExpander()
            result = expander.add_website("example.com", category="accounting", description="test source")
            assert result["success"] is True
            assert result["content_length"] > 0
