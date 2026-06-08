import pytest
from unittest.mock import MagicMock, patch
from services.user_service import UserService

def test_get_users_list_context():
    with patch('services.user_service.Role') as mock_role_model, \
         patch('services.user_service.Permission') as mock_perm_model, \
         patch('services.user_service.User') as mock_user_model, \
         patch('services.user_service.Tenant') as mock_tenant_model, \
         patch('services.user_service.scoped_user_query') as mock_scoped_query, \
         patch('services.user_service.joinedload', return_value=lambda x: x):
        
        # Mock roles
        mock_role = MagicMock(id=1, name='Manager')
        mock_role_model.query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = [mock_role]
        
        # Mock permissions
        mock_perm = MagicMock(category='sales', name='manage_sales')
        mock_perm_model.query.order_by.return_value.all.return_value = [mock_perm]
        
        # Mock tenants
        mock_tenant = MagicMock(id=1, name='Test Tenant')
        mock_tenant_model.query.filter_by.return_value.order_by.return_value.all.return_value = [mock_tenant]
        
        # Mock users query
        mock_user = MagicMock(id=1, username='testuser')
        
        # Proper chaining mock
        mock_query_obj = MagicMock()
        mock_scoped_query.return_value = mock_query_obj
        mock_query_obj.options.return_value.order_by.return_value.all.return_value = [mock_user]
        
        # Mock base for stats
        mock_base = MagicMock()
        # side_effect to handle two different calls to scoped_user_query()
        mock_scoped_query.side_effect = [mock_query_obj, mock_base]
        
        mock_base.count.return_value = 5
        mock_base.filter_by.return_value.count.return_value = 1
        mock_base.join.return_value.filter.return_value.count.return_value = 1
        
        # Mock User query for owner count
        mock_user_model.query.filter_by.return_value.count.return_value = 1
        
        context = UserService.get_users_list_context(tenant_id=1)
        
        assert 'users' in context
        assert 'stats' in context
        assert 'tenants' in context
        assert 'active_tenant_id' in context
        assert len(context['users']) == 1
        assert context['stats']['total'] == 5

def test_get_users_list_context_empty():
    with patch('services.user_service.Role') as mock_role_model, \
         patch('services.user_service.Permission') as mock_perm_model, \
         patch('services.user_service.Tenant') as mock_tenant_model, \
         patch('services.user_service.User') as mock_user_model, \
         patch('services.user_service.scoped_user_query') as mock_scoped_query, \
         patch('services.user_service.joinedload', return_value=lambda x: x):
        
        mock_role_model.query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
        mock_perm_model.query.order_by.return_value.all.return_value = []
        mock_tenant_model.query.filter_by.return_value.order_by.return_value.all.return_value = []
        
        mock_query_obj = MagicMock()
        mock_scoped_query.return_value = mock_query_obj
        mock_query_obj.options.return_value.order_by.return_value.all.return_value = []
        
        mock_base = MagicMock()
        mock_scoped_query.side_effect = [mock_query_obj, mock_base]
        
        mock_base.count.return_value = 0
        mock_base.filter_by.return_value.count.return_value = 0
        mock_base.join.return_value.filter.return_value.count.return_value = 0
        
        # Mock User query for owner count
        mock_user_model.query.filter_by.return_value.count.return_value = 0
        
        context = UserService.get_users_list_context(tenant_id=1)
        
        assert context['users'] == []
        assert context['tenants'] == []
        assert context['stats']['total'] == 0
