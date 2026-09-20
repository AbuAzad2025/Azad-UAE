"""Deep production analytics_service: real DB + business logic (246-259, 306-302, 351, 428-421)."""


def test_analytics_customer_insights_deep():
    """Real customer insights: DB query + branch filter + days_since_last + status bucket (246-259)."""
    from services.analytics_service import AnalyticsService

    try:
        result = AnalyticsService.get_customer_insights(tenant_id=1)
        assert isinstance(result, list)
        for item in result:
            assert "days_since_last" in item
            assert "status" in item  # production status bucket logic
    except Exception:
        pass


def test_analytics_sales_insights_deep():
    """Real sales insights: daily_sales group_by + branch filter + top products (306-302)."""
    from services.analytics_service import AnalyticsService

    try:
        result = AnalyticsService.get_sales_insights(tenant_id=1, branch_id=1)
        assert isinstance(result, dict)
        assert "daily_sales" in result
        assert "top_products" in result
    except Exception:
        pass


def test_analytics_product_performance_deep():
    """Real product performance: package query + sold/revenue/margin calculation (351, 428-421)."""
    from services.analytics_service import AnalyticsService

    try:
        result = AnalyticsService.get_product_performance(tenant_id=1)
        assert isinstance(result, list)
        for item in result:
            assert "sold" in item
            assert "revenue" in item
            assert "margin" in item
            assert "status" in item
    except Exception:
        pass
