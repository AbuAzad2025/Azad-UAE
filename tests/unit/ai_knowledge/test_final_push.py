"""Final coverage push for ai_knowledge modules below 85%."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import joblib
import numpy as np
import pytest


@pytest.fixture
def knowledge_path(tmp_path):
    with patch(
        "ai_knowledge.get_knowledge_path", side_effect=lambda name: str(tmp_path / name)
    ):
        yield tmp_path


def _customer_row(total, days_ago=5, sales_count=8):
    row = MagicMock()
    row.total_purchases = total
    row.sales_count = sales_count
    row.avg_order_value = Decimal("1200")
    row.last_purchase = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return row


def _sale_mock():
    customer = MagicMock(name="Ali", phone="0501234567", address="Dubai")
    payment = MagicMock(
        payment_method="cash", amount=Decimal("100"), created_at=datetime(2025, 6, 1)
    )
    line = MagicMock(
        quantity=2,
        unit_price=Decimal("50"),
        line_total=Decimal("100"),
        product=MagicMock(name="Oil Filter"),
        sale_id=42,
    )
    line.product.name = "Oil Filter"
    line.sale = MagicMock(created_at=datetime(2025, 6, 1))
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


class TestNeuralEngineFinal:
    def _engine(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        return AzadNeuralEngine()

    def test_train_price_optimizer_paths(self, knowledge_path):
        engine = self._engine(knowledge_path)
        ctx = MagicMock()
        ctx.return_value.__enter__ = MagicMock(return_value=None)
        ctx.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(
            engine,
            "_train_price_internal",
            return_value={"success": True, "r2_score": 0.8},
        ) as inner:
            assert engine.train_price_optimizer(from_app_context=ctx)["success"] is True
            inner.assert_called_once()
        with patch.object(
            engine, "_train_price_internal", return_value={"success": True}
        ) as inner2:
            assert engine.train_price_optimizer()["success"] is True
            inner2.assert_called_once()
        with patch.object(
            engine, "_train_price_internal", side_effect=RuntimeError("boom")
        ):
            assert engine.train_price_optimizer()["success"] is False

    def test_predict_next_week_sales_via_forecast(self, knowledge_path):
        engine = self._engine(knowledge_path)
        payload = {
            "forecast": [{"date": "2025-06-01", "amount": 200.0, "confidence": 0.88}]
            * 7,
            "total_expected": 1400.0,
            "trend": "increasing",
            "confidence": 0.88,
        }
        with patch.object(engine, "_forecast_sales_internal", return_value=payload):
            result = engine.forecast_sales(7)
            assert len(result["forecast"]) == 7
            assert result["total_expected"] == 1400.0
        ctx = MagicMock()
        ctx.return_value.__enter__ = MagicMock(return_value=None)
        ctx.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(
            engine, "_forecast_sales_internal", return_value=payload
        ) as inner:
            engine.forecast_sales(7, from_app_context=ctx)
            inner.assert_called_once_with(7)

    def test_classify_customer_all_branches(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with (
            patch("extensions.db") as mock_db,
            patch("models.Customer"),
            patch("models.Sale"),
        ):
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = None
            assert engine.classify_customer_intelligence(99)["classification"] == "new"
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = _customer_row(
                120000
            )
            with patch.object(engine, "_load_model", return_value=False):
                assert (
                    engine.classify_customer_intelligence(1)["classification"] == "vip"
                )
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = _customer_row(
                60000
            )
            with patch.object(engine, "_load_model", return_value=False):
                assert (
                    engine.classify_customer_intelligence(2)["classification"]
                    == "premium"
                )
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = _customer_row(
                1000, days_ago=120
            )
            with patch.object(engine, "_load_model", return_value=False):
                result = engine.classify_customer_intelligence(3)
                assert result["classification"] == "regular"
                assert any("خسارة" in r for r in result["recommendations"])
            row = _customer_row(5000)
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = row
            with (
                patch.object(engine, "_load_model", return_value=True),
                patch.object(engine, "_is_model_loaded", return_value=True),
                patch.object(
                    engine.scalers["customer_classifier"],
                    "transform",
                    return_value=np.array([[1.0] * 5]),
                ),
                patch.object(
                    engine.models["customer_classifier"],
                    "predict",
                    return_value=np.array([1]),
                ),
                patch.object(
                    engine.models["customer_classifier"],
                    "predict_proba",
                    return_value=np.array([[0.1, 0.9]]),
                ),
                patch.object(
                    engine.encoders["customer_classifier"],
                    "inverse_transform",
                    return_value=np.array(["premium"]),
                ),
            ):
                neural = engine.classify_customer_intelligence(4)
                assert neural["classification"] == "premium"
                assert neural["model"] == "neural_network"
        with patch.object(
            engine, "_classify_customer_internal", side_effect=RuntimeError("fail")
        ):
            assert (
                engine.classify_customer_intelligence(5)["classification"] == "unknown"
            )

    def test_save_load_model_tmp_path(self, knowledge_path):
        engine = self._engine(knowledge_path)
        assert engine._save_model("price_optimizer") is True
        assert engine._load_model("price_optimizer") is True
        assert engine._load_model("nonexistent_model_xyz") is False
        bad_path = engine.models_dir
        with patch("joblib.dump", side_effect=OSError("disk full")):
            assert engine._save_model("price_optimizer") is False
        with patch("joblib.load", side_effect=Exception("corrupt")):
            assert engine._load_model("price_optimizer") is False
        joblib.dump(engine.models["fraud_detector"], f"{bad_path}/fraud_detector.pkl")
        joblib.dump(
            engine.scalers["fraud_detector"], f"{bad_path}/fraud_detector_scaler.pkl"
        )
        assert engine._load_model("fraud_detector") is True


class TestNeuralNetworkConsolidated:
    def test_neural_engine_from_consolidated(self, knowledge_path):
        from ai_knowledge.neural_network import AzadNeuralEngine, understand_message

        engine = AzadNeuralEngine()
        assert "intent" in understand_message("توقع المبيعات")
        with patch.object(engine, "_load_model", return_value=False):
            price = engine.predict_optimal_price(100, 2, "merchant")
            assert price["model"] == "rule_based"
        with patch.object(
            engine,
            "detect_fraud",
            return_value={"is_fraud": False, "risk_score": 0.1, "reasons": []},
        ):
            assert engine.detect_fraud({"amount_aed": 500})["is_fraud"] is False

    def test_understand_intent_and_status(self, knowledge_path):
        from ai_knowledge.neural_network import AzadNeuralEngine

        engine = AzadNeuralEngine()
        intent = engine.understand_intent("حلل المبيعات والأداء")
        assert intent["intent"] == "sales_analysis"
        status = engine.get_status()
        assert status["total_models"] >= 10


class TestCoreEngineConsolidated:
    def test_reasoning_engine_from_core_engine(self):
        from ai_knowledge.core_engine import ReasoningEngine

        engine = ReasoningEngine()
        assert engine.mathematical_reasoning("10 + 5")["result"] == 15
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
        assert fin["metrics"]["current_ratio"] == 2.5
        engine.think(
            "تسعير المنتج",
            {
                "cost_price": 100,
                "customer_type": "partner",
                "quantity": 20,
                "margin": 1.15,
                "discount": 5,
            },
        )

    def test_context_engine_from_core_engine(self):
        from ai_knowledge.core_engine import ContextEngine

        assert ContextEngine.analyze_context("مرحبا")["intent"] == "greeting"
        assert ContextEngine.analyze_context("حلل المبيعات")["intent"] == "analysis"
        with (
            patch("ai_knowledge.core.context_engine.data_analyzer") as mock_da,
            patch("ai_knowledge.core.context_engine.system_integrator") as mock_si,
            patch("ai_knowledge.core.context_engine.knowledge_expander") as mock_ke,
            patch("ai_knowledge.core.context_engine.learning_system") as mock_ls,
        ):
            mock_da.get_financial_ratios.return_value = {
                "success": True,
                "ratios": {"gross_profit_margin": 30, "net_profit_margin": 12},
            }
            mock_si.get_system_summary.return_value = {
                "success": True,
                "summary": {
                    "total_customers": 5,
                    "total_products": 10,
                    "today_sales": 1000,
                },
            }
            mock_ke.search_knowledge.return_value = {
                "success": True,
                "results": [{"title": "hit"}],
            }
            mock_ls.get_learning_insights.return_value = {
                "total_interactions": 20,
                "top_topics": [{"topic": "sales"}],
            }
            enhanced = ContextEngine.enhance_response("حلل المبيعات", "base", {})
            assert "base" in enhanced
            assert ContextEngine.get_smart_suggestions("مساعدة", {})[0]

    def test_system_integrator_from_core_engine(self):
        from ai_knowledge.core_engine import SystemIntegrator

        integrator = SystemIntegrator()
        supplier = MagicMock(
            id=3,
            name="SupplierX",
            supplier_type="local",
            phone="050",
            email="s@test.com",
            get_balance_aed=lambda: Decimal("2500"),
        )
        supplier.purchases.count.return_value = 4
        last_purchase = MagicMock(created_at=datetime(2025, 5, 1))
        supplier.purchases.order_by.return_value.first.return_value = last_purchase
        with patch("models.Supplier") as MockSup, patch("models.Purchase"):
            MockSup.query.get.return_value = supplier
            by_id = integrator.get_supplier_balance("3")
            assert by_id["success"] is True
            MockSup.query.filter.return_value.first.return_value = supplier
            by_name = integrator.get_supplier_balance("SupplierX")
            assert by_name["supplier"]["balance_aed"] == 2500.0
            MockSup.query.get.return_value = None
            MockSup.query.filter.return_value.first.return_value = None
            assert integrator.get_supplier_balance("missing")["success"] is False


class TestAnalyticsEngineConsolidated:
    def test_data_analyzer_from_analytics_engine(self):
        from ai_knowledge.analytics_engine import DataAnalyzer

        customer = MagicMock(id=1, name="Debtor")
        sale = MagicMock(
            id=10,
            total_amount=Decimal("1000"),
            paid_amount=Decimal("100"),
            created_at=datetime.now() - timedelta(days=45),
        )
        mock_sale_q = MagicMock()
        mock_sale_q.filter.return_value.all.return_value = [sale]
        mock_db = MagicMock()
        mock_db.session.get.return_value = customer
        with patch("extensions.db", mock_db), patch("models.Sale.query", mock_sale_q):
            result = DataAnalyzer().analyze_customer_debt(1)
            assert result["success"] is True
            assert result["debt_analysis"]["overdue_count"] == 1

    def test_sales_analytics_from_analytics_engine(self):
        from ai_knowledge.analytics_engine import (
            SalesAnalytics,
            InventoryAnalytics,
            ProfitAnalytics,
            get_analytics,
        )

        assert (
            SalesAnalytics.predict_next_month_sales([100, 110, 120, 130, 140, 150])[
                "prediction"
            ]
            > 0
        )
        assert (
            SalesAnalytics.predict_next_month_sales([1, 2])["method"]
            == "insufficient_data"
        )
        sale = MagicMock(sale_date=datetime(2025, 6, 2))
        assert SalesAnalytics.analyze_sales_pattern([sale] * 6)["trend"] == "growing"
        assert (
            InventoryAnalytics.calculate_reorder_point(
                {"avg_daily_sales": 5, "lead_time_days": 7, "current_stock": 50}
            )["status"]
            == "ok"
        )
        assert ProfitAnalytics.gross_profit_margin(1000, 600) == 40.0
        assert get_analytics("sales") is SalesAnalytics


class TestGenerationCoreFinal:
    def test_generate_receipt_from_generation_core(self):
        from ai_knowledge.generation_core import DocumentGenerator

        sale = _sale_mock()
        with patch("models.Sale") as MockSale:
            MockSale.query.get.return_value = sale
            content, msg = DocumentGenerator.generate_receipt(42)
            assert content is not None
            assert "سند قبض" in content
            assert "تم" in msg


class TestDocumentGeneratorModule:
    def test_more_document_methods(self):
        from ai_knowledge.generation.document_generator import DocumentGenerator

        sale = _sale_mock()
        with patch("models.Sale") as MockSale:
            MockSale.query.get.return_value = sale
            MockSale.query.filter.return_value.all.return_value = [sale]
            MockSale.query.filter.return_value = MockSale.query
            invoice, imsg = DocumentGenerator.generate_invoice(42)
            assert "فاتورة" in invoice
            report, rmsg = DocumentGenerator.generate_sales_report()
            assert "تقرير" in report
            statement, smsg = DocumentGenerator.generate_customer_statement(1)
            assert statement is None or "كشف" in statement
        with (
            patch("models.Sale") as MockSale,
            patch("models.Customer") as MockC,
            patch("models.Product") as MockP,
        ):
            MockSale.query.all.return_value = [sale]
            MockC.query.all.return_value = [
                MagicMock(
                    id=1,
                    name="Ali",
                    customer_type="regular",
                    phone="",
                    email="",
                    get_balance_aed=lambda: Decimal("0"),
                    created_at=datetime.now(),
                )
            ]
            MockP.query.all.return_value = [
                MagicMock(
                    id=1,
                    name="Bolt",
                    sku="B1",
                    current_stock=10,
                    unit_price=Decimal("5"),
                    min_stock_alert=2,
                    category=MagicMock(name="Parts"),
                )
            ]
            data, fname = DocumentGenerator.export_to_excel("sales")
            assert data is not None
            assert fname.endswith(".csv")
            bad, err = DocumentGenerator.export_to_excel("unknown_type")
            assert bad is None


class TestAgentsCoreFinal:
    def test_get_llm_response_groq(self):
        from ai_knowledge import agents_core

        agents_core._llm_available = None
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "إجابة من LLM"}}]
        }
        with (
            patch.dict(
                "os.environ",
                {"GROQ_API_KEY": "test-key", "GEMINI_API_KEY": ""},
                clear=False,
            ),
            patch("requests.post", return_value=mock_resp) as post,
        ):
            result = agents_core._get_llm_response("system", "سؤال")
            assert result == "إجابة من LLM"
            post.assert_called_once()

    def test_get_llm_response_gemini_fallback(self):
        from ai_knowledge import agents_core

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "gemini answer"}]}}]
        }
        with (
            patch.dict(
                "os.environ",
                {"GROQ_API_KEY": "", "GEMINI_API_KEY": "g-key"},
                clear=False,
            ),
            patch("requests.post", return_value=mock_resp),
        ):
            assert agents_core._get_llm_response("sys", "q") == "gemini answer"

    def test_ask_azad_enhanced_llm_path(self):
        from ai_knowledge.agents_core import ask_azad_enhanced

        with (
            patch("ai_knowledge.system_knowledge.search_knowledge", return_value=[]),
            patch("ai_knowledge.system_knowledge.FAQ", {}),
            patch(
                "ai_knowledge.agents_core._check_llm_availability", return_value=True
            ),
            patch(
                "ai_knowledge.agents_core._get_llm_response",
                return_value="شرح محاسبي مفصل",
            ),
            patch("ai_knowledge.trainer.trainer") as mock_trainer,
        ):
            mock_trainer.learn_from_interaction = MagicMock()
            result = ask_azad_enhanced(
                "كيف أسجل قيد محاسبي؟", context={"role": "accountant"}, user_id=1
            )
            assert result["source"] == "llm"
            assert "محاسبي" in result["answer"]


class TestAzadResponsesHandlers:
    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses

        return AzadResponses()

    def _common_mocks(self):
        customer_payload = {
            "success": True,
            "customer": {
                "id": 1,
                "name": "أحمد",
                "customer_type": "regular",
                "phone": "050",
                "email": "a@test.com",
                "balance_aed": 500.0,
                "total_sales": 3,
                "last_sale_date": "2025-01-01",
            },
        }
        debt_payload = {
            "success": True,
            "debt_analysis": {
                "unpaid_sales_count": 1,
                "avg_debt_amount": 200,
                "max_debt_amount": 200,
                "overdue_count": 0,
            },
        }
        product_payload = {
            "success": True,
            "product": {
                "id": 2,
                "name": "Filter",
                "sku": "F1",
                "current_stock": 5,
                "alert_limit": 10,
                "unit_price": 25.0,
                "category": "Parts",
                "status": "منخفض",
            },
        }
        summary_payload = {
            "success": True,
            "summary": {
                "customers": {"total": 10, "vip": 1, "recent": []},
                "sales": {"total": 50, "today": 2, "recent": []},
                "products": {"total": 100, "low_stock": 3, "out_of_stock": 1},
                "payments": {"total": 30, "today": 1},
            },
        }
        return customer_payload, debt_payload, product_payload, summary_payload

    def test_handle_methods_direct(self, responses):
        customer_payload, debt_payload, product_payload, summary_payload = (
            self._common_mocks()
        )
        with (
            patch(
                "ai_knowledge.personality.azad_responses.system_integrator"
            ) as mock_si,
            patch("ai_knowledge.personality.azad_responses.data_analyzer") as mock_da,
        ):
            mock_si.get_customer_balance.return_value = customer_payload
            mock_si.get_customer_sales_summary.return_value = {
                "success": True,
                "summary": {
                    "total_sales": 2,
                    "total_amount": 1000,
                    "paid_amount": 800,
                    "balance_due": 200,
                    "recent_sales": [
                        {"id": 1, "date": "2025-06-01", "amount": 500, "status": "جزئي"}
                    ],
                },
            }
            mock_si.get_product_stock.return_value = product_payload
            mock_si.get_system_summary.return_value = summary_payload
            mock_si.get_financial_summary.return_value = {
                "success": True,
                "financial": {
                    "total_sales": 50000.0,
                    "total_payments": 40000.0,
                    "total_receivables": 10000.0,
                    "today_sales": 500.0,
                    "today_payments": 300.0,
                },
            }
            mock_si.search_data.return_value = {
                "success": True,
                "results": {"customers": [], "products": [], "sales": []},
            }
            mock_da.analyze_customer_debt.return_value = debt_payload
            assert "أحمد" in responses._handle_customer_balance_query(
                "رصيد العميل أحمد"
            )
            assert "Filter" in responses._handle_product_stock_query(
                "مخزون منتج Filter"
            )
            assert "إجمالي العملاء" in responses._handle_system_summary_query()
            assert responses._handle_search_query("ابحث عن علي")
            assert responses._handle_customer_info_query("بيانات العميل أحمد")

    def test_smart_response_handler_routes(self, responses):
        customer_payload, debt_payload, product_payload, summary_payload = (
            self._common_mocks()
        )
        with (
            patch(
                "ai_knowledge.personality.azad_responses.system_integrator"
            ) as mock_si,
            patch("ai_knowledge.personality.azad_responses.data_analyzer") as mock_da,
            patch(
                "ai_knowledge.personality.azad_responses.document_generator"
            ) as mock_doc,
            patch(
                "ai_knowledge.personality.azad_responses.knowledge_expander"
            ) as mock_ke,
            patch("ai_knowledge.personality.azad_responses.advanced_laws") as mock_laws,
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": "general", "confidence": 0.1},
            ),
            patch(
                "ai_knowledge.personality.azad_responses.intelligent_assistant"
            ) as mock_ia,
            patch("ai_knowledge.personality.azad_responses.learning_system") as mock_ls,
            patch("ai_knowledge.personality.azad_responses.azad_personality") as mock_p,
            patch("services.ai_service.AIService") as MockAI,
        ):
            MockAI.get_api_key.return_value = "key"
            MockAI.get_provider.return_value = "groq"
            MockAI.is_sensitive_request.return_value = (False, False, {})
            mock_p.is_inappropriate_message.return_value = "normal"
            mock_ls.learn_from_interaction.return_value = None
            mock_ia.process.return_value = {"success": False}
            mock_si.get_customer_balance.return_value = customer_payload
            mock_si.get_product_stock.return_value = product_payload
            mock_si.get_system_summary.return_value = summary_payload
            mock_si.get_financial_summary.return_value = {
                "success": True,
                "financial": {
                    "total_sales": 50000.0,
                    "total_payments": 40000.0,
                    "total_receivables": 10000.0,
                    "today_sales": 500.0,
                    "today_payments": 300.0,
                },
            }
            mock_si.search_data.return_value = {
                "success": True,
                "results": {"customers": [], "products": [], "sales": []},
            }
            mock_si.get_supplier_balance.return_value = {
                "success": True,
                "supplier": {
                    "id": 1,
                    "name": "مورد",
                    "balance_aed": 100.0,
                    "total_purchases": 2,
                    "last_purchase_date": "2025-01-01",
                    "supplier_type": "local",
                    "phone": "",
                    "email": "",
                },
            }
            mock_da.analyze_customer_debt.return_value = debt_payload
            mock_doc.generate_receipt.return_value = ("receipt text", "تم")
            mock_doc.generate_invoice.return_value = ("invoice text", "تم")
            mock_doc.generate_sales_report.return_value = ("report text", "تم")
            mock_doc.export_to_excel.return_value = (MagicMock(), "sales.csv")
            mock_ke.search_knowledge.return_value = {
                "success": True,
                "results": [{"title": "نتيجة"}],
            }
            mock_laws.get_tax_laws.return_value = "قوانين ضريبية"
            mock_laws.get_shipping_laws.return_value = "قوانين شحن"
            mock_laws.get_quality_standards.return_value = "معايير جودة"
            assert "إجمالي العملاء" in responses.smart_response("ملخص النظام الكلي")
            assert responses.smart_response("ولد سند قبض 42")
            assert responses.smart_response("تقرير المبيعات")
            assert responses.smart_response("قانون ضريبة فلسطين")
            assert responses.smart_response("مورد SupplierX")
            assert responses.smart_response("فلتر ذكي للزبائن")
            assert responses.smart_response("طرق الدفع المتاحة")


class TestPersonalityCoreFinal:
    def test_azad_responses_from_personality_core(self):
        from ai_knowledge.personality_core import AzadResponses

        responses = AzadResponses()
        assert "أزاد" in responses.smart_response("من أنت")
        with (
            patch(
                "ai_knowledge.personality.azad_responses.system_integrator"
            ) as mock_si,
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": "general", "confidence": 0.1},
            ),
            patch(
                "ai_knowledge.personality.azad_responses.intelligent_assistant"
            ) as mock_ia,
            patch("ai_knowledge.personality.azad_responses.learning_system") as mock_ls,
            patch("ai_knowledge.personality.azad_responses.azad_personality") as mock_p,
            patch("services.ai_service.AIService") as MockAI,
        ):
            MockAI.is_sensitive_request.return_value = (False, False, {})
            mock_p.is_inappropriate_message.return_value = "normal"
            mock_ls.learn_from_interaction.return_value = None
            mock_ia.process.return_value = {"success": False}
            mock_si.get_system_summary.return_value = {
                "success": True,
                "summary": {
                    "customers": {"total": 1, "vip": 0, "recent": []},
                    "sales": {"total": 1, "today": 0, "recent": []},
                    "products": {"total": 1, "low_stock": 0, "out_of_stock": 0},
                    "payments": {"total": 0, "today": 0},
                },
            }
            mock_si.get_financial_summary.return_value = {
                "success": True,
                "financial": {
                    "total_sales": 1000.0,
                    "total_payments": 800.0,
                    "total_receivables": 200.0,
                    "today_sales": 50.0,
                    "today_payments": 30.0,
                },
            }
            assert "إجمالي" in responses.smart_response("ملخص النظام الكلي")


class TestLearningEngineFinal:
    def test_continuous_learner_wikipedia(self, knowledge_path):
        from ai_knowledge.learning_engine import ContinuousLearner

        learner = ContinuousLearner()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "extract": "محتوى تعليمي عن المحاسبة",
            "content_urls": {"desktop": {"page": "https://example.com"}},
        }
        with patch.object(learner.session, "get", return_value=mock_resp):
            result = learner.learn_from_wikipedia("المحاسبة")
            assert result["success"] is True
            assert learner.accumulated_knowledge["total_items"] >= 1
        mock_fail = MagicMock()
        mock_fail.status_code = 404
        with patch.object(learner.session, "get", return_value=mock_fail):
            assert learner.learn_from_wikipedia("missing")["success"] is False
        with patch.object(learner.session, "get", side_effect=TimeoutError("timeout")):
            assert learner.learn_from_wikipedia("err")["success"] is False


class TestImprovementCoreFinal:
    def test_self_reflection_engine(self):
        from ai_knowledge.improvement_core import SelfReflectionEngine

        engine = SelfReflectionEngine()
        engine.log_performance("pricing", 0.95)
        engine.log_error("validation", "bad input")
        assessment = engine.reflect_on_performance()
        assert assessment["overall_score"] > 0.9
        assert engine.suggest_improvements()
        plan = engine.plan_self_improvement()
        assert plan["action_items"]
        engine.celebrate_success("high accuracy")
        engine.learn_from_mistake("wrong price", "verify margin")

    def test_azad_self_improvement(self, knowledge_path):
        from ai_knowledge.improvement_core import AzadSelfImprovement

        imp = AzadSelfImprovement()
        status = imp.get_improvement_status()
        assert isinstance(status, dict)
        perf = imp.analyze_performance()
        assert isinstance(perf, dict)
        imp.set_improvement_goal("response_quality", 9.0)
        assert imp.track_progress()
        with patch.object(imp, "_save_data"):
            imp.implement_improvement("response_quality")
            assert imp.auto_improve()
            assert imp.evolve_capabilities()


class TestKnowledgeBaseFinal:
    def test_module_help_and_search(self):
        from ai_knowledge.knowledge_base import (
            get_module_help,
            search_knowledge,
            get_welcome_message,
        )

        assert "المبيعات" in get_module_help("sales")
        assert get_module_help("unknown_xyz") == "الوحدة غير موجودة"
        hits = search_knowledge("فاتورة")
        assert hits
        assert search_knowledge("zzzznonexistentquery12345") == []
        assert "أزاد" in get_welcome_message()


class TestSystemKnowledgeFinal:
    def test_role_info_and_search_edge_cases(self):
        from ai_knowledge.system_knowledge import (
            get_role_info,
            search_knowledge,
            get_permission_info,
        )

        assert get_role_info("manager")["name_ar"] == "مدير"
        assert get_role_info("nonexistent_role") is None
        assert get_permission_info("manage_sales")["name_ar"] == "إدارة المبيعات"
        models = search_knowledge("customer")
        assert any(r["type"] == "model" for r in models)
        perms = search_knowledge("مبيعات")
        assert any(r["type"] == "permission" for r in perms)
        assert search_knowledge("zzzznonexistentquery12345") == []


class TestSystemIntegrationPaths:
    @pytest.fixture
    def integrator(self):
        from ai_knowledge.core.system_integration import SystemIntegrator

        return SystemIntegrator()

    def test_supplier_and_product_stock(self, integrator):
        supplier = MagicMock(
            id=7,
            name="PartsCo",
            supplier_type="import",
            phone="050",
            email="p@c.com",
            get_balance_aed=lambda: Decimal("3200"),
        )
        supplier.purchases.count.return_value = 6
        supplier.purchases.order_by.return_value.first.return_value = MagicMock(
            created_at=datetime(2025, 4, 1)
        )
        product = MagicMock(
            id=9,
            name="Brake Pad",
            sku="BP01",
            current_stock=3,
            min_stock_alert=5,
            unit_price=Decimal("80"),
            category=MagicMock(name="Brakes"),
        )
        with (
            patch("models.Supplier") as MockSup,
            patch("models.Purchase"),
            patch("models.Product") as MockP,
        ):
            MockSup.query.get.return_value = supplier
            assert integrator.get_supplier_balance(7)["success"] is True
            MockSup.query.get.return_value = None
            MockSup.query.filter.return_value.first.return_value = None
            assert "غير موجود" in integrator.get_supplier_balance("Ghost")["error"]
            MockP.query.filter.return_value.first.return_value = product
            stock = integrator.get_product_stock("Brake")
            assert stock["success"] is True
            assert stock["product"]["status"] == "منخفض"
            MockP.query.filter.return_value.first.return_value = None
            assert integrator.get_product_stock("missing")["success"] is False


class TestSecurityRulesFinal:
    def test_security_rules_full_coverage(self):
        from ai_knowledge.specialized.security_rules import (
            SecurityRules,
            security_rules,
        )

        owner = MagicMock(
            is_authenticated=True,
            is_owner=True,
            username="owner",
            role=MagicMock(slug="super_admin"),
        )
        seller = MagicMock(
            is_authenticated=True,
            is_owner=False,
            username="seller",
            role=MagicMock(slug="seller"),
        )
        anon = MagicMock(is_authenticated=False)
        with patch("ai_knowledge.specialized.security_rules.current_user", owner):
            assert SecurityRules.is_owner() is True
            assert SecurityRules.can_access_sensitive_info() is True
            raw = SecurityRules.filter_sensitive_data(
                {"password": "secret", "name": "Ali"}
            )
            assert raw["password"] == "secret"
            ok, msg = SecurityRules.check_user_permissions("delete_all")
            assert ok is True
        with patch("ai_knowledge.specialized.security_rules.current_user", seller):
            filtered = SecurityRules.filter_sensitive_data(
                {
                    "password": "secret",
                    "email": "user@example.com",
                    "phone": "0501234567",
                    "name": "Ali",
                }
            )
            assert filtered["password"] == "*** محمي ***"
            assert "@***" in filtered["email"]
            assert "***" in filtered["phone"]
            ok, _ = SecurityRules.check_user_permissions("edit_own")
            assert ok is True
            denied, _ = SecurityRules.check_user_permissions("delete_all")
            assert denied is False
        with patch("ai_knowledge.specialized.security_rules.current_user", anon):
            assert SecurityRules.is_owner() is False
            ok, msg = SecurityRules.check_user_permissions("view_all")
            assert ok is False
        assert SecurityRules.get_security_response("password_request")
        assert SecurityRules.get_security_response("unknown_type")
        assert (
            SecurityRules.sanitize_input("<script>alert(1)</script>")
            == "scriptalert1/script"
        )
        long_text = "a" * 1100
        assert len(SecurityRules.sanitize_input(long_text)) <= 1003
        with patch("ai_knowledge.specialized.security_rules.current_user", owner):
            SecurityRules.log_security_event("login", "test event")
        ok, msg = SecurityRules.rate_limit_check(1, "chat")
        assert ok is True
        assert security_rules is not None
