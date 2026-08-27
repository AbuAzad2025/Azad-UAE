"""Deep behavioral coverage for ActionDispatcher handler branches.

These tests exercise the *real* handlers registered in ActionDispatcher
against the real test database (or a seam-mocked service at the boundary),
covering guard clauses, duplicate guards, category resolution, and error
funnels that the parsing-focused suite (test_action_dispatcher.py) misses.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from ai_knowledge.action_dispatcher import ActionDispatcher


@pytest.fixture
def dispatcher():
    return ActionDispatcher()


def _handler(dispatcher: ActionDispatcher, action: str):
    return dispatcher._registry[action]["handler"]


# ── customers ────────────────────────────────────────────────────────────


class TestCustomerHandlers:
    def test_create_customer_requires_name(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "create_customer")({"name": "   "})
        assert not result.success
        assert "اسم العميل" in result.message

    def test_create_customer_duplicate_blocked(self, dispatcher, mock_ai_user, db_session):
        from models import Customer

        db_session.add(Customer(tenant_id=1, name="C4-Dup-Customer", is_active=True))
        db_session.commit()

        result = _handler(dispatcher, "create_customer")({"name": "C4-Dup-Customer"})
        assert not result.success
        assert result.action_type == "customer_duplicate"
        assert isinstance(result.data.get("id"), int)

    def test_create_customer_error_funnel(self, dispatcher, mock_ai_user):
        with patch("models.Customer", side_effect=RuntimeError("boom-customer")):
            result = _handler(dispatcher, "create_customer")({"name": "C4-Boom"})
        assert not result.success
        assert "boom-customer" in result.message

    def test_customer_balance_requires_name(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "customer_balance")({})
        assert not result.success
        assert "اسم العميل" in result.message


# ── products / stock ─────────────────────────────────────────────────────


class TestProductStockHandlers:
    def test_create_product_requires_name(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "create_product")({})
        assert not result.success
        assert "اسم المنتج" in result.message

    def test_check_stock_search_finds_seeded_product(self, dispatcher, mock_ai_user, db_session):
        from decimal import Decimal

        from models import Product

        db_session.add(
            Product(
                tenant_id=1,
                name="C4 Filter product",
                sku="C4-SKU-1",
                cost_price=Decimal("10"),
                regular_price=Decimal("20"),
                current_stock=Decimal("25"),
                min_stock_alert=Decimal("5"),
            )
        )
        db_session.commit()

        result = _handler(dispatcher, "check_stock")({"search": "C4 Filter"})
        assert result.success
        assert result.data["count"] == 1
        item = result.data["items"][0]
        assert item["name"] == "C4 Filter product"
        assert item["stock"] == pytest.approx(25.0)
        assert item["min"] == pytest.approx(5.0)

    def test_check_stock_unknown_item_prompts_operator(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "check_stock")({"search": "لا-شيء-مطابق-c4"})
        assert not result.success
        assert "لا يوجد منتج مطابق" in result.message

    def test_check_stock_low_stock_report_uses_min_stock_alert(self, dispatcher, mock_ai_user, db_session):
        from decimal import Decimal

        from models import Product

        db_session.add(
            Product(
                tenant_id=1,
                name="C4 Low Product",
                sku="C4-LOW-1",
                cost_price=Decimal("10"),
                regular_price=Decimal("20"),
                current_stock=Decimal("2"),
                min_stock_alert=Decimal("8"),
            )
        )
        db_session.commit()

        result = _handler(dispatcher, "check_stock")({})
        assert result.success, result.message
        row = next(i for i in result.data["low_stock"] if i["name"] == "C4 Low Product")
        assert row["stock"] == pytest.approx(2.0)
        assert row["min"] == pytest.approx(8.0)

    def test_transfer_stock_requires_args(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "transfer_stock")({"product_name": "x", "from_warehouse_id": None})
        assert not result.success
        assert "المستودع المصدر" in result.message

    def test_transfer_stock_single_warehouse_guard(self, dispatcher, mock_ai_user, db_session):
        from models import Warehouse

        db_session.add(Warehouse(tenant_id=1, branch_id=None, name="C4 Only WH", is_active=True))
        db_session.commit()

        result = _handler(dispatcher, "transfer_stock")(
            {"product_name": "p", "quantity": 3, "from_warehouse_id": 1, "to_warehouse_id": 2}
        )
        assert not result.success
        assert "مستودع واحد نشط" in result.message

    def test_transfer_stock_unknown_product(self, dispatcher, mock_ai_user, db_session):
        from models import Warehouse

        db_session.add(Warehouse(tenant_id=1, branch_id=None, name="C4 WH A", is_active=True))
        db_session.add(Warehouse(tenant_id=1, branch_id=None, name="C4 WH B", is_active=True))
        db_session.commit()

        result = _handler(dispatcher, "transfer_stock")(
            {"product_name": "غير-موجود-c4", "quantity": 2, "from_warehouse_id": 1, "to_warehouse_id": 2}
        )
        assert not result.success
        assert "غير موجود" in result.message

    def test_transfer_stock_success_through_service_seam(self, dispatcher, mock_ai_user, db_session):
        from decimal import Decimal

        from models import Product, Warehouse

        db_session.add(Warehouse(tenant_id=1, branch_id=None, name="C4 WH Src", is_active=True))
        db_session.add(Warehouse(tenant_id=1, branch_id=None, name="C4 WH Dst", is_active=True))
        db_session.add(
            Product(
                tenant_id=1,
                name="C4 Transfer Product",
                sku="C4-XFER",
                cost_price=Decimal("5"),
                regular_price=Decimal("9"),
            )
        )
        db_session.commit()

        with (
            patch("services.stock_service.StockService.transfer_stock") as transfer,
            patch("ai_knowledge.action_dispatcher._audit") as audit,
        ):
            result = _handler(dispatcher, "transfer_stock")(
                {
                    "product_name": "C4 Transfer",
                    "quantity": 7,
                    "from_warehouse_id": 1,
                    "to_warehouse_id": 2,
                    "notes": "c4-note",
                }
            )
        assert result.success
        assert result.action_type == "stock_transfer"
        assert result.data["quantity"] == 7.0
        transfer.assert_called_once()
        audit.assert_called_once()

    def test_transfer_stock_value_error_passthrough(self, dispatcher, mock_ai_user, db_session):
        from decimal import Decimal

        from models import Product, Warehouse

        db_session.add(Warehouse(tenant_id=1, branch_id=None, name="C4 WH E", is_active=True))
        db_session.add(Warehouse(tenant_id=1, branch_id=None, name="C4 WH F", is_active=True))
        db_session.add(
            Product(
                tenant_id=1,
                name="C4 VE Product",
                sku="C4-VE",
                cost_price=Decimal("5"),
                regular_price=Decimal("9"),
            )
        )
        db_session.commit()

        with patch(
            "services.stock_service.StockService.transfer_stock",
            side_effect=ValueError("الكمية يجب أن تكون أكبر من صفر."),
        ):
            result = _handler(dispatcher, "transfer_stock")(
                {"product_name": "C4 VE", "quantity": -1, "from_warehouse_id": 1, "to_warehouse_id": 2}
            )
        assert not result.success
        assert "أكبر من صفر" in result.message

    def test_transfer_stock_generic_error_funnel(self, dispatcher, mock_ai_user, db_session):
        from decimal import Decimal

        from models import Product, Warehouse

        db_session.add(Warehouse(tenant_id=1, branch_id=None, name="C4 WH G", is_active=True))
        db_session.add(Warehouse(tenant_id=1, branch_id=None, name="C4 WH H", is_active=True))
        db_session.add(
            Product(
                tenant_id=1,
                name="C4 GE Product",
                sku="C4-GE",
                cost_price=Decimal("5"),
                regular_price=Decimal("9"),
            )
        )
        db_session.commit()

        with patch(
            "services.stock_service.StockService.transfer_stock",
            side_effect=RuntimeError("storage blew up"),
        ):
            result = _handler(dispatcher, "transfer_stock")(
                {"product_name": "C4 GE", "quantity": 1, "from_warehouse_id": 1, "to_warehouse_id": 2}
            )
        assert not result.success
        assert "خطأ في تحويل المخزون" in result.message


# ── sales ────────────────────────────────────────────────────────────────


def _executor_patch(method: str, return_value=None, init_exc: Exception | None = None):
    """Patch the AIExecutor service seam imported inside dispatcher handlers."""
    cls = MagicMock()
    if init_exc is not None:
        cls.side_effect = init_exc
    else:
        getattr(cls.return_value, method).return_value = return_value or {}
    return patch("services.ai_executor.AIExecutor", cls)


class TestSaleHandlers:
    def test_create_sale_requires_names(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "create_sale")({"customer_name": "", "product_name": ""})
        assert not result.success
        assert "اسم العميل والمنتج" in result.message

    def test_create_sale_success_with_unit_price(self, dispatcher, mock_ai_user):
        executor_payload = {
            "success": True,
            "message": "تمت الفاتورة",
            "sale_id": 11,
            "sale_number": "S-C4-1",
            "total": 240.0,
        }
        with _executor_patch("create_sale", executor_payload) as executor_cls:
            result = _handler(dispatcher, "create_sale")(
                {
                    "customer_name": "عميل C4",
                    "product_name": "منتج C4",
                    "quantity": 3,
                    "unit_price": 80,
                    "paid_amount": 100,
                    "payment_method": "cash",
                }
            )
        assert result.success
        assert result.data["sale_number"] == "S-C4-1"
        lines_arg = executor_cls.return_value.create_sale.call_args.kwargs["product_lines"]
        assert lines_arg[0]["unit_price"] == 80.0

    def test_create_sale_failure_result_path(self, dispatcher, mock_ai_user):
        with _executor_patch("create_sale", {"success": False, "message": "الكمية غير متوفرة"}):
            result = _handler(dispatcher, "create_sale")({"customer_name": "عميل C4", "product_name": "منتج C4"})
        assert not result.success
        assert "الكمية غير متوفرة" in result.message

    def test_create_sale_executor_crash_funnel(self, dispatcher, mock_ai_user):
        with _executor_patch("create_sale", init_exc=RuntimeError("no stock service")):
            result = _handler(dispatcher, "create_sale")({"customer_name": "عميل C4", "product_name": "منتج C4"})
        assert not result.success
        assert "خطأ في إنشاء الفاتورة" in result.message

    def test_cancel_sale_requires_identifier(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "cancel_sale")({})
        assert not result.success
        assert "رقم الفاتورة" in result.message

    def test_cancel_sale_not_found(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "cancel_sale")({"sale_number": "NOPE-C4-404"})
        assert not result.success
        assert "غير موجودة" in result.message

    def _patched_sale_lookup(self, sale_id=5, number="S-C4-9", total="88.500"):
        fake_sale = MagicMock()
        fake_sale.id = sale_id
        fake_sale.sale_number = number
        fake_sale.total_amount = Decimal(total)
        chain = MagicMock()
        chain.filter_by.return_value.first.return_value = fake_sale
        return (
            patch("models.Sale.query", chain),
            fake_sale,
        )

    def _seed_real_sale(self, db_session, *, number="S-C4-REAL"):
        from datetime import UTC, datetime

        from models import Customer, Sale

        customer = Customer(tenant_id=1, name=f"cust-{number}")
        db_session.add(customer)
        db_session.commit()
        sale = Sale(
            tenant_id=1,
            customer_id=customer.id,
            sale_number=number,
            sale_date=datetime.now(UTC),
            seller_id=1,
            subtotal=Decimal("88.500"),
            total_amount=Decimal("88.500"),
            amount=Decimal("88.500"),
            amount_aed=Decimal("88.500"),
            paid_amount=Decimal("0"),
            paid_amount_aed=Decimal("0"),
            balance_due=Decimal("88.500"),
            currency="AED",
            exchange_rate=1,
            payment_status="unpaid",
            status="confirmed",
            source="internal",
            notes="c4-cancel-seed",
        )
        db_session.add(sale)
        db_session.commit()
        return sale

    def test_cancel_sale_success_reverses_via_service(self, dispatcher, mock_ai_user, db_session):
        self._seed_real_sale(db_session)
        with (
            patch("services.sale_service.SaleService.cancel_sale") as cancel,
            patch("ai_knowledge.action_dispatcher._audit") as audit,
        ):
            result = _handler(dispatcher, "cancel_sale")({"sale_number": "S-C4-REAL"})
        assert result.success
        assert result.action_type == "sale_cancel"
        assert result.data["total"] == pytest.approx(88.5)
        cancel.assert_called_once()
        audit.assert_called_once()

    def test_cancel_sale_value_error_passthrough(self, dispatcher, mock_ai_user):
        sale_query_patch, _ = self._patched_sale_lookup()
        with (
            sale_query_patch,
            patch(
                "services.sale_service.SaleService.cancel_sale",
                side_effect=ValueError("لا يمكن إلغاء فاتورة مرتجعة"),
            ),
        ):
            result = _handler(dispatcher, "cancel_sale")({"sale_id": 5})
        assert not result.success
        assert "مرتجعة" in result.message

    def test_cancel_sale_generic_error_funnel(self, dispatcher, mock_ai_user):
        sale_query_patch, _ = self._patched_sale_lookup()
        with (
            sale_query_patch,
            patch("services.sale_service.SaleService.cancel_sale", side_effect=RuntimeError("glitch")),
        ):
            result = _handler(dispatcher, "cancel_sale")({"sale_number": "S-C4-9"})
        assert not result.success
        assert "خطأ في إلغاء الفاتورة" in result.message


# ── payments / expenses ──────────────────────────────────────────────────


class TestPaymentExpenseHandlers:
    def test_receive_payment_requires_customer_and_amount(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "receive_payment")({"customer_name": "أحمد", "amount": 0})
        assert not result.success
        assert "اسم العميل والمبلغ" in result.message

    def test_add_expense_requires_description_and_amount(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "add_expense")({"description": "", "amount": -5})
        assert not result.success
        assert "الوصف والمبلغ" in result.message

    def test_add_expense_unknown_category_prompt(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "add_expense")(
            {"description": "C4 بند", "amount": 33, "category": "فئة-غير-موجودة-C4"}
        )
        assert not result.success
        assert "غير موجودة" in result.message

    def test_add_expense_resolves_category_and_persists(self, dispatcher, mock_ai_user, db_session):
        from models import Expense, ExpenseCategory

        mock_ai_user.id = 1  # FK anchor users.id=1 exists in the test DB
        db_session.add(ExpenseCategory(tenant_id=1, name="C4 مصروف تجريبي"))
        db_session.commit()

        result = _handler(dispatcher, "add_expense")(
            {"description": "C4 اشتراك خدمة", "amount": 45.5, "category": "C4 مصروف تجريبي"}
        )
        assert result.success, result.message
        assert result.action_type == "expense_add"
        expense = db_session.query(Expense).filter_by(description="C4 اشتراك خدمة").one()
        assert float(expense.amount) == pytest.approx(45.5)
        assert expense.expense_number.startswith("AIE-")
        assert expense.user_id == mock_ai_user.id


# ── suppliers ────────────────────────────────────────────────────────────


class TestSupplierHandlers:
    def test_create_supplier_requires_name(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "create_supplier")({"phone": "0500"})
        assert not result.success
        assert "اسم المورد" in result.message

    def test_create_supplier_duplicate_blocked(self, dispatcher, mock_ai_user, db_session):
        from models import Supplier

        db_session.add(Supplier(tenant_id=1, name="C4-Dup-Supplier"))
        db_session.commit()

        result = _handler(dispatcher, "create_supplier")({"name": "C4-Dup-Supplier"})
        assert not result.success
        assert result.action_type == "supplier_duplicate"

    def test_create_supplier_success_persists(self, dispatcher, mock_ai_user, db_session):
        from models import Supplier

        result = _handler(dispatcher, "create_supplier")(
            {"name": "C4 New Supplier", "company": "C4 Co", "phone": "0551112222", "tax_number": "TXN-C4"}
        )
        assert result.success
        assert result.action_type == "supplier_create"
        supplier = db_session.query(Supplier).filter_by(name="C4 New Supplier").one()
        assert supplier.tax_number == "TXN-C4"


# ── employees / purchases / users ────────────────────────────────────────


class TestEmployeePurchaseUserHandlers:
    def test_create_employee_requires_name(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "create_employee")({})
        assert not result.success
        assert "اسم الموظف" in result.message

    def test_create_purchase_requires_supplier_and_product(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "create_purchase")({"supplier_name": "س"})
        assert not result.success
        assert "اسم المورد والمنتج" in result.message

    def test_create_purchase_demands_unit_cost(self, dispatcher, mock_ai_user):
        result = _handler(dispatcher, "create_purchase")(
            {"supplier_name": "مورد C4", "product_name": "منتج C4", "quantity": 2}
        )
        assert not result.success
        assert "سعر تكلفة الوحدة" in result.message

    def test_create_purchase_failure_result_path(self, dispatcher, mock_ai_user):
        with _executor_patch(
            "create_purchase", {"success": False, "message": "المورد غير مسجل — أنشئه أولاً"}
        ) as executor_cls:
            result = _handler(dispatcher, "create_purchase")(
                {
                    "supplier_name": "مورد C4",
                    "product_name": "منتج C4",
                    "quantity": 2,
                    "unit_cost": 12.5,
                }
            )
        assert not result.success
        assert "المورد غير مسجل" in result.message
        assert executor_cls.return_value.create_purchase.call_args.kwargs["product_lines"][0]["unit_cost"] == 12.5

    def test_create_purchase_executor_crash_funnel(self, dispatcher, mock_ai_user):
        with _executor_patch("create_purchase", init_exc=RuntimeError("db locked")):
            result = _handler(dispatcher, "create_purchase")(
                {"supplier_name": "مورد C4", "product_name": "منتج C4", "unit_cost": 3}
            )
        assert not result.success
        assert "حدث خطأ" not in result.message  # generic funnel text is specific
        assert not result.data

    def test_create_user_denied_for_non_owner(self, dispatcher, mock_ai_user):
        with patch("ai_knowledge.action_dispatcher._is_owner", return_value=False):
            result = _handler(dispatcher, "create_user")({"username": "u", "password": "p"})
        assert not result.success
        assert result.needs_permission == "admin"

    def test_create_user_owner_requires_credentials(self, dispatcher, mock_ai_user):
        with patch("ai_knowledge.action_dispatcher._is_owner", return_value=True):
            result = _handler(dispatcher, "create_user")({"username": "", "password": ""})
        assert not result.success
        assert "اسم المستخدم وكلمة المرور" in result.message

    def test_create_user_unknown_role_lists_available(self, dispatcher, mock_ai_user):
        with patch("ai_knowledge.action_dispatcher._is_owner", return_value=True):
            result = _handler(dispatcher, "create_user")(
                {"username": "c4-user", "password": "secret123", "role": "role-does-not-exist-c4"}
            )
        assert not result.success
        assert "الدور الوظيفي" in result.message

    def test_create_user_constructor_crash_funnel(self, dispatcher, mock_ai_user, db_session):
        from models import Role

        db_session.add(Role(name="C4 Role", slug="c4-role-real", is_active=True))
        db_session.commit()
        with (
            patch("ai_knowledge.action_dispatcher._is_owner", return_value=True),
            patch("models.User", side_effect=RuntimeError("hash failed")),
        ):
            result = _handler(dispatcher, "create_user")(
                {"username": "c4-u2", "password": "pw", "role": "c4-role-real"}
            )
        assert not result.success
        assert "hash failed" in result.message
