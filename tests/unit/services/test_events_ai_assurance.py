"""Events AI service — learning handlers, predictions, TESTING guards."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock


def _mock_learning(mocker):
    ls = MagicMock()
    mocker.patch(
        "ai_knowledge.core.learning_system.AzadLearningSystem", return_value=ls
    )
    return ls


class TestSaleLearning:
    """_learn_sale_patterns / _comprehensive_sale_analysis — discount math."""

    def test_learn_sale_patterns_zero_subtotal_discount(self, mocker):
        ls = _mock_learning(mocker)
        target = MagicMock(
            id=1,
            sale_number="S-1",
            customer_id=2,
            amount_aed=Decimal("100"),
            subtotal=Decimal("0"),
            discount_amount=Decimal("0"),
            payment_status="paid",
            sale_date=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
            lines=[],
        )
        from services.events_ai_service import _learn_sale_patterns

        _learn_sale_patterns(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_learn_sale_patterns_missing_sale_date(self, mocker):
        ls = _mock_learning(mocker)
        target = MagicMock(
            id=3,
            sale_number="S-3",
            customer_id=1,
            amount_aed=Decimal("50"),
            subtotal=Decimal("50"),
            discount_amount=Decimal("0"),
            payment_status="paid",
            sale_date=None,
            lines=[],
        )
        from services.events_ai_service import _learn_sale_patterns

        _learn_sale_patterns(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_comprehensive_sale_large_amount_anomaly(self, mocker):
        ls = _mock_learning(mocker)
        target = MagicMock(
            id=1,
            sale_number="S-2",
            amount_aed=Decimal("60000"),
            discount_amount=Decimal("0"),
            subtotal=Decimal("60000"),
            lines=[],
        )
        from services.events_ai_service import _comprehensive_sale_analysis

        _comprehensive_sale_analysis(None, None, target)
        assert ls.learn_from_interaction.call_args[1]["user_feedback"] == 3

    def test_comprehensive_sale_large_discount_anomaly(self, mocker):
        ls = _mock_learning(mocker)
        line = MagicMock(cost_price=Decimal("10"), quantity=Decimal("1"))
        target = MagicMock(
            id=1,
            sale_number="S-2B",
            amount_aed=Decimal("100"),
            discount_amount=Decimal("60"),
            subtotal=Decimal("100"),
            lines=[line],
        )
        from services.events_ai_service import _comprehensive_sale_analysis

        _comprehensive_sale_analysis(None, None, target)
        assert ls.learn_from_interaction.call_args[1]["user_feedback"] == 3


class TestCustomerAndStock:
    """_customer_analysis / _detect_stock_anomaly — alert branches."""

    def test_customer_high_balance_alert(self, mocker):
        _mock_learning(mocker)
        target = MagicMock(
            id=5,
            balance=Decimal("15000"),
            total_purchases=Decimal("0"),
            customer_classification="regular",
            credit_limit=Decimal("0"),
        )
        from services.events_ai_service import _customer_analysis

        _customer_analysis(None, None, target)

    def test_detect_stock_anomaly_low_stock(self, mocker):
        target = MagicMock(id=1, name="Item", current_stock=2, min_stock_alert=10)
        from services.events_ai_service import _detect_stock_anomaly

        _detect_stock_anomaly(None, None, target)


class TestPredictions:
    """Neural/inventory handlers — branches without heavy ORM imports."""

    def test_neural_inventory_out_of_stock(self, mocker):
        target = MagicMock(id=1, current_stock=0, min_stock_alert=5)
        from services.events_ai_service import _neural_inventory_learning

        _neural_inventory_learning(None, None, target)

    def test_intelligent_inventory_alert_recommends_reorder(self, mocker):
        target = MagicMock(id=1, name="Widget", current_stock=2, min_stock_alert=10)
        from services.events_ai_service import _intelligent_inventory_alert

        _intelligent_inventory_alert(None, None, target)

    def test_learn_expense_patterns_calls_learning(self, mocker):
        ls = _mock_learning(mocker)
        target = MagicMock(
            category_id=1,
            amount_aed=Decimal("50"),
            payment_method="cash",
            is_recurring=False,
        )
        from services.events_ai_service import _learn_expense_patterns

        _learn_expense_patterns(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_intelligent_sale_analysis_skips_in_testing(self, mocker):
        mock_app = MagicMock()
        mock_app.config.get.return_value = True
        mocker.patch("flask.current_app", mock_app, create=True)
        target = MagicMock(
            status="confirmed",
            is_active=True,
            amount_aed=100,
            lines=[],
            sale_number="S",
        )
        from services.events_ai_service import _intelligent_sale_analysis

        _intelligent_sale_analysis(None, None, target)


class TestRegistration:
    """Extra learning handlers for coverage."""

    def test_learn_product_terminology(self, mocker):
        ls = _mock_learning(mocker)
        target = SimpleNamespace(
            id=1,
            name="Phone",
            name_ar="هاتف",
            commercial_name="XPhone",
            part_number="P1",
            category=None,
        )
        from services.events_ai_service import _learn_product_terminology

        _learn_product_terminology(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_learn_sales_practices(self, mocker):
        ls = _mock_learning(mocker)
        target = SimpleNamespace(
            sale_number="S-9",
            amount_aed=Decimal("200"),
            paid_amount_aed=Decimal("200"),
            payment_status="paid",
            discount_amount=Decimal("0"),
            subtotal=Decimal("200"),
            shipping_cost=Decimal("0"),
            tax_amount=Decimal("0"),
        )
        from services.events_ai_service import _learn_sales_practices

        _learn_sales_practices(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_learn_revenue_recognition(self, mocker):
        ls = _mock_learning(mocker)
        target = SimpleNamespace(
            sale_number="S-10",
            amount_aed=Decimal("300"),
            status="confirmed",
            paid_amount_aed=Decimal("100"),
            balance_due=Decimal("200"),
        )
        from services.events_ai_service import _learn_revenue_recognition

        _learn_revenue_recognition(None, None, target)
        ls.learn_from_interaction.assert_called_once()


class TestMoreHandlers:
    """Additional AI handlers for coverage depth."""

    def test_learn_product_performance_low_stock(self, mocker):
        ls = _mock_learning(mocker)
        target = SimpleNamespace(
            id=1,
            name="Cable",
            current_stock=Decimal("1"),
            min_stock_alert=Decimal("5"),
            cost_price=Decimal("10"),
            regular_price=Decimal("20"),
        )
        from services.events_ai_service import _learn_product_performance

        _learn_product_performance(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_learn_customer_names(self, mocker):
        ls = _mock_learning(mocker)
        target = SimpleNamespace(
            name="Ahmad",
            name_ar="أحمد",
            customer_type="retail",
            phone="050",
            email="a@b.com",
        )
        from services.events_ai_service import _learn_customer_names

        _learn_customer_names(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_learn_procurement_strategy(self, mocker):
        ls = _mock_learning(mocker)
        target = SimpleNamespace(
            supplier_id=3,
            amount_aed=Decimal("1000"),
            payment_method="credit",
            status="open",
            purchase_number="P-1",
        )
        from services.events_ai_service import _learn_procurement_strategy

        _learn_procurement_strategy(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_learn_expense_recognition(self, mocker):
        ls = _mock_learning(mocker)
        target = SimpleNamespace(
            purchase_number="P-2",
            amount_aed=Decimal("400"),
            status="confirmed",
            paid_amount_aed=Decimal("100"),
        )
        from services.events_ai_service import _learn_expense_recognition

        _learn_expense_recognition(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_learn_accounting_entries_balanced(self, mocker):
        ls = _mock_learning(mocker)
        target = SimpleNamespace(
            entry_number="JE-1",
            total_debit=Decimal("100"),
            total_credit=Decimal("100"),
            reference_type="sale",
            reference_id=1,
            lines=[],
        )
        target.is_balanced = lambda: True
        ins = MagicMock()
        ins.unloaded = ["lines"]
        mocker.patch("sqlalchemy.inspect", return_value=ins)
        from services.events_ai_service import _learn_accounting_entries

        _learn_accounting_entries(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_comprehensive_sale_high_margin_insight(self, mocker):
        ls = _mock_learning(mocker)
        line = SimpleNamespace(cost_price=Decimal("10"), quantity=Decimal("1"))
        target = SimpleNamespace(
            id=2,
            sale_number="S-H",
            amount_aed=Decimal("100"),
            discount_amount=Decimal("0"),
            subtotal=Decimal("100"),
            lines=[line],
        )
        from services.events_ai_service import _comprehensive_sale_analysis

        _comprehensive_sale_analysis(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_customer_vip_candidate_alert(self, mocker):
        _mock_learning(mocker)
        target = SimpleNamespace(
            id=8,
            balance=Decimal("0"),
            total_purchases=Decimal("150000"),
            customer_classification="regular",
            credit_limit=Decimal("0"),
        )
        from services.events_ai_service import _customer_analysis

        _customer_analysis(None, None, target)

    def test_detect_stock_anomaly_high_stock(self, mocker):
        target = SimpleNamespace(
            id=2,
            name="Slow",
            current_stock=Decimal("2000"),
            min_stock_alert=Decimal("10"),
        )
        from services.events_ai_service import _detect_stock_anomaly

        _detect_stock_anomaly(None, None, target)

    def test_intelligent_sale_analysis_profit_insights(self, mocker):
        mock_app = MagicMock()
        mock_app.config.get.return_value = False
        mocker.patch("flask.current_app", mock_app, create=True)
        line = SimpleNamespace(cost_price=Decimal("80"), quantity=Decimal("1"))
        customer = SimpleNamespace(customer_type="retail")
        target = SimpleNamespace(
            status="confirmed",
            is_active=True,
            amount_aed=Decimal("100"),
            lines=[line],
            sale_number="S-PROFIT",
            customer=customer,
            payment_status="paid",
        )
        from services.events_ai_service import _intelligent_sale_analysis

        _intelligent_sale_analysis(None, None, target)

    def test_intelligent_customer_monitoring_debt(self, mocker):
        mock_app = MagicMock()
        mock_app.config.get.return_value = False
        mocker.patch("flask.current_app", mock_app, create=True)
        analyzer = MagicMock()
        analyzer.analyze_customer_debt.return_value = {
            "success": True,
            "debt_analysis": {"total_debt": 15000, "overdue_count": 4},
        }
        mocker.patch("ai_knowledge.analytics.data_analyzer.data_analyzer", analyzer)
        target = SimpleNamespace(id=12)
        from services.events_ai_service import _intelligent_customer_monitoring

        _intelligent_customer_monitoring(None, None, target)

    def test_register_ai_event_listeners(self, app, mocker):
        listens = mocker.patch("sqlalchemy.event.listens_for")
        from services.events_ai_service import register_ai_event_listeners

        with app.app_context():
            register_ai_event_listeners()
        assert listens.call_count >= 10

    def test_register_neural_event_listeners(self, app, mocker):
        listens = mocker.patch("sqlalchemy.event.listens_for")
        from services.events_ai_service import register_neural_event_listeners

        with app.app_context():
            register_neural_event_listeners()
        assert listens.call_count >= 3


class TestPredictionHandlers:
    def test_predict_future_sales_with_data(self, mocker):
        from decimal import Decimal

        rows = [SimpleNamespace(amount_aed=Decimal("100")) for _ in range(12)]
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = rows
        from services.events_ai_service import _predict_future_sales

        _predict_future_sales(None, conn, MagicMock())

    def test_predict_stockout_imminent(self, mocker):
        from decimal import Decimal

        mov = SimpleNamespace(quantity=Decimal("-30"))
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [mov] * 5
        target = SimpleNamespace(
            id=1, name="Part", current_stock=Decimal("3"), min_stock_alert=Decimal("10")
        )
        from services.events_ai_service import _predict_stockout

        _predict_stockout(None, conn, target)

    def test_predict_customer_churn_high_risk(self, mocker):
        ls = _mock_learning(mocker)
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        conn = MagicMock()
        conn.execute.return_value.first.return_value = SimpleNamespace(sale_date=old)
        target = SimpleNamespace(id=20)
        from services.events_ai_service import _predict_customer_churn

        _predict_customer_churn(None, conn, target)
        ls.learn_from_interaction.assert_called_once()

    def test_predict_customer_churn_medium_risk(self, mocker):
        _mock_learning(mocker)
        old = datetime.now(timezone.utc) - __import__("datetime").timedelta(days=70)
        conn = MagicMock()
        conn.execute.return_value.first.return_value = SimpleNamespace(sale_date=old)
        from services.events_ai_service import _predict_customer_churn

        _predict_customer_churn(None, conn, SimpleNamespace(id=21))

    def test_predict_customer_churn_naive_datetime(self, mocker):
        _mock_learning(mocker)
        naive = datetime(2024, 1, 1)
        conn = MagicMock()
        conn.execute.return_value.first.return_value = SimpleNamespace(sale_date=naive)
        from services.events_ai_service import _predict_customer_churn

        _predict_customer_churn(None, conn, SimpleNamespace(id=22))


class TestNeuralHandlers:
    def test_neural_auto_retrain_milestone(self, mocker, app):
        rows = [MagicMock()] * 100
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = rows
        mocker.patch("ai_knowledge.learning.auto_retraining.AutoRetrainingScheduler")
        mocker.patch("threading.Thread")
        from services.events_ai_service import _neural_auto_retrain

        with app.app_context():
            _neural_auto_retrain(None, conn, MagicMock())

    def test_neural_customer_data_milestone(self, mocker):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [MagicMock()] * 50
        from services.events_ai_service import _neural_customer_data

        _neural_customer_data(None, conn, MagicMock())

    def test_neural_inventory_low_stock(self, mocker):
        target = SimpleNamespace(id=3, current_stock=2, min_stock_alert=10)
        from services.events_ai_service import _neural_inventory_learning

        _neural_inventory_learning(None, None, target)


class TestErrorPaths:
    def test_learn_sale_patterns_logs_error(self, mocker):
        mocker.patch(
            "ai_knowledge.core.learning_system.AzadLearningSystem",
            side_effect=RuntimeError("boom"),
        )
        target = MagicMock(sale_date=None, lines=None)
        from services.events_ai_service import _learn_sale_patterns

        _learn_sale_patterns(None, None, target)

    def test_customer_analysis_learning_unavailable(self, mocker):
        mocker.patch(
            "ai_knowledge.core.learning_system.AzadLearningSystem",
            side_effect=RuntimeError("down"),
        )
        target = SimpleNamespace(
            id=1,
            balance=Decimal("0"),
            total_purchases=Decimal("0"),
            customer_classification="regular",
            credit_limit=Decimal("100"),
        )
        from services.events_ai_service import _customer_analysis

        _customer_analysis(None, None, target)

    def test_customer_credit_limit_exceeded(self, mocker):
        _mock_learning(mocker)
        target = SimpleNamespace(
            id=6,
            balance=Decimal("500"),
            total_purchases=Decimal("0"),
            customer_classification="regular",
            credit_limit=Decimal("100"),
        )
        from services.events_ai_service import _customer_analysis

        _customer_analysis(None, None, target)

    def test_comprehensive_sale_low_margin(self, mocker):
        ls = _mock_learning(mocker)
        line = SimpleNamespace(cost_price=Decimal("95"), quantity=Decimal("1"))
        target = SimpleNamespace(
            id=1,
            sale_number="S-L",
            amount_aed=Decimal("100"),
            discount_amount=Decimal("0"),
            subtotal=Decimal("100"),
            lines=[line],
        )
        from services.events_ai_service import _comprehensive_sale_analysis

        _comprehensive_sale_analysis(None, None, target)
        ls.learn_from_interaction.assert_called_once()

    def test_learn_accounting_entries_unbalanced(self, mocker):
        ls = _mock_learning(mocker)
        target = SimpleNamespace(
            entry_number="JE-2",
            total_debit=Decimal("100"),
            total_credit=Decimal("50"),
            reference_type="sale",
            reference_id=1,
            lines=[1, 2],
        )
        target.is_balanced = lambda: False
        ins = MagicMock()
        ins.unloaded = []
        mocker.patch("sqlalchemy.inspect", return_value=ins)
        from services.events_ai_service import _learn_accounting_entries

        _learn_accounting_entries(None, None, target)
        assert ls.learn_from_interaction.call_args[1]["user_feedback"] == 1

    def test_intelligent_sale_analysis_large_invoice(self, mocker):
        mock_app = MagicMock()
        mock_app.config.get.return_value = False
        mocker.patch("flask.current_app", mock_app, create=True)
        line = SimpleNamespace(cost_price=Decimal("10"), quantity=Decimal("1"))
        customer = SimpleNamespace(customer_type="vip")
        target = SimpleNamespace(
            status="confirmed",
            is_active=True,
            amount_aed=Decimal("15000"),
            lines=[line] * 12,
            sale_number="S-BIG",
            customer=customer,
            payment_status="paid",
        )
        from services.events_ai_service import _intelligent_sale_analysis

        _intelligent_sale_analysis(None, None, target)

    def test_intelligent_inventory_alert_stock_positive(self, mocker):
        target = SimpleNamespace(id=4, name="Bolt", current_stock=3, min_stock_alert=10)
        from services.events_ai_service import _intelligent_inventory_alert

        _intelligent_inventory_alert(None, None, target)

    def test_learn_product_terminology_with_category(self, mocker):
        ls = _mock_learning(mocker)
        cat = SimpleNamespace(name="Electronics")
        target = SimpleNamespace(
            id=2,
            name="Laptop",
            name_ar="حاسوب",
            commercial_name="Pro",
            part_number="L1",
            category=cat,
        )
        from services.events_ai_service import _learn_product_terminology

        _learn_product_terminology(None, None, target)
        ls.learn_from_interaction.assert_called_once()


class TestHandlerExceptions:
    def test_outer_exception_handlers(self, mocker):
        targets = {
            "_learn_sale_patterns": MagicMock(
                sale_date=None,
                lines=None,
                subtotal=0,
                discount_amount=0,
                amount_aed=1,
                sale_number="S",
            ),
            "_customer_analysis": SimpleNamespace(
                id=1,
                balance=0,
                total_purchases=0,
                customer_classification="r",
                credit_limit=0,
            ),
            "_learn_product_performance": SimpleNamespace(
                id=1,
                name="X",
                current_stock=1,
                min_stock_alert=0,
                cost_price=1,
                regular_price=2,
            ),
            "_detect_stock_anomaly": SimpleNamespace(
                id=1,
                name="X",
                current_stock=1,
                min_stock_alert=0,
            ),
            "_comprehensive_sale_analysis": SimpleNamespace(
                id=1,
                sale_number="S",
                amount_aed=1,
                discount_amount=0,
                subtotal=1,
                lines=[],
            ),
            "_learn_product_terminology": SimpleNamespace(
                id=1,
                name="X",
                name_ar=None,
                commercial_name=None,
                part_number=None,
                category=None,
            ),
            "_learn_customer_names": SimpleNamespace(
                name="A",
                name_ar=None,
                customer_type="r",
                phone=None,
                email=None,
            ),
            "_learn_sales_practices": SimpleNamespace(
                sale_number="S",
                amount_aed=1,
                paid_amount_aed=1,
                payment_status="paid",
                discount_amount=0,
                subtotal=1,
                shipping_cost=0,
                tax_amount=0,
            ),
            "_learn_procurement_strategy": SimpleNamespace(
                supplier_id=1,
                amount_aed=1,
                payment_method="cash",
                status="open",
                purchase_number="P",
            ),
            "_learn_expense_patterns": SimpleNamespace(
                category_id=1,
                amount_aed=1,
                payment_method="cash",
                is_recurring=False,
            ),
            "_learn_accounting_entries": SimpleNamespace(
                entry_number="J",
                total_debit=1,
                total_credit=1,
                reference_type="x",
                reference_id=1,
                lines=[],
            ),
            "_learn_revenue_recognition": SimpleNamespace(
                sale_number="S",
                amount_aed=1,
                status="confirmed",
                paid_amount_aed=1,
                balance_due=0,
            ),
            "_learn_expense_recognition": SimpleNamespace(
                purchase_number="P",
                amount_aed=1,
                status="confirmed",
                paid_amount_aed=0,
            ),
            "_predict_future_sales": MagicMock(),
            "_predict_stockout": SimpleNamespace(
                id=1,
                name="X",
                current_stock=1,
                min_stock_alert=10,
            ),
            "_predict_customer_churn": SimpleNamespace(id=1),
            "_neural_auto_retrain": MagicMock(),
            "_neural_customer_data": MagicMock(),
            "_neural_inventory_learning": SimpleNamespace(
                id=1,
                current_stock=1,
                min_stock_alert=0,
            ),
            "_intelligent_sale_analysis": SimpleNamespace(
                status="draft",
                is_active=True,
                amount_aed=1,
                lines=[],
                sale_number="S",
                customer=None,
                payment_status="paid",
            ),
            "_intelligent_customer_monitoring": SimpleNamespace(id=1),
            "_intelligent_inventory_alert": SimpleNamespace(
                id=1,
                name="X",
                current_stock=0,
                min_stock_alert=1,
            ),
        }
        mocker.patch(
            "ai_knowledge.core.learning_system.AzadLearningSystem",
            side_effect=RuntimeError("down"),
        )
        import services.events_ai_service as mod

        for name, target in targets.items():
            getattr(mod, name)(None, None, target)

    def test_register_handlers_are_invoked(self, app, mocker):
        captured = []

        def capture(model, event):
            def decorator(fn):
                captured.append(fn)
                return fn

            return decorator

        mocker.patch("sqlalchemy.event.listens_for", side_effect=capture)
        mocker.patch("ai_knowledge.core.learning_system.AzadLearningSystem")
        from services.events_ai_service import (
            register_ai_event_listeners,
            register_neural_event_listeners,
        )

        with app.app_context():
            register_ai_event_listeners()
            register_neural_event_listeners()
        assert len(captured) >= 15
        sale = SimpleNamespace(
            id=1,
            sale_number="S",
            customer_id=1,
            amount_aed=Decimal("10"),
            subtotal=Decimal("10"),
            discount_amount=Decimal("0"),
            payment_status="paid",
            sale_date=datetime.now(timezone.utc),
            lines=[],
            status="confirmed",
            is_active=True,
            paid_amount_aed=Decimal("10"),
            shipping_cost=0,
            tax_amount=0,
            balance_due=0,
        )
        for handler in captured:
            handler(None, MagicMock(), sale)

    def test_accounting_entries_inner_learning_failure(self, mocker):
        target = SimpleNamespace(
            entry_number="JE-3",
            total_debit=Decimal("1"),
            total_credit=Decimal("1"),
            reference_type="sale",
            reference_id=1,
            lines=[],
        )
        target.is_balanced = lambda: True
        ins = MagicMock()
        ins.unloaded = ["lines"]
        mocker.patch("sqlalchemy.inspect", return_value=ins)
        mocker.patch(
            "ai_knowledge.core.learning_system.AzadLearningSystem",
            side_effect=RuntimeError("down"),
        )
        from services.events_ai_service import _learn_accounting_entries

        _learn_accounting_entries(None, None, target)

    def test_intelligent_sale_analysis_exception(self, mocker):
        mock_app = MagicMock()
        mock_app.config.get.return_value = False
        mocker.patch("flask.current_app", mock_app, create=True)
        mocker.patch("builtins.sum", side_effect=RuntimeError("sum fail"))
        line = SimpleNamespace(cost_price=Decimal("10"), quantity=Decimal("1"))
        target = SimpleNamespace(
            status="confirmed",
            is_active=True,
            amount_aed=Decimal("100"),
            lines=[line],
            sale_number="S-ERR",
            customer=None,
            payment_status="paid",
        )
        from services.events_ai_service import _intelligent_sale_analysis

        _intelligent_sale_analysis(None, None, target)

    def test_neural_handlers_outer_failure(self, mocker):
        conn = MagicMock()
        conn.execute.side_effect = RuntimeError("db")
        from services.events_ai_service import (
            _neural_auto_retrain,
            _neural_customer_data,
        )

        _neural_auto_retrain(None, conn, MagicMock())
        _neural_customer_data(None, conn, MagicMock())

    def test_churn_low_risk_branch(self, mocker):
        _mock_learning(mocker)
        recent = datetime.now(timezone.utc) - __import__("datetime").timedelta(days=10)
        conn = MagicMock()
        conn.execute.return_value.first.return_value = SimpleNamespace(sale_date=recent)
        from services.events_ai_service import _predict_customer_churn

        _predict_customer_churn(None, conn, SimpleNamespace(id=30))

    def test_predict_stockout_logs_days_remaining(self, mocker):
        from decimal import Decimal

        mov = SimpleNamespace(quantity=Decimal("-10"))
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = [mov]
        target = SimpleNamespace(
            id=2,
            name="Widget",
            current_stock=Decimal("8"),
            min_stock_alert=Decimal("10"),
        )
        from services.events_ai_service import _predict_stockout

        _predict_stockout(None, conn, target)

    def test_intelligent_sale_low_margin_insight_line(self, mocker):
        mock_app = MagicMock()
        mock_app.config.get.return_value = False
        mocker.patch("flask.current_app", mock_app, create=True)
        line = SimpleNamespace(cost_price=Decimal("96"), quantity=Decimal("1"))
        target = SimpleNamespace(
            status="confirmed",
            is_active=True,
            amount_aed=Decimal("100"),
            lines=[line],
            sale_number="S-LOW",
            customer=None,
            payment_status="paid",
        )
        from services.events_ai_service import _intelligent_sale_analysis

        _intelligent_sale_analysis(None, None, target)

    def test_intelligent_sale_skips_non_confirmed(self, mocker):
        mock_app = MagicMock()
        mock_app.config.get.return_value = False
        mocker.patch("flask.current_app", mock_app, create=True)
        target = SimpleNamespace(
            status="draft",
            is_active=True,
            amount_aed=Decimal("100"),
            lines=[],
            sale_number="S",
            customer=None,
            payment_status="paid",
        )
        from services.events_ai_service import _intelligent_sale_analysis

        _intelligent_sale_analysis(None, None, target)

    def test_neural_auto_retrain_thread_failure(self, mocker, app):
        rows = [MagicMock()] * 100
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = rows
        mocker.patch("threading.Thread", side_effect=RuntimeError("no thread"))
        from services.events_ai_service import _neural_auto_retrain

        with app.app_context():
            _neural_auto_retrain(None, conn, MagicMock())

    def test_intelligent_sale_excellent_margin(self, mocker):
        mock_app = MagicMock()
        mock_app.config.get.return_value = False
        mocker.patch("flask.current_app", mock_app, create=True)
        line = SimpleNamespace(cost_price=Decimal("10"), quantity=Decimal("1"))
        target = SimpleNamespace(
            status="confirmed",
            is_active=True,
            amount_aed=Decimal("100"),
            lines=[line],
            sale_number="S-HIGH",
            customer=None,
            payment_status="paid",
        )
        from services.events_ai_service import _intelligent_sale_analysis

        _intelligent_sale_analysis(None, None, target)

    def test_neural_inventory_outer_failure(self, mocker):
        target = MagicMock()
        type(target).current_stock = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("bad"))
        )
        from services.events_ai_service import _neural_inventory_learning

        _neural_inventory_learning(None, None, target)

    def test_intelligent_customer_monitoring_failure(self, mocker):
        mock_app = MagicMock()
        mock_app.config.get.return_value = False
        mocker.patch("flask.current_app", mock_app, create=True)
        mocker.patch(
            "ai_knowledge.analytics.data_analyzer.data_analyzer.analyze_customer_debt",
            side_effect=RuntimeError("analyzer down"),
        )
        from services.events_ai_service import _intelligent_customer_monitoring

        _intelligent_customer_monitoring(None, None, SimpleNamespace(id=99))
