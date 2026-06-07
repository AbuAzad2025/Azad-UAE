import pytest
from unittest.mock import MagicMock, patch
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
