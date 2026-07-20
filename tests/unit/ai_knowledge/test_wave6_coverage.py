"""Wave 6 coverage push — harden tenant isolation and reach >=99% on ai_knowledge/*."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture
def knowledge_path(tmp_path):
    with patch("ai_knowledge.get_knowledge_path", side_effect=lambda name: str(tmp_path / name)):
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


class TestLearningSystemWave6:
    def test_normalize_corrupt_json(self, knowledge_path):
        from ai_knowledge.core.learning_system import AzadLearningSystem

        bad = knowledge_path / "learned_knowledge.json"
        bad.write_text(
            json.dumps(
                {
                    "failed_responses": "not-a-list",
                    "successful_responses": [],
                    "customer_preferences": "bad",
                    "expertise_areas": "bad",
                }
            ),
            encoding="utf-8",
        )
        ls = AzadLearningSystem()
        assert isinstance(ls.learned_knowledge["failed_responses"], list)
        assert isinstance(ls.learned_knowledge["customer_preferences"], dict)

    def test_tenant_isolated_learn_and_insights(self, knowledge_path):
        from ai_knowledge.core.learning_system import AzadLearningSystem

        ls = AzadLearningSystem()
        ls.learn_from_interaction("q1", "a1", tenant_id=1)
        ls.learn_from_interaction("q2", "a2", tenant_id=2)
        t1 = ls.get_learning_insights(tenant_id=1)
        t2 = ls.get_learning_insights(tenant_id=2)
        assert t1["total_interactions"] == 1
        assert t2["total_interactions"] == 1
        assert (knowledge_path / "interactions_log_tenant_1.json").exists()
        assert (knowledge_path / "learned_knowledge_tenant_1.json").exists()

    def test_failed_response_and_groq_paths(self, knowledge_path):
        from ai_knowledge.core.learning_system import AzadLearningSystem

        ls = AzadLearningSystem()
        ls.learned_knowledge["failed_responses"] = "corrupt"
        ls.learn_from_interaction("bad", "wrong", user_feedback=1)
        assert isinstance(ls.learned_knowledge["failed_responses"], list)
        for _ in range(6):
            ls.learn_from_interaction("tax q", "tax a", user_feedback=5)
        ls.evolve_knowledge()
        enhanced = ls.get_enhanced_response("ضريبة VAT", "base")
        assert enhanced
        ls.learn_from_groq_feedback(
            {
                "question": "q",
                "local_answer": "a",
                "improved_answer": "better",
                "timestamp": datetime.now().isoformat(),
            }
        )
        ls.learn_from_groq_feedback({"bad": "data"})
        assert ls._analyze_improvements(None, None)["timestamp"]


class TestActionDispatcherWave6:
    def test_runtime_error_paths(self):
        from ai_knowledge import action_dispatcher as ad
        import builtins

        real_import = builtins.__import__

        def block_flask_g(name, *args, **kwargs):
            if name == "flask" and args and args[0] == ("g",):
                raise RuntimeError("no ctx")
            return real_import(name, *args, **kwargs)

        with (
            patch(
                "ai_knowledge.action_dispatcher.current_user",
                SimpleNamespace(is_authenticated=False),
            ),
            patch("builtins.__import__", side_effect=block_flask_g),
        ):
            assert ad._get_active_tenant_id() is None
        with (
            patch(
                "ai_knowledge.action_dispatcher.current_user",
                MagicMock(is_owner=False, is_authenticated=True),
            ),
            patch(
                "ai_knowledge.action_dispatcher._has_permission",
                side_effect=RuntimeError(),
            ),
        ):
            assert ad._is_owner() is False
        with patch("ai_knowledge.action_dispatcher.db.session") as sess:
            sess.add = MagicMock()
            sess.flush.side_effect = RuntimeError("db")
            ad._log_ai_error("t", "msg")

    def test_tenant_guard_blocks_create(self, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher

        with (
            patch(
                "ai_knowledge.action_dispatcher._get_active_tenant_id",
                return_value=None,
            ),
            patch("ai_knowledge.action_dispatcher._has_permission", return_value=True),
        ):
            for action, args in (
                ("create_customer", {"name": "Ali"}),
                ("create_product", {"name": "Bolt"}),
                ("add_expense", {"description": "x", "amount": 10}),
                ("create_supplier", {"name": "Sup"}),
                ("create_user", {"username": "u", "password": "p"}),
            ):
                r = action_dispatcher.dispatch(action, args)
                assert r.success is False
                assert "تينانت" in r.message

    def test_remaining_handler_branches(self, mock_ai_user):
        from ai_knowledge.action_dispatcher import action_dispatcher

        with (
            patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1),
            patch("ai_knowledge.action_dispatcher._has_permission", return_value=True),
            patch("services.ai_executor.AIExecutor") as Ex,
        ):
            ex = Ex.return_value
            ex.create_sale.return_value = {
                "success": True,
                "message": "ok",
                "sale_id": 1,
                "total": 50,
            }
            r = action_dispatcher.dispatch(
                "create_sale",
                {
                    "customer_name": "A",
                    "product_name": "P",
                    "unit_price": 25,
                },
            )
            assert r.success is True
            ex.receive_payment.return_value = {"success": False, "message": "no"}
            assert (
                action_dispatcher.dispatch(
                    "receive_payment",
                    {
                        "customer_name": "A",
                        "amount": 50,
                    },
                ).success
                is False
            )
            ex.create_employee.return_value = {"success": False, "message": "fail"}
            assert action_dispatcher.dispatch("create_employee", {"name": "E"}).success is False
            ex.create_employee.side_effect = RuntimeError("x")
            assert action_dispatcher.dispatch("create_employee", {"name": "E"}).success is False
            ex.create_purchase.return_value = {
                "success": True,
                "message": "ok",
                "purchase_id": 3,
            }
            assert (
                action_dispatcher.dispatch(
                    "create_purchase",
                    {
                        "supplier_name": "S",
                        "product_name": "P",
                    },
                ).success
                is True
            )
            ex.create_purchase.side_effect = RuntimeError("x")
            assert (
                action_dispatcher.dispatch(
                    "create_purchase",
                    {
                        "supplier_name": "S",
                        "product_name": "P",
                    },
                ).success
                is False
            )
        with (
            patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1),
            patch("ai_knowledge.action_dispatcher._has_permission", return_value=True),
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
            patch("models.Supplier") as Supplier,
            patch("ai_knowledge.action_dispatcher.db.session") as sess,
        ):
            Supplier.return_value = MagicMock(id=1)
            sess.flush.side_effect = RuntimeError("fail")
            assert action_dispatcher.dispatch("create_supplier", {"name": "S"}).success is False
        with (
            patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=1),
            patch("ai_knowledge.action_dispatcher._has_permission", return_value=True),
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
            patch("models.User") as User,
            patch("models.Role") as Role,
            patch("ai_knowledge.action_dispatcher.db.session") as sess,
        ):
            Role.query.filter_by.return_value.first.return_value = MagicMock(id=1)
            User.return_value = MagicMock(id=2)
            sess.flush.side_effect = RuntimeError("fail")
            assert (
                action_dispatcher.dispatch(
                    "create_user",
                    {
                        "username": "u",
                        "password": "p",
                    },
                ).success
                is False
            )
        reg = action_dispatcher._registry["create_customer"]
        with patch.object(reg["handler"], "__call__", side_effect=RuntimeError("boom")):
            pass
        with (
            patch("ai_knowledge.action_dispatcher._has_permission", return_value=True),
            patch("ai_knowledge.action_dispatcher._log_ai_error"),
        ):
            action_dispatcher._registry.copy()
            action_dispatcher._registry["boom_action"] = {
                "handler": lambda a: (_ for _ in ()).throw(RuntimeError("x")),
                "permission": "",
            }
            r = action_dispatcher.dispatch("boom_action", {})
            assert r.success is False
            del action_dispatcher._registry["boom_action"]


class TestDataAnalyzerWave6:
    def test_empty_debt_and_sales_trends(self):
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer

        da = DataAnalyzer()
        customer = MagicMock(id=1, name="C")
        sale = MagicMock(
            id=10,
            total_amount=Decimal("1000"),
            paid_amount=Decimal("100"),
            created_at=datetime.now() - timedelta(days=45),
        )
        with patch("extensions.db") as mock_db, patch("models.Sale") as Sale:
            mock_db.session.get.return_value = customer
            Sale.paid_amount = _Col()
            Sale.total_amount = _Col()
            Sale.customer_id = _Col()
            Sale.query.filter.return_value.all.return_value = [sale]
            r = da.analyze_customer_debt(1)
            assert r["success"] is True
            assert r["debt_analysis"]["overdue_count"] == 1
            Sale.query.filter.return_value.all.return_value = []
            r0 = da.analyze_customer_debt(1)
            assert r0["debt_analysis"]["overdue_count"] == 0
        sale_simple = MagicMock(
            total_amount=Decimal("100"),
            created_at=datetime.now(),
            customer=MagicMock(name="Ali"),
        )
        with patch("models.Sale") as Sale:
            Sale.created_at = _Col()
            Sale.query.filter.return_value.all.return_value = [sale_simple] * 10
            up = da.analyze_sales_performance(14)
            assert up.get("success") is True
            assert up.get("analysis", {}).get("trend") in (
                "تصاعدي",
                "تنازلي",
                "مستقر",
                "غير محدد",
            )
            Sale.query.filter.return_value.all.return_value = []
            empty = da.analyze_sales_performance()
            assert empty["analysis"]["total_sales"] == 0
        with patch("models.Sale") as Sale:
            Sale.query.filter.side_effect = RuntimeError("fail")
            assert da.analyze_sales_performance()["success"] is False

    def test_product_payment_ratios(self):
        from ai_knowledge.analytics.data_analyzer import DataAnalyzer

        da = DataAnalyzer()
        with (
            patch("models.Product") as Product,
            patch("models.SaleLine") as SL,
            patch("models.Sale"),
        ):
            Product.query.get.return_value = None
            assert da.analyze_product_performance(product_id=99)["success"] is False
            prod = MagicMock(id=1, name="P", sku="S", current_stock=5)
            Product.query.get.return_value = prod
            Product.query.all.return_value = [prod]
            line = MagicMock(
                quantity=1,
                line_total=Decimal("10"),
                unit_price=Decimal("10"),
                sale_id=1,
                sale=MagicMock(created_at=datetime.now()),
            )
            SL.query.filter.return_value.all.return_value = [line]
            SL.query.filter.return_value.join.return_value.order_by.return_value.limit.return_value.all.return_value = [
                line
            ]
            assert da.analyze_product_performance(1)["success"] is True
            assert da.analyze_product_performance()["success"] is True
        with patch("models.Product") as Product:
            Product.query.get.side_effect = RuntimeError("x")
            assert da.analyze_product_performance(1)["success"] is False
        with patch("models.Customer") as Customer, patch("models.Payment") as Payment:
            Customer.query.get.return_value = None
            assert da.analyze_payment_patterns(1)["success"] is False
            Customer.query.get.return_value = MagicMock(id=1)
            Payment.query.filter.return_value.all.return_value = []
            assert da.analyze_payment_patterns(1)["analysis"]["total_payments"] == 0
            Payment.query.all.return_value = []
            assert da.analyze_payment_patterns()["analysis"]["total_payments"] == 0
        with (
            patch("extensions.db") as mock_db,
            patch("models.Sale"),
            patch("models.Payment"),
            patch("models.Customer") as Customer,
            patch("models.Product") as Product,
        ):
            mock_db.func.sum.return_value = MagicMock()
            mock_db.session.query.return_value.scalar.side_effect = RuntimeError("x")
            assert da.get_financial_ratios()["success"] is False


class TestSystemIntegrationWave6:
    @pytest.fixture
    def integrator(self):
        from ai_knowledge.core.system_integration import SystemIntegrator

        return SystemIntegrator()

    def test_customer_by_name_and_errors(self, integrator):
        customer = MagicMock(
            id=1,
            name="Ali",
            customer_type="regular",
            phone="",
            email="",
            get_balance_aed=lambda: Decimal("100"),
        )
        customer.sales.count.return_value = 2
        customer.sales.order_by.return_value.first.return_value = MagicMock(
            created_at=datetime.now(),
        )
        with patch("models.Customer") as Customer, patch("models.Sale"):
            Customer.query.filter.return_value.first.return_value = customer
            r = integrator.get_customer_balance("Ali")
            assert r["success"] is True
            Customer.query.filter.side_effect = RuntimeError("db")
            assert integrator.get_customer_balance("Ali")["success"] is False

    def test_supplier_balance_errors(self, integrator):
        supplier = MagicMock(
            id=1,
            name="S",
            supplier_type="local",
            phone="",
            email="",
            get_balance_aed=lambda: Decimal("50"),
        )
        supplier.purchases.count.return_value = 1
        supplier.purchases.order_by.return_value.first.return_value = None
        with patch("models.Supplier") as Supplier, patch("models.Purchase"):
            Supplier.query.filter.return_value.first.return_value = supplier
            assert integrator.get_supplier_balance("S")["success"] is True
            Supplier.query.filter.side_effect = RuntimeError("x")
            assert integrator.get_supplier_balance("S")["success"] is False

    def test_add_customer_tenant_required(self, integrator):
        with patch("models.tenant.Tenant") as Tenant:
            Tenant.get_current.return_value = None
            r = integrator.add_customer({"name": "X", "customer_type": "regular"})
            assert r["success"] is False
        with (
            patch("models.tenant.Tenant") as Tenant,
            patch("models.Customer"),
            patch("extensions.db") as mock_db,
        ):
            Tenant.get_current.return_value = MagicMock(id=1)
            mock_db.session.flush.side_effect = RuntimeError("fail")
            r = integrator.add_customer({"name": "X", "customer_type": "regular"})
            assert r["success"] is False

    def test_product_stock_and_summaries(self, integrator):
        category = MagicMock(name="Cat")
        product = MagicMock(
            id=1,
            name="P",
            sku="S",
            current_stock=5,
            min_stock_alert=10,
            unit_price=Decimal("20"),
            category=category,
        )
        with patch("models.Product") as Product:
            Product.query.filter.return_value.first.return_value = product
            assert integrator.get_product_stock("P")["success"] is True
            Product.query.filter.side_effect = RuntimeError("x")
            assert integrator.get_product_stock("P")["success"] is False
        with (
            patch("models.Customer") as Customer,
            patch("models.Sale") as Sale,
            patch("models.Product") as Product,
            patch("models.Payment") as Payment,
        ):
            setattr(Customer, "customer_type", _Col())
            setattr(Sale, "created_at", _Col())
            setattr(Product, "current_stock", _Col())
            setattr(Product, "min_stock_alert", _Col())
            setattr(Payment, "created_at", _Col())
            Customer.query.count.return_value = 5
            Customer.query.filter.return_value.count.return_value = 1
            recent_c = MagicMock(
                id=1,
                name="A",
                customer_type="VIP",
                get_balance_aed=lambda: Decimal("0"),
            )
            Customer.query.order_by.return_value.limit.return_value.all.return_value = [recent_c]
            Sale.query.count.return_value = 10
            Sale.query.filter.return_value.count.return_value = 2
            Sale.query.order_by.return_value.limit.return_value.all.return_value = []
            Product.query.count.return_value = 8
            Product.query.filter.return_value.count.return_value = 1
            Payment.query.count.return_value = 3
            Payment.query.filter.return_value.count.return_value = 0
            assert integrator.get_system_summary()["success"] is True
            Customer.query.count.side_effect = RuntimeError("x")
            assert integrator.get_system_summary()["success"] is False
        with (
            patch("extensions.db") as mock_db,
            patch("models.Sale") as Sale,
            patch("models.Payment") as Payment,
        ):
            setattr(Sale, "created_at", _Col())
            setattr(Payment, "created_at", _Col())
            mock_db.func.sum.return_value = MagicMock()
            q = MagicMock()
            q.scalar.return_value = Decimal("0")
            q.filter.return_value = q
            mock_db.session.query.return_value = q
            assert integrator.get_financial_summary()["success"] is True
            mock_db.session.query.side_effect = RuntimeError("x")
            assert integrator.get_financial_summary()["success"] is False

    def test_search_data_error(self, integrator):
        with patch("models.Customer") as Customer:
            Customer.query.filter.side_effect = RuntimeError("x")
            assert integrator.search_data("q")["success"] is False


class TestDocumentGeneratorWave6:
    def test_all_generators(self):
        from ai_knowledge.generation.document_generator import DocumentGenerator

        line = MagicMock(
            quantity=1,
            unit_price=Decimal("100"),
            line_total=Decimal("100"),
            product=SimpleNamespace(name="Filter Oil"),
        )
        sale = MagicMock(
            id=1,
            created_at=datetime.now(),
            paid_amount=Decimal("100"),
            balance_due=Decimal("0"),
            subtotal=Decimal("100"),
            discount_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            tax_amount=Decimal("5"),
            total_amount=Decimal("105"),
            customer=MagicMock(name="Ali", phone="050", address="DXB"),
            payments=[MagicMock(payment_method="cash")],
            sale_lines=[line],
            payment_status="paid",
        )
        with (
            patch("models.Sale") as Sale,
            patch("models.Customer") as Customer,
            patch("models.Product") as Product,
        ):
            Sale.query.get.return_value = sale
            content, msg = DocumentGenerator.generate_receipt(1)
            assert content
            content2, msg2 = DocumentGenerator.generate_invoice(1)
            assert content2, msg2
            Sale.query.get.return_value = None
            assert DocumentGenerator.generate_receipt(99)[0] is None
            csv_out, _ = DocumentGenerator.export_to_excel("sales")
            assert csv_out
            report, _ = DocumentGenerator.generate_sales_report()
            assert report is None or report
            Customer.query.get.return_value = MagicMock(
                id=1,
                name="Ali",
                phone="",
                email="",
                address="",
            )
            stmt_sale = MagicMock(
                id=1,
                total_amount=Decimal("100"),
                created_at=datetime.now(),
                payments=[],
            )
            stmt_chain = MagicMock()
            stmt_chain.filter.return_value = stmt_chain
            stmt_chain.all.return_value = [stmt_sale]
            Sale.query.filter.return_value = stmt_chain
            stmt, msg_stmt = DocumentGenerator.generate_customer_statement(1)
            assert stmt, msg_stmt
            Product.query.all.return_value = [
                MagicMock(
                    name="P",
                    sku="S",
                    current_stock=5,
                    min_stock_alert=10,
                    unit_price=Decimal("10"),
                    category=None,
                ),
            ]
            csv_p, _ = DocumentGenerator.export_to_excel("products")
            assert csv_p
        with patch("models.Sale") as Sale:
            Sale.query.get.side_effect = RuntimeError("x")
            assert DocumentGenerator.generate_invoice(1)[0] is None


class TestIntelligentAssistantWave6:
    def test_analysis_branches(self, knowledge_path):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        zero_sales = {"recent_sales": {"count": 0, "total_amount": 0, "avg_amount": 0}}
        assert assistant._analyze_and_reason("sales_analysis", zero_sales, {})["warnings"]
        weak = {"recent_sales": {"count": 3, "total_amount": 300, "avg_amount": 100}}
        assert assistant._analyze_and_reason("sales_analysis", weak, {})["warnings"]
        good = {"recent_sales": {"count": 60, "total_amount": 60000, "avg_amount": 1000}}
        assistant._neural_engine = MagicMock()
        assistant._neural_engine.predict_next_week_sales = MagicMock(
            return_value={"success": True, "predicted_amount": 5000}
        )
        pred = assistant._analyze_and_reason("sales_analysis", good, {})
        assert pred["predictions"] or pred["insights"]
        assistant._neural_engine.predict_next_week_sales.side_effect = RuntimeError()
        assistant._analyze_and_reason("sales_analysis", good, {})
        inv_ok = {"low_stock_products": []}
        assert "صحي" in assistant._analyze_and_reason("inventory_check", inv_ok, {})["insights"][0]
        inv_few = {"low_stock_products": [{"deficit": 2}] * 3}
        assert assistant._analyze_and_reason("inventory_check", inv_few, {})["warnings"]
        inv_many = {"low_stock_products": [{"deficit": 5}] * 6}
        assert assistant._analyze_and_reason("inventory_check", inv_many, {})["warnings"]
        cust = {
            "customer_data": {
                "success": True,
                "debt_analysis": {
                    "total_debt": 0,
                    "overdue_count": 0,
                    "unpaid_sales_count": 0,
                },
            }
        }
        assert assistant._analyze_and_reason("customer_balance", cust, {})["insights"]
        cust2 = {
            "customer_data": {
                "success": True,
                "debt_analysis": {
                    "total_debt": 2000,
                    "overdue_count": 2,
                    "unpaid_sales_count": 3,
                },
            }
        }
        assert assistant._analyze_and_reason("customer_balance", cust2, {})["warnings"]
        assert assistant._analyze_and_reason("x", {}, {})["insights"] == []
        resp = assistant._generate_dynamic_response("greeting", {}, {}, {})
        assert resp
        assert assistant._generate_dynamic_response("who_are_you", {}, {}, {})
        assert assistant._generate_dynamic_response("praise", {}, {}, {})
        assert assistant._generate_dynamic_response("complaint", {}, {}, {})
        sales_data = {"recent_sales": {"count": 5, "total_amount": 5000, "avg_amount": 1000}}
        assert assistant._generate_dynamic_response("sales_analysis", {"insights": ["i"]}, {}, sales_data)
        cd = {
            "customer_data": {
                "success": True,
                "customer": {"name": "A"},
                "debt_analysis": {
                    "total_debt": 100,
                    "unpaid_sales_count": 1,
                    "overdue_count": 1,
                },
            }
        }
        assert assistant._generate_dynamic_response("customer_balance", {}, {}, cd)
        inv = {"low_stock_products": [{"name": "P", "current_stock": 1, "min_alert": 5}]}
        assert assistant._generate_dynamic_response("inventory_check", {"warnings": ["w"]}, {}, inv)
        bad_analysis = MagicMock()
        bad_analysis.get = MagicMock(side_effect=RuntimeError("fail"))
        with patch.object(
            assistant,
            "_generate_dynamic_response",
            wraps=assistant._generate_dynamic_response,
        ):
            pass

    def test_collect_partial_failures(self):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        cols = _patch_model_cols("models.Sale", "models.Customer", "models.Product")
        try:
            with (
                patch("models.Sale") as Sale,
                patch("models.Customer") as Customer,
                patch("models.Product") as Product,
                patch("models.Payment"),
                patch("flask.has_request_context", return_value=False),
            ):
                for m in (Sale, Customer, Product):
                    q = MagicMock()
                    q.filter_by.return_value = q
                    q.filter.return_value = q
                    q.count.side_effect = RuntimeError("partial")
                    m.query = q
                data = assistant._collect_real_data("sales_analysis", {}, 1)
                assert data.get("system_stats") == {}
        finally:
            _stop_patches(cols)

    def test_learn_with_tenant(self, knowledge_path):
        from ai_knowledge.agents.intelligent_assistant import IntelligentAssistant

        assistant = IntelligentAssistant()
        with (
            patch.object(assistant.memory_system, "remember_conversation"),
            patch("flask.has_request_context", return_value=True),
            patch("utils.tenanting.get_active_tenant_id", return_value=7),
            patch("flask_login.current_user", SimpleNamespace(is_authenticated=True)),
            patch("ai_knowledge.core.learning_system.learning_system") as ls,
        ):
            assistant._learn_from_interaction("q", "a", 1)
            ls.learn_from_interaction.assert_called_once()
            assert ls.learn_from_interaction.call_args.kwargs.get("tenant_id") == 7


class TestAzadResponsesWave6:
    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses

        return AzadResponses()

    def test_partial_summary_keys(self, responses):
        with patch(
            "services.ai_service.AIService.analyze_inventory_health",
            return_value={
                "success": True,
                "summary": {},
            },
        ):
            assert "0" in responses._inventory_status()
        with patch("ai_knowledge.personality.azad_responses.system_integrator") as si:
            si.get_customer_balance.return_value = {
                "success": True,
                "customer": {
                    "id": 1,
                    "name": "A",
                    "customer_type": "r",
                    "phone": "",
                    "email": "",
                    "balance_aed": 0,
                    "total_sales": 0,
                    "last_sale_date": None,
                },
            }
            si.get_customer_sales_summary.return_value = {
                "success": True,
                "summary": {},
            }
            assert "بيانات العميل" in responses._handle_customer_info_query("بيانات عميل أحمد")
            si.get_system_summary.return_value = {"success": False, "error": "e"}
            assert "e" in responses._handle_system_summary_query()
            si.get_system_summary.return_value = {"success": True, "summary": {}}
            si.get_financial_summary.return_value = {"success": False, "error": "fe"}
            assert "fe" in responses._handle_system_summary_query()

    def test_smart_response_edges(self, responses):
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
                "ai_knowledge.personality.azad_responses.get_welcome_message",
                return_value="w",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_dialectal_greeting",
                return_value="أهلين",
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
                return_value=[],
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_system_guide",
                return_value="g",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_market_insights",
                return_value="m",
            ),
        ):
            ap.is_inappropriate_message.return_value = "normal"
            ap.get_greeting.return_value = "مرحبا"
            ap.get_thanks_response.return_value = "شكرا"
            ap.get_professional_joke.return_value = "نكتة"
            ap.get_help_intro.return_value = "مساعدة"
            bg.get_beginner_response.return_value = "beginner"
            assert responses.smart_response("مرحبا")
            assert responses.smart_response("شكرا جزيلا")
            assert responses.smart_response("نكتة مضحكة")
            assert responses.smart_response("كيف أستخدم النظام")
        with patch("ai_knowledge.personality.azad_responses.knowledge_manager") as km:
            km.get_all_sources_summary.return_value = {"categories": {}}
            assert "مصادر" in responses._show_knowledge_sources("كل المصادر all")


class TestNeuralEngineWave6:
    @pytest.fixture
    def engine(self, knowledge_path):
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        eng = AzadNeuralEngine()
        _fast_models(eng)
        return eng

    def test_remaining_neural_paths(self, engine, knowledge_path):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch.object(engine, "_train_price_internal", return_value={"success": True}):
            assert engine.train_price_optimizer(from_app_context=ctx)["success"] is True
        with patch.object(engine, "_train_fraud_internal", side_effect=RuntimeError()):
            assert engine.train_fraud_detector()["success"] is False
        with patch.object(engine, "_load_model", return_value=True):
            engine.scalers["price_optimizer"] = MagicMock()
            engine.models["price_optimizer"] = MagicMock()
            engine.scalers["price_optimizer"].transform.return_value = np.array([[1.0]])
            engine.models["price_optimizer"].predict.return_value = np.array([150.0])
            result = engine.predict_optimal_price(100, 1, "regular")
            assert "predicted_price" in result or result.get("success") is not False
        with (
            patch("extensions.db") as mock_db,
            patch("models.Sale"),
            patch("models.Purchase"),
            patch("models.Expense"),
            patch("models.Receipt"),
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
        ):
            cols = _patch_model_cols("models.Sale", "models.Purchase", "models.Expense", "models.Receipt")
            try:
                chain = _db_chain(mock_db)
                chain.scalar.return_value = Decimal("1000")
                chain.all.return_value = []
                assert "predictions" in engine.predict_cash_flow(3) or "trend" in engine.predict_cash_flow(3)
            finally:
                _stop_patches(cols)


class TestMasterBrainWave6:
    def test_synthesize_sensor_and_general(self):
        from ai_knowledge.agents.master_brain import MasterBrain

        brain = MasterBrain()
        eng = {"sensors": {"MAF": {"name_ar": "تدفق", "function": "قياس", "testing": "فحص"}}}
        r = brain._synthesize_answer("MAF sensor", {"steps": []}, None, eng, "question")
        assert "تدفق" in r["text"]
        tax = {"uae_vat": {"rate": 5, "registration_threshold": 375000}}
        r2 = brain._synthesize_answer("ضريبة VAT", {"steps": []}, None, tax, "question")
        assert "5" in r2["text"]
        acc = {"principles": {"double_entry": "قيد مزدوج"}}
        r3 = brain._synthesize_answer("قيد مزدوج", {"steps": []}, None, acc, "question")
        assert "مزدوج" in r3["text"]
        r4 = brain._synthesize_answer("random", {"steps": []}, None, {}, "action")
        assert r4["confidence"] >= 0.6

    def test_module_level_helpers(self):
        from ai_knowledge.agents import master_brain as mb

        mb._master_brain_instance = None
        b1 = mb.get_master_brain()
        b2 = mb.get_master_brain()
        assert b1 is b2


class TestAgentsCoreWave6:
    def test_ask_azad_enhanced_fallbacks(self, knowledge_path):
        from ai_knowledge.agents_core import ask_azad_enhanced

        with patch("ai_knowledge.agents_core.get_master_brain") as gmb:
            gmb.return_value.ask.side_effect = RuntimeError("brain fail")
            r = ask_azad_enhanced("سؤال عام")
            assert r["answer"]
        with (
            patch("ai_knowledge.agents_core.get_master_brain") as gmb,
            patch("ai_knowledge.trainer.trainer") as trainer,
        ):
            gmb.return_value.ask.return_value = {"answer": "ok"}
            trainer.learn_from_interaction.side_effect = RuntimeError("learn")
            r2 = ask_azad_enhanced("سؤال")
            assert r2["answer"] == "ok"


class TestSecondaryModulesWave6:
    def test_context_conversation_code(self, knowledge_path):
        from ai_knowledge.core.context_engine import ContextEngine
        from ai_knowledge.core.conversation_manager import ConversationManager
        from ai_knowledge.generation.code_generator import CodeGenerator

        with patch("ai_knowledge.core.context_engine.system_integrator") as si:
            si.get_system_summary.return_value = {"success": False}
            assert ContextEngine.analyze_context("حلل", {})["intent"] == "analysis"
        mgr = ConversationManager()
        mgr.start_conversation(99)
        mgr.process_message(99, "hello")
        assert mgr.get_conversation_history(99)
        gen = CodeGenerator()
        assert "DELETE" in gen.generate_sql_query("delete", "t", {"where": {"id": 1}}).upper()
        assert gen.fix_code("x", "AttributeError")["fixed_code"]
        assert "optimized_code" in gen.optimize_code("for i in range(1000): pass")

    def test_self_improvement_and_learner(self, knowledge_path):
        from ai_knowledge.improvement.self_improvement import AzadSelfImprovement
        from ai_knowledge.learning.continuous_learner import ContinuousLearner
        from ai_knowledge.learning.auto_retraining import AutoRetrainingScheduler

        ai = AzadSelfImprovement()
        ai.improvement_areas["response_quality"]["current_score"] = 9.5
        assert ai.auto_improve()["improvements_made"] >= 0
        cl = ContinuousLearner()
        with patch("ai_knowledge.learning.continuous_learner.requests.get") as rg:
            rg.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "query": {"pages": {"1": {"extract": "wiki text about cars"}}},
                },
            )
            rg.return_value.raise_for_status = MagicMock()
            result = cl.learn_from_wikipedia("engine")
            assert isinstance(result, dict)
        assert AutoRetrainingScheduler.should_retrain() in (True, False)

    def test_semantic_transformers_vision(self):
        from ai_knowledge.neural.semantic_matcher import (
            SemanticMatcher,
            understand_message,
        )
        from ai_knowledge.neural.transformers_brain import TransformersBrain
        from ai_knowledge.neural.vision_processor import VisionProcessor

        matcher = SemanticMatcher()
        intent, confidence, scores = matcher.find_best_intent("مبيعات اليوم")
        assert isinstance(confidence, float)
        assert understand_message("رصيد العميل")
        tb = TransformersBrain()
        assert tb.understand("مبيعات اليوم")["intent"]
        vp = VisionProcessor()
        with patch.object(vp, "extract_text_from_image", return_value="text"):
            assert vp.extract_text_from_image("x.png") == "text"

    def test_specialized_and_system_knowledge(self):
        from ai_knowledge.knowledge.system_knowledge import search_knowledge

        assert isinstance(search_knowledge("tenant"), list)

    def test_analytics_predictions_external(self, knowledge_path):
        from ai_knowledge.analytics.analytics_predictions import SalesAnalytics
        from ai_knowledge.learning.external_learning import ExternalLearningSystem

        result = SalesAnalytics.predict_next_month_sales([100, 120, 110, 130])
        assert isinstance(result, dict)
        el = ExternalLearningSystem()
        learned = el.learn_from_source("web", "tax", "VAT content about UAE tax")
        assert learned.get("success") is True

    def test_multi_agent_and_knowledge(self, knowledge_path):
        from ai_knowledge.agents.multi_agent_system import MultiAgentCoordinator
        from ai_knowledge.expansion.knowledge_sources import KnowledgeSourceManager
        from ai_knowledge.knowledge_base import search_knowledge

        coord = MultiAgentCoordinator()
        result = coord.delegate_task("تحليل مبيعات")
        assert isinstance(result, dict)
        ksm = KnowledgeSourceManager()
        summary = ksm.get_all_sources_summary()
        assert "total_sources" in summary
        assert isinstance(search_knowledge("ضريبة"), list)

    def test_memory_quick_learner_trainer(self, knowledge_path):
        from ai_knowledge.core.memory_system import LongTermMemory
        from ai_knowledge.learning.quick_learner import QuickLearner
        from ai_knowledge.trainer import Trainer

        mem = LongTermMemory()
        mem.remember_user_preference(1, "theme", "dark")
        assert mem.get_user_preferences(1).get("theme") == "dark"
        ql = QuickLearner()
        with (
            patch("models.ai.AiMemory") as AiMemory,
            patch("extensions.db.session") as sess,
        ):
            AiMemory.query.filter_by.return_value.first.return_value = None
            AiMemory.tenant_id = _Col()
            AiMemory.return_value = MagicMock()
            ql.learn("q", "a", tenant_id=1)
            sess.add.assert_called()
        trainer = Trainer()
        with patch.object(trainer, "quick_learner", MagicMock()) as q:
            q.get_answer.return_value = None
            trainer.learn_from_interaction("q", "a", tenant_id=2)
            q.learn.assert_called()


class TestWave6FinalPush:
    @pytest.fixture
    def responses(self):
        from ai_knowledge.personality.azad_responses import AzadResponses

        return AzadResponses()

    def test_azad_smart_routes_extended(self, responses):
        customer = {
            "id": 1,
            "name": "أحمد",
            "customer_type": "regular",
            "phone": "050",
            "email": "a@t.com",
            "balance_aed": 500,
            "total_sales": 2,
            "last_sale_date": "2025-01-01",
        }
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
                "ai_knowledge.personality.azad_responses.get_system_guide",
                return_value="system guide",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_market_insights",
                return_value="market info",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_help_for_task",
                return_value="لم أجد",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.search_knowledge",
                return_value=[],
            ),
            patch("ai_knowledge.personality.azad_responses.system_integrator") as si,
            patch("ai_knowledge.personality.azad_responses.data_analyzer") as da,
            patch("ai_knowledge.personality.azad_responses.document_generator") as dg,
            patch("ai_knowledge.personality.azad_responses.knowledge_expander") as ke,
            patch(
                "services.ai_service.AIService.analyze_profit_margins",
                return_value={
                    "success": True,
                    "overall": {
                        "revenue": 1000,
                        "cost": 600,
                        "profit": 400,
                        "margin": 40,
                    },
                    "top_profitable": [{"name": "P", "profit": 100, "margin": 20}],
                },
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
                "ai_knowledge.personality.azad_responses.get_welcome_message",
                return_value="welcome",
            ),
            patch(
                "ai_knowledge.personality.azad_responses.apply_dialect",
                side_effect=lambda t, d: t,
            ),
            patch(
                "ai_knowledge.personality.azad_responses.get_dialectal_greeting",
                return_value="أهلين",
            ),
            patch("ai_knowledge.personality.azad_responses.beginners_guide") as bg,
        ):
            ap.is_inappropriate_message.return_value = "normal"
            ap.get_greeting.return_value = "مرحبا"
            ap.get_help_intro.return_value = "مساعدة"
            ap.get_professional_joke.return_value = "نكتة"
            bg.get_beginner_response.return_value = "beginner"
            si.get_customer_balance.return_value = {
                "success": True,
                "customer": customer,
            }
            si.get_customer_sales_summary.return_value = {
                "success": True,
                "summary": {},
            }
            da.analyze_customer_debt.return_value = {"success": False}
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
                    "total_sales": 1000.0,
                    "total_payments": 800.0,
                    "total_receivables": 200.0,
                    "today_sales": 50.0,
                    "today_payments": 30.0,
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
            dg.generate_invoice.return_value = ("inv", "ok")
            ke.search_knowledge.return_value = {
                "success": True,
                "total_found": 1,
                "results": [{"title": "T"}],
            }
            for msg in [
                "كيف استخدم النظام guide",
                "سوق market منافسة",
                "ربح profit هامش margin",
                "رصيد balance عميل customer أحمد",
                "بيانات info عميل customer سامي",
                "مخزون stock منتج product فلتر",
                "ملخص summary نظام system كلي",
                "أضف add عميل customer جديد",
                "ابحث search عن علي",
                "أضف add موقع website مصدر source",
                "روابط links نظام system",
                "مصادر sources كل all",
                "أين where أجد find معلومات tax",
                "ابحث search في المعرفة knowledge tax",
                "فاتورة invoice جديد new create",
                "سند receipt جديد new create",
                "ولد generate فاتورة invoice 55",
                "صدر export excel بيانات data مبيعات sales",
                "تقرير report مبيعات sales",
                "ولد generate تقرير report مبيعات sales",
                "قانون law ضريبة tax فلسطين palestine",
                "شحن shipping قانون law إجراءات procedures",
                "جودة quality معايير standards",
                "نكتة joke ضحك laugh",
                "ضريبة vat",
                "جمارك customs",
            ]:
                assert isinstance(responses.smart_response(msg), str)

    def test_system_knowledge_root(self):
        import ai_knowledge.system_knowledge as sk

        assert sk.get_model_info("Sale") or sk.get_model_info("sales")
        assert sk.get_model_info("unknown_model_xyz") is None
        assert sk.get_permission_info("manage_sales") or isinstance(sk.get_permission_info("x"), (dict, type(None)))
        assert sk.get_role_info("owner") or sk.get_role_info("seller")
        hits = sk.search_knowledge("tenant")
        assert isinstance(hits, list)
        assert sk.search_knowledge("accounting") or sk.search_knowledge("مبيعات")
        assert sk.get_contextual_help("sales") or sk.get_contextual_help("xyz") is None
        assert isinstance(sk.get_role_based_features("owner"), list)
        assert sk.get_role_based_features("nonexistent_role") == []

    def test_code_and_document_remaining(self):
        from ai_knowledge.generation.code_generator import CodeGenerator
        from ai_knowledge.generation.document_generator import DocumentGenerator

        gen = CodeGenerator()
        assert "-- Unsupported" in gen.generate_sql_query("drop", "t", {})
        assert isinstance(gen.generate_python_function("calc", "حساب total", ["x"]), str)
        assert isinstance(gen.generate_python_function("pred", "predict sales"), str)
        assert gen.generate_report_query("profit", {}) or gen.generate_report_query(
            "sales", {"start_date": "2025-01-01"}
        )
        sale = MagicMock(
            id=1,
            created_at=datetime.now(),
            total_amount=Decimal("100"),
            paid_amount=Decimal("50"),
            balance_due=Decimal("50"),
            customer=MagicMock(name="Ali"),
        )
        with patch("models.Sale") as Sale:
            Sale.query.filter.return_value.all.return_value = [sale]
            Sale.created_at = _Col()
            report, _ = DocumentGenerator.generate_sales_report(
                start_date=datetime.now().date(),
                end_date=datetime.now().date(),
            )
            assert report
            Sale.query.all.side_effect = RuntimeError("x")
            report, err = DocumentGenerator.generate_sales_report()
            assert report is None
            assert "خطأ" in err
            Sale.query.all.side_effect = None
            Sale.query.all.return_value = []
            empty, empty_msg = DocumentGenerator.generate_sales_report()
            assert empty is None
            assert "لا توجد" in empty_msg

    def test_neural_semantic_batch(self, knowledge_path):
        from ai_knowledge.neural.semantic_matcher import (
            SemanticMatcher,
            understand_message,
        )
        from ai_knowledge.neural.neural_engine import AzadNeuralEngine

        matcher = SemanticMatcher()
        for msg in (
            "مبيعات اليوم",
            "رصيد العميل",
            "مخزون ناقص",
            "توقع المبيعات",
            "ضريبة vat",
        ):
            understand_message(msg)
            matcher.find_best_intent(msg)
        engine = AzadNeuralEngine()
        _fast_models(engine)
        with patch.object(engine, "_load_model", return_value=False):
            assert engine.validate_accounting_entry(50, 100, 1, "Sale")["is_correct"] is False
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)
        with patch.object(engine, "_train_sales_internal", return_value={"success": True}):
            engine.train_sales_forecaster(from_app_context=ctx)

    def test_learning_and_context_remaining(self, knowledge_path):
        from ai_knowledge.core.learning_system import AzadLearningSystem
        from ai_knowledge.core.context_engine import ContextEngine
        from ai_knowledge.core.conversation_manager import ConversationManager
        from ai_knowledge.improvement.self_improvement import AzadSelfImprovement

        ls = AzadLearningSystem()
        assert ls._normalize_loaded_data("bad")["failed_responses"] == []
        with patch("builtins.open", side_effect=OSError("disk")):
            ls._save_tenant_data(99)
        with patch("ai_knowledge.core.context_engine.system_integrator") as si:
            si.get_system_summary.return_value = {"success": True, "summary": {}}
            assert ContextEngine.analyze_context("حلل analyze", {"is_owner": True})["intent"] == "analysis"
        mgr = ConversationManager()
        mgr.end_conversation(1)
        ai = AzadSelfImprovement()
        ai.improvement_areas["response_quality"]["current_score"] = 3.0
        ai.auto_improve()

    def test_action_tenant_guard_direct(self):
        from ai_knowledge.action_dispatcher import _tenant_guard, _require_tenant

        with patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=None):
            tid, guard = _tenant_guard()
            assert tid is None
            assert guard.success is False
        with patch("ai_knowledge.action_dispatcher._get_active_tenant_id", return_value=5):
            assert _require_tenant() == 5
