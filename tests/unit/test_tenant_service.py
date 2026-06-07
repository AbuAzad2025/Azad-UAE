import pytest
from unittest.mock import MagicMock, patch
from services.tenant_service import TenantService

def test_get_tenants_list_context_structure():
    from app import create_app
    app = create_app()
    with app.app_context():
        with patch('services.tenant_service.Tenant.query') as mock_tenant_query, \
             patch('services.tenant_service.db.session.query') as mock_db_query:
            
            # Mock tenants
            mock_tenant = MagicMock(id=1, name='Test Tenant')
            mock_tenant_query.order_by.return_value.all.return_value = [mock_tenant]
            
            # Mock counts (user_counts, branch_counts, store_counts)
            mock_db_query.return_value.filter.return_value.group_by.return_value.all.return_value = [(1, 5)]
            
            context = TenantService.get_tenants_list_context()
            
            assert 'tenants' in context
            assert 'user_counts' in context
            assert 'branch_counts' in context
            assert 'store_counts' in context
            assert len(context['tenants']) == 1
            assert context['user_counts'][1] == 5

def test_get_tenants_list_context_empty():
    from app import create_app
    app = create_app()
    with app.app_context():
        with patch('services.tenant_service.Tenant.query') as mock_tenant_query:
            mock_tenant_query.order_by.return_value.all.return_value = []
            
            context = TenantService.get_tenants_list_context()
            
            assert context['tenants'] == []
            assert context['user_counts'] == {}
            assert context['branch_counts'] == {}
            assert context['store_counts'] == {}
