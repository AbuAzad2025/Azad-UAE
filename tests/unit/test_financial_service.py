from decimal import Decimal
import pytest
from unittest.mock import MagicMock, patch
from services.financial_service import FinancialService

def test_financial_overview_structure():
    from app import create_app
    app = create_app()
    with app.app_context():
        with patch('flask_login.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.has_permission = MagicMock(return_value=True)
            with patch('services.financial_service.render_template') as mock_render:
                mock_render.return_value = "rendered_template"
                with patch.object(FinancialService, 'sum_sales', return_value=Decimal('100.0')):
                    with patch.object(FinancialService, 'sum_purchases', return_value=Decimal('30.0')):
                        with patch.object(FinancialService, 'sum_receipts', return_value=Decimal('20.0')):
                            with patch('services.financial_service.db.session.query') as mock_query:
                                m = MagicMock()
                                m.filter.return_value = m
                                m.scalar.side_effect = [50.0, 1, 1]
                                mock_query.return_value = m
                                tenant_id = 1
                                result = FinancialService.financial_overview('month', tenant_id, None)
                                assert result == "rendered_template"
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
    with patch.object(FinancialService, 'sum_sales', return_value=100.0):
        with patch('services.financial_service.db.session.query') as mock_query:
            m = MagicMock()
            m.filter.return_value = m
            m.scalar.return_value = 20.0
            mock_query.return_value = m
            context = FinancialService.get_financial_dashboard_advanced_context(tenant_id=1, branch_id=10)
            assert 'months_data' in context
            assert 'kpis' in context
            assert len(context['months_data']) == 12
            item = context['months_data'][0]
            assert 'month' in item
            assert 'revenue' in item
            assert 'expenses' in item
            assert 'profit' in item
            assert 'margin' in item
            assert item['profit'] == 80.0
            assert 'avg_revenue' in context['kpis']
            assert 'avg_profit' in context['kpis']
            assert 'avg_margin' in context['kpis']
            assert 'growth_rate' in context['kpis']

def test_get_financial_dashboard_advanced_context_empty():
    with patch.object(FinancialService, 'sum_sales', return_value=0.0):
        with patch('services.financial_service.db.session.query') as mock_query:
            m = MagicMock()
            m.filter.return_value = m
            m.scalar.return_value = 0.0
            mock_query.return_value = m
            context = FinancialService.get_financial_dashboard_advanced_context(tenant_id=1, branch_id=10)
            assert len(context['months_data']) == 12
            assert all(m['revenue'] == 0.0 for m in context['months_data'])
