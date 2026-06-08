import pytest
from unittest.mock import MagicMock, patch
from services.financial_service import FinancialService

def test_financial_overview_structure():
    from app import create_app
    app = create_app()
    with app.app_context():
        # Mock current_user for template processors
        with patch('flask_login.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.has_permission = MagicMock(return_value=True)

            # Mock db.session.query to simulate sales, purchases, and receipts
            with patch('services.financial_service.db.session.query') as mock_query:
                # Helper to make mocking easier for chained calls
                def create_mock_query():
                    m = MagicMock()
                    m.filter.return_value = m
                    m.first.return_value = [100.0, 50.0, 1]
                    m.scalar.return_value = 20.0
                    return m

                mock_sales = create_mock_query()
                mock_sales.first.return_value = [100.0, 50.0, 1]
                
                mock_purchases = create_mock_query()
                mock_purchases.first.return_value = [30.0, 1]
                
                mock_receipts = create_mock_query()
                mock_receipts.scalar.return_value = 20.0
                
                mock_query.side_effect = [mock_sales, mock_purchases, mock_receipts]
                
                with patch('services.financial_service.render_template') as mock_render:
                    mock_render.return_value = "rendered_template"
                    
                    tenant_id = 1
                    result = FinancialService.financial_overview('month', tenant_id, None)
                    
                    assert result == "rendered_template"
                    
                    # Verify render_template was called with correct data
                    args, kwargs = mock_render.call_args
                    assert args[0] == 'owner/financial_overview.html'
                    financial_data = kwargs['financial_data']
                    assert financial_data['sales_total'] == 100.0
                    assert financial_data['sales_paid'] == 50.0
                    assert financial_data['sales_count'] == 1
                    assert financial_data['purchases_total'] == 30.0
                    assert financial_data['purchases_count'] == 1
                    assert financial_data['receipts_total'] == 20.0
                    assert financial_data['net_revenue'] == 70.0

def test_get_financial_dashboard_advanced_context():
    with patch('services.financial_service.db.session.query') as mock_query:
        # Mocking the filter().filter().scalar() chain
        mock_query_obj = MagicMock()
        mock_query.return_value.filter.return_value.filter.return_value = mock_query_obj
        mock_query_obj.scalar.side_effect = [100.0, 20.0] * 12
        
        context = FinancialService.get_financial_dashboard_advanced_context(tenant_id=1, branch_id=10)
        
        assert 'months_data' in context
        assert 'kpis' in context
        assert len(context['months_data']) == 12
        
        # Check an item structure
        item = context['months_data'][0]
        assert 'month' in item
        assert 'revenue' in item
        assert 'expenses' in item
        assert 'profit' in item
        assert 'margin' in item
        assert item['profit'] == 80.0
        
        # Check KPIs
        assert 'avg_revenue' in context['kpis']
        assert 'avg_profit' in context['kpis']
        assert 'avg_margin' in context['kpis']
        assert 'growth_rate' in context['kpis']
        
def test_get_financial_dashboard_advanced_context_empty():
    with patch('services.financial_service.db.session.query') as mock_query:
        mock_query_obj = MagicMock()
        mock_query.return_value.filter.return_value.filter.return_value = mock_query_obj
        mock_query_obj.scalar.return_value = 0.0
        
        context = FinancialService.get_financial_dashboard_advanced_context(tenant_id=1, branch_id=10)
        
        assert len(context['months_data']) == 12
        assert all(m['revenue'] == 0.0 for m in context['months_data'])
