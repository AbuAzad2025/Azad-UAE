import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from services.analytics_service import AnalyticsService

def test_get_product_performance_structure():
    # Mocking db.session.query to simulate data structure
    with patch('services.analytics_service.db.session.query') as mock_query:
        # Simulate query chaining
        mock_result = MagicMock()
        mock_query.return_value.select_from.return_value.join.return_value.join.return_value.filter.return_value.group_by.return_value.all.return_value = [
            MagicMock(
                id=1, name='Test Product', sku='TP001', cost_price=10.0,
                total_sold=5.0, total_revenue=100.0, transactions=2
            )
        ]

        tenant_id = 1
        performance = AnalyticsService.get_product_performance(tenant_id)

        assert isinstance(performance, list)
        assert len(performance) == 1
        item = performance[0]
        assert 'name' in item
        assert 'sold' in item
        assert 'revenue' in item
        assert 'margin' in item
        assert 'status' in item

def test_get_product_performance_empty():
    with patch('services.analytics_service.db.session.query') as mock_query:
        mock_query.return_value.select_from.return_value.join.return_value.join.return_value.filter.return_value.group_by.return_value.all.return_value = []

        tenant_id = 1
        performance = AnalyticsService.get_product_performance(tenant_id)
        assert performance == []

def test_get_customer_insights_structure():
    # Use app_context to avoid RuntimeError
    from app import create_app
    app = create_app()
    with app.app_context():
        with patch('models.Customer.query') as mock_customer_query, \
             patch('services.analytics_service.db.session.query') as mock_db_query:
            # Mock customer query
            mock_customer = MagicMock(id=1, name='Test Customer')
            mock_customer_query.filter_by.return_value.all.return_value = [mock_customer]

            # Mock sales query (total_sales)
            mock_db_query.return_value.filter.return_value.filter.return_value.scalar.return_value = 100.0

            # Mock Sale.query (sales_count and last_sale)
            with patch('models.Sale.query') as mock_sale_query:
                mock_sale_query.filter_by.return_value.count.return_value = 2
                mock_sale_query.filter_by.return_value.order_by.return_value.first.return_value = MagicMock(sale_date=datetime.now())

                insights = AnalyticsService.get_customer_insights(tenant_id=1)

                assert isinstance(insights, list)
                assert len(insights) == 1
                item = insights[0]
                assert 'name' in item
                assert 'lifetime_value' in item
                assert 'sales_count' in item
                assert 'avg_sale' in item
                assert 'days_since_last' in item
                assert 'status' in item


def test_get_customer_insights_empty():
    from app import create_app
    app = create_app()
    with app.app_context():
        with patch('models.Customer.query') as mock_customer_query:
            mock_customer_query.filter_by.return_value.all.return_value = []
            insights = AnalyticsService.get_customer_insights(tenant_id=1)
            assert insights == []


