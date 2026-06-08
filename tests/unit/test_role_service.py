import pytest
from unittest.mock import MagicMock, patch
from services.role_service import RoleService

def test_get_roles_permissions_context():
    with patch('services.role_service.Role.query') as mock_role_query, \
         patch('services.role_service.Permission.query') as mock_perm_query, \
         patch('services.role_service.User.query') as mock_user_query:
        
        # Mock roles
        mock_role = MagicMock(id=1, name='Manager')
        mock_role_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = [mock_role]
        
        # Mock permissions
        mock_perm = MagicMock(category='sales', name='manage_sales')
        mock_perm_query.order_by.return_value.all.return_value = [mock_perm]
        
        # Mock user counts - now correctly mocking the filter_by chaining
        mock_query_chain = MagicMock()
        mock_user_query.filter_by.return_value = mock_query_chain
        mock_query_chain.filter_by.return_value.count.return_value = 2
        
        context = RoleService.get_roles_permissions_context(tenant_id=1)
        
        assert 'roles' in context
        assert 'permissions' in context
        assert 'perm_categories' in context
        assert 'role_user_counts' in context
        assert len(context['roles']) == 1
        assert context['role_user_counts'][1] == 2
        
        # Verify the call sequence
        mock_user_query.filter_by.assert_called_with(role_id=1, is_active=True)
        mock_query_chain.filter_by.assert_called_with(tenant_id=1)

def test_get_roles_permissions_context_empty():
    with patch('services.role_service.Role.query') as mock_role_query, \
         patch('services.role_service.Permission.query') as mock_perm_query:
        
        mock_role_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
        mock_perm_query.order_by.return_value.all.return_value = []
        
        context = RoleService.get_roles_permissions_context(tenant_id=1)
        
        assert context['roles'] == []
        assert context['permissions'] == []
        assert context['perm_categories'] == {}
        assert context['role_user_counts'] == {}
