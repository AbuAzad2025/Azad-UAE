from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 42
    user.tenant_id = 1
    user.branch_id = 2
    user.is_authenticated = True
    return user


@pytest.fixture
def executor(mock_user, mocker):
    mocker.patch('services.ai_executor.get_active_tenant_id', return_value=1)
    from services.ai_executor import AIExecutor
    return AIExecutor(user=mock_user)


class TestAIExecutorExtended:
    def test_get_customer_balance_success(self, executor, mocker):
        customer = MagicMock(id=1, name='Acme', balance=Decimal('150'), credit_limit=Decimal('500'))
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.first.return_value = customer
        result = executor.get_customer_balance('Acme')
        assert result['balance'] == 150.0

    def test_get_customer_balance_not_found(self, executor, mocker):
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.first.return_value = None
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='غير موجود'):
            executor.get_customer_balance('Missing')

    def test_create_product_success(self, executor, app, mocker):
        product = MagicMock(id=7)
        product.to_dict.return_value = {'id': 7}
        Product = mocker.patch('models.Product')
        Product.return_value = product
        mocker.patch('services.ai_executor.db.session')
        with app.app_context():
            result = executor.create_product('Widget', regular_price=99, cost_price=50)
        assert result['success'] is True
        assert result['id'] == 7

    def test_create_sale_delegates_to_service(self, executor, mocker):
        customer = MagicMock(id=1, is_active=True)
        product = MagicMock(id=2, is_active=True, current_stock=Decimal('10'))
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.first.return_value = customer
        Product = mocker.patch('models.Product')
        Product.query.filter_by.return_value.first.return_value = product
        sale = MagicMock(id=5, sale_number='S-1', total_amount=Decimal('100'))
        mocker.patch('services.sale_service.SaleService.create_sale', return_value=sale)
        result = executor.create_sale('Acme', [{'product_name': 'Widget', 'quantity': 1, 'unit_price': 100}])
        assert result['success'] is True
        assert result['sale_number'] == 'S-1'

    def test_receive_payment_success(self, executor, mocker, app):
        class _Col:
            def __gt__(self, other):
                return self
            def __eq__(self, other):
                return self
            def in_(self, other):
                return self

        customer = MagicMock(id=1, name='Acme', balance=Decimal('0'))
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.first.return_value = customer
        Sale = mocker.patch('models.Sale')
        Sale.balance_due = _Col()
        Sale.tenant_id = _Col()
        Sale.customer_id = _Col()
        Sale.status = _Col()
        Sale.sale_date = _Col()
        Sale.query.filter.return_value.order_by.return_value.all.return_value = []
        Payment = mocker.patch('models.Payment')
        Payment.return_value = MagicMock(id=9)
        mocker.patch('services.ai_executor.db.session')
        with app.app_context():
            result = executor.receive_payment('Acme', 100, method='cash')
        assert result['success'] is True

    def test_add_expense_success(self, executor, app, mocker):
        expense = MagicMock(id=3)
        Expense = mocker.patch('models.Expense')
        Expense.return_value = expense
        ExpenseCategory = mocker.patch('models.ExpenseCategory')
        ExpenseCategory.query.filter_by.return_value.first.return_value = MagicMock(id=1)
        mocker.patch('utils.helpers.generate_number', return_value='EXP-1')
        mocker.patch('services.ai_executor.db.session')
        with app.app_context():
            result = executor.add_expense('Office supplies', 250)
        assert result['success'] is True

    def test_create_employee_success(self, executor, app, mocker):
        employee = MagicMock(id=4)
        Employee = mocker.patch('models.payroll.Employee')
        Employee.return_value = employee
        mocker.patch('services.ai_executor.db.session')
        with app.app_context():
            result = executor.create_employee('Sara', phone='0500000000')
        assert result['success'] is True

    def test_create_purchase_success(self, executor, mocker):
        supplier = MagicMock(id=1, is_active=True, name='Vendor')
        product = MagicMock(id=2, is_active=True)
        warehouse = MagicMock(id=3, is_active=True)
        Supplier = mocker.patch('models.Supplier')
        Supplier.query.filter_by.return_value.first.return_value = supplier
        Product = mocker.patch('models.Product')
        Product.query.filter_by.return_value.first.return_value = product
        Warehouse = mocker.patch('models.Warehouse')
        Warehouse.query.filter_by.return_value.first.return_value = warehouse
        purchase = MagicMock(id=8, purchase_number='P-1')
        mocker.patch('services.purchase_service.PurchaseService.create_purchase', return_value=purchase)
        result = executor.create_purchase('Vendor', [{'product_name': 'Part', 'quantity': 2, 'unit_cost': 10}])
        assert result['success'] is True

    def test_current_user_id_and_branch(self, executor):
        assert executor._current_user_id() == 42
        assert executor._current_branch_id() == 2

    def test_list_products_with_search(self, executor, mocker, app):
        with app.app_context():
            from models import Product
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value.limit.return_value.all.return_value = []
            mocker.patch.object(Product, 'query', new_callable=mocker.PropertyMock, return_value=mock_q)
            result = executor.list_products(search='bolt', limit=5)
        assert result['success'] is True
