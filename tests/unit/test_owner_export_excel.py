import pytest
from flask import Flask
from unittest.mock import MagicMock, patch
from routes.owner import export_excel

@pytest.fixture
def app():
    app = Flask(__name__)
    return app

def test_export_excel_scoping(app):
    with app.app_context():
        # Patch decorators directly to bypass authentication
        with patch('routes.owner.login_required', lambda f: f), \
             patch('routes.owner.owner_required', lambda f: f), \
             patch('routes.owner.current_user') as mock_user:
            
            mock_user.is_authenticated = True
            
            with patch('routes.owner.get_active_tenant_id', return_value=1), \
                 patch('routes.owner._owner_branch_scope', return_value=None), \
                 patch('routes.owner.Customer.query') as mock_customer_query:
                
                mock_customer_query.filter_by.return_value.all.return_value = []
                
                with patch('routes.owner.flash'), patch('routes.owner.redirect'), patch('routes.owner.url_for'):
                    export_excel('customers')
                    mock_customer_query.filter_by.assert_called_with(tenant_id=1)

def test_export_excel_invalid_table(app):
    with app.app_context():
        with patch('routes.owner.flash'), patch('routes.owner.redirect'), patch('routes.owner.url_for'):
            response = export_excel('invalid_table')
            assert response.status_code == 302
