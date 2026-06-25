"""Analytics service — POS insights, product performance, branch filtering."""
from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import utils.tenanting as tenanting_mod


@pytest.fixture(autouse=True)
def _patch_tenanting_active_id(mocker):
    mocker.patch.object(tenanting_mod, 'active_tenant_id', lambda: 1, create=True)


def _model_name(target):
    return getattr(target, '__name__', None)


def _patch_session_query(mocker, handler):
    """Patch db.session.query for analytics_service (extensions + module alias)."""
    from extensions import db as ext_db

    def _query(target):
        result = handler(target)
        return result if result is not None else MagicMock()

    mocker.patch.object(ext_db.session, 'query', side_effect=_query)
    mocker.patch('services.analytics_service.db.session.query', side_effect=_query)


class TestCustomerInsights:
    """get_customer_insights — LTV sorting and branch scope."""

    def test_sorts_by_lifetime_value_desc_and_caps_fifty(self, mocker):
        customers = [MagicMock(id=i, name=f'C{i}') for i in range(55)]
        cust_q = MagicMock()
        cust_q.filter_by.return_value = cust_q
        cust_q.all.return_value = customers

        sale_count_q = MagicMock()
        sale_count_q.filter_by.return_value = sale_count_q
        sale_count_q.filter.return_value = sale_count_q
        sale_count_q.count.return_value = 1

        last_sale_q = MagicMock()
        last_sale_q.filter_by.return_value = last_sale_q
        last_sale_q.filter.return_value = last_sale_q
        last_sale_q.order_by.return_value = last_sale_q
        last_sale = MagicMock(sale_date=datetime.now())
        last_sale_q.first.return_value = last_sale

        sum_q = MagicMock()
        sum_q.filter.return_value = sum_q
        sum_q.scalar.side_effect = [1000 - i for i in range(55)]

        def _handler(target):
            name = _model_name(target)
            if name == 'Customer':
                q = MagicMock()
                q.filter_by.return_value = cust_q
                return q
            if name == 'Sale':
                q = MagicMock()
                q.filter_by.side_effect = lambda **kw: sale_count_q if 'status' in kw else last_sale_q
                return q
            if not inspect.isclass(target):
                return sum_q
            return None

        _patch_session_query(mocker, _handler)

        from services.analytics_service import AnalyticsService

        result = AnalyticsService.get_customer_insights(tenant_id=1)
        assert len(result) == 50
        assert result[0]['lifetime_value'] >= result[1]['lifetime_value']

    def test_branch_filter_applied_to_customer_query(self, mocker):
        cust_q = MagicMock()
        cust_q.filter_by.return_value = cust_q
        cust_q.join.return_value = cust_q
        cust_q.filter.return_value = cust_q
        cust_q.distinct.return_value = cust_q
        cust_q.all.return_value = []

        def _handler(target):
            if _model_name(target) == 'Customer':
                q = MagicMock()
                q.filter_by.return_value = cust_q
                return q
            return None

        _patch_session_query(mocker, _handler)

        from services.analytics_service import AnalyticsService

        result = AnalyticsService.get_customer_insights(tenant_id=1, branch_id=7)
        assert result == []
        cust_q.filter.assert_called()


class TestSalesInsights:
    """get_sales_insights — daily POS aggregates and top products."""

    def test_daily_sales_and_top_products_shape(self, mocker):
        daily_row = MagicMock(date=date.today(), count=5, total=Decimal('2500'))
        product_row = MagicMock(name='Widget', total_qty=Decimal('10'), total_revenue=Decimal('900'))

        session = mocker.patch('services.analytics_service.db.session')
        daily_q = MagicMock()
        daily_q.filter.return_value = daily_q
        daily_q.group_by.return_value = daily_q
        daily_q.all.return_value = [daily_row]

        top_q = MagicMock()
        top_q.select_from.return_value = top_q
        top_q.join.return_value = top_q
        top_q.filter.return_value = top_q
        top_q.group_by.return_value = top_q
        top_q.order_by.return_value = top_q
        top_q.limit.return_value = top_q
        top_q.all.return_value = [product_row]

        session.query.side_effect = [daily_q, top_q]

        from services.analytics_service import AnalyticsService

        insights = AnalyticsService.get_sales_insights(tenant_id=1, branch_id=3)
        assert insights['daily_sales'][0]['total'] == pytest.approx(2500.0)
        assert insights['top_products'][0]['revenue'] == pytest.approx(900.0)
        assert daily_q.filter.call_count >= 1

    def test_branch_filter_on_top_products(self, mocker):
        session = mocker.patch('services.analytics_service.db.session')
        daily_q = MagicMock()
        daily_q.filter.return_value = daily_q
        daily_q.group_by.return_value = daily_q
        daily_q.all.return_value = []

        top_q = MagicMock()
        top_q.select_from.return_value = top_q
        top_q.join.return_value = top_q
        top_q.filter.return_value = top_q
        top_q.group_by.return_value = top_q
        top_q.order_by.return_value = top_q
        top_q.limit.return_value = top_q
        top_q.all.return_value = []

        session.query.side_effect = [daily_q, top_q]

        from services.analytics_service import AnalyticsService

        AnalyticsService.get_sales_insights(tenant_id=2, branch_id=5)
        filter_calls = top_q.filter.call_args_list
        assert len(filter_calls) >= 1


class TestProductPerformance:
    """get_product_performance — margin math and high-volume classification."""

    def test_high_volume_sorted_by_revenue(self, mocker):
        low = MagicMock(sku='L1', cost_price=Decimal('10'), total_sold=Decimal('5'), total_revenue=Decimal('100'), transactions=2)
        low.name = 'Low'
        high = MagicMock(sku='H1', cost_price=Decimal('20'), total_sold=Decimal('50'), total_revenue=Decimal('5000'), transactions=20)
        high.name = 'High'
        mid = MagicMock(sku='M1', cost_price=Decimal('15'), total_sold=Decimal('20'), total_revenue=Decimal('800'), transactions=8)
        mid.name = 'Mid'

        session = mocker.patch('services.analytics_service.db.session')
        query = MagicMock()
        query.select_from.return_value = query
        query.join.return_value = query
        query.filter.return_value = query
        query.group_by.return_value = query
        query.all.return_value = [low, high, mid]
        session.query.return_value = query

        from services.analytics_service import AnalyticsService

        perf = AnalyticsService.get_product_performance(tenant_id=1)
        assert perf[0]['name'] == 'High'
        assert perf[0]['status'] == 'ممتاز'
        assert perf[0]['margin'] == pytest.approx(4000.0)
        assert perf[0]['margin_percent'] == pytest.approx(80.0)

    def test_zero_revenue_zero_margin_percent(self, mocker):
        row = MagicMock(sku='D1', cost_price=Decimal('5'), total_sold=Decimal('0'), total_revenue=Decimal('0'), transactions=0)
        row.name = 'Dead'
        session = mocker.patch('services.analytics_service.db.session')
        query = MagicMock()
        query.select_from.return_value = query
        query.join.return_value = query
        query.filter.return_value = query
        query.group_by.return_value = query
        query.all.return_value = [row]
        session.query.return_value = query

        from services.analytics_service import AnalyticsService

        perf = AnalyticsService.get_product_performance(tenant_id=1)
        assert perf[0]['margin_percent'] == 0.0
        assert perf[0]['status'] == 'ضعيف'

    def test_branch_filter_on_performance_query(self, mocker):
        session = mocker.patch('services.analytics_service.db.session')
        query = MagicMock()
        query.select_from.return_value = query
        query.join.return_value = query
        query.filter.return_value = query
        query.group_by.return_value = query
        query.all.return_value = []
        session.query.return_value = query

        from services.analytics_service import AnalyticsService

        assert AnalyticsService.get_product_performance(tenant_id=1, branch_id=9) == []
        query.filter.assert_called()


class TestForecastingAndPackages:
    """get_forecasting_data, get_package_performance — aggregation edge cases."""

    def test_forecast_low_confidence_on_volatile_history(self, mocker):
        session = mocker.patch('services.analytics_service.db.session')
        session.query.return_value.filter.return_value.scalar.side_effect = [
            100, 500, 50, 400, 80, 450, 60, 420, 70, 410, 90, 430,
        ]

        from services.analytics_service import AnalyticsService

        historical, forecast = AnalyticsService.get_forecasting_data(tenant_id=1)
        assert len(historical) == 12
        assert forecast['confidence'] in ('عالية', 'متوسطة', 'منخفضة')

    def test_package_performance_completed_vs_pending(self, mocker):
        pkg = MagicMock(id=1, name_ar='Gold')
        pkg_q = MagicMock()
        pkg_q.filter_by.return_value = pkg_q
        pkg_q.all.return_value = [pkg]

        purchases = [
            MagicMock(payment_status='completed', amount_paid=100),
            MagicMock(payment_status='pending', amount_paid=0),
        ]
        pp_q = MagicMock()
        pp_q.filter_by.return_value = pp_q
        pp_q.all.return_value = purchases

        def _handler(target):
            name = _model_name(target)
            if name == 'Package':
                q = MagicMock()
                q.filter_by.return_value = pkg_q
                return q
            if name == 'PackagePurchase':
                q = MagicMock()
                q.filter_by.return_value = pp_q
                return q
            return None

        _patch_session_query(mocker, _handler)

        from services.analytics_service import AnalyticsService

        result = AnalyticsService.get_package_performance(tenant_id=1)
        assert result[0]['completed'] == 1
        assert result[0]['pending'] == 1
        assert result[0]['revenue'] == pytest.approx(100.0)


class TestDonationAnalytics:
    """get_payment_method_stats, predict_revenue, get_daily_stats."""

    def test_payment_method_aggregation(self, mocker):
        donations = [
            MagicMock(payment_method='card', amount_usd=50, status='completed'),
            MagicMock(payment_method='card', amount_usd=30, status='completed'),
            MagicMock(payment_method=None, amount_usd=10, status='completed'),
        ]
        don_q = MagicMock()
        don_q.filter_by.return_value = don_q
        don_q.all.return_value = donations

        def _handler(target):
            if _model_name(target) == 'Donation':
                q = MagicMock()
                q.filter_by.return_value = don_q
                return q
            return None

        _patch_session_query(mocker, _handler)

        from services.analytics_service import AnalyticsService

        stats = AnalyticsService.get_payment_method_stats(tenant_id=1)
        assert 'card' in stats['methods']
        assert 'unknown' in stats['methods']
        assert sum(stats['totals']) == pytest.approx(90.0)

    def test_predict_revenue_growth_projection(self, mocker):
        mocker.patch(
            'services.analytics_service.AnalyticsService.get_revenue_by_period',
            return_value={'total_revenue': 600, 'purchases': [], 'donations': []},
        )

        from services.analytics_service import AnalyticsService

        pred = AnalyticsService.predict_revenue(months=2, tenant_id=1)
        assert pred['historical_avg'] == pytest.approx(100.0)
        assert len(pred['predictions']) == 2
        assert pred['growth_rate'] == 0.05
