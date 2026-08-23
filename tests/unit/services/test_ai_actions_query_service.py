"""Unit tests for AiActionsQueryService — read-only lookups for AI wizard flows."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.ai_actions_query_service import AiActionsQueryService


def _obj(**kwargs):
    return MagicMock(**kwargs)


def _first_chain(result):
    chain = MagicMock()
    chain.first.return_value = result
    return chain


class TestCustomerLookups:
    def test_active_customers_all(self):
        rows = [_obj(name="A"), _obj(name="B")]
        chain = MagicMock()
        chain.all.return_value = rows
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            assert AiActionsQueryService.active_customers(1) is rows
            Customer.query.filter_by.assert_called_once_with(tenant_id=1, is_active=True)

    def test_active_customers_limit(self):
        row = _obj(name="A")
        chain = MagicMock()
        chain.limit.return_value.all.return_value = [row]
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = chain
            assert AiActionsQueryService.active_customers(1, limit=10) == [row]
            chain.limit.assert_called_once_with(10)

    def test_find_customer_by_name(self):
        customer = _obj(id=3, name="Ali", balance=Decimal("10"))
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = _first_chain(customer)
            assert AiActionsQueryService.find_customer_by_name(1, "Ali") is customer
            Customer.query.filter_by.assert_called_once_with(tenant_id=1, name="Ali", is_active=True)

    def test_customer_by_id_keeps_inactive_visible(self):
        customer = _obj(id=5)
        with patch("models.customer.Customer") as Customer:
            Customer.query.filter_by.return_value = _first_chain(customer)
            assert AiActionsQueryService.customer_by_id(5, 1) is customer
            Customer.query.filter_by.assert_called_once_with(id=5, tenant_id=1)

    def test_resolve_customer_by_name_uses_models_package_seam(self):
        with patch("models.Customer") as Customer:
            Customer.query.filter_by.return_value = _first_chain(None)
            assert AiActionsQueryService.resolve_customer_by_name(1, "Ghost") is None
            Customer.query.filter_by.assert_called_once_with(tenant_id=1, name="Ghost", is_active=True)


class TestProductSupplierWarehouseLookups:
    def test_find_product_by_name(self):
        product = _obj(id=2, name="Filter")
        with patch("models.product.Product") as Product:
            Product.query.filter_by.return_value = _first_chain(product)
            assert AiActionsQueryService.find_product_by_name(1, "Filter") is product
            Product.query.filter_by.assert_called_once_with(tenant_id=1, name="Filter", is_active=True)

    def test_active_products_limit(self):
        product = _obj(id=2)
        chain = MagicMock()
        chain.limit.return_value.all.return_value = [product]
        with patch("models.product.Product") as Product:
            Product.query.filter_by.return_value = chain
            assert AiActionsQueryService.active_products(1, limit=10) == [product]
            chain.limit.assert_called_once_with(10)

    def test_find_supplier_by_name(self):
        supplier = _obj(id=4, name="SupCo")
        with patch("models.supplier.Supplier") as Supplier:
            Supplier.query.filter_by.return_value = _first_chain(supplier)
            assert AiActionsQueryService.find_supplier_by_name(1, "SupCo") is supplier
            Supplier.query.filter_by.assert_called_once_with(name="SupCo", is_active=True, tenant_id=1)

    def test_active_suppliers_and_warehouses(self):
        supplier_row = _obj(id=4)
        warehouse_row = _obj(id=9)
        sup_chain = MagicMock()
        sup_chain.all.return_value = [supplier_row]
        wh_chain = MagicMock()
        wh_chain.all.return_value = [warehouse_row]
        with (
            patch("models.supplier.Supplier") as Supplier,
            patch("models.Warehouse") as Warehouse,
        ):
            Supplier.query.filter_by.return_value = sup_chain
            Warehouse.query.filter_by.return_value = wh_chain
            assert AiActionsQueryService.active_suppliers(1) == [supplier_row]
            assert AiActionsQueryService.active_warehouses(1) == [warehouse_row]
            Supplier.query.filter_by.assert_called_once_with(is_active=True, tenant_id=1)
            Warehouse.query.filter_by.assert_called_once_with(is_active=True, tenant_id=1)


class TestLedgerStockUserLists:
    def test_recent_gl_entries_ordering_and_limit(self):
        entry = _obj(id=7)
        chain = MagicMock()
        chain.order_by.return_value.limit.return_value.all.return_value = [entry]
        with patch("models.gl.GLJournalEntry") as GLJournalEntry:
            GLJournalEntry.query.filter_by.return_value = chain
            assert AiActionsQueryService.recent_gl_entries(1) == [entry]
            GLJournalEntry.query.filter_by.assert_called_once_with(is_active=True, tenant_id=1)
            chain.order_by.assert_called_once_with(GLJournalEntry.entry_date.desc())
            chain.order_by.return_value.limit.assert_called_once_with(20)

    @pytest.mark.parametrize(
        "method,model_path",
        [
            ("all_active_sales", "models.sale.Sale"),
            ("all_active_expenses", "models.expense.Expense"),
            ("all_active_purchases", "models.purchase.Purchase"),
            ("all_active_cheques", "models.cheque.Cheque"),
        ],
    )
    def test_unscoped_option_two_lists(self, method, model_path):
        row = _obj(id=1)
        chain = MagicMock()
        chain.all.return_value = [row]
        with patch(model_path) as Model:
            Model.query.filter_by.return_value = chain
            assert getattr(AiActionsQueryService, method)() == [row]
            Model.query.filter_by.assert_called_once_with(is_active=True)

    def test_active_users_delegates_to_scoped_user_query(self):
        user_row = _obj(username="admin")
        chain = MagicMock()
        chain.all.return_value = [user_row]
        with patch("utils.tenanting.scoped_user_query", return_value=chain) as suq:
            assert AiActionsQueryService.active_users() == [user_row]
            suq.assert_called_once_with(active_only=True)


class TestPaymentHistoryLookup:
    def test_recent_customer_payments(self):
        payment = _obj(id=11)
        chain = MagicMock()
        chain.order_by.return_value.limit.return_value.all.return_value = [payment]
        with patch("models.Payment") as Payment:
            Payment.query.filter_by.return_value = chain
            assert AiActionsQueryService.recent_customer_payments(3) == [payment]
            Payment.query.filter_by.assert_called_once_with(customer_id=3)
            chain.order_by.assert_called_once_with(Payment.payment_date.desc())
            chain.order_by.return_value.limit.assert_called_once_with(5)
