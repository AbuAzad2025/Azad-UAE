"""AI executor — tenant guards, validation, payment matching, execution fallbacks."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from datetime import datetime


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


class TestAIExecutorInit:
    """Construction — Flask context fallback and tenant binding."""

    def test_init_without_flask_context(self, mocker):
        mocker.patch('services.ai_executor.get_active_tenant_id', return_value=5)
        from services.ai_executor import AIExecutor
        ex = AIExecutor(user=MagicMock(id=1))
        assert ex.tenant_id == 5

    def test_init_runtime_error_uses_explicit_user(self, mocker):
        mocker.patch('services.ai_executor.flask_user', side_effect=RuntimeError('no context'))
        mocker.patch('services.ai_executor.get_active_tenant_id', return_value=3)
        from services.ai_executor import AIExecutor
        user = MagicMock(id=9)
        ex = AIExecutor(user=user)
        assert ex.user is user

    def test_require_tenant_raises_without_tenant(self, mocker):
        mocker.patch('services.ai_executor.get_active_tenant_id', return_value=None)
        from services.ai_executor import AIExecutor, AIExecutorError
        ex = AIExecutor(user=MagicMock())
        with pytest.raises(AIExecutorError, match='لا يوجد تينانت نشط'):
            ex._require_tenant()


class TestAIExecutorValidation:
    """Input validation — empty names, zero amounts, price guards."""

    def test_create_customer_rejects_empty_name(self, executor):
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='اسم العميل مطلوب'):
            executor.create_customer(name='')

    def test_create_product_rejects_zero_price(self, executor):
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='سعر البيع'):
            executor.create_product(name='Widget', regular_price=0)

    def test_receive_payment_rejects_zero_amount(self, executor, mocker):
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.first.return_value = MagicMock()
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='مبلغ الدفع'):
            executor.receive_payment('Acme', 0)

    def test_add_expense_rejects_empty_description(self, executor):
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='وصف المصروف'):
            executor.add_expense('', 100)


class TestAIExecutorCustomerOps:
    """Customer CRUD and search sanitization."""

    def test_create_customer_success(self, executor, app, mocker):
        mock_customer = MagicMock()
        mock_customer.id = 10
        mock_customer.to_dict.return_value = {'id': 10, 'name': 'Acme'}
        Customer = mocker.patch('models.Customer')
        Customer.return_value = mock_customer
        mock_session = mocker.patch('services.ai_executor.db.session')

        with app.app_context():
            result = executor.create_customer('Acme', phone='0500000000')

        assert result['success'] is True
        assert result['id'] == 10
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_list_customers_search_sanitized(self, executor, mocker):
        mock_c = MagicMock(id=1, name='Test', phone='1', balance=Decimal('0'))
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value.limit.return_value.all.return_value = [mock_c]
        Customer = mocker.patch('models.Customer')
        Customer.query = mock_q
        Customer.name = MagicMock()
        Customer.name.ilike = MagicMock(return_value=True)

        result = executor.list_customers(search="'; DROP TABLE--", limit=5)
        assert result['count'] == 1
        mock_q.filter.assert_called_once()

    def test_get_customer_balance_not_found(self, executor, mocker):
        Customer = mocker.patch('models.Customer')
        Customer.query.filter_by.return_value.first.return_value = None
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='غير موجود'):
            executor.get_customer_balance('Missing')


class TestAIExecutorPaymentMatching:
    """receive_payment — full, partial, and multi-invoice allocation."""

    def _run_payment(self, executor, mocker, app, customer, sales, amount):
        with app.app_context():
            from models import Customer, Sale
            cust_q = MagicMock()
            cust_q.filter_by.return_value.first.return_value = customer
            mocker.patch.object(Customer, 'query', new_callable=mocker.PropertyMock, return_value=cust_q)
            sale_q = MagicMock()
            sale_q.filter.return_value.order_by.return_value.all.return_value = sales
            mocker.patch.object(Sale, 'query', new_callable=mocker.PropertyMock, return_value=sale_q)
            mocker.patch.object(executor, '_generate_number', return_value='PAY-001')
            mocker.patch('services.ai_executor.db.session')
            return executor.receive_payment('Acme', amount)

    def test_full_payment_clears_balance(self, executor, mocker, app):
        customer = MagicMock(id=1, balance=Decimal('500'))
        sale = MagicMock(balance_due=Decimal('500'), paid_amount=Decimal('0'), payment_status='unpaid')
        result = self._run_payment(executor, mocker, app, customer, [sale], 500)
        assert result['success'] is True
        assert sale.balance_due == Decimal('0')
        assert sale.payment_status == 'paid'

    def test_partial_payment_sets_partial_status(self, executor, mocker, app):
        customer = MagicMock(id=1, balance=Decimal('1000'))
        sale = MagicMock(balance_due=Decimal('1000'), paid_amount=Decimal('0'), payment_status='unpaid')
        self._run_payment(executor, mocker, app, customer, [sale], 400)
        assert sale.balance_due == Decimal('600')
        assert sale.payment_status == 'partial'

    def test_overpayment_allocates_across_sales(self, executor, mocker, app):
        customer = MagicMock(id=1, balance=Decimal('2000'))
        sale1 = MagicMock(balance_due=Decimal('500'), paid_amount=Decimal('0'), payment_status='unpaid')
        sale2 = MagicMock(balance_due=Decimal('300'), paid_amount=Decimal('0'), payment_status='unpaid')
        self._run_payment(executor, mocker, app, customer, [sale1, sale2], 700)
        assert sale1.payment_status == 'paid'
        assert sale2.payment_status == 'partial'
        assert sale2.balance_due == Decimal('100')


class TestAIExecutorFallbacks:
    """Execution fallbacks — number generation and executor cache."""

    def test_generate_number_fallback_on_failure(self, mocker):
        mocker.patch('utils.helpers.generate_number', side_effect=RuntimeError('db down'))
        from services.ai_executor import AIExecutor
        num = AIExecutor._generate_number('PAY', MagicMock())
        assert num.startswith('PAY-')

    def test_get_ai_executor_caches_by_user_id(self, mocker):
        mocker.patch('services.ai_executor.get_active_tenant_id', return_value=1)
        mocker.patch('services.ai_executor._executor_cache', {})
        user = MagicMock(id=77, is_authenticated=True)
        from services.ai_executor import get_ai_executor
        ex1 = get_ai_executor(user)
        ex2 = get_ai_executor(user)
        assert ex1 is ex2

    def test_profit_summary_zero_revenue_margin(self, executor, mocker):
        mocker.patch('services.ai_executor.db.session')
        mocker.patch('services.ai_executor.db.session.query') \
            .return_value.filter.return_value.scalar.return_value = 0
        Sale = mocker.patch('models.Sale')
        Sale.query.filter.return_value.count.return_value = 0
        SaleLine = mocker.patch('models.SaleLine')
        SaleLine.query.join.return_value.filter.return_value.all.return_value = []

        result = executor.profit_summary()
        assert result['margin_percent'] == 0

    def test_list_products_respects_token_limit(self, executor, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value.limit.return_value.all.return_value = []
        Product = mocker.patch('models.Product')
        Product.query = mock_q

        executor.list_products(limit=3)
        mock_q.order_by.return_value.limit.assert_called_with(3)

    def test_create_supplier_success(self, executor, app, mocker):
        mock_supplier = MagicMock(id=5)
        Supplier = mocker.patch('models.Supplier')
        Supplier.return_value = mock_supplier
        mocker.patch('services.ai_executor.db.session')
        with app.app_context():
            result = executor.create_supplier('Vendor Co')
        assert result['success'] is True
        assert result['id'] == 5

    def test_create_supplier_rejects_empty_name(self, executor):
        from services.ai_executor import AIExecutorError
        with pytest.raises(AIExecutorError, match='اسم المورد'):
            executor.create_supplier('')

    def test_list_sales_returns_confirmed(self, executor, mocker, app):
        sale = MagicMock(
            id=1, sale_number='S-1', total_amount=Decimal('100'),
            payment_status='paid', sale_date=datetime(2026, 6, 1),
        )
        sale.customer.name = 'Acme'
        with app.app_context():
            from models import Sale
            mock_q = MagicMock()
            mock_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [sale]
            mocker.patch.object(Sale, 'query', new_callable=mocker.PropertyMock, return_value=mock_q)
            result = executor.list_sales(limit=5)
        assert result['success'] is True
        assert len(result['sales']) == 1
        assert result['sales'][0]['number'] == 'S-1'

    def test_sales_summary_aggregates(self, executor, mocker):
        mocker.patch('services.ai_executor.db.session')
        db_query = mocker.patch('services.ai_executor.db.session.query')
        db_query.return_value.filter.return_value.scalar.return_value = Decimal('15000')
        Sale = mocker.patch('models.Sale')
        Sale.query.filter.return_value.count.return_value = 12
        result = executor.sales_summary()
        assert result['total_sales'] == 15000.0
        assert result['count'] == 12

    def test_check_stock_low_inventory(self, executor, mocker, app):
        product = MagicMock(current_stock=Decimal('1'), min_stock_alert=Decimal('5'))
        product.name = 'Low Item'
        with app.app_context():
            from models import Product
            mock_q = MagicMock()
            mock_q.filter.return_value.all.return_value = [product]
            mocker.patch.object(Product, 'query', new_callable=mocker.PropertyMock, return_value=mock_q)
            result = executor.check_stock()
        assert result['count'] == 1
        assert result['low_stock'][0]['name'] == 'Low Item'

    def test_get_ai_executor_without_user_id(self, mocker):
        mocker.patch('services.ai_executor.get_active_tenant_id', return_value=1)
        mocker.patch('services.ai_executor._executor_cache', {})
        mocker.patch('services.ai_executor.flask_user', None)
        from services.ai_executor import get_ai_executor
        ex = get_ai_executor(user=None)
        assert ex.tenant_id == 1
        assert ex.user is None
