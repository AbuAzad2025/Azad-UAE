import pytest
from unittest.mock import MagicMock, patch
from services.analytics_service import AnalyticsService

def test_get_sales_insights_structure():
    # Mock db.session.query to return controlled data
    with patch('services.analytics_service.db.session.query') as mock_query:
        # Set up mock query results
        mock_daily = [MagicMock(date='2026-06-01', count=5, total=100.0)]
        mock_products = [MagicMock(name='Test Product', total_qty=2.0, total_revenue=50.0)]
        
        # This is a simplification; chaining SQLAlchemy queries is complex to mock fully
        # This test primarily checks the structure and callability
        mock_query.return_value.filter.return_value.filter.return_value.group_by.return_value.all.side_effect = [
            mock_daily,
            mock_products
        ]
        
        tenant_id = 1
        insights = AnalyticsService.get_sales_insights(tenant_id)
        
        assert 'daily_sales' in insights
        assert 'top_products' in insights
        assert isinstance(insights['daily_sales'], list)
        assert isinstance(insights['top_products'], list)

def test_get_sales_insights_empty_results():
    with patch('services.analytics_service.db.session.query') as mock_query:
        # Mock empty results
        mock_query.return_value.filter.return_value.filter.return_value.group_by.return_value.all.side_effect = [[], []]
        
        tenant_id = 1
        insights = AnalyticsService.get_sales_insights(tenant_id)
        
        assert insights['daily_sales'] == []
        assert insights['top_products'] == []
