"""
Comprehensive smoke tests for core services.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch


class TestPrintService:
    """Test PrintService — print engine with PDF, bulk print, audit."""

    def test_import(self):
        from services.print_service import PrintService

        assert PrintService is not None

    def test_user_context_returns_dict(self):
        from services.print_service import PrintService

        ctx = PrintService._user_context()
        assert isinstance(ctx, dict)
        assert "print_user_name" in ctx
        assert "print_user_id" in ctx

    def test_user_context_handles_missing_user(self):
        from services.print_service import PrintService

        with patch("services.print_service.current_user", create=True) as mock:
            type(mock).full_name = PropertyMock(side_effect=Exception("no user"))
            ctx = PrintService._user_context()
            assert ctx["print_user_name"] == "—"
            assert ctx["print_user_id"] is None

    @patch(
        "services.print_service.render_template", return_value="<html>printed</html>"
    )
    def test_render_print_basic(self, mock_render):
        from services.print_service import PrintService

        with patch.object(
            PrintService,
            "_get_tenant_context",
            return_value={
                "tenant": None,
                "settings": None,
                "company": None,
                "print_branding": {},
                "print_tenant_id": 1,
            },
        ):
            with patch.object(
                PrintService,
                "_user_context",
                return_value={"print_user_name": "test", "print_user_id": 1},
            ):
                result = PrintService.render_print("print/test.html")
                assert result == "<html>printed</html>"
                mock_render.assert_called_once()

    @patch(
        "services.print_service.render_template", return_value="<html>with-extra</html>"
    )
    def test_render_print_with_extra_context(self, mock_render):
        from services.print_service import PrintService

        with patch.object(
            PrintService,
            "_get_tenant_context",
            return_value={
                "tenant": None,
                "settings": None,
                "company": None,
                "print_branding": {},
                "print_tenant_id": 1,
            },
        ):
            with patch.object(
                PrintService,
                "_user_context",
                return_value={"print_user_name": "test", "print_user_id": 1},
            ):
                result = PrintService.render_print(
                    "print/test.html", extra_context={"doc_id": 42}
                )
                assert result == "<html>with-extra</html>"
                args, kwargs = mock_render.call_args
                assert "doc_id" in kwargs

    def test_audit_print_creates_record(self, app):
        from services.print_service import PrintService

        with app.app_context():
            record_instance = MagicMock()
            with (
                patch("extensions.db") as mock_db,
                patch(
                    "models.print_history.PrintHistory", return_value=record_instance
                ),
            ):
                PrintService.audit_print(
                    tenant_id=1, document_type="sale", document_id=100, user_id=5
                )
                assert mock_db.session.add.called
                assert mock_db.session.flush.called

    @patch(
        "services.print_service.PrintService.render_print",
        return_value="<html>page-1</html>",
    )
    def test_bulk_print_documents_single(self, mock_render):
        from services.print_service import PrintService

        docs = [{"type": "sale", "context": {"sale_id": 1}}]
        tmpl_map = {"sale": "print/sale.html"}
        result = PrintService.bulk_print_documents(docs, tmpl_map, tenant_id=1)
        assert "<html" in result
        assert "page-1" in result
        mock_render.assert_called_once()

    @patch(
        "services.print_service.PrintService.render_print",
        side_effect=["<html>page-1</html>", "<html>page-2</html>"],
    )
    def test_bulk_print_documents_multiple(self, mock_render):
        from services.print_service import PrintService

        docs = [
            {"type": "sale", "context": {"sale_id": 1}},
            {"type": "purchase", "context": {"purchase_id": 2}},
        ]
        tmpl_map = {"sale": "print/sale.html", "purchase": "print/purchase.html"}
        result = PrintService.bulk_print_documents(docs, tmpl_map, tenant_id=1)
        assert "page-1" in result
        assert "page-2" in result
        assert "page-break" in result
        assert mock_render.call_count == 2

    def test_bulk_print_empty_docs(self):
        from services.print_service import PrintService

        result = PrintService.bulk_print_documents([], {}, tenant_id=1)
        assert "لا توجد مستندات للطباعة" in result


class TestUserService:
    """Test UserService — user listing, stats, tenant scoping."""

    def test_import(self):
        from services.user_service import UserService

        assert UserService is not None

    def test_get_users_list_context(self):
        from services.user_service import UserService

        with (
            patch("services.user_service.Role") as mock_role,
            patch("services.user_service.User") as mock_user,
            patch("services.user_service.Tenant") as mock_tenant,
            patch("services.user_service.scoped_user_query") as mock_scoped,
            patch("services.user_service.joinedload", return_value=lambda x: x),
        ):
            mock_role.query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_tenant.query.filter_by.return_value.order_by.return_value.all.return_value = []

            q = MagicMock()
            mock_scoped.return_value = q
            q.options.return_value.order_by.return_value.all.return_value = []

            base = MagicMock()
            mock_scoped.side_effect = [q, base]
            base.count.return_value = 0
            base.filter_by.return_value.count.return_value = 0
            base.join.return_value.filter.return_value.count.return_value = 0
            mock_user.query.filter_by.return_value.count.return_value = 0

            ctx = UserService.get_users_list_context(tenant_id=1)
            assert "users" in ctx
            assert "stats" in ctx
            assert "tenants" in ctx
            assert "active_tenant_id" in ctx
            assert ctx["stats"]["total"] == 0

    def test_get_users_list_context_with_data(self):
        from services.user_service import UserService

        with (
            patch("services.user_service.Role") as mock_role,
            patch("services.user_service.User") as mock_user,
            patch("services.user_service.Tenant") as mock_tenant,
            patch("services.user_service.scoped_user_query") as mock_scoped,
            patch("services.user_service.joinedload", return_value=lambda x: x),
        ):
            mock_role.query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_tenant.query.filter_by.return_value.order_by.return_value.all.return_value = []

            user_mock = MagicMock(id=1, username="testuser")
            q = MagicMock()
            mock_scoped.return_value = q
            q.options.return_value.order_by.return_value.all.return_value = [user_mock]

            base = MagicMock()
            mock_scoped.side_effect = [q, base]
            base.count.return_value = 5
            base.filter_by.return_value.count.return_value = 3
            base.join.return_value.filter.return_value.count.return_value = 2
            mock_user.query.filter_by.return_value.count.return_value = 1

            ctx = UserService.get_users_list_context(tenant_id=1)
            assert len(ctx["users"]) == 1
            assert ctx["stats"]["total"] == 5
            assert ctx["stats"]["active"] == 3


class TestTenantService:
    """Test TenantService — tenant listing with counts."""

    def test_import(self):
        from services.tenant_service import TenantService

        assert TenantService is not None

    def test_get_tenants_list_context_empty(self):
        from services.tenant_service import TenantService

        with patch("services.tenant_service.Tenant.query") as mock_query:
            mock_query.order_by.return_value.all.return_value = []
            ctx = TenantService.get_tenants_list_context()
            assert ctx["tenants"] == []
            assert ctx["user_counts"] == {}
            assert ctx["branch_counts"] == {}
            assert ctx["store_counts"] == {}

    def test_get_tenants_list_context_with_data(self):
        from services.tenant_service import TenantService

        with (
            patch("services.tenant_service.Tenant.query") as mock_query,
            patch("services.tenant_service.db.session.query") as mock_dbq,
        ):
            t = MagicMock(id=1, name="Test Co")
            mock_query.order_by.return_value.all.return_value = [t]
            mock_dbq.return_value.filter.return_value.group_by.return_value.all.return_value = [
                (1, 5)
            ]
            ctx = TenantService.get_tenants_list_context()
            assert len(ctx["tenants"]) == 1
            assert ctx["user_counts"][1] == 5
            assert ctx["branch_counts"][1] == 5
            assert ctx["store_counts"][1] == 5


class TestRoleService:
    """Test RoleService — roles, permissions, categories."""

    def test_import(self):
        from services.role_service import RoleService

        assert RoleService is not None

    def test_get_roles_permissions_context_empty(self):
        from services.role_service import RoleService

        with (
            patch("services.role_service.Role") as mock_role,
            patch("services.role_service.Permission") as mock_perm,
            patch("services.role_service.joinedload"),
        ):
            mock_role.query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_perm.query.order_by.return_value.all.return_value = []
            ctx = RoleService.get_roles_permissions_context(tenant_id=1)
            assert ctx["roles"] == []
            assert ctx["permissions"] == []
            assert ctx["perm_categories"] == {}
            assert ctx["role_user_counts"] == {}

    def test_get_roles_permissions_context_with_data(self):
        from services.role_service import RoleService

        with (
            patch("services.role_service.Role") as mock_role,
            patch("services.role_service.Permission") as mock_perm,
            patch("services.role_service.User") as mock_user,
            patch("services.role_service.joinedload"),
        ):
            r = MagicMock(id=1, name="Admin")
            mock_role.query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = [
                r
            ]
            p = MagicMock(category="sales", name="manage_sales")
            mock_perm.query.order_by.return_value.all.return_value = [p]
            mock_user.query.filter_by.return_value.filter_by.return_value.count.return_value = 3
            ctx = RoleService.get_roles_permissions_context(tenant_id=1)
            assert len(ctx["roles"]) == 1
            assert ctx["role_user_counts"][1] == 3
            assert "sales" in ctx["perm_categories"]


class TestStockService:
    """Test StockService — stock movements, MWAC, COGS, reconciliations."""

    def test_import(self):
        from services.stock_service import StockService

        assert StockService is not None

    def test_mwac_calc_initial(self):
        from services.stock_service import StockService

        new_qty, new_val, new_avg = StockService._mwac_calc(
            Decimal("0"), Decimal("0"), Decimal("10"), Decimal("50")
        )
        assert new_qty == Decimal("10")
        assert new_val == Decimal("500")
        assert new_avg == Decimal("50.0000")

    def test_mwac_calc_addition(self):
        from services.stock_service import StockService

        new_qty, new_val, new_avg = StockService._mwac_calc(
            Decimal("10"), Decimal("500"), Decimal("5"), Decimal("60")
        )
        assert new_qty == Decimal("15")
        assert new_val == Decimal("800")
        assert new_avg == Decimal("53.3333")

    def test_mwac_calc_removal(self):
        from services.stock_service import StockService

        new_qty, new_val, new_avg = StockService._mwac_calc(
            Decimal("15"), Decimal("800"), Decimal("-5"), Decimal("53.3333")
        )
        assert new_qty == Decimal("10")
        assert new_val == Decimal("533.3335")
        assert new_avg == Decimal("53.3334")

    def test_mwac_calc_zero_result(self):
        from services.stock_service import StockService

        new_qty, new_val, new_avg = StockService._mwac_calc(
            Decimal("5"), Decimal("250"), Decimal("-5"), Decimal("50")
        )
        assert new_qty == Decimal("0")
        assert new_val == Decimal("0")
        assert new_avg == Decimal("0")

    def test_check_availability_product_not_found(self):
        from services.stock_service import StockService

        with patch("services.stock_service.db.session.get", return_value=None):
            ok, msg = StockService.check_availability(1, Decimal("5"))
            assert ok is False
            assert "غير موجود" in msg

    def test_check_availability_inactive_product(self):
        from services.stock_service import StockService

        p = MagicMock(is_active=False, current_stock=Decimal("10"))
        with patch("services.stock_service.db.session.get", return_value=p):
            ok, msg = StockService.check_availability(1, Decimal("5"))
            assert ok is False
            assert "غير نشط" in msg

    def test_check_availability_insufficient_stock(self):
        from services.stock_service import StockService

        p = MagicMock(is_active=True, current_stock=Decimal("3"))
        with patch("services.stock_service.db.session.get", return_value=p):
            ok, msg = StockService.check_availability(1, Decimal("5"))
            assert ok is False
            assert "غير كافٍ" in msg

    def test_check_availability_sufficient(self):
        from services.stock_service import StockService

        p = MagicMock(is_active=True, current_stock=Decimal("10"))
        with patch("services.stock_service.db.session.get", return_value=p):
            ok, msg = StockService.check_availability(1, Decimal("5"))
            assert ok is True
            assert msg == "متوفر"

    def test_resolve_cogs_raises_when_no_data(self, app):
        from services.stock_service import StockService

        with app.app_context():
            with (
                patch("services.stock_service.ProductWarehouseCost.query") as pwc_q,
                patch("services.stock_service.ProductCostHistory.query") as pch_q,
            ):
                pwc_q.filter_by.return_value.first.return_value = None
                pch_q.filter_by.return_value.order_by.return_value.first.return_value = None
                with pytest.raises(ValueError, match="لا يمكن تحديد تكلفة"):
                    StockService._resolve_cogs_unit_cost(
                        999, 999, 1, line_cost_price=None
                    )

    def test_resolve_cogs_from_cost_price(self, app):
        from services.stock_service import StockService

        with app.app_context():
            with patch("services.stock_service.ProductWarehouseCost.query") as pwc_q:
                pwc_q.filter_by.return_value.first.return_value = None
                cost, source = StockService._resolve_cogs_unit_cost(
                    999, 999, 1, line_cost_price=Decimal("150")
                )
                assert cost == Decimal("150")
                assert source == "cost_price"

    def test_resolve_cogs_from_mwac(self, app):
        from services.stock_service import StockService

        with app.app_context():
            with patch("services.stock_service.ProductWarehouseCost.query") as pwc_q:
                pwc = MagicMock(
                    total_quantity=Decimal("10"), average_cost=Decimal("45.5000")
                )
                pwc_q.filter_by.return_value.first.return_value = pwc
                cost, source = StockService._resolve_cogs_unit_cost(
                    999, 999, 1, line_cost_price=None
                )
                assert cost == Decimal("45.5000")
                assert source == "mwac"


class TestPurchaseService:
    """Test PurchaseService — purchase creation, cancellation, returns."""

    def test_import(self):
        from services.purchase_service import PurchaseService

        assert PurchaseService is not None

    def test_create_purchase_needs_warehouse(self):
        from services.purchase_service import PurchaseService

        with pytest.raises(ValueError, match="يجب اختيار المستودع"):
            PurchaseService.create_purchase(
                user=MagicMock(id=1),
                supplier_data={"supplier_name": "Test"},
                lines_data=[],
                warehouse_id=None,
            )

    def test_cancel_purchase_already_cancelled(self, app, db_session):
        from services.purchase_service import PurchaseService
        from models import Purchase

        with app.app_context():
            p = Purchase(status="cancelled")
            with pytest.raises(ValueError, match="ملغاة بالفعل"):
                PurchaseService.cancel_purchase(p)

    def test_create_purchase_return_needs_lines(self, app):
        from services.purchase_service import PurchaseService
        from models import Purchase

        with app.app_context():
            p = Purchase(status="received", id=1)
            with pytest.raises(ValueError, match="يجب إرجاع"):
                PurchaseService.create_purchase_return(p, MagicMock(id=1), [])


class TestSaleService:
    """Test SaleService — sale creation, fulfillment, cancellation."""

    def test_import(self):
        from services.sale_service import SaleService

        assert SaleService is not None

    def test_create_sale_needs_active_customer(self):
        from services.sale_service import SaleService

        customer = MagicMock(is_active=False)
        seller = MagicMock(is_active=True)
        with pytest.raises(ValueError, match="العميل غير صالح"):
            SaleService.create_sale(customer, seller, [])

    def test_create_sale_needs_active_seller(self):
        from services.sale_service import SaleService

        customer = MagicMock(is_active=True)
        seller = MagicMock(is_active=False)
        with pytest.raises(ValueError, match="البائع غير صالح"):
            SaleService.create_sale(customer, seller, [])

    def test_create_sale_needs_lines(self):
        from services.sale_service import SaleService

        customer = MagicMock(is_active=True)
        seller = MagicMock(is_active=True)
        with pytest.raises(ValueError, match="يجب إضافة منتج"):
            SaleService.create_sale(customer, seller, [])

    def test_fulfill_sale_needs_customer(self):
        from services.sale_service import SaleService

        sale = MagicMock(customer=None)
        with pytest.raises(ValueError, match="العميل غير موجود"):
            SaleService.fulfill_sale(sale)

    def test_cancel_sale_already_cancelled(self):
        from services.sale_service import SaleService

        sale = MagicMock(status="cancelled")
        with pytest.raises(ValueError, match="ملغاة بالفعل"):
            SaleService.cancel_sale(sale)

    def test_create_payment_for_sale_zero_amount(self):
        from services.sale_service import SaleService

        sale = MagicMock(branch_id=1)
        with pytest.raises(ValueError, match="مبلغ الدفع يجب أن يكون أكبر من صفر"):
            SaleService.create_payment_for_sale(sale, amount=0, payment_method="cash")

    def test_create_payment_for_sale_needs_cheque_number(self):
        from services.sale_service import SaleService

        sale = MagicMock(branch_id=1)
        with pytest.raises(ValueError, match="رقم الشيك مطلوب"):
            SaleService.create_payment_for_sale(
                sale,
                amount=100,
                payment_method="cheque",
                cheque_number=None,
                cheque_date="2025-06-01",
                bank_name="Test Bank",
            )

    def test_has_inventory_posted_no_records(self, app):
        from services.sale_service import SaleService

        with app.app_context():
            with patch("models.warehouse.StockMovement") as mock_sm:
                mock_sm.query.filter_by.return_value.first.return_value = None
                sale = MagicMock(id=99999)
                assert SaleService.has_inventory_posted(sale) is False

    def test_has_inventory_posted_with_records(self, app):
        from services.sale_service import SaleService

        with app.app_context():
            with patch("models.warehouse.StockMovement") as mock_sm:
                mock_sm.query.filter_by.return_value.first.return_value = MagicMock()
                sale = MagicMock(id=1)
                assert SaleService.has_inventory_posted(sale) is True

    def test_update_payment_status(self, app):
        from services.sale_service import SaleService

        with app.app_context():
            sale = MagicMock()
            sale.recalculate_payment_status = MagicMock()
            SaleService.update_payment_status(sale)
            sale.recalculate_payment_status.assert_called_once()
