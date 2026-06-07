import pytest
from unittest.mock import MagicMock, patch
from services.financial_service import FinancialService

def test_financial_overview_structure():
    from app import create_app
    app = create_app()
    with app.test_request_context():
        # Mock current_user for template processors
        with patch('flask_login.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.has_permission = MagicMock(return_value=True)

            # Mock db.session.query to simulate sales, purchases, and receipts
            with patch('services.financial_service.db.session.query') as mock_query:
                # Simulate query chaining for sales_data, purchases_data, receipts_total
                mock_sales = MagicMock()
                mock_sales.filter.return_value.filter.return_value.first.return_value = [100.0, 50.0, 1]

                mock_purchases = MagicMock()
                mock_purchases.filter.return_value.filter.return_value.first.return_value = [30.0, 1]

                mock_receipts = MagicMock()
                mock_receipts.filter.return_value.filter.return_value.scalar.return_value = 20.0

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
                    assert financial_data['net_revenue'] == 70.0

