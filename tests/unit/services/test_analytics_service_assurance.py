"""Analytics service — customer/sales insights and donation analytics."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


def _chain(**terminals):
    q = MagicMock()
    q.filter_by.return_value = q
    q.filter.return_value = q
    q.join.return_value = q
    q.distinct.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.select_from.return_value = q
    q.limit.return_value = q
    q.scalar.return_value = terminals.get("scalar", 0)
    q.count.return_value = terminals.get("count", 0)
    q.all.return_value = terminals.get("all", [])
    q.first.return_value = terminals.get("first")
    return q


class TestCustomerInsights:
    def test_customer_insights_with_branch(self, mocker):
        customer = MagicMock(name="Ali", id=1)
        sale = MagicMock(sale_date=datetime(2025, 6, 1))
        cq = _chain(all=[customer])
        sq = _chain(scalar=1000, count=2, first=sale)
        mocker.patch("services.analytics_service._db_session").return_value.query.side_effect = [cq, sq, sq, sq]
        from services.analytics_service import AnalyticsService

        data = AnalyticsService.get_customer_insights(tenant_id=1, branch_id=2)
        assert data[0]["lifetime_value"] == 1000.0
        assert data[0]["avg_sale"] == 500.0

    def test_customer_insights_no_last_sale(self, mocker):
        customer = MagicMock(name="Bob", id=2)
        cq = _chain(all=[customer])
        sq = _chain(scalar=0, count=0, first=None)
        mocker.patch("services.analytics_service._db_session").return_value.query.side_effect = [cq, sq, sq, sq]
        from services.analytics_service import AnalyticsService

        data = AnalyticsService.get_customer_insights(tenant_id=1)
        assert data[0]["days_since_last"] == 999
        assert data[0]["status"] == "متوقف"


class TestSalesInsights:
    def test_sales_insights(self, mocker):
        daily = MagicMock(date="2025-06-01", count=3, total=Decimal("900"))
        product = MagicMock(name="Widget", total_qty=Decimal("10"), total_revenue=Decimal("500"))
        session = MagicMock()
        session.query.side_effect = [_chain(all=[daily]), _chain(all=[product])]
        mocker.patch("services.analytics_service._db_session", return_value=session)
        from services.analytics_service import AnalyticsService

        insights = AnalyticsService.get_sales_insights(tenant_id=1, branch_id=1)
        assert insights["daily_sales"][0]["total"] == 900.0
        assert insights["top_products"][0]["revenue"] == 500.0


class TestProductPerformance:
    def test_product_performance_status_buckets(self, mocker):
        row = MagicMock(
            name="A",
            sku="SKU1",
            cost_price=Decimal("10"),
            total_sold=Decimal("100"),
            total_revenue=Decimal("2000"),
            transactions=5,
        )
        mocker.patch("services.analytics_service._db_session").return_value.query.return_value = _chain(all=[row])
        from services.analytics_service import AnalyticsService

        perf = AnalyticsService.get_product_performance(tenant_id=1)
        assert perf[0]["status"] in ("ممتاز", "جيد", "ضعيف")
        assert perf[0]["margin_percent"] == pytest.approx(50.0)

    def test_product_performance_with_branch(self, mocker):
        row = MagicMock(
            name="A",
            sku="SKU1",
            cost_price=Decimal("10"),
            total_sold=Decimal("100"),
            total_revenue=Decimal("2000"),
            transactions=5,
        )
        session = MagicMock()
        session.query.return_value = _chain(all=[row])
        mocker.patch("services.analytics_service._db_session", return_value=session)
        from services.analytics_service import AnalyticsService

        assert AnalyticsService.get_product_performance(tenant_id=1, branch_id=2)


class TestForecasting:
    def test_forecasting_with_history(self, mocker):
        session = mocker.patch("services.analytics_service._db_session").return_value
        session.query.return_value.scalar.side_effect = [1000, 1200, 900] * 4
        from services.analytics_service import AnalyticsService

        history, forecast = AnalyticsService.get_forecasting_data(tenant_id=1)
        assert len(history) == 12
        assert forecast["confidence"] in ("عالية", "متوسطة", "منخفضة", "غير متوفرة")

    def test_forecasting_with_branch(self, mocker):
        session = mocker.patch("services.analytics_service._db_session").return_value
        session.query.return_value.scalar.side_effect = [1000] * 12
        from services.analytics_service import AnalyticsService

        history, forecast = AnalyticsService.get_forecasting_data(tenant_id=1, branch_id=1)
        assert len(history) == 12


class TestDonationAnalytics:
    def test_revenue_by_period(self, mocker):
        donation = MagicMock(
            transaction_type="purchase",
            amount_usd=50,
            created_at=datetime.now(timezone.utc),
            status="completed",
        )
        mocker.patch("services.analytics_service._db_session").return_value.query.return_value.all.return_value = [
            donation
        ]
        mocker.patch(
            "services.analytics_service.get_active_tenant_id",
            return_value=1,
            create=True,
        )
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from services.analytics_service import AnalyticsService

        data = AnalyticsService.get_revenue_by_period(months=2, tenant_id=1)
        assert len(data["labels"]) == 2
        assert data["total_revenue"] >= 0

    def test_revenue_by_period_donation_rows(self, mocker):
        donation = MagicMock(
            transaction_type="donation",
            amount_usd=20,
            created_at=datetime.now(timezone.utc),
            status="completed",
        )
        mocker.patch(
            "services.analytics_service._db_session"
        ).return_value.query.return_value.filter.return_value.all.return_value = [donation]
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from services.analytics_service import AnalyticsService

        data = AnalyticsService.get_revenue_by_period(months=1, tenant_id=1)
        assert data["total_revenue"] >= 0

    def test_revenue_by_period_skips_bad_dates(self, mocker):
        donation = MagicMock(
            transaction_type="purchase",
            amount_usd=50,
            created_at=None,
            status="completed",
        )
        mocker.patch(
            "services.analytics_service._db_session"
        ).return_value.query.return_value.filter.return_value.all.return_value = [donation]
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from services.analytics_service import AnalyticsService

        data = AnalyticsService.get_revenue_by_period(months=1, tenant_id=1)
        assert data["total_revenue"] == 0

    def test_revenue_by_period_with_tz_aware_dates(self, mocker):
        donation = MagicMock(
            transaction_type="donation",
            amount_usd=15,
            created_at=datetime.now(timezone.utc),
            status="completed",
        )
        mocker.patch(
            "services.analytics_service._db_session"
        ).return_value.query.return_value.filter.return_value.all.return_value = [donation]
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from services.analytics_service import AnalyticsService

        data = AnalyticsService.get_revenue_by_period(months=1, tenant_id=1)
        assert data["total_revenue"] >= 0

    def test_db_session_helper(self):
        from services.analytics_service import _db_session

        assert _db_session() is not None

    def test_package_performance(self, mocker):
        package = MagicMock(id=1, name_ar="Gold")
        purchase = MagicMock(payment_status="completed", amount_paid=100)
        pending = MagicMock(payment_status="pending", amount_paid=0)
        session = MagicMock()
        session.query.side_effect = [
            _chain(all=[package]),
            _chain(all=[purchase, pending]),
        ]
        mocker.patch("services.analytics_service._db_session", return_value=session)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from services.analytics_service import AnalyticsService

        perf = AnalyticsService.get_package_performance(tenant_id=1)
        assert perf[0]["completed"] == 1
        assert perf[0]["pending"] == 1

    def test_payment_method_stats(self, mocker):
        donation = MagicMock(payment_method="card", amount_usd=25, status="completed")
        session = MagicMock()
        session.query.return_value = _chain(all=[donation, donation])
        mocker.patch("services.analytics_service._db_session", return_value=session)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from services.analytics_service import AnalyticsService

        stats = AnalyticsService.get_payment_method_stats(tenant_id=1)
        assert stats["methods"] == ["card"]
        assert stats["counts"] == [2]

    def test_customer_behavior(self, mocker):
        purchase = MagicMock(
            customer_email="a@test.com",
            amount_paid=1500,
            package=MagicMock(name_ar="Pro"),
        )
        mocker.patch(
            "services.analytics_service._db_session",
        ).return_value.query.return_value = _chain(all=[purchase, purchase])
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from services.analytics_service import AnalyticsService

        behavior = AnalyticsService.get_customer_behavior(tenant_id=1)
        assert behavior["returning_customers"] == 1
        assert behavior["vip_customers"] == 1

    def test_predict_revenue(self, mocker):
        mocker.patch(
            "services.analytics_service.AnalyticsService.get_revenue_by_period",
            return_value={
                "total_revenue": 600,
                "labels": [],
                "purchases": [],
                "donations": [],
            },
        )
        from services.analytics_service import AnalyticsService

        pred = AnalyticsService.predict_revenue(months=2, tenant_id=1)
        assert pred["historical_avg"] == 100.0
        assert len(pred["predictions"]) == 2

    def test_daily_stats(self, mocker):
        donation = MagicMock(status="completed", amount_usd=10)
        pending = MagicMock(status="pending", amount_usd=0)
        session = MagicMock()
        session.query.return_value = _chain(all=[donation, pending])
        mocker.patch("services.analytics_service._db_session", return_value=session)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from services.analytics_service import AnalyticsService

        stats = AnalyticsService.get_daily_stats(tenant_id=1)
        assert stats["today_transactions"] == 2
        assert stats["pending_today"] == 1

    def test_revenue_by_period_date_compare_exception(self, mocker):
        class _BadDate:
            tzinfo = None

            def replace(self, **kwargs):
                return self

            def __le__(self, other):
                raise TypeError("bad compare")

            def __lt__(self, other):
                raise TypeError("bad compare")

        donation = MagicMock(
            transaction_type="purchase",
            amount_usd=50,
            created_at=_BadDate(),
            status="completed",
        )
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [donation]
        mocker.patch("services.analytics_service._db_session").return_value.query.return_value = q
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from services.analytics_service import AnalyticsService

        data = AnalyticsService.get_revenue_by_period(months=1, tenant_id=1)
        assert data["total_revenue"] == 0

    def test_revenue_by_period_donation_exception_path(self, mocker):
        class _BadDate:
            tzinfo = None

            def replace(self, **kwargs):
                return self

            def __le__(self, other):
                raise TypeError("bad compare")

            def __lt__(self, other):
                raise TypeError("bad compare")

        donation = MagicMock(
            transaction_type="donation",
            amount_usd=20,
            created_at=_BadDate(),
            status="completed",
        )
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [donation]
        mocker.patch("services.analytics_service._db_session").return_value.query.return_value = q
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from services.analytics_service import AnalyticsService

        data = AnalyticsService.get_revenue_by_period(months=1, tenant_id=1)
        assert data["donations"] == [0]

    def test_revenue_by_period_counts_in_window(self, mocker):
        now = datetime.now(timezone.utc)
        purchase = MagicMock(
            transaction_type="purchase",
            amount_usd=40,
            created_at=now,
            status="completed",
        )
        donation = MagicMock(
            transaction_type="donation",
            amount_usd=10,
            created_at=now,
            status="completed",
        )
        q = MagicMock()
        q.filter.return_value = q
        q.all.return_value = [purchase, donation]
        mocker.patch("services.analytics_service._db_session").return_value.query.return_value = q
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from services.analytics_service import AnalyticsService

        data = AnalyticsService.get_revenue_by_period(months=1, tenant_id=1)
        assert data["total_revenue"] == 50.0
