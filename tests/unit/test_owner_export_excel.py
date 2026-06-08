import pytest
from flask import Flask
from unittest.mock import MagicMock, patch
from routes.owner import export_excel
from app import create_app

@pytest.fixture
def app():
    return create_app()

def test_export_excel_scoping_customers(app):
    with app.app_context():
        with patch('routes.owner.get_active_tenant_id', return_value=1), \
             patch('routes.owner._owner_branch_scope', return_value=None), \
             patch('routes.owner.Customer') as mock_customer_model, \
             patch('routes.owner.flash'), patch('routes.owner.redirect'), patch('routes.owner.url_for'), \
             patch('flask.send_file'), patch('routes.owner._audit_owner_db_action'):
            
            # The code: query = model.query.filter_by(tenant_id=tid)
            # So, model.query.filter_by is called.
            mock_query = MagicMock()
            mock_customer_model.query = mock_query
            # Mock the chain
            mock_filter_by_result = MagicMock()
            mock_query.filter_by.return_value = mock_filter_by_result
            mock_filter_by_result.all.return_value = []
            
            export_excel('customers')
            
            # Verify the call
            mock_query.filter_by.assert_called_with(tenant_id=1)

def test_export_excel_scoping_products(app):
    with app.app_context():
        with patch('routes.owner.get_active_tenant_id', return_value=1), \
             patch('routes.owner._owner_branch_scope', return_value=None), \
             patch('routes.owner.Product') as mock_product_model, \
             patch('routes.owner.flash'), patch('routes.owner.redirect'), patch('routes.owner.url_for'), \
             patch('flask.send_file'), patch('routes.owner._audit_owner_db_action'):
            
            mock_query = MagicMock()
            mock_product_model.query = mock_query
            mock_filter_by_result = MagicMock()
            mock_query.filter_by.return_value = mock_filter_by_result
            mock_filter_by_result.all.return_value = []
            
            export_excel('products')
            mock_query.filter_by.assert_called_with(tenant_id=1)

def test_export_excel_scoping_sales_with_branch(app):
    with app.app_context():
        with patch('routes.owner.get_active_tenant_id', return_value=1), \
             patch('routes.owner._owner_branch_scope', return_value=10), \
             patch('routes.owner.Sale') as mock_sale_model, \
             patch('routes.owner.flash'), patch('routes.owner.redirect'), patch('routes.owner.url_for'), \
             patch('flask.send_file'), patch('routes.owner._audit_owner_db_action'):
            
            mock_query = MagicMock()
            mock_sale_model.query = mock_query
            # The code: query = model.query.filter_by(tenant_id=tid)
            #           query = query.filter_by(branch_id=branch_id)
            mock_filter_by_1 = MagicMock()
            mock_filter_by_2 = MagicMock()
            mock_query.filter_by.return_value = mock_filter_by_1
            mock_filter_by_1.filter_by.return_value = mock_filter_by_2
            mock_filter_by_2.all.return_value = []
            
            export_excel('sales')
            # Verify
            mock_query.filter_by.assert_called_with(tenant_id=1)
            mock_filter_by_1.filter_by.assert_called_with(branch_id=10)

def test_export_excel_scoping_expenses_with_branch(app):
    with app.app_context():
        with patch('routes.owner.get_active_tenant_id', return_value=1), \
             patch('routes.owner._owner_branch_scope', return_value=10), \
             patch('routes.owner.Expense') as mock_expense_model, \
             patch('routes.owner.flash'), patch('routes.owner.redirect'), patch('routes.owner.url_for'), \
             patch('flask.send_file'), patch('routes.owner._audit_owner_db_action'):
            
            mock_query = MagicMock()
            mock_expense_model.query = mock_query
            mock_filter_by_1 = MagicMock()
            mock_filter_by_2 = MagicMock()
            mock_query.filter_by.return_value = mock_filter_by_1
            mock_filter_by_1.filter_by.return_value = mock_filter_by_2
            mock_filter_by_2.all.return_value = []
            
            export_excel('expenses')
            mock_query.filter_by.assert_called_with(tenant_id=1)
            mock_filter_by_1.filter_by.assert_called_with(branch_id=10)

def test_export_excel_invalid_table(app):
    with app.app_context():
        with patch('routes.owner.flash'), patch('routes.owner.redirect'), patch('routes.owner.url_for'):
            response = export_excel('invalid_table')
            assert response.status_code == 302
