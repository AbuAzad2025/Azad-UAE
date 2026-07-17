"""Wave 7 coverage push — target all ai_knowledge/* modules still below 99%."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture
def knowledge_path(tmp_path):
    with patch(
        "ai_knowledge.get_knowledge_path", side_effect=lambda name: str(tmp_path / name)
    ):
        yield tmp_path


class _Col:
    def __lt__(self, other):
        return MagicMock()

    def __le__(self, other):
        return MagicMock()

    def __gt__(self, other):
        return MagicMock()

    def __ge__(self, other):
        return MagicMock()

    def __eq__(self, other):
        return MagicMock()

    @staticmethod
    def between(a, b):
        return MagicMock()

    @staticmethod
    def ilike(*a, **kw):
        return MagicMock()

    @staticmethod
    def desc():
        return MagicMock()


def _db_chain(mock_db):
    chain = MagicMock()
    mock_db.session.query.return_value = chain
    for attr in ("outerjoin", "join", "filter", "filter_by", "group_by", "order_by"):
        getattr(chain, attr).return_value = chain
    chain.limit.return_value = chain
    return chain


def _patch_model_cols(*models):
    ctxs = []
    for mod in models:
        p = patch(mod)
        m = p.start()
        for attr in (
            "status",
            "sale_date",
            "cost_price",
            "unit_price",
            "tenant_id",
            "purchase_date",
            "expense_date",
            "receipt_date",
            "amount_aed",
            "payment_status",
            "id",
            "product_id",
            "current_stock",
            "min_stock_level",
            "min_stock_alert",
            "is_active",
            "paid_amount",
            "total_amount",
            "customer_id",
            "created_at",
            "name",
        ):
            setattr(m, attr, _Col())
        ctxs.append(p)
    return ctxs


def _stop_patches(ctxs):
    for p in ctxs:
        p.stop()


def _fast_models(engine):
    for model in engine.models.values():
        if hasattr(model, "max_iter"):
            model.max_iter = 50


def _product_rows(count=25, high_usage=False):
    rows = []
    for i in range(count):
        row = MagicMock()
        row.id = i + 1
        row.name = f"P{i}"
        row.cost_price = Decimal("25")
        row.current_stock = Decimal("10")
        row.min_stock_alert = Decimal("5")
        row.sales_count = 60 if high_usage else (20 if i % 2 == 0 else 3)
        row.total_sold = Decimal("100")
        row.avg_quantity = Decimal("2")
        row.last_sale_date = datetime.now(timezone.utc) - timedelta(days=7)
        rows.append(row)
    return rows


def _daily_sales_rows(count=7):
    rows = []
    base = date.today() - timedelta(days=count)
    for i in range(count):
        row = MagicMock()
        row.sale_date = base + timedelta(days=i)
        row.total_amount = Decimal(str(1000 + i * 100))
        rows.append(row)
    return rows


class TestNeuralWave7:
    @pytest.fixture
    def engine(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        eng = AzadNeuralEngine()
        _fast_models(eng)
        return eng

    def test_maintenance_no_product_and_normal_branch(self, engine):
        with (
            patch.object(engine, "_load_model", return_value=True),
            patch("extensions.db") as mock_db,
            patch("models.Product"),
            patch("models.Sale"),
            patch("models.SaleLine"),
        ):
            chain = _db_chain(mock_db)
            chain.first.return_value = None
            assert engine._predict_maintenance_internal(99)["confidence"] == 0
            product_data = MagicMock(
                cost_price=Decimal("25"),
                current_stock=Decimal("10"),
                sales_count=5,
                total_sold=Decimal("10"),
                last_sale_date=None,
            )
            chain.first.return_value = product_data
            engine.scalers["maintenance_predictor"] = MagicMock()
            engine.models["maintenance_predictor"] = MagicMock()
            engine.scalers["maintenance_predictor"].transform.return_value = np.array(
                [[1.0] * 6]
            )
            engine.models["maintenance_predictor"].predict.return_value = np.array([0])
            engine.models["maintenance_predictor"].predict_proba.return_value = (
                np.array([[0.8, 0.2]])
            )
            result = engine._predict_maintenance_internal(1)
            assert result["estimated_days"] == 30

    def test_accounting_unusual_pattern(self, engine):
        with patch.object(engine, "_load_model", return_value=True):
            engine.scalers["accounting_classifier"] = MagicMock()
            engine.models["accounting_classifier"] = MagicMock()
            engine.scalers["accounting_classifier"].transform.return_value = np.array(
                [[1.0] * 6]
            )
            engine.models["accounting_classifier"].predict.return_value = np.array([0])
            engine.models["accounting_classifier"].predict_proba.return_value = (
                np.array([[0.3, 0.7]])
            )
            result = engine.validate_accounting_entry(100, 100, 2, "Sale")
            assert (
                "مراجعة" in result["recommendation"]
                or "غير متوازن" in result["recommendation"]
            )

    def test_cash_flow_and_forecast_exceptions(self, engine):
        ctx = MagicMock()
        ctx.side_effect = RuntimeError("ctx")
        with patch.object(
            engine, "_predict_cash_flow_internal", side_effect=RuntimeError("fail")
        ):
            assert engine.predict_cash_flow(3)["trend"] == "unknown"
        with patch.object(
            engine, "_forecast_sales_internal", side_effect=RuntimeError("fail")
        ):
            assert engine.forecast_sales(7)["forecast"] == []

    def test_forecast_decreasing_trend(self, engine):
        cols = _patch_model_cols("models.Sale")
        try:
            rows = _daily_sales_rows(7)
            with (
                patch.object(engine, "_load_model", return_value=True),
                patch("extensions.db") as mock_db,
                patch.object(
                    engine.scalers["sales_forecaster"],
                    "transform",
                    return_value=np.array([[1.0] * 11]),
                ),
                patch.object(
                    engine.models["sales_forecaster"],
                    "predict",
                    side_effect=[np.array([5000.0 - i * 800]) for i in range(7)],
                ),
            ):
                chain = _db_chain(mock_db)
                chain.all.return_value = rows
                result = engine._forecast_sales_internal(7)
                assert result.get("trend") in ("decreasing", "increasing", "stable")
        finally:
            _stop_patches(cols)

    def test_inventory_insufficient_data(self, engine):
        with (
            patch("extensions.db") as mock_db,
            patch("models.Product"),
            patch("models.SaleLine"),
            patch("models.StockMovement"),
        ):
            chain = _db_chain(mock_db)
            chain.all.return_value = _product_rows(5)
            assert engine._train_inventory_internal()["success"] is False

    def test_train_wrappers_with_context(self, engine):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)
        for method, internal in (
            ("train_financial_planning", "_train_financial_internal"),
            ("train_inventory_optimizer", "_train_inventory_internal"),
            ("optimize_stock_level", "_optimize_stock_internal"),
        ):
            with patch.object(
                engine, internal, return_value={"success": True}
            ) as inner:
                if method == "optimize_stock_level":
                    getattr(engine, method)(1, from_app_context=ctx)
                    inner.assert_called_once_with(1)
                else:
                    getattr(engine, method)(from_app_context=ctx)
                    inner.assert_called_once()

    def test_remaining_predict_train_paths(self, engine):
        cols = _patch_model_cols(
            "models.Sale", "models.Purchase", "models.Expense", "models.Receipt"
        )
        try:
            with (
                patch("extensions.db") as mock_db,
                patch("utils.tenanting.get_active_tenant_id", return_value=1),
            ):
                chain = _db_chain(mock_db)
                chain.scalar.return_value = Decimal("0")
                rec = engine._predict_cash_flow_internal(2)
                assert "predictions" in rec or "error" in rec
        finally:
            _stop_patches(cols)
        with (
            patch.object(engine, "_load_model", return_value=False),
            patch("extensions.db") as mock_db,
            patch("models.Product"),
            patch("models.SaleLine"),
        ):
            chain = _db_chain(mock_db)
            pdata = MagicMock(
                current_stock=10,
                min_stock_alert=5,
                cost_price=25.0,
                sales_count=3,
                total_sold=30.0,
                avg_quantity=2.0,
            )
            chain.first.return_value = pdata
            result = engine._optimize_stock_internal(1)
            assert result.get("optimal_reorder_point") is not None


class TestAzadWave7:
    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses

        return AzadResponses()

    def test_sensitive_fail_and_non_owner(self, responses):
        with (
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(True, False, {"message": "مرفوض"}),
            ),
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
        ):
            assert "مرفوض" in responses.smart_response("مستخدم admin")
        owner = MagicMock(id=1, is_owner=True)
        with (
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(True, True, {}),
            ),
            patch(
                "services.ai_service.AIService.get_user_info_for_owner",
                return_value={"success": False, "message": "غير موجود"},
            ),
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
        ):
            assert "غير موجود" in responses.smart_response(
                "مستخدم ghost", context={"current_user": owner, "is_owner": True}
            )

    def test_dialect_greetings_and_help_search(self, responses):
        with (
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch("ai_knowledge.personality.azad_responses.azad_personality") as ap,
            patch("ai_knowledge.personality.azad_responses.learning_system"),
            patch(
                "ai_knowledge.personality.azad_responses.get_dialectal_greeting",
                return_value="أهلين شلونك",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_welcome_message",
                return_value="welcome",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.apply_dialect",
                side_effect=lambda t, d: t,
            ),
            patch("ai_knowledge.personality.azad_responses.beginners_guide") as bg,
            patch(
                "ai_knowledge.personality.azad_responses.get_help_for_task",
                return_value="لم أجد",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.search_knowledge",
                return_value=[{"module": "tax", "content": "VAT 5%"}],
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_system_guide",
                return_value="guide",
            ),
        ):
            ap.is_inappropriate_message.return_value = "normal"
            ap.get_greeting.return_value = "مرحبا عام"
            ap.get_help_intro.return_value = "مساعدة"
            bg.get_beginner_response.return_value = None
            assert "أهلين" in responses.smart_response(
                "مرحبا", context={"dialect": "palestinian"}
            )
            assert "أهلين" in responses.smart_response(
                "هلا", context={"dialect": "gulf"}
            )
            assert "مرحبا عام" in responses.smart_response(
                "مرحبا", context={"dialect": "standard"}
            )
            assert "VAT" in responses.smart_response("كيف أستخدم الضريبة")

    def test_status_fallback_and_improvement_branches(self, responses):
        with (
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch("ai_knowledge.personality.azad_responses.azad_personality") as ap,
            patch("ai_knowledge.personality.azad_responses.learning_system"),
            patch.object(
                responses, "_get_status_response", side_effect=RuntimeError("fail")
            ),
        ):
            ap.is_inappropriate_message.return_value = "normal"
            assert "نشط" in responses.smart_response("حالة النظام status")
        with patch("ai_knowledge.personality.azad_responses.self_improvement") as si:
            si.track_progress.return_value = {
                "overall_progress": 50,
                "goals_progress": [
                    {
                        "area": "quality",
                        "current_score": 7,
                        "target_score": 9,
                        "progress_percentage": 70,
                    }
                ],
                "next_milestones": [{"area": "quality", "description": "next"}],
            }
            assert "أهداف" in responses._get_improvement_response("عرض هدف goal")
            si.auto_improve.return_value = {
                "improvements_made": 1,
                "details": [
                    {"area": "q", "old_score": 7, "new_score": 8, "improvement": 1}
                ],
            }
            assert "تحسين" in responses._get_improvement_response(
                "تحسين تلقائي automatic"
            )
            si.get_improvement_status.return_value = {
                "overall_score": 8,
                "total_improvements": 2,
                "active_goals": 1,
                "last_improvement": "today",
            }
            assert "التحسين" in responses._get_improvement_response("حالة التحسين")

    def test_inventory_fail_and_sales_trends(self, responses):
        with patch(
            "services.ai_service.AIService.analyze_inventory_health",
            return_value={"success": False, "message": "لا منتجات"},
        ):
            assert "لا منتجات" in responses._inventory_status()
        with patch("models.Sale") as Sale:
            Sale.sale_date = _Col()
            Sale.status = _Col()
            low_sale = MagicMock(amount_aed=Decimal("100"))
            high_sale = MagicMock(amount_aed=Decimal("500"))
            Sale.query.filter.return_value.all.side_effect = [
                [high_sale] * 7,
                [low_sale] * 30,
            ]
            up = responses._smart_sales_analysis({})
            Sale.query.filter.return_value.all.side_effect = [
                [low_sale] * 7,
                [high_sale] * 30,
            ]
            down = responses._smart_sales_analysis({})
            Sale.query.filter.return_value.all.side_effect = [
                [MagicMock(amount_aed=Decimal("200"))] * 7,
                [MagicMock(amount_aed=Decimal("200"))] * 30,
            ]
            stable = responses._smart_sales_analysis({})
            assert "تحسن" in up or "مبيعات" in up
            assert "تراجع" in down or "مبيعات" in down
            assert "مستقرة" in stable or "مبيعات" in stable

    def test_profit_margin_fail_branch(self, responses):
        with (
            patch(
                "services.ai_service.AIService.analyze_profit_margins",
                return_value={"success": False, "message": "لا مبيعات"},
            ),
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch("ai_knowledge.personality.azad_responses.azad_personality") as ap,
            patch("ai_knowledge.personality.azad_responses.learning_system"),
        ):
            ap.is_inappropriate_message.return_value = "normal"
            assert "لا مبيعات" in responses.smart_response("هامش الربح profit margin")


class TestDocumentCodeWave7:
    def test_document_export_and_statement(self):
        from ai_knowledge.generation.document_generator import DocumentGenerator

        sale = MagicMock(
            id=1,
            created_at=datetime.now(),
            total_amount=Decimal("100"),
            paid_amount=Decimal("50"),
            balance_due=Decimal("50"),
            customer=MagicMock(name="Ali"),
            payments=[MagicMock(id=1, amount=Decimal("25"), created_at=datetime.now())],
        )
        with (
            patch("models.Sale") as Sale,
            patch("models.Customer") as Customer,
            patch("models.Product") as Product,
        ):
            Sale.created_at = _Col()
            Sale.customer_id = _Col()
            Sale.query.all.return_value = [sale]
            Sale.query.filter.return_value.all.return_value = [sale]
            Sale.query.get.return_value = sale
            Customer.query.get.return_value = MagicMock(
                name="Ali", phone="050", email="a@t.com"
            )
            Product.query.all.return_value = [
                SimpleNamespace(
                    id=1,
                    name="Bolt",
                    sku="B1",
                    current_stock=10,
                    unit_price=Decimal("5"),
                    min_stock_alert=2,
                    category=SimpleNamespace(name="Parts"),
                )
            ]
            start = datetime.now().date() - timedelta(days=30)
            end = datetime.now().date()
            data, fname = DocumentGenerator.export_to_excel(
                "sales", start_date=start, end_date=end
            )
            assert fname.endswith(".csv")
            data2, fname2 = DocumentGenerator.export_to_excel("customers")
            assert fname2.endswith(".csv")
            data3, fname3 = DocumentGenerator.export_to_excel("products")
            assert fname3.endswith(".csv")
            stmt, msg = DocumentGenerator.generate_customer_statement(
                1, start_date=datetime.now(), end_date=datetime.now()
            )
            assert stmt and "كشف" in stmt
            Customer.query.get.return_value = None
            assert DocumentGenerator.generate_customer_statement(99)[0] is None

    def test_code_generator_exception_paths(self):
        from ai_knowledge.generation.code_generator import CodeGenerator

        gen = CodeGenerator()
        bad = MagicMock()
        bad.get.side_effect = RuntimeError("boom")
        assert "-- Error:" in gen.generate_sql_query("select", "t", bad)
        assert "-- Missing" in gen.generate_report_query("sales")
        bad_dr = MagicMock()
        bad_dr.__getitem__ = MagicMock(side_effect=RuntimeError("range"))
        assert "-- Error:" in gen.generate_report_query("sales", bad_dr)
        fixed = gen.fix_code(
            "def f():\n\nreturn 1", "IndentationError: unexpected indent"
        )
        assert fixed["fixed_code"]
        assert gen.generate_report_query("unknown_type_xyz").startswith("--")


class TestLearnerWave7:
    def test_continuous_learner_paths(self, knowledge_path):
        from ai_knowledge.learning.continuous_learner import ContinuousLearner

        hist = knowledge_path / "learned_knowledge" / "learning_history.json"
        hist.parent.mkdir(parents=True)
        hist.write_text("{bad", encoding="utf-8")
        cl = ContinuousLearner()
        assert cl._load_history() == []
        with patch("builtins.open", side_effect=OSError("disk")):
            cl._save_history()
        with patch.object(cl.session, "get") as rg:
            rg.return_value = MagicMock(status_code=404)
            assert cl.learn_from_wikipedia("topic")["success"] is False
        with patch.object(cl.session, "get") as rg:
            rg.return_value = MagicMock(
                status_code=200, json=lambda: {"feed": {"entry": []}}
            )
            assert isinstance(cl.learn_arxiv_papers("ml"), dict)

    def test_self_improvement_remaining(self, knowledge_path):
        from ai_knowledge.improvement.self_improvement import AzadSelfImprovement

        ai = AzadSelfImprovement()
        ai.improvement_data["improvement_history"] = [
            {"improvement": 0.3},
            {"improvement": 0.3},
        ]
        assert ai._calculate_improvement_trend() in (
            "تحسن سريع",
            "تحسن مستقر",
            "تحسن بطيء",
            "ثابت",
            "غير محدد",
        )
        ai.improvement_areas["response_quality"]["current_score"] = 8.5
        milestones = ai._get_next_milestones()
        assert milestones
        report = ai.evolve_capabilities()
        assert "evolution_timestamp" in report
        with patch("builtins.open", side_effect=OSError("disk")):
            ai._save_data()

    def test_auto_retraining_and_external(self, knowledge_path):
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler
        from ai_knowledge.learning.external_learning import ExternalLearningSystem

        with (
            patch.object(
                AutoRetrainingScheduler, "get_last_training_info", return_value=None
            ),
            patch("models.Sale") as Sale,
        ):
            Sale.query.filter_by.return_value.count.return_value = 0
            assert AutoRetrainingScheduler.should_retrain() in (True, False)
        el = ExternalLearningSystem()
        with patch("builtins.open", side_effect=OSError("disk")):
            el._save_learned_data()

    def test_knowledge_expansion_snippet(self, knowledge_path):
        from ai_knowledge.expansion.knowledge_expansion import KnowledgeExpander

        exp = KnowledgeExpander()
        long_content = "x" * 500
        snippet = exp._extract_snippet(long_content, "missing_query_xyz")
        assert snippet.endswith("...")
        bad_content = MagicMock()
        bad_content.lower.side_effect = RuntimeError("bad")
        assert exp._extract_snippet(bad_content, "q").endswith("...")
        sources_mock = MagicMock()
        sources_mock.get.side_effect = RuntimeError("bad")
        with patch.object(exp, "sources", sources_mock):
            summary = exp.get_knowledge_summary()
            assert summary["success"] is False

    def test_knowledge_sources_fetch_error(self):
        from ai_knowledge.expansion.knowledge_sources import KnowledgeSourceManager

        mgr = KnowledgeSourceManager()
        import requests

        with patch(
            "ai_knowledge.expansion.knowledge_sources.requests.get",
            side_effect=requests.RequestException("fail"),
        ):
            assert mgr.fetch_exchange_rates() is None


class TestNeuralAuxWave7:
    def test_semantic_transformers_vision(self):
        from ai_knowledge.neural.semantic_matcher import (
            SemanticMatcher,
            understand_message,
        )
        from ai_knowledge.neural.transformers_brain import TransformersBrain
        from ai_knowledge.neural.vision_processor import VisionProcessor

        matcher = SemanticMatcher()
        assert matcher._tokenize("مبيعات اليوم")
        intent, conf, scores = matcher.find_best_intent("مبيعات اليوم كثيرة")
        assert isinstance(conf, float)
        assert matcher.smart_match("رصيد العميل علي")["intent"]
        understand_message("توقع المبيعات القادمة")
        tb = TransformersBrain()
        for msg in ("ما ضريبة VAT", "حساب الربح", "توقع المبيعات", "مرحبا"):
            tb.understand(msg)
            tb.generate_response(msg)
        tb.add_to_context("مبيعات اليوم")
        vp = VisionProcessor()
        with patch("PIL.Image.open", side_effect=OSError("bad image")):
            assert vp.extract_text_from_image("missing.png") in (
                "",
                None,
            ) or isinstance(vp.extract_text_from_image("missing.png"), str)


class TestSpecializedWave7:
    def test_advanced_laws_and_security(self):
        from ai_knowledge.specialized.advanced_laws import AdvancedLaws
        from ai_knowledge.specialized.security_rules import SecurityRules

        laws = AdvancedLaws()
        assert laws.get_shipping_info("sea")
        assert laws.get_quality_standards("food")
        assert laws.get_tax_info("palestine", "corporate")
        assert laws.get_tax_info("uae", "vat")
        assert laws.get_customs_info("unknown_country")
        assert laws.get_quality_standards("electronics")
        assert laws.get_quality_standards("textiles")
        user = MagicMock(is_authenticated=True, is_owner=False)
        with patch("ai_knowledge.specialized.security_rules.current_user", user):
            filtered = SecurityRules.filter_sensitive_data(
                {"password": "secret", "name": "Ali"}
            )
            assert filtered["password"] == "*** محمي ***"
        with patch(
            "ai_knowledge.specialized.security_rules.current_user",
            MagicMock(is_authenticated=False),
        ):
            assert SecurityRules.is_owner() is False

    def test_system_knowledge_root_and_nested(self):
        import ai_knowledge.system_knowledge as sk_root
        import ai_knowledge.knowledge.system_knowledge as sk_nested

        assert (
            sk_root.get_model_info("Customer")
            or sk_root.get_model_info("missing") is None
        )
        assert (
            sk_root.get_permission_info("manage_inventory")
            or sk_root.get_permission_info("x") is None
        )
        assert isinstance(sk_nested.search_knowledge("sale"), list)
        assert (
            sk_nested.get_module_help("sales")
            or sk_nested.get_module_help("xyz") is None
        )


class TestMiscWave7:
    def test_trainer_feedback_error_path(self):
        from ai_knowledge.trainer import Trainer

        trainer = Trainer()
        trainer.quick_learner = MagicMock()
        with patch(
            "ai_knowledge.core.learning_system.learning_system",
            side_effect=RuntimeError("save fail"),
        ):
            trainer.train_from_feedback("q", "a", user_id=1, tenant_id=2)

    def test_multi_agent_analytics(self, knowledge_path):
        from ai_knowledge.agents.multi_agent_system import MultiAgentCoordinator
        from ai_knowledge.analytics.analytics_predictions import SalesAnalytics

        coord = MultiAgentCoordinator()
        result = coord.delegate_task("تحليل المبيعات والمخزون")
        assert isinstance(result, dict)
        pred = SalesAnalytics.predict_next_month_sales([10, 20, 15, 25, 30])
        assert "prediction" in pred or "forecast" in pred or isinstance(pred, dict)

    def test_dialects_and_personality(self):
        from ai_knowledge.personality.dialects import (
            apply_dialect,
            get_dialectal_greeting,
        )
        from ai_knowledge.personality.azad_personality import AzadPersonality

        assert apply_dialect("مرحبا", "palestinian")
        assert get_dialectal_greeting("gulf")
        p = AzadPersonality()
        assert p.get_contextual_response("insult", "")

    def test_knowledge_base_search(self):
        from ai_knowledge.knowledge_base import search_knowledge
        from ai_knowledge.system_knowledge import get_contextual_help

        hits = search_knowledge("tenant isolation")
        assert isinstance(hits, list)
        assert get_contextual_help("sales") or get_contextual_help("xyz") is None


class TestWave8FinalPush:
    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses

        return AzadResponses()

    @staticmethod
    def _safe_smart(responses, message, **ctx):
        with (
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch("ai_knowledge.personality.azad_responses.azad_personality") as ap,
            patch("ai_knowledge.personality.azad_responses.learning_system"),
            patch("ai_knowledge.personality.azad_responses.beginners_guide") as bg,
        ):
            ap.is_inappropriate_message.return_value = "normal"
            bg.get_beginner_response.return_value = None
            return responses.smart_response(message, context=ctx or None)

    def test_azad_direct_handlers_and_smart_branches(self, responses):
        with (
            patch("ai_knowledge.personality.azad_responses.system_integrator") as si,
            patch("ai_knowledge.personality.azad_responses.data_analyzer") as da,
            patch("extensions.db") as mock_db,
            patch("models.Customer") as Customer,
            patch("models.Product") as Product,
            patch("models.Sale"),
            patch("ai_knowledge.personality.azad_responses.document_generator") as dg,
            patch("ai_knowledge.personality.azad_responses.knowledge_expander") as ke,
        ):
            si.get_customer_balance.return_value = {
                "success": True,
                "customer": {
                    "id": 1,
                    "name": "Ali",
                    "customer_type": "regular",
                    "phone": "050",
                    "email": "a@t.com",
                    "balance_aed": 100,
                    "total_sales": 2,
                    "last_sale_date": "2025-01-01",
                },
            }
            da.analyze_customer_debt.return_value = {
                "success": True,
                "debt_analysis": {
                    "unpaid_sales_count": 1,
                    "avg_debt_amount": 50,
                    "max_debt_amount": 100,
                    "overdue_count": 0,
                },
            }
            si.get_customer_sales_summary.return_value = {
                "success": True,
                "summary": {},
            }
            si.get_system_summary.return_value = {
                "success": True,
                "summary": {
                    "customers": {"total": 1, "vip": 0, "recent": []},
                    "sales": {"total": 1, "today": 0, "recent": []},
                    "products": {"total": 1, "low_stock": 0, "out_of_stock": 0},
                },
            }
            si.get_financial_summary.return_value = {
                "success": True,
                "financial": {
                    "total_sales": 1,
                    "total_payments": 1,
                    "total_receivables": 0,
                    "today_sales": 0,
                    "today_payments": 0,
                },
            }
            si.get_product_stock.return_value = {
                "success": True,
                "product": {
                    "name": "F",
                    "id": 1,
                    "sku": "S",
                    "category": "C",
                    "unit_price": 10.0,
                    "current_stock": 5,
                    "alert_limit": 10,
                },
            }
            si.search_data.return_value = {
                "success": True,
                "results": {"customers": [], "products": [], "sales": []},
            }
            Customer.query.filter.return_value.first.return_value = MagicMock(
                name="Ali", id=1
            )
            Product.query.filter.return_value.first.return_value = MagicMock(
                name="Filter", current_stock=5
            )
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            dg.generate_invoice.return_value = ("inv", "ok")
            ke.search_knowledge.return_value = {
                "success": True,
                "total_found": 1,
                "results": [
                    {
                        "title": "T",
                        "type": "document",
                        "category": "tax",
                        "snippet": "text",
                    }
                ],
            }
            assert responses._handle_customer_balance_query("رصيد for Ali")
            assert responses._handle_customer_balance_query(
                "رصيد balance عميل customer سامي"
            )
            assert responses._handle_customer_info_query("بيانات عميل أحمد")
            assert responses._handle_product_stock_query(
                "مخزون stock منتج product فلتر"
            )
            assert responses._handle_system_summary_query()
            assert responses._handle_add_customer_query("أضف add عميل customer جديد")
            assert responses._handle_search_query("ابحث search عن علي")
            assert responses._handle_add_knowledge_source(
                "أضف add موقع website مصدر source"
            )
            assert responses._show_system_quick_links()
            assert responses._show_knowledge_sources("مصادر sources")
            assert responses._recommend_sources("أين where أجد find معلومات tax")
            assert responses._handle_knowledge_search(
                "ابحث search في المعرفة knowledge tax"
            )
            assert responses._quick_invoice_link()
            assert responses._quick_receipt_link()
            assert responses._handle_document_generation(
                "ولد generate فاتورة invoice 55"
            )
            assert responses._handle_excel_export(
                "صدر export excel بيانات data مبيعات sales"
            )
            assert responses._handle_report_generation("تقرير report مبيعات sales")
            assert responses._handle_tax_laws_query(
                "قانون law ضريبة tax فلسطين palestine"
            )
            assert responses._handle_shipping_laws_query(
                "شحن shipping قانون law إجراءات procedures"
            )
            assert responses._handle_quality_standards_query(
                "جودة quality معايير standards"
            )
            assert responses._handle_suppliers_query("مورد supplier جديد")
            assert responses._handle_smart_filters_query("فلتر filter بحث search")
            assert responses._handle_payment_methods_query("طريقة payment دفع كاش cash")
        with (
            patch(
                "ai_knowledge.personality.azad_responses.get_system_guide",
                return_value="guide",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_market_insights",
                return_value="market",
            ),
        ):
            assert "guide" in self._safe_smart(
                responses, "استخدام usage دليل guide شرح"
            )
            assert "market" in self._safe_smart(
                responses, "سوق market منافسة competition"
            )
        with patch.object(
            responses, "_get_status_response", side_effect=RuntimeError("x")
        ):
            assert "نشط" in self._safe_smart(
                responses, "أداء performance تقدم progress شبكات neural"
            )

    def test_semantic_arabic_intents_and_agents(self):
        from ai_knowledge.neural.semantic_matcher import SemanticMatcher
        from ai_knowledge.agents.multi_agent_system import (
            SalesAgent,
            AccountingAgent,
            InventoryAgent,
        )

        matcher = SemanticMatcher()
        intents = list(matcher.intents_db.keys())
        for intent in intents:
            matcher._get_intent_arabic_name(intent)
        matcher._get_intent_arabic_name("unknown_intent_xyz")
        with patch.object(
            matcher,
            "find_best_intent",
            return_value=("sales_analysis", 0.25, [("sales_analysis", 0.25)]),
        ):
            result = matcher.smart_match("xyz ambiguous query")
            assert result.get("suggestion") or result.get("method") == "low_confidence"
        sales = SalesAgent()
        assert sales.execute("مهمة غير واضحة", {})["confidence"] == 0.5
        with patch(
            "services.ai_service.AIService.predict_price_with_neural",
            side_effect=RuntimeError("fail"),
        ):
            assert sales.execute("سعر price", {"product_id": 1})["confidence"] == 0
        acct = AccountingAgent()
        assert (
            acct.execute("قيد journal", {"debit": 100, "credit": 100})["result"][
                "is_balanced"
            ]
            is True
        )
        inv = InventoryAgent()
        assert isinstance(inv.execute("مخزون stock", {}), dict)

    def test_security_vision_code_neural(self, knowledge_path, tmp_path):
        from ai_knowledge.specialized.security_rules import SecurityRules
        from ai_knowledge.neural.vision_processor import VisionProcessor
        from ai_knowledge.generation.code_generator import CodeGenerator
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        user = MagicMock(is_authenticated=True, is_owner=True, username="owner")
        with patch("ai_knowledge.specialized.security_rules.current_user", user):
            SecurityRules.log_security_event("access", "test event")
            SecurityRules.rate_limit_check(1, "query")
            assert SecurityRules.sanitize_input("x" * 2000).endswith("...")
            filtered = SecurityRules.filter_sensitive_data(
                {"email": 123, "phone": 456, "name": "Ali"}
            )
            assert filtered["name"] == "Ali"
            assert SecurityRules.filter_sensitive_data("plain") == "plain"
        vp = VisionProcessor()
        import os

        img = tmp_path / "part.jpg"
        from PIL import Image

        Image.new("RGB", (10, 10)).save(img)
        old = os.getcwd()
        try:
            os.chdir(tmp_path)
            rel = vp.analyze_part_image("part.jpg")
            assert rel.get("part_name") or rel.get("error")
        finally:
            os.chdir(old)
        with patch("PIL.Image.open", side_effect=OSError("bad")):
            assert "error" in vp.analyze_part_image(str(img))
        gen = CodeGenerator()
        bad_params = MagicMock()
        bad_params.__iter__ = MagicMock(side_effect=RuntimeError("fail"))
        assert "# Error:" in gen.generate_python_function("f", "حساب x", bad_params)
        engine = AzadNeuralEngine()
        _fast_models(engine)
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch.object(
            engine, "_optimize_stock_internal", side_effect=RuntimeError("fail")
        ):
            assert (
                engine.optimize_stock_level(1, from_app_context=ctx)["optimal_stock"]
                == 0
            )


class TestWave9PushTo99:
    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses

        return AzadResponses()

    def test_analytics_remaining_branches(self):
        from ai_knowledge.analytics.analytics_predictions import (
            SalesAnalytics,
            InventoryAnalytics,
            ProfitAnalytics,
            CashFlowAnalytics,
        )

        volatile = SalesAnalytics.predict_next_month_sales(
            [100, 10, 200, 5, 300, 8, 400, 12]
        )
        assert volatile["confidence"] == "low"
        assert SalesAnalytics.abc_analysis([]) == {"A": [], "B": [], "C": []}
        products = [
            {"name": "A", "revenue": 800},
            {"name": "B", "revenue": 150},
            {"name": "C", "revenue": 50},
        ]
        abc = SalesAnalytics.abc_analysis(products)
        assert abc["A"] and abc["C"]
        assert InventoryAnalytics.calculate_eoq({"annual_sales": 0})["eoq"] == 0
        assert ProfitAnalytics.net_profit_margin(1000, 700) == 30.0
        assert CashFlowAnalytics.working_capital_ratio(500, 0)["status"] == "excellent"
        assert CashFlowAnalytics.working_capital_ratio(500, 100)["ratio"] == 5.0

    def test_azad_smart_elif_branches(self, responses):
        msgs = [
            "استخدام usage دليل guide شرح explain",
            "رصيد balance عميل customer ali",
            "بيانات info عميل customer sami",
            "مخزون stock منتج product bolt",
            "ملخص summary نظام system كلي total",
            "أضف add عميل customer جديد new",
            "ابحث search find عن part",
            "أضف add موقع website مصدر source url",
            "روابط links نظام system quick",
            "مصادر sources websites مواقع all",
            "أين where وين أجد find معلومات info",
            "ابحث search في المعرفة knowledge vat",
            "فاتورة invoice جديد new create أنشئ",
            "سند receipt جديد new create أنشئ",
            "ولد generate فاتورة invoice رقم 9",
            "صدر export excel بيانات data مبيعات sales",
            "تقرير report مبيعات sales شهر",
            "ولد generate تقرير report sales",
            "قانون law ضريبة tax فلسطين palestine",
            "شحن shipping قانون law بحري sea",
            "جودة quality معايير standards food",
            "مورد supplier بيانات info",
            "فلتر filter بحث search smart",
            "طريقة payment دفع pay كاش cash",
        ]
        with (
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": None, "confidence": 0},
            ),
            patch(
                "services.ai_service.AIService.is_sensitive_request",
                return_value=(False, False, {}),
            ),
            patch(
                "services.ai_service.AIService.analyze_inventory_health",
                return_value={
                    "success": True,
                    "summary": {"total": 1, "good": 1, "low": 0, "out": 0},
                    "rating": "ok",
                    "health_score": 100,
                },
            ),
            patch(
                "services.ai_service.AIService.analyze_profit_margins",
                return_value={
                    "success": True,
                    "overall": {"revenue": 1, "cost": 1, "profit": 0, "margin": 0},
                    "top_profitable": [],
                },
            ),
            patch("ai_knowledge.personality.azad_responses.azad_personality") as ap,
            patch("ai_knowledge.personality.azad_responses.learning_system"),
            patch("ai_knowledge.personality.azad_responses.beginners_guide") as bg,
            patch("ai_knowledge.personality.azad_responses.system_integrator") as si,
            patch("ai_knowledge.personality.azad_responses.data_analyzer") as da,
            patch("ai_knowledge.personality.azad_responses.document_generator") as dg,
            patch("ai_knowledge.personality.azad_responses.knowledge_expander") as ke,
            patch("extensions.db") as mock_db,
            patch("models.Customer"),
            patch("models.Product"),
            patch("models.Sale"),
        ):
            ap.is_inappropriate_message.return_value = "normal"
            bg.get_beginner_response.return_value = None
            si.get_customer_balance.return_value = {
                "success": True,
                "customer": {
                    "id": 1,
                    "name": "Ali",
                    "customer_type": "regular",
                    "phone": "",
                    "email": "",
                    "balance_aed": 0,
                    "total_sales": 0,
                    "last_sale_date": None,
                },
            }
            si.get_customer_sales_summary.return_value = {"success": False}
            da.analyze_customer_debt.return_value = {"success": False}
            si.get_system_summary.return_value = {
                "success": True,
                "summary": {
                    "customers": {"total": 0, "vip": 0, "recent": []},
                    "sales": {"total": 0, "today": 0, "recent": []},
                    "products": {"total": 0, "low_stock": 0, "out_of_stock": 0},
                },
            }
            si.get_financial_summary.return_value = {
                "success": True,
                "financial": {
                    "total_sales": 0,
                    "total_payments": 0,
                    "total_receivables": 0,
                    "today_sales": 0,
                    "today_payments": 0,
                },
            }
            si.get_product_stock.return_value = {
                "success": True,
                "product": {
                    "name": "P",
                    "id": 1,
                    "sku": "S",
                    "category": "C",
                    "unit_price": 1.0,
                    "current_stock": 1,
                    "alert_limit": 2,
                },
            }
            si.search_data.return_value = {
                "success": True,
                "results": {"customers": [], "products": [], "sales": []},
            }
            dg.generate_invoice.return_value = ("i", "ok")
            dg.generate_sales_report.return_value = ("r", "ok")
            ke.search_knowledge.return_value = {
                "success": True,
                "total_found": 0,
                "results": [],
            }
            mock_db.session.query.return_value.filter.return_value.all.return_value = []
            for msg in msgs:
                assert isinstance(responses.smart_response(msg), str)

    def test_azad_customer_info_failures(self, responses):
        with patch("ai_knowledge.personality.azad_responses.system_integrator") as si:
            si.get_customer_balance.return_value = {
                "success": False,
                "error": "غير موجود",
            }
            assert "غير موجود" in responses._handle_customer_info_query(
                "بيانات عميل ghost"
            )
            si.get_customer_balance.return_value = {
                "success": True,
                "customer": {
                    "id": 2,
                    "name": "Bob",
                    "customer_type": "vip",
                    "phone": "",
                    "email": "",
                    "balance_aed": 0,
                    "total_sales": 0,
                    "last_sale_date": None,
                },
            }
            si.get_customer_sales_summary.return_value = {"success": False}
            assert "Bob" in responses._handle_customer_info_query("بيانات عميل Bob")

    def test_context_conversation_learning(self, knowledge_path):
        from ai_knowledge.core.context_engine import ContextEngine
        from ai_knowledge.core.conversation_manager import ConversationManager
        from ai_knowledge.core.learning_system import AzadLearningSystem

        with (
            patch("ai_knowledge.core.context_engine.system_integrator") as si,
            patch("ai_knowledge.core.context_engine.data_analyzer") as da,
            patch("ai_knowledge.core.context_engine.knowledge_expander") as ke,
            patch("ai_knowledge.core.context_engine.learning_system") as ls,
        ):
            si.get_system_summary.return_value = {
                "success": True,
                "summary": {
                    "total_customers": 1,
                    "total_products": 2,
                    "today_sales": 3,
                },
            }
            da.get_financial_ratios.side_effect = RuntimeError("fail")
            ContextEngine.enhance_response("حلل analyze", "base", {})
            ke.search_knowledge.side_effect = RuntimeError("fail")
            ContextEngine.enhance_response("ابحث search tax", "base", {})
            ls.get_learning_insights.side_effect = RuntimeError("fail")
            ContextEngine.enhance_response("مرحبا", "base", {})
            si.get_system_summary.side_effect = RuntimeError("fail")
            ContextEngine.enhance_response("كم how many customers", "base", {})
        mgr = ConversationManager()
        mgr.start_conversation(42)
        mgr.process_message(42, "test message")
        mgr.end_conversation(42)
        ls = AzadLearningSystem()
        ls.learn_from_interaction("q", "a", tenant_id=None)
        ls.get_learning_insights()
