"""Targeted coverage push for ai_knowledge modules below 99%."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


@pytest.fixture
def knowledge_path(tmp_path):
    with patch(
        "ai_knowledge.get_knowledge_path", side_effect=lambda name: str(tmp_path / name)
    ):
        yield tmp_path


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


class TestTrainer:
    def test_seed_idempotent(self, knowledge_path):
        from ai_knowledge.trainer import Trainer

        ql = MagicMock()
        ql.get_answer.return_value = None
        trainer = Trainer()
        trainer.quick_learner = ql
        trainer.seed()
        first = ql.learn.call_count
        trainer.seed()
        assert trainer._seeded is True
        assert ql.learn.call_count == first

    def test_seed_from_expertise_json(self, knowledge_path, tmp_path):
        from ai_knowledge.trainer import Trainer

        expertise_dir = tmp_path / "ai_training" / "GLOBAL" / "expertise"
        expertise_dir.mkdir(parents=True)
        (expertise_dir / "test.json").write_text(
            json.dumps({"expertise_areas": [{"topic": "VAT", "knowledge": "5%"}]}),
            encoding="utf-8",
        )
        ql = MagicMock()
        ql.get_answer.return_value = None
        trainer = Trainer()
        trainer.quick_learner = ql
        with (
            patch("ai_knowledge.trainer.os.path.dirname", return_value=str(tmp_path)),
            patch("ai_knowledge.trainer.os.path.abspath", side_effect=lambda p: p),
            patch("ai_knowledge.trainer.os.path.join", side_effect=os.path.join),
            patch("glob.glob", return_value=[str(expertise_dir / "test.json")]),
        ):
            trainer.seed()
        assert ql.learn.called

    def test_get_ql_fallback_import(self):
        from ai_knowledge.trainer import Trainer

        trainer = Trainer()
        trainer.quick_learner = None
        with patch.dict("sys.modules", {"ai_knowledge.learning_engine": None}):
            with patch(
                "ai_knowledge.learning.quick_learner.quick_learner", MagicMock()
            ) as ql:
                assert trainer._get_ql() is ql

    def test_seed_expertise_read_error(self, knowledge_path, tmp_path):
        from ai_knowledge.trainer import Trainer

        bad = tmp_path / "bad.json"
        bad.write_text("x", encoding="utf-8")
        ql = MagicMock()
        ql.get_answer.return_value = None
        trainer = Trainer()
        trainer.quick_learner = ql
        trainer._seeded = False
        with (
            patch("glob.glob", return_value=[str(bad)]),
            patch("ai_knowledge.trainer.os.path.dirname", return_value=str(tmp_path)),
            patch("ai_knowledge.trainer.os.path.abspath", side_effect=lambda p: p),
            patch("ai_knowledge.trainer.os.path.join", side_effect=os.path.join),
            patch("builtins.open", side_effect=OSError("read fail")),
        ):
            trainer.seed()
        assert trainer._seeded is True

    def test_learn_from_interaction_empty(self):
        from ai_knowledge.trainer import Trainer

        trainer = Trainer()
        trainer.quick_learner = MagicMock()
        trainer.learn_from_interaction("", "answer")
        trainer.learn_from_interaction("q", "")
        trainer.quick_learner.learn.assert_not_called()

    def test_learn_from_interaction_success(self, knowledge_path):
        from ai_knowledge.trainer import Trainer

        ql = MagicMock()
        ql.get_answer.return_value = None
        trainer = Trainer()
        trainer.quick_learner = ql
        trainer._seeded = True
        with patch("ai_knowledge.core.learning_system.learning_system") as ls:
            trainer.learn_from_interaction("سؤال", "جواب", user_id=1, tenant_id=2)
            ql.learn.assert_called_once()
            ls.learn_from_interaction.assert_called_once()

    def test_learn_skips_existing_answer(self):
        from ai_knowledge.trainer import Trainer

        ql = MagicMock()
        ql.get_answer.return_value = "existing"
        trainer = Trainer()
        trainer.quick_learner = ql
        trainer._seeded = True
        trainer.learn_from_interaction("سؤال", "جواب", success=True)
        ql.learn.assert_not_called()

    def test_learn_learning_system_error(self):
        from ai_knowledge.trainer import Trainer

        ql = MagicMock()
        ql.get_answer.return_value = None
        trainer = Trainer()
        trainer.quick_learner = ql
        trainer._seeded = True
        with patch(
            "ai_knowledge.core.learning_system.learning_system",
            side_effect=RuntimeError(),
        ):
            trainer.learn_from_interaction("q", "a")

    def test_train_from_feedback(self):
        from ai_knowledge.trainer import Trainer

        ql = MagicMock()
        trainer = Trainer()
        trainer.quick_learner = ql
        with patch("ai_knowledge.core.learning_system.learning_system") as ls:
            trainer.train_from_feedback("q", "correct", user_id=3, tenant_id=1)
            ql.learn.assert_called_once()
            ls.learn_from_interaction.assert_called_once()

    def test_train_from_feedback_error(self):
        from ai_knowledge.trainer import Trainer

        trainer = Trainer()
        trainer.quick_learner = MagicMock()
        with patch(
            "ai_knowledge.core.learning_system.learning_system",
            side_effect=RuntimeError(),
        ):
            trainer.train_from_feedback("q", "a")

    def test_get_stats(self):
        from ai_knowledge.trainer import Trainer

        row = MagicMock(category="system", id=1)
        with patch("extensions.db") as mock_db:
            mock_db.session.query.return_value.filter.return_value.count.return_value = 3
            mock_db.session.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
                ("system", 2),
                ("learned", 1),
            ]
            stats = Trainer().get_stats()
        assert stats["total_qa"] == 3
        assert stats["categories"]["system"] == 2


class TestMemorySystem:
    def test_long_term_memory_full_lifecycle(self, knowledge_path):
        import ai_knowledge.core.memory_system as mem_mod

        mem_mod._memory_instance = None
        from ai_knowledge.core.memory_system import LongTermMemory, get_memory_system

        mem = LongTermMemory()
        mem.remember_conversation(
            1, "كم المخزون المتاح", "المخزون جيد", {"page": "inventory"}
        )
        mem.remember_fact("ضريبة القيمة المضافة 5%", "tax", source="system")
        mem.remember_procedure("إنشاء فاتورة", ["افتح المبيعات", "أضف عميل"], "sales")
        mem.remember_user_preference(1, "language", "ar")
        assert len(mem.recall_conversations(1)) == 1
        assert mem.recall_similar_conversations("المخزون المتاح")
        assert mem.recall_fact("ضريبة")
        assert mem.recall_procedure("فاتورة") is not None
        assert mem.get_user_preferences(1)["language"] == "ar"
        mem.search_memory("ضريبة")
        mem.forget_old_memories(days=0)
        stats = mem.get_memory_stats()
        assert stats["total_memories"] >= 2
        assert get_memory_system() is mem_mod.get_memory_system()

    def test_load_corrupted_memory(self, knowledge_path):
        from ai_knowledge.core.memory_system import LongTermMemory

        mem_dir = knowledge_path / "memory"
        mem_dir.mkdir()
        (mem_dir / "episodic_memory.json").write_text("{bad", encoding="utf-8")
        mem = LongTermMemory()
        assert isinstance(mem.episodic_memory.get("memories"), list)

    def test_save_memory_failure(self, knowledge_path):
        from ai_knowledge.core.memory_system import LongTermMemory

        mem = LongTermMemory()
        with patch("builtins.open", side_effect=OSError("disk full")):
            assert mem._save_memory("episodic", mem.episodic_memory) is False

    def test_episodic_trim(self, knowledge_path):
        from ai_knowledge.core.memory_system import LongTermMemory

        mem = LongTermMemory()
        for i in range(1002):
            mem.remember_conversation(1, f"msg {i}", f"resp {i}")
        assert len(mem.episodic_memory["memories"]) == 1000

    def test_core_engine_memory(self, knowledge_path):
        import ai_knowledge.core.memory_system as ms

        ms._memory_instance = None
        from ai_knowledge.core_engine import LongTermMemory, get_memory_system
        import ai_knowledge.core_engine as ce

        mem = LongTermMemory()
        mem.remember_conversation(2, "مرحبا", "أهلا")
        mem.remember_user_preference(2, "dialect", "gulf")
        assert mem.get_user_preferences(2)["dialect"] == "gulf"
        assert get_memory_system() is ce.get_memory_system()


class TestExpansionCore:
    def test_knowledge_expander_website(self, knowledge_path):
        from ai_knowledge.expansion_core import KnowledgeExpander

        html = "<html><head><title>Test Site</title></head><body><p>heavy equipment parts</p></body></html>"
        mock_resp = MagicMock(status_code=200, content=html.encode())
        with patch(
            "ai_knowledge.expansion.knowledge_expansion.requests.get",
            return_value=mock_resp,
        ):
            result = KnowledgeExpander().add_website("example.com", category="parts")
        assert result["success"] is True

    def test_knowledge_expander_invalid_url(self, knowledge_path):
        from ai_knowledge.expansion_core import KnowledgeExpander

        assert KnowledgeExpander().add_website("")["success"] is False

    def test_knowledge_expander_fetch_failure(self, knowledge_path):
        from ai_knowledge.expansion_core import KnowledgeExpander
        import requests

        with patch(
            "ai_knowledge.expansion.knowledge_expansion.requests.get",
            side_effect=requests.RequestException("timeout"),
        ):
            result = KnowledgeExpander()._fetch_website_content("https://fail.test")
        assert result["success"] is False

    def test_knowledge_expander_document_and_search(self, knowledge_path):
        from ai_knowledge.expansion_core import KnowledgeExpander

        exp = KnowledgeExpander()
        assert exp.add_document("", "title")["success"] is False
        added = exp.add_document("content about customs", "Customs Doc", "customs")
        assert added["success"] is True
        found = exp.search_knowledge("customs")
        assert found["success"] is True
        summary = exp.get_knowledge_summary()
        assert summary["success"] is True

    def test_load_sources_corrupt(self, knowledge_path):
        from ai_knowledge.expansion_core import KnowledgeExpander

        sources = knowledge_path / "knowledge_sources.json"
        sources.write_text("{bad", encoding="utf-8")
        exp = KnowledgeExpander()
        assert "websites" in exp.sources

    def test_global_knowledge_connector(self):
        from ai_knowledge.expansion_core import GlobalKnowledgeConnector

        conn = GlobalKnowledgeConnector()
        assert conn.fetch_global_automotive_news()["success"] is True
        assert conn.fetch_heavy_equipment_trends()["success"] is True
        assert conn.fetch_tax_regulation_updates()["success"] is True
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"rates": {"USD": 0.27}, "date": "2025-06-01"}
        with patch(
            "ai_knowledge.expansion.global_knowledge.requests.get",
            return_value=mock_resp,
        ):
            assert conn.fetch_currency_rates()["success"] is True
        with patch(
            "ai_knowledge.expansion.global_knowledge.requests.get",
            side_effect=RuntimeError("net"),
        ):
            assert conn.fetch_currency_rates()["success"] is False
        insights = conn.get_global_insights()
        assert "automotive_trends" in insights

    def test_knowledge_source_manager(self):
        from ai_knowledge.expansion_core import (
            KnowledgeSourceManager,
            get_learning_resources,
        )

        mgr = KnowledgeSourceManager()
        assert mgr.get_sources_by_topic("parts")
        assert mgr.search_part_info("1R0716")["part_number"] == "1R0716"
        assert mgr.get_tax_resources("UAE")
        assert mgr.get_tax_resources("Unknown") == []
        assert mgr.learn_from_source("http://x", "parts")["status"] == "planned"
        assert mgr.get_all_sources_summary()["total_sources"] > 0
        rec = mgr.recommend_sources("ما هي الضريبة على الاستيراد")
        assert isinstance(rec, list)
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"rates": {"USD": 0.27}}
        with patch(
            "ai_knowledge.expansion.knowledge_sources.requests.get",
            return_value=mock_resp,
        ):
            assert mgr.fetch_exchange_rates() is not None
        mgr.cache["exchange_rates"] = ({"rates": {}}, datetime.now())
        assert mgr.fetch_exchange_rates() == {"rates": {}}
        assert isinstance(get_learning_resources("parts"), list)
        assert isinstance(get_learning_resources(), dict)


class TestGenerationCore:
    def test_document_generator_all(self):
        from ai_knowledge.generation_core import DocumentGenerator, document_generator

        sale = _sale_mock()
        with patch("models.Sale") as MockSale, patch("models.Customer") as MockC:
            MockSale.query.get.return_value = sale
            MockSale.query.filter.return_value.all.return_value = [sale]
            MockSale.query.filter.return_value = MockSale.query
            receipt, rmsg = DocumentGenerator.generate_receipt(42)
            assert "سند قبض" in receipt
            invoice, imsg = DocumentGenerator.generate_invoice(42)
            assert "فاتورة" in invoice
            report, repmsg = DocumentGenerator.generate_sales_report()
            assert "تقرير" in report
            MockC.query.get.return_value = sale.customer
            statement, smsg = DocumentGenerator.generate_customer_statement(1)
            assert statement is None or "كشف" in statement
            MockSale.query.get.return_value = None
            assert DocumentGenerator.generate_receipt(99)[0] is None
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
            assert fname.endswith(".csv")
            assert DocumentGenerator.export_to_excel("unknown")[0] is None
        assert document_generator is not None

    def test_code_generator_all(self):
        from ai_knowledge.generation_core import CodeGenerator, get_code_generator

        gen = CodeGenerator()
        assert "SELECT" in gen.generate_sql_query(
            "select", "sales", {"where": {"id": 1}, "order_by": "id", "limit": 10}
        )
        assert "INSERT" in gen.generate_sql_query(
            "insert", "t", {"columns": ["a"], "values": ["x"]}
        )
        assert "UPDATE" in gen.generate_sql_query(
            "update", "t", {"set": {"a": "b"}, "where": {"id": 1}}
        )
        assert gen.generate_sql_query("bad", "t").startswith("--")
        assert "def calc" in gen.generate_python_function("calc", "حساب الربح", ["x"])
        assert "predict" in gen.generate_python_function("pred", "توقع المبيعات")
        assert "Product" in gen.generate_python_function("find", "بحث منتج")
        assert "def generic" in gen.generate_python_function("generic", "other")
        assert "sales" in gen.generate_report_query(
            "sales", {"start_date": "2025-01-01", "end_date": "2025-06-01"}
        )
        assert "products" in gen.generate_report_query("inventory")
        assert "customers" in gen.generate_report_query("customers")
        assert "Unknown" in gen.generate_report_query("other")
        fixed = gen.fix_code("x = 'bad", "SyntaxError: quote")
        assert fixed["confidence"] > 0
        fixed2 = gen.fix_code("def f():\nreturn 1", "IndentationError")
        assert fixed2["changes"]
        fixed3 = gen.fix_code("x = db", "NameError: name 'db' is not defined")
        assert "db" in fixed3["fixed_code"]
        opt = gen.optimize_code(
            "for x in y:\n    z.append(x)\n" + "db.session.add(x)\n" * 6
        )
        assert opt["performance_gain_percent"] > 0
        assert get_code_generator() is get_code_generator()


class TestLearningEngineConsolidated:
    def test_quick_learner_delegate(self, knowledge_path):
        from ai_knowledge.learning_engine import QuickLearner, quick_learner

        impl = MagicMock()
        impl.learn.return_value = True
        impl.get_answer.return_value = "answer"
        impl.knowledge_base = {}
        with patch(
            "ai_knowledge.learning.quick_learner.QuickLearner", return_value=impl
        ):
            QuickLearner._klass = None
            ql = QuickLearner()
            ql.learn("q", "a", "cat", 1)
            ql.get_answer("q", 1)
            ql.save_knowledge()
            assert ql.knowledge_base == {}
        assert quick_learner is not None

    def test_auto_retraining(self, knowledge_path):
        from ai_knowledge.learning_engine import AutoRetrainingScheduler

        with (
            patch.object(
                AutoRetrainingScheduler, "get_last_training_info", return_value=None
            ),
            patch("models.Sale") as MockSale,
        ):
            MockSale.query.filter_by.return_value.count.return_value = 150
            assert AutoRetrainingScheduler.should_retrain() is True
            MockSale.query.filter_by.return_value.count.return_value = 60
            history = knowledge_path / "training_history.json"
            history.write_text(
                json.dumps(
                    [
                        {
                            "timestamp": (
                                datetime.now() - timedelta(days=8)
                            ).isoformat(),
                            "sales_count": 5,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            with patch.object(
                AutoRetrainingScheduler,
                "get_last_training_info",
                return_value={
                    "timestamp": (datetime.now() - timedelta(days=8)).isoformat(),
                    "sales_count": 5,
                },
            ):
                assert AutoRetrainingScheduler.should_retrain() is True
        with patch.object(
            AutoRetrainingScheduler, "get_last_training_info", return_value=None
        ):
            with patch("models.Sale") as MockSale:
                MockSale.query.filter_by.return_value.count.return_value = 50
                assert AutoRetrainingScheduler.should_retrain() is False
        with (
            patch("ai_knowledge.neural.neural_engine.get_neural_engine") as gne,
            patch("models.Sale") as MockSale,
        ):
            gne.return_value.train_all_models.return_value = {"success": True}
            MockSale.query.filter_by.return_value.count.return_value = 100
            assert AutoRetrainingScheduler.trigger_retraining()["success"] is True
        with patch(
            "ai_knowledge.neural.neural_engine.get_neural_engine",
            side_effect=RuntimeError(),
        ):
            assert AutoRetrainingScheduler.trigger_retraining()["success"] is False
        log_path = knowledge_path / "training_history.json"
        with patch.object(AutoRetrainingScheduler, "TRAINING_LOG_FILE", str(log_path)):
            AutoRetrainingScheduler.log_training(10, {"ok": True})
            assert AutoRetrainingScheduler.get_last_training_info() is not None
        with patch.object(
            AutoRetrainingScheduler, "should_retrain", return_value=False
        ):
            assert "message" in AutoRetrainingScheduler.check_and_train_if_needed()

    def test_continuous_learner(self, knowledge_path):
        from ai_knowledge.learning_engine import (
            ContinuousLearner,
            get_continuous_learner,
        )

        learner = ContinuousLearner()
        with (
            patch.object(
                learner, "learn_from_wikipedia", return_value={"success": True}
            ),
            patch.object(
                learner,
                "learn_arxiv_papers",
                return_value={"success": True, "papers": 2},
            ),
        ):
            result = learner.daily_learning_routine()
            assert result["items_learned"] >= 1
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"extract": "محتوى تعليمي"}
        with patch.object(learner.session, "get", return_value=mock_resp):
            assert learner.learn_from_wikipedia("المحاسبة")["success"] is True
        assert learner.get_learning_stats()["learning_sessions"] >= 0
        assert get_continuous_learner() is get_continuous_learner()


class TestNeuralNetworkConsolidatedDeep:
    def test_vision_processor(self, knowledge_path):
        from ai_knowledge.neural_network import VisionProcessor, get_vision_processor

        proc = VisionProcessor()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            Image.new("RGB", (30, 30), color="white").save(f.name)
            path = f.name
        try:
            assert proc.read_invoice_image(path).get("confidence") == 0.75
            assert proc.analyze_part_image(path).get("confidence") == 0.6
            assert "OCR" in proc.extract_text_from_image(path)
        finally:
            os.unlink(path)
        assert get_vision_processor() is get_vision_processor()

    def test_semantic_and_transformers(self):
        from ai_knowledge.neural_network import (
            SemanticMatcher,
            TransformersBrain,
            get_confidence,
            get_intent,
            get_transformers_brain,
            semantic_matcher,
            understand_message,
        )

        matcher = SemanticMatcher()
        assert matcher.smart_match("فاتورة جديدة")["intent"] == "create_invoice"
        assert understand_message("فاتورة")["intent"] is not None
        assert get_intent("فاتورة") is not None
        assert get_confidence("فاتورة") >= 0
        brain = TransformersBrain(vocab_size=64, d_model=32, n_heads=4)
        assert brain.understand("كم الضريبة؟")["intent"] == "question"
        assert brain.generate_response("كم الضريبة؟")
        assert semantic_matcher is not None
        assert get_transformers_brain() is get_transformers_brain()

    def test_neural_engine_branches(self, knowledge_path):
        from ai_knowledge.neural_network import AzadNeuralEngine, get_neural_engine

        engine = AzadNeuralEngine()
        with patch.object(engine, "_load_model", return_value=False):
            assert (
                engine.predict_optimal_price(100, 2, "merchant")["model"]
                == "rule_based"
            )
            assert (
                engine.validate_accounting_entry(100, 100, 2, "Sale")["is_correct"]
                is True
            )
        with (
            patch("extensions.db") as mock_db,
            patch("models.Customer"),
            patch("models.Sale"),
        ):
            mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.group_by.return_value.first.return_value = None
            assert engine.classify_customer_intelligence(1)["classification"] == "new"
        status = engine.get_status()
        assert status["total_models"] >= 10
        assert get_neural_engine() is get_neural_engine()


class TestActionDispatcherHandlers:
    @pytest.fixture
    def permitted(self):
        return (
            patch(
                "ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1
            ),
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
            patch("ai_knowledge.action_dispatcher._audit"),
            patch("ai_knowledge.action_dispatcher._log_ai_error"),
        )

    def test_customer_balance_paths(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher

        with (
            permitted[0],
            permitted[1],
            permitted[2],
            permitted[3],
            patch("models.Customer") as Customer,
        ):
            Customer.query.filter_by.return_value.first.return_value = None
            r = action_dispatcher.dispatch("customer_balance", {"name": "missing"})
            assert r.success is False
            cust = MagicMock(
                id=1, name="Ali", balance=Decimal("2500"), credit_limit=Decimal("1000")
            )
            Customer.query.filter_by.return_value.first.return_value = cust
            r2 = action_dispatcher.dispatch("customer_balance", {"name": "Ali"})
            assert r2.success is True

    def test_create_customer_validation(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher

        with permitted[0], permitted[1], permitted[2], permitted[3]:
            assert (
                action_dispatcher.dispatch("create_customer", {"name": ""}).success
                is False
            )

    def test_list_products_and_stock(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher

        product = MagicMock(
            id=1,
            name="Bolt",
            sku="B1",
            selling_price=Decimal("10"),
            current_stock=Decimal("5"),
        )
        with (
            permitted[0],
            permitted[1],
            permitted[2],
            permitted[3],
            patch("models.Product") as Product,
        ):
            list_q = MagicMock()
            list_q.filter_by.return_value = list_q
            list_q.filter.return_value = list_q
            list_q.order_by.return_value.limit.return_value.all.return_value = [product]
            Product.query = list_q
            Product.name = MagicMock()
            assert (
                action_dispatcher.dispatch("list_products", {"search": "bolt"}).success
                is True
            )

    def test_sales_payment_expense(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher

        with (
            permitted[0],
            permitted[1],
            permitted[2],
            permitted[3],
            patch("services.ai_executor.AIExecutor") as Ex,
            patch("models.Sale") as Sale,
            patch("models.Expense") as Expense,
            patch("ai_knowledge.action_dispatcher.db.session"),
        ):
            Ex.return_value.create_sale.return_value = {
                "success": True,
                "sale_id": 5,
                "message": "ok",
                "total": 100,
            }
            assert (
                action_dispatcher.dispatch(
                    "create_sale",
                    {
                        "customer_name": "Ali",
                        "product_name": "Bolt",
                        "quantity": 2,
                    },
                ).success
                is True
            )
            Ex.return_value.create_sale.return_value = {
                "success": False,
                "error": "fail",
            }
            assert (
                action_dispatcher.dispatch(
                    "create_sale",
                    {
                        "customer_name": "Ali",
                        "product_name": "Bolt",
                        "quantity": 1,
                    },
                ).success
                is False
            )
            q = MagicMock()
            q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
            Sale.query = q
            assert action_dispatcher.dispatch("list_sales", {}).success is True
            Ex.return_value.receive_payment.return_value = {
                "success": True,
                "message": "ok",
                "payment_id": 1,
            }
            assert (
                action_dispatcher.dispatch(
                    "receive_payment", {"customer_name": "Ali", "amount": 100}
                ).success
                is True
            )
            assert (
                action_dispatcher.dispatch(
                    "add_expense", {"description": "fuel", "amount": 50}
                ).success
                is True
            )

    def test_supplier_reports_employee(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher

        with (
            permitted[0],
            permitted[1],
            permitted[2],
            permitted[3],
            patch("models.Supplier") as Supplier,
            patch("models.Sale") as Sale,
            patch("models.SaleLine") as SaleLine,
            patch("models.Product") as Product,
            patch("services.ai_executor.AIExecutor") as Ex,
            patch("ai_knowledge.action_dispatcher.db.session") as session,
        ):
            Supplier.return_value = MagicMock(id=1)
            assert (
                action_dispatcher.dispatch("create_supplier", {"name": "Sup"}).success
                is True
            )
            session.query.return_value.filter.return_value.scalar.return_value = (
                Decimal("1000")
            )
            Sale.query.filter_by.return_value.count.return_value = 5
            assert action_dispatcher.dispatch("sales_summary", {}).success is True
            session.query.return_value.join.return_value.filter.return_value.all.return_value = []
            assert action_dispatcher.dispatch("profit_summary", {}).success is True
            Ex.return_value.create_employee.return_value = {
                "success": True,
                "message": "ok",
                "id": 2,
            }
            assert (
                action_dispatcher.dispatch(
                    "create_employee", {"name": "Emp", "salary": 3000}
                ).success
                is True
            )
            Ex.return_value.create_purchase.return_value = {
                "success": True,
                "message": "ok",
                "purchase_id": 9,
            }
            assert (
                action_dispatcher.dispatch(
                    "create_purchase",
                    {
                        "supplier_name": "S",
                        "product_name": "P",
                        "quantity": 1,
                    },
                ).success
                is True
            )

    def test_create_user_and_helpers(self, permitted, mock_ai_user):
        from ai_knowledge.action_dispatcher import (
            action_dispatcher,
            _get_active_tenant_id,
            _is_owner,
        )

        with patch(
            "ai_knowledge.action_dispatcher.current_user",
            SimpleNamespace(is_authenticated=False),
        ):
            assert _get_active_tenant_id() is None
        user = MagicMock(is_owner=False)
        user.has_permission.side_effect = RuntimeError()
        with patch("ai_knowledge.action_dispatcher.current_user", user):
            assert _is_owner() is False
        with (
            permitted[0],
            permitted[1],
            permitted[2],
            permitted[3],
            patch("models.User") as User,
            patch("models.Role") as Role,
            patch("ai_knowledge.action_dispatcher.db.session"),
        ):
            Role.query.filter_by.return_value.first.return_value = MagicMock(id=1)
            User.return_value = MagicMock(id=9)
            assert (
                action_dispatcher.dispatch(
                    "create_user",
                    {
                        "username": "u1",
                        "password": "secret",
                        "role": "seller",
                    },
                ).success
                is True
            )


class TestInitAndPaths:
    def test_get_knowledge_path_priority(self, tmp_path):
        from ai_knowledge import AI_KNOWLEDGE_DIR, get_knowledge_path

        training = os.path.join(AI_KNOWLEDGE_DIR, "data", "training", "prio.json")
        models = os.path.join(AI_KNOWLEDGE_DIR, "data", "models", "prio.json")
        expanded = os.path.join(AI_KNOWLEDGE_DIR, "data", "expanded", "prio.json")
        memory = os.path.join(AI_KNOWLEDGE_DIR, "memory", "prio.json")
        created = []
        try:
            for p in (training, models, expanded, memory):
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "w").close()
                created.append(p)
                assert get_knowledge_path("prio.json") == p
                os.unlink(p)
                created.pop()
        finally:
            for p in created:
                if os.path.exists(p):
                    os.unlink(p)


class TestPersonalityCoreDeep:
    def test_azad_personality_branches(self):
        from ai_knowledge.personality_core import AzadPersonality, azad_personality

        p = AzadPersonality()
        assert p.is_inappropriate_message("normal") == "normal"
        assert isinstance(p.get_greeting(), str)
        assert isinstance(p.get_positive_response(), str)
        assert azad_personality is not None

    def test_azad_responses_handlers(self):
        from ai_knowledge.personality_core import AzadResponses

        resp = AzadResponses()
        with (
            patch("ai_knowledge.personality.azad_responses.system_integrator") as si,
            patch(
                "ai_knowledge.personality.azad_responses.understand_message",
                return_value={"intent": "greeting", "confidence": 0.9},
            ),
            patch(
                "ai_knowledge.personality.azad_responses.intelligent_assistant"
            ) as ia,
            patch("ai_knowledge.personality.azad_responses.learning_system") as ls,
            patch("ai_knowledge.personality.azad_responses.azad_personality") as ap,
        ):
            si.get_system_summary.return_value = {"success": True, "summary": {}}
            ia.process_query.return_value = {"response": "ok"}
            ls.get_learning_insights.return_value = {}
            ap.is_inappropriate_message.return_value = "normal"
            result = resp.smart_response("مرحبا")
            assert isinstance(result, str)


class TestCoreEngineExpanded:
    def test_conversation_manager(self, knowledge_path):
        import ai_knowledge.core.conversation_manager as cm

        cm._conversation_manager_instance = None
        import ai_knowledge.core_engine as ce
        from ai_knowledge.core_engine import (
            ConversationManager,
            get_conversation_manager,
        )

        mgr = ConversationManager()
        mgr.start_conversation(1, {"name": "Ali"})
        mgr.process_message(1, "كم المخزون؟")
        assert mgr.get_conversation_history(1)
        assert mgr.end_conversation(1)["summary"]["messages_count"] >= 1
        assert get_conversation_manager() is ce.get_conversation_manager()

    def test_system_integrator_more(self):
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
            assert by_id["supplier"]["balance_aed"] == 2500.0

    def test_reasoning_engine_from_core(self):
        from ai_knowledge.core_engine import ReasoningEngine, get_reasoning_engine

        engine = ReasoningEngine()
        assert engine.think("مخزون منخفض")["solution"] is not None
        assert get_reasoning_engine() is get_reasoning_engine()
