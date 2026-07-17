"""Deep branch coverage for ai_knowledge modules."""

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


class TestNeuralEngineDeep:
    def _engine(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        return AzadNeuralEngine()

    def test_validate_accounting_fallback_balanced(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with patch.object(engine, "_load_model", return_value=False):
            result = engine.validate_accounting_entry(100, 100, 2, "Sale")
            assert result["is_correct"] is True

    def test_validate_accounting_fallback_unbalanced(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with patch.object(engine, "_load_model", return_value=False):
            result = engine.validate_accounting_entry(100, 50, 2, "Sale")
            assert result["is_correct"] is False

    def _customer_row(self, total, days_ago=5):
        row = MagicMock()
        row.total_purchases = total
        row.sales_count = 8
        row.avg_order_value = 1200
        row.last_purchase = datetime.now(timezone.utc) - timedelta(days=days_ago)
        return row

    def test_classify_vip_fallback(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with (
            patch.object(engine, "_load_model", return_value=False),
            patch("extensions.db") as mock_db,
            patch("models.Customer"),
            patch("models.Sale"),
        ):
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = self._customer_row(
                150000
            )
            result = engine.classify_customer_intelligence(1)
            assert result["classification"] == "vip"

    def test_classify_premium_fallback(self, knowledge_path):
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
            result = engine.classify_customer_intelligence(2)
            assert result["classification"] == "premium"

    def test_classify_regular_stale(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with (
            patch.object(engine, "_load_model", return_value=False),
            patch("extensions.db") as mock_db,
            patch("models.Customer"),
            patch("models.Sale"),
        ):
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = self._customer_row(
                5000, days_ago=120
            )
            result = engine.classify_customer_intelligence(3)
            assert result["classification"] == "regular"
            assert any("خسارة" in r for r in result["recommendations"])

    def test_classify_new_customer(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with (
            patch("extensions.db") as mock_db,
            patch("models.Customer"),
            patch("models.Sale"),
        ):
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = None
            result = engine.classify_customer_intelligence(99)
            assert result["classification"] == "new"

    def test_classify_exception(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with patch.object(
            engine, "_classify_customer_internal", side_effect=RuntimeError("fail")
        ):
            assert engine.classify_customer_intelligence(1)["confidence"] == 0

    def _product_row(self, stock, min_alert, total_sold):
        row = MagicMock()
        row.current_stock = stock
        row.min_stock_alert = min_alert
        row.cost_price = Decimal("25")
        row.sales_count = 12
        row.total_sold = total_sold
        row.avg_quantity = 2
        return row

    def test_optimize_stock_high_urgency(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with (
            patch.object(engine, "_load_model", return_value=False),
            patch("extensions.db") as mock_db,
            patch("models.Product"),
            patch("models.SaleLine"),
        ):
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = self._product_row(
                3, 20, 60
            )
            result = engine.optimize_stock_level(1)
            assert result["urgency"] == "high"

    def test_optimize_stock_low_urgency(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with (
            patch.object(engine, "_load_model", return_value=False),
            patch("extensions.db") as mock_db,
            patch("models.Product"),
            patch("models.SaleLine"),
        ):
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = self._product_row(
                500, 10, 10
            )
            result = engine.optimize_stock_level(2)
            assert result["urgency"] == "low"

    def test_optimize_stock_missing_product(self, knowledge_path):
        engine = self._engine(knowledge_path)
        with (
            patch("extensions.db") as mock_db,
            patch("models.Product"),
            patch("models.SaleLine"),
        ):
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = None
            result = engine.optimize_stock_level(404)
            assert result["optimal_stock"] == 0

    def test_train_maintenance_mocked(self, knowledge_path):
        engine = self._engine(knowledge_path)
        payload = {"success": False, "error": "Not enough data", "samples": 3}
        with patch.object(engine, "_train_maintenance_internal", return_value=payload):
            assert engine.train_maintenance_prediction()["samples"] == 3

    def test_train_with_app_context(self, knowledge_path):
        engine = self._engine(knowledge_path)
        ctx = MagicMock()
        ctx.return_value.__enter__ = MagicMock(return_value=None)
        ctx.return_value.__exit__ = MagicMock(return_value=False)
        with patch.object(
            engine, "_train_maintenance_internal", return_value={"success": True}
        ) as inner:
            engine.train_maintenance_prediction(from_app_context=ctx)
            inner.assert_called_once()


class TestReasoningEngineDeep:
    @pytest.fixture
    def engine(self):
        from ai_knowledge.core.reasoning_engine import ReasoningEngine

        return ReasoningEngine()

    @pytest.mark.parametrize(
        "problem",
        [
            "مخزون المنتج منخفض",
            "توقع المبيعات القادمة",
            "قيد محاسبي جديد",
            "صيانة المحرك",
            "عميل مهم",
            "تسعير المنتج 500",
        ],
    )
    def test_think_problem_types(self, engine, problem):
        result = engine.think(
            problem, {"cost_price": 80, "customer_type": "vip", "quantity": 2}
        )
        assert result.get("solution") is not None or result.get("reasoning_steps")

    def test_business_reasoning(self, engine):
        result = engine.business_reasoning("خطة النمو", {"revenue": 50000})
        assert "swot" in result and len(result["recommendations"]) >= 3


class TestConversationStoreDeep:
    def _mem(self, value='{"topic":"sales"}', hours_ago=0):
        mem = MagicMock()
        mem.value = value
        mem.last_accessed = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        mem.created_at = mem.last_accessed
        mem.access_count = 1
        mem.is_active = True
        return mem

    def test_get_context_valid(self):
        from ai_knowledge.core.conversation_store import get_context

        mem = self._mem()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = mem
        with (
            patch("ai_knowledge.core.conversation_store.AiMemory") as MockMem,
            patch("ai_knowledge.core.conversation_store.db") as mock_db,
        ):
            MockMem.query = mock_q
            assert get_context(5, tenant_id=1)["topic"] == "sales"
            mock_db.session.flush.assert_called()

    def test_get_context_expired(self):
        from ai_knowledge.core.conversation_store import get_context

        mem = self._mem(hours_ago=5)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = mem
        with (
            patch("ai_knowledge.core.conversation_store.AiMemory") as MockMem,
            patch("ai_knowledge.core.conversation_store.db"),
        ):
            MockMem.query = mock_q
            assert get_context(6) is None
            assert mem.is_active is False

    def test_get_context_bad_json(self):
        from ai_knowledge.core.conversation_store import get_context

        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = self._mem(value="broken")
        with (
            patch("ai_knowledge.core.conversation_store.AiMemory") as MockMem,
            patch("ai_knowledge.core.conversation_store.db"),
        ):
            MockMem.query = mock_q
            assert get_context(7) is None

    def test_set_context_update(self):
        from ai_knowledge.core.conversation_store import set_context

        existing = MagicMock()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = existing
        with (
            patch("ai_knowledge.core.conversation_store.AiMemory") as MockMem,
            patch("ai_knowledge.core.conversation_store.db") as mock_db,
        ):
            MockMem.query = mock_q
            set_context(8, {"step": 2}, tenant_id=1)
            mock_db.session.add.assert_not_called()
            assert existing.is_active is True


class TestContextEngineEnhance:
    def test_enhance_analysis(self):
        from ai_knowledge.core.context_engine import ContextEngine

        with (
            patch("ai_knowledge.core.context_engine.data_analyzer") as mock_da,
            patch("ai_knowledge.core.context_engine.learning_system") as mock_ls,
        ):
            mock_da.get_financial_ratios.return_value = {
                "success": True,
                "ratios": {"gross_profit_margin": 30, "net_profit_margin": 12},
            }
            mock_ls.get_learning_insights.return_value = {"total_interactions": 0}
            out = ContextEngine.enhance_response("حلل الأرباح", "أساس", {})
            assert "هامش الربح" in out

    def test_enhance_data_query(self):
        from ai_knowledge.core.context_engine import ContextEngine

        with (
            patch("ai_knowledge.core.context_engine.system_integrator") as mock_si,
            patch("ai_knowledge.core.context_engine.learning_system") as mock_ls,
        ):
            mock_si.get_system_summary.return_value = {
                "success": True,
                "summary": {
                    "total_customers": 10,
                    "total_products": 5,
                    "today_sales": 2000,
                },
            }
            mock_ls.get_learning_insights.return_value = {}
            out = ContextEngine.enhance_response("كم عدد العملاء", "أساس", {})
            assert "حالة النظام" in out

    def test_enhance_prediction_create_search(self):
        from ai_knowledge.core.context_engine import ContextEngine

        with patch("ai_knowledge.core.context_engine.learning_system") as mock_ls:
            mock_ls.get_learning_insights.return_value = {}
            pred = ContextEngine.enhance_response("توقع المبيعات", "أساس", {})
            assert "توقع المبيعات" in pred
        with patch("ai_knowledge.core.context_engine.learning_system") as mock_ls:
            mock_ls.get_learning_insights.return_value = {}
            create = ContextEngine.enhance_response("أنشئ وثيقة", "أساس", {})
            assert "يمكنني إنشاء" in create
        with (
            patch("ai_knowledge.core.context_engine.knowledge_expander") as mock_ke,
            patch("ai_knowledge.core.context_engine.learning_system") as mock_ls,
        ):
            mock_ke.search_knowledge.return_value = {
                "success": True,
                "results": [{"title": "دليل الضريبة"}],
            }
            mock_ls.get_learning_insights.return_value = {
                "total_interactions": 20,
                "top_topics": [{"topic": "مبيعات"}],
            }
            search = ContextEngine.enhance_response("ابحث عن دليل النظام", "أساس", {})
            assert "دليل الضريبة" in search
            assert "خبرتي" in search


class TestSystemIntegrationDeep:
    @pytest.fixture
    def integrator(self):
        from ai_knowledge.core.system_integration import SystemIntegrator

        return SystemIntegrator()

    def test_financial_summary(self, integrator):
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

    def test_search_data_all_types(self, integrator):
        customer = MagicMock(
            id=1,
            name="Ali",
            customer_type="VIP",
            phone="050",
            get_balance_aed=lambda: Decimal("100"),
        )
        product = MagicMock(
            id=2, name="Filter", sku="F1", current_stock=5, unit_price=Decimal("50")
        )
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
            MockC.query.filter.return_value.limit.return_value.all.return_value = [
                customer
            ]
            MockP.query.filter.return_value.limit.return_value.all.return_value = [
                product
            ]
            MockS.query.join.return_value.filter.return_value.limit.return_value.all.return_value = [
                sale
            ]
            for dtype in ("all", "customers", "products", "sales"):
                result = integrator.search_data("Ali", dtype)
                assert result["success"] is True

    def test_get_product_stock(self, integrator):
        category = MagicMock(name="Filters")
        product = MagicMock(
            id=1,
            name="Oil",
            sku="O1",
            current_stock=2,
            min_stock_alert=10,
            unit_price=Decimal("40"),
            category=category,
        )
        with patch("models.Product") as MockP:
            MockP.query.filter.return_value.first.return_value = product
            result = integrator.get_product_stock("Oil")
            assert result["success"] is True
            assert result["product"]["status"] == "منخفض"


class TestDataAnalyzerDeep:
    def test_customer_debt_overdue(self):
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer

        customer = MagicMock(id=1, name="Debtor")
        sale = MagicMock(
            id=10,
            total_amount=Decimal("1000"),
            paid_amount=Decimal("100"),
            created_at=datetime.now() - timedelta(days=45),
        )
        with (
            patch("extensions.db") as mock_db,
            patch("models.Sale.query") as mock_sale_q,
        ):
            mock_db.session.get.return_value = customer
            mock_sale_q.filter.return_value.all.return_value = [sale]
            result = DataAnalyzer().analyze_customer_debt(1)
            assert result["success"] is True
            assert result["debt_analysis"]["overdue_count"] == 1

    def test_product_performance_single(self):
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer

        product = MagicMock(id=2, name="Piston", sku="P1", current_stock=20)
        line = MagicMock(
            quantity=4,
            line_total=Decimal("400"),
            unit_price=Decimal("100"),
            sale_id=5,
            sale=MagicMock(created_at=datetime.now()),
        )
        with (
            patch("models.Product") as MockP,
            patch("models.SaleLine") as MockSL,
            patch("models.Sale"),
        ):
            MockP.query.get.return_value = product
            MockSL.query.filter.return_value.all.return_value = [line]
            MockSL.query.filter.return_value.join.return_value.order_by.return_value.limit.return_value.all.return_value = [
                line
            ]
            result = DataAnalyzer().analyze_product_performance(product_id=2)
            assert result["performance"]["total_quantity_sold"] == 4

    def test_payment_patterns_and_ratios(self):
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer

        payment = MagicMock(payment_method="cash", amount=Decimal("500"))
        mock_db = MagicMock()
        mock_db.func.sum.return_value = MagicMock()
        mock_db.session.query.return_value.scalar.side_effect = [
            Decimal("2000"),
            Decimal("1500"),
        ]
        with (
            patch("extensions.db", mock_db),
            patch("models.Customer") as MockC,
            patch("models.Payment") as MockPay,
            patch("models.Sale"),
            patch("models.Product") as MockP,
        ):
            MockC.query.get.return_value = MagicMock(id=1)
            MockC.query.count.return_value = 5
            MockP.query.count.return_value = 12
            MockPay.query.filter.return_value.all.return_value = [payment]
            MockPay.query.all.return_value = [payment]
            assert DataAnalyzer().analyze_payment_patterns(1)["success"] is True
            ratios = DataAnalyzer().get_financial_ratios()
            assert ratios["success"] is True
            assert "collection_rate" in ratios["ratios"]


class TestCodeGeneratorDeep:
    @pytest.fixture
    def gen(self):
        from ai_knowledge.generation.code_generator import CodeGenerator

        return CodeGenerator()

    def test_sql_update(self, gen):
        sql = gen.generate_sql_query(
            "update", "products", {"set": {"price": "10"}, "where": {"id": "1"}}
        )
        assert "UPDATE products" in sql

    def test_fix_and_optimize(self, gen):
        fixed = gen.fix_code("print('x')", "SyntaxError: quote")
        assert fixed["confidence"] >= 0.3
        indent = gen.fix_code("def f():\nprint(1)", "IndentationError")
        assert "    " in indent["fixed_code"]
        name = gen.fix_code("db.add(x)", "NameError: name 'db' is not defined")
        assert "extensions" in name["fixed_code"]
        loop = (
            "items = []\nfor x in range(10):\n    items.append(x)\n"
            + "db.session.add(x)\n" * 6
        )
        opt = gen.optimize_code(loop + ".all()")
        assert opt["performance_gain_percent"] > 0

    def test_report_queries(self, gen):
        sales = gen.generate_report_query(
            "sales", {"start_date": "2025-01-01", "end_date": "2025-01-31"}
        )
        assert "SELECT" in sales
        assert "products" in gen.generate_report_query("inventory").lower()
        assert "customers" in gen.generate_report_query("customers").lower()
        assert "Unknown" in gen.generate_report_query("other")


class TestSelfReflectionDeep:
    def test_celebrate_and_plan(self):
        from ai_knowledge.improvement.self_reflection import SelfReflectionEngine

        engine = SelfReflectionEngine()
        engine.log_performance("forecast", 0.6)
        engine.log_error("timeout", "slow")
        engine.celebrate_success("accuracy milestone")
        plan = engine.plan_self_improvement()
        assert plan["action_items"]
        assert any(e["type"] == "success" for e in engine.improvements_log)


class TestSelfImprovementDeep:
    def test_auto_track_evolve(self, knowledge_path):
        from ai_knowledge.improvement.self_improvement import AzadSelfImprovement

        ai = AzadSelfImprovement()
        ai.improvement_areas["prediction_accuracy"]["current_score"] = 6.0
        auto = ai.auto_improve()
        assert auto["improvements_made"] >= 0
        progress = ai.track_progress()
        assert "area_progress" in progress
        evolution = ai.evolve_capabilities()
        assert "enhanced_capabilities" in evolution


class TestQuickLearnerDeep:
    def test_get_answer_modes(self):
        from ai_knowledge.learning.quick_learner import QuickLearner

        exact = MagicMock(key="vat rate", value="5%", access_count=0)
        partial = MagicMock(key="invoice help", value="steps", access_count=0)
        fuzzy = MagicMock(key="inventory status", value="ok", access_count=0)
        existing = MagicMock()
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.side_effect = [[exact], [partial], [fuzzy]]
        with patch("models.ai.AiMemory") as MockMem, patch("extensions.db") as mock_db:
            MockMem.query = mock_q
            mock_db.or_.return_value = MagicMock()
            learner = QuickLearner()
            assert learner.get_answer("vat rate") == "5%"
            assert learner.get_answer("need invoice help now") == "steps"
            assert learner.get_answer("inventry status") == "ok"

    def test_learn_update_existing(self):
        from ai_knowledge.learning.quick_learner import QuickLearner

        existing = MagicMock()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = existing
        with patch("models.ai.AiMemory") as MockMem, patch("extensions.db") as mock_db:
            MockMem.query = mock_q
            assert QuickLearner().learn("question", "new answer") is True
            mock_db.session.add.assert_not_called()
            assert existing.value == "new answer"


class TestAzadPersonalityDeep:
    @pytest.mark.parametrize(
        "getter,expected",
        [
            ("get_greeting", "مرحبا"),
            ("get_positive_response", "نعم"),
            ("get_success_response", "تم"),
            ("get_silly_response", "ههه"),
            ("get_inappropriate_response", "محترف"),
            ("get_insult_response", "احترام"),
            ("get_professional_joke", "محاسب"),
            ("get_encouragement", "رائع"),
            ("get_help_intro", "سرور"),
            ("get_thanks_response", "العفو"),
        ],
    )
    def test_all_getters(self, getter, expected):
        from ai_knowledge.personality.azad_personality import AzadPersonality

        with patch("secrets.choice", return_value=expected):
            assert expected in getattr(AzadPersonality, getter)()

    @pytest.mark.parametrize(
        "mood,emoji",
        [
            ("happy", "😊"),
            ("excited", "🚀"),
            ("proud", "🌟"),
            ("smart", "💡"),
            ("love", "💚"),
            ("other", "😄"),
        ],
    )
    def test_all_moods(self, mood, emoji):
        from ai_knowledge.personality.azad_personality import AzadPersonality

        assert emoji in AzadPersonality.add_personality_to_response("ok", mood)


class TestSecurityRulesDeep:
    def test_permissions_matrix(self):
        from ai_knowledge.specialized.security_rules import SecurityRules

        anon = MagicMock(is_authenticated=False)
        with patch("ai_knowledge.specialized.security_rules.current_user", anon):
            ok, msg = SecurityRules.check_user_permissions("view_all")
            assert ok is False
        owner = MagicMock(is_authenticated=True, is_owner=True)
        with patch("ai_knowledge.specialized.security_rules.current_user", owner):
            ok, msg = SecurityRules.check_user_permissions("delete_all")
            assert ok is True
        seller = MagicMock(
            is_authenticated=True, is_owner=False, role=MagicMock(slug="seller")
        )
        with patch("ai_knowledge.specialized.security_rules.current_user", seller):
            ok, _ = SecurityRules.check_user_permissions("edit_own")
            assert ok is True
            denied, _ = SecurityRules.check_user_permissions("delete_all")
            assert denied is False

    def test_rate_limit_and_filter(self):
        from ai_knowledge.specialized.security_rules import SecurityRules

        ok, msg = SecurityRules.rate_limit_check(1, "chat")
        assert ok is True
        user = MagicMock(is_authenticated=True, is_owner=False)
        with (
            patch("ai_knowledge.specialized.security_rules.current_user", user),
            patch.object(
                SecurityRules, "can_access_sensitive_info", return_value=False
            ),
        ):
            filtered = SecurityRules.filter_sensitive_data(
                {
                    "email": "user@example.com",
                    "phone": "0501234567",
                    "name": "Ali",
                }
            )
            assert "@***" in filtered["email"]
            assert "***" in filtered["phone"]
            assert filtered["name"] == "Ali"
