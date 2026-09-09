"""Residual-line/arc coverage for cli_commands.py ``_do_seed_demo``.

Targets (branch coverage):
- line 638 (``break``): product loop exhausts the catalogue before the
  branch/iteration grid ends.
- line 731 (``continue``): sale spec with missing customer/product skipped.
- line 766 (``continue``): purchase spec with missing supplier/product skipped.
- line 858 (``continue``): sale return with no usable first line skipped.
- arc 445->462: ``TenantStore`` already exists — store creation skipped.
- line 699 (``continue``): payroll user lookup misses.
- arc 701->705: payroll employee already exists — creation skipped.
- arc 705->696: payroll transaction already exists — loops back.
- arc 811->810: salary advance already exists — creation skipped.

Every test runs ``_do_seed_demo`` with the persistence/service layers fully
mocked, so no database is touched.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


def _install_seed_mocks(mocker):
    """Patch every external dependency of ``_do_seed_demo`` with defaults."""
    ctx = {}
    mock_db = mocker.patch("extensions.db")
    ctx["db"] = mock_db
    mock_db.session.query.return_value.filter.return_value.scalar.return_value = Decimal("0")

    tenant_cls = mocker.patch("models.tenant.Tenant")
    tenant_cls.query.filter_by.return_value.first.return_value = None
    tenant_cls.return_value = MagicMock(id=777)
    ctx["tenant_cls"] = tenant_cls

    ctx["branch_cls"] = mocker.patch("models.branch.Branch")
    ctx["branch_cls"].return_value = MagicMock(id=10)
    ctx["branch_cls"].query.filter_by.return_value.first.return_value = MagicMock(id=5)

    ctx["warehouse_cls"] = mocker.patch("models.warehouse.Warehouse")
    ctx["cashbox_cls"] = mocker.patch("models.cash_box.CashBox")
    ctx["tenant_store_cls"] = mocker.patch("models.tenant_store.TenantStore")
    ctx["tenant_store_cls"].query.filter_by.return_value.first.return_value = None

    ctx["product_category_cls"] = mocker.patch("models.product.ProductCategory")
    pos_order_type_cls = mocker.patch("models.PosOrderType")
    pos_order_type_cls.__table__ = MagicMock()
    ctx["pos_order_type_cls"] = pos_order_type_cls
    ctx["ensure_pos_types"] = mocker.patch("models.ensure_default_pos_order_types")

    customer_cls = mocker.patch("models.customer.Customer")
    ctx["sale_customers"] = [MagicMock(id=1), MagicMock(id=2), MagicMock(id=3)]
    customer_cls.query.filter_by.return_value.limit.return_value.all.return_value = ctx["sale_customers"]
    customer_cls.query.filter_by.return_value.all.return_value = [MagicMock(id=1, balance=Decimal("0"))]
    ctx["customer_cls"] = customer_cls

    supplier_cls = mocker.patch("models.supplier.Supplier")
    ctx["suppliers"] = [MagicMock(id=11), MagicMock(id=12), MagicMock(id=13)]
    supplier_cls.query.filter_by.return_value.limit.return_value.all.return_value = ctx["suppliers"]
    ctx["supplier_cls"] = supplier_cls

    product_cls = mocker.patch("models.product.Product")
    ctx["products_for_sale"] = [MagicMock(id=i) for i in range(21, 27)]
    product_cls.query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = ctx[
        "products_for_sale"
    ]
    ctx["product_cls"] = product_cls

    partner_cls = mocker.patch("models.partner.Partner")
    partner_cls.query.filter_by.return_value.all.return_value = []
    ctx["partner_cls"] = partner_cls

    role_cls = mocker.patch("models.user.Role")
    role_cls.query.filter_by.return_value.first.return_value = MagicMock(id=9)
    ctx["role_cls"] = role_cls
    permission_cls = mocker.patch("models.user.Permission")
    permission_cls.query.filter.return_value.all.return_value = []
    permission_cls.query.all.return_value = []

    user_cls = mocker.patch("models.user.User")
    ctx["seller"] = MagicMock(id=31, full_name_ar="Seller")
    ctx["cashier"] = MagicMock(id=32, full_name_ar="Cashier")
    payroll_users = [
        MagicMock(id=41, full_name_ar="Manager"),
        MagicMock(id=42, full_name_ar="Accountant"),
        MagicMock(id=43, full_name_ar="Cashier One"),
    ]
    user_cls.query.filter_by.return_value.first.side_effect = [
        *payroll_users,
        ctx["seller"],
        ctx["cashier"],
    ]
    ctx["user_cls"] = user_cls

    employee_cls = mocker.patch("models.payroll.Employee")
    employee_cls.query.filter_by.return_value.first.return_value = None
    employee_cls.query.filter_by.return_value.all.return_value = [MagicMock(id=51), MagicMock(id=52)]
    ctx["employee_cls"] = employee_cls

    payroll_tx_cls = mocker.patch("models.payroll.PayrollTransaction")
    payroll_tx_cls.query.filter_by.return_value.first.return_value = None
    ctx["payroll_tx_cls"] = payroll_tx_cls

    advance_cls = mocker.patch("models.payroll.SalaryAdvance")
    advance_cls.query.filter_by.return_value.first.return_value = None
    ctx["advance_cls"] = advance_cls

    expense_cls = mocker.patch("models.expense.Expense")
    ctx["expense_cls"] = expense_cls
    ctx["expense_category_cls"] = mocker.patch("models.expense.ExpenseCategory")
    ctx["pos_session_cls"] = mocker.patch("models.pos_session.PosSession")

    sale_cls = mocker.patch("models.sale.Sale")
    good_sale = MagicMock(id=61)
    good_sale.lines = [MagicMock(id=71, product=MagicMock(id=81))]
    sale_cls.query.filter_by.return_value.limit.return_value.all.return_value = [good_sale]
    ctx["sale_cls"] = sale_cls

    pws_cls = mocker.patch("models.warehouse.ProductWarehouseStock")
    pws_cls.query.filter_by.return_value.first.return_value = MagicMock(warehouse_id=11)

    ctx["doc_seq"] = mocker.patch("services.document_sequence_service.DocumentSequenceService")
    ctx["provision_gl"] = mocker.patch("services.tenant_provisioning.provision_tenant_gl")
    ctx["validate_industry"] = mocker.patch("services.tenant_provisioning.validate_tenant_industry")
    ctx["stock_service"] = mocker.patch("services.stock_service.StockService")
    ctx["sale_service"] = mocker.patch("services.sale_service.SaleService")
    ctx["purchase_service"] = mocker.patch("services.purchase_service.PurchaseService")
    ctx["payment_service"] = mocker.patch("services.payment_service.PaymentService")
    ctx["return_service"] = mocker.patch("services.return_service.ReturnService")
    return ctx


def _run_seed():
    import cli_commands

    cli_commands._do_seed_demo(MagicMock())


class TestSeedDemoStoreExistsArc:
    """Arc 445->462: existing TenantStore skips store creation."""

    def test_existing_store_skips_creation(self, mocker):
        ctx = _install_seed_mocks(mocker)
        ctx["tenant_store_cls"].query.filter_by.return_value.first.return_value = MagicMock(id=99)
        _run_seed()
        ctx["tenant_store_cls"].assert_not_called()


class TestSeedDemoProductBreak:
    """Line 638: catalogue exhausted before the branch grid ends."""

    def test_break_when_products_exhausted(self, mocker):
        ctx = _install_seed_mocks(mocker)
        real_range = range

        def _wide_range(*args, **kwargs):
            if tuple(args) == (3,) and not kwargs:
                return real_range(10)
            return real_range(*args, **kwargs)

        mocker.patch("builtins.range", side_effect=_wide_range)
        _run_seed()
        assert ctx["stock_service"].add_stock.call_count == 12


class TestSeedDemoSalePurchaseContinues:
    """Lines 731/766: specs with missing party/product are skipped."""

    def test_missing_customer_and_supplier_skip_specs(self, mocker):
        ctx = _install_seed_mocks(mocker)
        ctx["sale_customers"][1] = None
        ctx["customer_cls"].query.filter_by.return_value.limit.return_value.all.return_value = ctx["sale_customers"]
        ctx["suppliers"][1] = None
        ctx["supplier_cls"].query.filter_by.return_value.limit.return_value.all.return_value = ctx["suppliers"]
        _run_seed()
        assert ctx["sale_service"].create_sale.call_count == 2
        assert ctx["purchase_service"].create_purchase.call_count == 2


class TestSeedDemoReturnContinue:
    """Line 858: sales without a usable first line are skipped."""

    def test_sales_without_lines_skipped(self, mocker):
        ctx = _install_seed_mocks(mocker)
        empty_sale = MagicMock(id=62)
        empty_sale.lines = []
        bad_sale = MagicMock(id=63)
        bad_sale.lines = [MagicMock(id=72, product=None)]
        good_sale = MagicMock(id=64)
        good_sale.lines = [MagicMock(id=73, product=MagicMock(id=83))]
        ctx["sale_cls"].query.filter_by.return_value.limit.return_value.all.return_value = [
            empty_sale,
            bad_sale,
            good_sale,
        ]
        _run_seed()
        assert ctx["return_service"].create_return.call_count == 1


class TestSeedDemoPayrollBranches:
    """Line 699 + arcs 701->705 / 705->696 in the payroll section."""

    def test_missing_user_skips_and_new_employees_created(self, mocker):
        ctx = _install_seed_mocks(mocker)
        found_one = MagicMock(id=42, full_name_ar="Accountant")
        found_two = MagicMock(id=43, full_name_ar="Cashier One")
        ctx["user_cls"].query.filter_by.return_value.first.side_effect = [
            None,
            found_one,
            found_two,
            ctx["seller"],
            ctx["cashier"],
        ]
        ctx["employee_cls"].query.filter_by.return_value.first.side_effect = [None, None]
        ctx["payroll_tx_cls"].query.filter_by.return_value.first.side_effect = [None, None]
        _run_seed()
        assert ctx["employee_cls"].call_count == 2
        assert ctx["payroll_tx_cls"].call_count == 2

    def test_existing_employee_and_payroll_skip_creation(self, mocker):
        ctx = _install_seed_mocks(mocker)
        ctx["employee_cls"].query.filter_by.return_value.first.side_effect = [
            MagicMock(id=51),
            MagicMock(id=52),
            MagicMock(id=53),
        ]
        ctx["payroll_tx_cls"].query.filter_by.return_value.first.side_effect = [
            MagicMock(id=91),
            MagicMock(id=92),
            MagicMock(id=93),
        ]
        _run_seed()
        assert ctx["employee_cls"].call_count == 0
        assert ctx["payroll_tx_cls"].call_count == 0


class TestSeedDemoAdvanceExistsArc:
    """Arc 811->810: existing salary advance skips creation."""

    def test_existing_advance_skips_creation(self, mocker):
        ctx = _install_seed_mocks(mocker)
        ctx["employee_cls"].query.filter_by.return_value.all.return_value = [
            MagicMock(id=51),
            MagicMock(id=52),
            MagicMock(id=53),
        ]
        ctx["advance_cls"].query.filter_by.return_value.first.side_effect = [
            MagicMock(id=71),
            None,
            None,
        ]
        _run_seed()
        assert ctx["advance_cls"].call_count == 2
