import pytest
from unittest.mock import MagicMock, patch
from app import create_app

@pytest.fixture
def app():
    return create_app()


def _login_mock_owner():
    from flask_login import login_user
    user = MagicMock()
    user.is_authenticated = True
    user.is_owner = True
    user.tenant_id = None
    user.id = 1
    user.get_id.return_value = '1'
    login_user(user)
    return user


def test_export_excel_scoping_customers(app):
    with app.test_request_context():
        _login_mock_owner()
        with patch('routes.owner.get_active_tenant_id', return_value=1), \
             patch('routes.owner._owner_branch_scope', return_value=None), \
             patch('routes.owner.Customer') as mock_customer_model, \
             patch('routes.owner.flash'), patch('routes.owner.redirect'), patch('routes.owner.url_for'), \
             patch('flask.send_file'), patch('routes.owner._audit_owner_db_action'):
            mock_query = MagicMock()
            mock_customer_model.query = mock_query
            mock_query.filter_by.return_value.all.return_value = []
            from routes.owner import export_excel
            export_excel('customers')
            mock_query.filter_by.assert_called_with(tenant_id=1)


def test_export_excel_scoping_products(app):
    with app.test_request_context():
        _login_mock_owner()
        with patch('routes.owner.get_active_tenant_id', return_value=1), \
             patch('routes.owner._owner_branch_scope', return_value=None), \
             patch('routes.owner.Product') as mock_product_model, \
             patch('routes.owner.flash'), patch('routes.owner.redirect'), patch('routes.owner.url_for'), \
             patch('flask.send_file'), patch('routes.owner._audit_owner_db_action'):
            mock_query = MagicMock()
            mock_product_model.query = mock_query
            mock_query.filter_by.return_value.all.return_value = []
            from routes.owner import export_excel
            export_excel('products')
            mock_query.filter_by.assert_called_with(tenant_id=1)


def test_export_excel_scoping_sales_with_branch(app):
    with app.test_request_context():
        _login_mock_owner()
        with patch('routes.owner.get_active_tenant_id', return_value=1), \
             patch('routes.owner._owner_branch_scope', return_value=10), \
             patch('routes.owner.Sale') as mock_sale_model, \
             patch('routes.owner.flash'), patch('routes.owner.redirect'), patch('routes.owner.url_for'), \
             patch('flask.send_file'), patch('routes.owner._audit_owner_db_action'):
            mock_query = MagicMock()
            mock_sale_model.query = mock_query
            mock_query.filter_by.return_value.filter_by.return_value.all.return_value = []
            from routes.owner import export_excel
            export_excel('sales')
            mock_query.filter_by.assert_called_with(tenant_id=1)
            mock_query.filter_by.return_value.filter_by.assert_called_with(branch_id=10)


def test_export_excel_scoping_expenses_with_branch(app):
    with app.test_request_context():
        _login_mock_owner()
        with patch('routes.owner.get_active_tenant_id', return_value=1), \
             patch('routes.owner._owner_branch_scope', return_value=10), \
             patch('routes.owner.Expense') as mock_expense_model, \
             patch('routes.owner.flash'), patch('routes.owner.redirect'), patch('routes.owner.url_for'), \
             patch('flask.send_file'), patch('routes.owner._audit_owner_db_action'):
            mock_query = MagicMock()
            mock_expense_model.query = mock_query
            mock_query.filter_by.return_value.filter_by.return_value.all.return_value = []
            from routes.owner import export_excel
            export_excel('expenses')
            mock_query.filter_by.assert_called_with(tenant_id=1)
            mock_query.filter_by.return_value.filter_by.assert_called_with(branch_id=10)


def test_export_excel_invalid_table(app):
    with app.test_request_context():
        _login_mock_owner()
        with patch('routes.owner.flash') as mock_flash, \
             patch('routes.owner.redirect') as mock_redirect, \
             patch('routes.owner.url_for') as mock_url_for:
            from routes.owner import export_excel
            export_excel('invalid_table')
            mock_url_for.assert_called_once()
            mock_flash.assert_called_once()
            mock_redirect.assert_called_once()
