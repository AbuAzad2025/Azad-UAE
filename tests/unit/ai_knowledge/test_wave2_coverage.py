"""Wave 2 coverage push for consolidated modules and priority gaps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def knowledge_path(tmp_path):
    with patch(
        "ai_knowledge.get_knowledge_path", side_effect=lambda name: str(tmp_path / name)
    ):
        yield tmp_path


def _product_rows(count=25):
    rows = []
    for i in range(count):
        row = MagicMock()
        row.id = i + 1
        row.name = f"Product{i}"
        row.cost_price = Decimal("25")
        row.current_stock = Decimal("10")
        row.sales_count = 20 if i % 2 == 0 else 5
        row.total_sold = Decimal("100")
        row.last_sale_date = datetime.now(timezone.utc) - timedelta(days=7)
        rows.append(row)
    return rows


def _sale_rows(count=55):
    rows = []
    for i in range(count):
        row = MagicMock()
        row.cost_price = Decimal("50")
        row.unit_price = Decimal("75")
        row.quantity = Decimal("2")
        row.discount_percent = Decimal("0")
        row.customer_type = "regular"
        row.category_id = 1
        row.sale_date = datetime.now()
        row.payment_status = "paid"
        rows.append(row)
    return rows


class TestConsolidatedImports:
    def test_neural_network_reexports(self):
        import ai_knowledge.neural_network as nn

        assert nn.AzadNeuralEngine is not None
        assert nn.understand_message("فاتورة")["intent"]

    def test_personality_core_reexports(self):
        from ai_knowledge.personality_core import (
            AzadPersonality,
            AzadResponses,
            azad_responses,
        )

        assert AzadPersonality().get_greeting()
        assert azad_responses is not None
        assert AzadResponses.get_error_response()

    def test_core_engine_reexports(self):
        from ai_knowledge.core_engine import (
            ContextEngine,
            ReasoningEngine,
            get_memory_system,
        )

        assert ContextEngine.analyze_context("مرحبا")["intent"] == "greeting"
        assert ReasoningEngine().mathematical_reasoning("2+2")["result"] == 4
        assert get_memory_system() is not None

    def test_analytics_engine_reexports(self):
        from ai_knowledge.analytics_engine import SalesAnalytics, data_analyzer

        assert (
            SalesAnalytics.predict_next_month_sales([10, 20, 30, 40, 50, 60])[
                "prediction"
            ]
            > 0
        )
        assert data_analyzer is not None

    def test_learning_and_expansion_reexports(self):
        from ai_knowledge.learning_engine import (
            ContinuousLearner,
            QuickLearner,
            evaluate_and_learn,
        )
        from ai_knowledge.expansion_core import KnowledgeExpander, global_connector
        from ai_knowledge.generation_core import CodeGenerator
        from ai_knowledge.improvement_core import AzadSelfImprovement

        assert ContinuousLearner() is not None
        assert QuickLearner() is not None
        assert evaluate_and_learn([]) == []
        assert KnowledgeExpander() is not None
        assert global_connector is not None
        assert "SELECT" in CodeGenerator().generate_sql_query("select", "sales")
        assert isinstance(AzadSelfImprovement().get_improvement_status(), dict)


class TestAdvancedLawsWave2:
    def test_all_tax_branches(self):
        from ai_knowledge.specialized.advanced_laws import AdvancedLaws

        assert "16%" in AdvancedLaws.get_tax_info("palestine", "vat")
        assert "17%" in AdvancedLaws.get_tax_info("israel", "vat")
        assert "5%" in AdvancedLaws.get_tax_info("uae", "vat")
        assert "15%" in AdvancedLaws.get_tax_info("saudi", "vat")
        assert AdvancedLaws.get_tax_info("unknown", "vat") is None
        assert "ضريبة الشركات" in AdvancedLaws.get_tax_info("uae", "corporate")

    def test_shipping_customs_quality(self):
        from ai_knowledge.specialized.advanced_laws import AdvancedLaws

        assert "بحري" in AdvancedLaws.get_shipping_info("sea")
        assert "جوي" in AdvancedLaws.get_shipping_info("air")
        assert "بري" in AdvancedLaws.get_shipping_info("land")
        assert AdvancedLaws.get_shipping_info("unknown") == "نوع الشحن غير محدد"
        assert "الإمارات" in AdvancedLaws.get_customs_info("uae")
        assert "السعودية" in AdvancedLaws.get_customs_info("saudi")
        assert "ISO" in AdvancedLaws.get_quality_standards("unknown")
        assert "حلال" in AdvancedLaws.get_quality_standards("food")


class TestNeuralEngineTrainWave2:
    @staticmethod
    def _engine(knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        return AzadNeuralEngine()

    def test_train_maintenance_internal_success(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with (
            patch("extensions.db") as mock_db,
            patch("models.Product"),
            patch("models.Sale"),
            patch("models.SaleLine"),
            patch("models.StockMovement"),
        ):
            chain = (
                mock_db.session.query.return_value.outerjoin.return_value.outerjoin.return_value.group_by.return_value.limit.return_value
            )
            chain.all.return_value = _product_rows(25)
            result = engine._train_maintenance_internal()
            assert result["success"] is True

    def test_train_price_optimizer_public_api(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with patch.object(
            engine,
            "_train_price_internal",
            return_value={"success": True, "r2_score": 0.85},
        ) as inner:
            assert engine.train_price_optimizer()["success"] is True
            inner.assert_called_once()

    def test_train_maintenance_insufficient_data(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with (
            patch("extensions.db") as mock_db,
            patch("models.Product"),
            patch("models.Sale"),
            patch("models.SaleLine"),
            patch("models.StockMovement"),
        ):
            chain = (
                mock_db.session.query.return_value.outerjoin.return_value.outerjoin.return_value.group_by.return_value.limit.return_value
            )
            chain.all.return_value = _product_rows(5)
            result = engine._train_maintenance_internal()
            assert result["success"] is False

    def test_consolidated_neural_engine_paths(self, knowledge_path):
        from ai_knowledge.neural_network import AzadNeuralEngine, get_neural_engine

        engine = AzadNeuralEngine()
        with patch.object(engine, "_load_model", return_value=False):
            assert (
                engine.predict_optimal_price(80, 3, "partner")["predicted_price"] > 80
            )
            assert (
                engine.detect_fraud(
                    {"amount_aed": 5000, "discount_amount": 0, "subtotal": 5000}
                )["is_fraud"]
                is False
            )
        assert get_neural_engine() is get_neural_engine()


class TestAzadResponsesWave2:
    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses

        return AzadResponses()

    @pytest.fixture
    def safe_mocks(self):
        with (
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": "general", "confidence": 0.1},
            ),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch("services.ai_service.AIService.get_api_key", return_value=None),
            patch("services.ai_service.AIService.get_provider", return_value=None),
        ):
            yield

    @pytest.mark.parametrize(
        "message",
        [
            "مرحبا أزاد",
            "شكرا جزيلا",
            "نكتة مضحكة",
            "كيف أستخدم النظام",
            "ما هي ضريبة VAT في الإمارات",
            "قطعة محرك بستم",
            "خدمة العملاء للزبون",
            "مورد جديد للتوريد",
            "فلتر بحث المنتجات",
            "طريقة دفع كاش",
            "حلل المبيعات الشهرية",
            "تحسين الأداء والتعلم",
            "حالة النظام والأداء",
            "توقع المبيعات القادمة",
            "مخزون المنتجات منخفض",
            "هامش الربح الصافي",
            "دليل استخدام النظام",
            "سوق المنافسة والاستراتيجية",
            "رصيد العميل أحمد",
            "بيانات العميل علي",
            "مخزون منتج فلتر",
            "ملخص النظام الكلي",
            "أنشئ عميل جديد",
            "ابحث عن منتج زيت",
            "أضف موقع معرفة جديد",
            "روابط النظام",
            "مصادر موثوقة للتعلم",
            "أين أجد معلومات الضريبة",
            "ابحث في المعرفة عن الجمارك",
            "فاتورة بيع جديدة",
            "سند قبض جديد",
            "ولد فاتورة للعميل",
            "صدر بيانات المبيعات excel",
            "تقرير المبيعات الشهري",
            "قانون ضريبة فلسطين",
            "شحن بحري وقوانين التخليص",
            "معايير جودة الطعام",
        ],
    )
    def test_smart_response_keywords(self, responses, safe_mocks, message):
        assert isinstance(responses.smart_response(message), str)

    def test_analytical_intent_path(self, responses):
        with (
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": "sales_analysis", "confidence": 0.9},
            ),
            patch(
                "ai_knowledge.personality.azad_responses.intelligent_assistant"
            ) as ia,
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
        ):
            ia.process.return_value = {
                "success": True,
                "data_used": True,
                "response": "تحليل المبيعات",
            }
            assert "تحليل" in responses.smart_response("حلل المبيعات")

    def test_handler_methods(self, responses):
        summary_payload = {
            "success": True,
            "summary": {
                "customers": {
                    "total": 10,
                    "vip": 2,
                    "recent": [{"name": "Ali", "type": "vip", "balance": 100}],
                },
                "sales": {
                    "total": 100,
                    "today": 5,
                    "recent": [
                        {
                            "id": 1,
                            "customer": "Ali",
                            "amount": 500,
                            "date": "2025-06-01",
                        }
                    ],
                },
                "products": {"total": 50, "low_stock": 3, "out_of_stock": 1},
            },
        }
        financial_payload = {
            "success": True,
            "financial": {
                "total_sales": 10000,
                "total_payments": 8000,
                "total_receivables": 2000,
                "today_sales": 500,
                "today_payments": 300,
            },
        }
        with patch("ai_knowledge.personality.azad_responses.system_integrator") as si:
            si.get_system_summary.return_value = summary_payload
            si.get_financial_summary.return_value = financial_payload
            assert responses._handle_system_summary_query()
        assert responses._get_improvement_response("ما هي أهداف التحسين")
        assert responses._get_status_response()
        assert responses._quick_invoice_link()


class TestIntelligentAssistantWave2:
    @pytest.fixture
    def assistant(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        return IntelligentAssistant()

    def test_lazy_properties(self, assistant):
        assert assistant.quick_learner is not None
        assert assistant.neural_engine is not None
        assert assistant.reasoning_engine is not None
        assert assistant.data_analyzer is not None
        assert assistant.memory_system is not None
        assert assistant.context_engine is not None

    def test_full_sales_analysis_path(self, assistant, mock_ai_user):
        sale = MagicMock(
            id=1,
            total_amount=Decimal("500"),
            sale_date=datetime.now(),
            customer=MagicMock(name="Ali"),
        )
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.count.return_value = 3
        mock_q.all.return_value = [sale]
        with (
            patch(
                "ai_knowledge.learning.quick_learner.quick_learner.get_answer",
                return_value=None,
            ),
            patch(
                "ai_knowledge.neural.semantic_matcher.understand_message",
                return_value={"intent": "sales_analysis", "confidence": 0.9},
            ),
            patch("models.Sale") as MockSale,
            patch("models.Customer") as MockCustomer,
            patch("models.Product") as MockProduct,
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch("flask.has_request_context", return_value=True),
        ):
            MockSale.query = mock_q
            MockCustomer.query = mock_q
            MockProduct.query = mock_q
            result = assistant.process("حلل المبيعات", user_id=1, context={})
            assert result["success"] is True
            assert result["method"] == "intelligent_ai"

    def test_extract_entities_and_help(self, assistant):
        entities = assistant._extract_entities("العميل أحمد اشترى منتج فلتر زيت")
        assert isinstance(entities["names"], list)
        assert isinstance(entities["products"], list)
        help_resp = assistant._generate_help_response("سؤال غامض")
        assert "response" in help_resp

    def test_intelligent_response_function(self):
        from ai_knowledge.agents.intelligent_assistant import intelligent_response

        with patch(
            "ai_knowledge.agents.intelligent_assistant.intelligent_assistant.process",
            return_value={"response": "ok"},
        ):
            assert intelligent_response("test") == "ok"


class TestAgentsCoreWave2:
    def test_intelligent_response_help_action(self, mock_ai_user):
        from ai_knowledge.agents_core import intelligent_response

        with (
            patch(
                "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
                return_value=("help", {}),
            ),
            patch(
                "ai_knowledge.action_dispatcher.action_dispatcher.format_help",
                return_value="مساعدة",
            ),
        ):
            assert "مساعدة" in intelligent_response("مساعدة")

    def test_intelligent_response_greeting_action(self, mock_ai_user):
        from ai_knowledge.agents_core import intelligent_response

        with (
            patch(
                "ai_knowledge.action_dispatcher.action_dispatcher.parse_chat_action",
                return_value=("greeting", {"name": "Ali"}),
            ),
            patch(
                "ai_knowledge.action_dispatcher.action_dispatcher.format_help",
                return_value="help",
            ),
        ):
            assert "أزاد" in intelligent_response("مرحبا")

    def test_ask_azad_enhanced_faq(self):
        from ai_knowledge.agents_core import ask_azad_enhanced

        result = ask_azad_enhanced("كيف أنشئ فاتورة")
        assert result["answer"]
        assert result["source"] in (
            "faq",
            "system_knowledge",
            "master_brain",
            "llm",
            "local",
        )

    def test_check_llm_and_build_prompt(self):
        from ai_knowledge.agents_core import (
            _build_system_prompt,
            _check_llm_availability,
        )

        with patch.dict("os.environ", {}, clear=True):
            import ai_knowledge.agents_core as ac

            ac._llm_available = None
            assert _check_llm_availability() is False
        prompt = _build_system_prompt("كيف أضيف منتج", "manager")
        assert "أزاد" in prompt


class TestContinuousLearnerWave2:
    def test_evaluate_and_learn(self):
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn

        svc = MagicMock()
        svc.ask_genius.return_value = {"answer": "ضريبة 5% VAT في الإمارات"}
        mem = MagicMock()
        svc.get_learning_system.return_value = mem
        tests = [
            {
                "question": "ما الضريبة",
                "expected_keywords": ["5%", "vat"],
                "context": {},
            }
        ]
        results = evaluate_and_learn(tests, ai_service=svc)
        assert results[0]["success"] is True
        mem.learn_from_interaction.assert_called()

    def test_evaluate_and_learn_no_service(self):
        from ai_knowledge.learning.continuous_learner import evaluate_and_learn

        with patch("services.ai_service.AIService", None):
            assert evaluate_and_learn([{"question": "x"}], ai_service=None) == []

    def test_daily_routine(self, knowledge_path):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner

        learner = ContinuousLearner()
        with (
            patch.object(
                learner, "learn_from_wikipedia", return_value={"success": True}
            ),
            patch.object(
                learner,
                "learn_arxiv_papers",
                return_value={"success": True, "papers": 1},
            ),
        ):
            assert learner.daily_learning_routine()["items_learned"] >= 1


class TestCoreEngineLazyAttrs:
    def test_memory_and_conversation_singletons(self, knowledge_path):
        import ai_knowledge.core.memory_system as ms
        import ai_knowledge.core.conversation_manager as cm
        import ai_knowledge.core_engine as ce

        ms._memory_instance = None
        cm._conversation_manager_instance = None
        from ai_knowledge.core_engine import get_memory_system, get_conversation_manager

        assert get_memory_system() is ce.get_memory_system()
        assert get_conversation_manager() is ce.get_conversation_manager()
        assert ce._memory_instance is ms._memory_instance
