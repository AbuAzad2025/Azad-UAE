"""Cov5b: reports_query_service — filter-variant and fragment arcs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal


def test_paid_maps_empty_and_unscoped(db_session, sample_tenant):
    from services.reports_query_service import ReportsQueryService as R

    assert R.get_confirmed_sale_paid_map([]) == {}
    assert R.get_confirmed_sale_paid_map([424242]) == {}
    assert R.get_confirmed_supplier_paid_aed(424242) == Decimal("0")


def test_scoped_queries_with_branch(mocker, sample_branch):
    from services.reports_query_service import ReportsQueryService as R

    mocker.patch("services.reports_query_service.report_branch_scope_id", return_value=sample_branch.id)
    assert isinstance(R._scoped_customer_query().all(), list)
    assert isinstance(R._scoped_supplier_query().all(), list)
    assert R.supplier_in_branch_scope(424242) in (True, False)
    assert R.customer_in_branch_scope(424242) in (True, False)


def test_fetch_unscoped_variants(db_session, sample_tenant, sample_user):
    from services.reports_query_service import ReportsQueryService as R

    assert isinstance(R.fetch_sales_report(None, None, None, None, None, None), list)
    assert isinstance(R.fetch_report_customers(None, None), list)
    assert isinstance(R.fetch_purchases_report(None, None, None, None, None), list)
    assert isinstance(R.fetch_receivables_sales(None, None, None), list)
    assert isinstance(R.fetch_inventory_warehouses(None, None, sample_user), list)
    assert isinstance(R.list_active_suppliers_for_filter(), list)
    assert R.find_active_warehouse(999999999) is None


def test_fetch_sellers_variants(db_session):
    from services.reports_query_service import ReportsQueryService as R

    assert isinstance(R.fetch_report_sellers(None), list)
    assert isinstance(R.fetch_report_sellers(424242), list)


def test_fetch_inventory_products_variants(db_session, sample_tenant, sample_product):
    from services.reports_query_service import ReportsQueryService as R

    assert isinstance(R.fetch_inventory_products(None, True, {}), list)
    stock_map = {sample_product.id: 5, 424242: 0}
    out = R.fetch_inventory_products(sample_product.category_id, False, stock_map)
    assert isinstance(out, list)
    assert R.fetch_inventory_products(None, False, {}) == []
    decimal_map = {sample_product.id: Decimal("5"), 424242: Decimal("0")}
    assert isinstance(R.fetch_inventory_products(None, False, decimal_map), list)


def test_search_entities_variants(db_session, sample_tenant, sample_supplier, sample_customer):
    from services.reports_query_service import ReportsQueryService as R

    assert isinstance(R.search_entities("Test", "supplier"), list)
    assert isinstance(R.search_entities("Test", "partner"), list)
    assert isinstance(R.search_entities("Test", "merchant"), list)
    assert isinstance(R.search_entities("Test", "customer"), list)


def test_reconciliation_warehouses_variants(db_session, sample_user, sample_branch):
    from services.reports_query_service import ReportsQueryService as R

    assert isinstance(R.fetch_inventory_reconciliation_warehouses(sample_branch.id, sample_user), list)
    assert isinstance(R.fetch_inventory_reconciliation_warehouses(None, sample_user), list)
    assert R.find_active_warehouse(999999999) is None


def test_fetch_sales_seller_filters(db_session, sample_tenant, sample_user, sample_customer):
    from services.reports_query_service import ReportsQueryService as R

    assert isinstance(R.fetch_sales_report(sample_tenant.id, None, None, None, None, sample_user.id), list)
    assert isinstance(R.fetch_sales_report(sample_tenant.id, None, None, None, sample_user.id, None), list)


def test_fetch_purchases_full_filters(db_session, sample_tenant, sample_branch, sample_supplier):
    from services.reports_query_service import ReportsQueryService as R

    day = date.today()
    assert isinstance(R.fetch_purchases_report(sample_tenant.id, None, day, day, sample_supplier.id), list)
    by_supplier, _ = R.fetch_purchases_payments(sample_tenant.id, None, day, day, sample_supplier.id)
    assert isinstance(by_supplier, dict)


def test_stock_maps_unscoped():
    from services.reports_query_service import ReportsQueryService as R

    day = date.today()
    out = R.build_stock_maps([424242], None, day, day, day, day)
    assert len(out) == 4


def test_fragments_unscoped(db_session, sample_supplier, sample_customer):
    from services.reports_query_service import ReportsQueryService as R

    R.build_supplier_fragment_data(sample_supplier.id, None, None)
    R.build_customer_fragment_data(sample_customer.id, "regular", None, None)
    R.build_customer_fragment_data(sample_customer.id, "partner", None, None)
    R.build_customer_fragment_data(sample_customer.id, "merchant", None, None)


def test_supplier_fragment_payment_only_no_invoices(
    db_session, sample_tenant, sample_branch, sample_user, sample_supplier
):
    from datetime import datetime

    from models import Payment
    from services.reports_query_service import ReportsQueryService as R

    p = Payment(
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        payment_number="R5F-1",
        payment_type="supplier",
        direction="outgoing",
        supplier_id=sample_supplier.id,
        amount=Decimal("30"),
        amount_aed=Decimal("30"),
        currency="ILS",
        payment_method="cash",
        payment_confirmed=True,
        payment_date=datetime.now(),
        user_id=sample_user.id,
    )
    db_session.add(p)
    db_session.flush()
    out = R.build_supplier_fragment_data(sample_supplier.id, sample_tenant.id, sample_branch.id)
    assert out["allocation_exact"] is False


def test_customer_fragment_negative_balance(db_session, sample_tenant, sample_branch, sample_user):
    from datetime import datetime

    from models import Customer, Receipt
    from services.reports_query_service import ReportsQueryService as R

    customer = Customer(tenant_id=sample_tenant.id, name="R5N")
    db_session.add(customer)
    db_session.flush()
    db_session.add(
        Receipt(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            receipt_number="R5N-1",
            customer_id=customer.id,
            amount=Decimal("100"),
            currency="ILS",
            amount_aed=Decimal("100"),
            payment_method="cash",
            payment_confirmed=True,
            receipt_date=datetime.now(),
            user_id=sample_user.id,
        )
    )
    db_session.flush()
    out = R.build_customer_fragment_data(customer.id, "regular", sample_tenant.id, sample_branch.id)
    assert out["balance"] == 100
    assert out["balance_label"] == "مستحق للعميل"
    assert out["transactions"]


def test_customer_fragment_outgoing_payment(db_session, sample_tenant, sample_branch, sample_user, sample_customer):
    from datetime import datetime

    from models import Payment
    from services.reports_query_service import ReportsQueryService as R

    db_session.add(
        Payment(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            payment_number="R5O-1",
            payment_type="customer",
            direction="outgoing",
            customer_id=sample_customer.id,
            amount=Decimal("10"),
            amount_aed=Decimal("10"),
            currency="ILS",
            payment_method="cash",
            payment_confirmed=True,
            payment_date=datetime.now(),
            user_id=sample_user.id,
        )
    )
    db_session.flush()
    out = R.build_customer_fragment_data(sample_customer.id, "regular", sample_tenant.id, sample_branch.id)
    assert isinstance(out["transactions"], list)


def test_top_selling_unscoped():
    from services.reports_query_service import ReportsQueryService as R

    day = date.today()
    assert isinstance(R.fetch_top_selling_products(day, day, None, None, 10), list)


def test_paid_maps_with_branch_and_purchase(db_session, sample_tenant, sample_branch):
    from services.reports_query_service import ReportsQueryService as R

    assert R.get_confirmed_sale_paid_map([424242], tenant_id=sample_tenant.id, branch_id=sample_branch.id) == {}
    assert R.get_confirmed_supplier_paid_aed(424242, purchase_id=424242, tenant_id=sample_tenant.id) == Decimal("0")


def test_fetch_sales_full_filters(db_session, sample_tenant, sample_branch, sample_user, sample_customer):
    from services.reports_query_service import ReportsQueryService as R

    day = date.today()
    assert isinstance(
        R.fetch_sales_report(sample_tenant.id, sample_branch.id, day, day, sample_customer.id, sample_user.id),
        list,
    )
    assert isinstance(R.fetch_sales_report(sample_tenant.id, None, None, None, None, sample_user.id), list)


def test_fetch_purchases_and_payments_full_filters(db_session, sample_tenant, sample_branch, sample_supplier):
    from services.reports_query_service import ReportsQueryService as R

    day = date.today()
    assert isinstance(R.fetch_purchases_report(sample_tenant.id, None, day, day, sample_supplier.id), list)
    by_supplier, _ = R.fetch_purchases_payments(sample_tenant.id, None, None, day, None)
    assert isinstance(by_supplier, dict)
    assert isinstance(R.fetch_receivables_sales(sample_tenant.id, None, sample_supplier.id), list)


def test_reconciliation_warehouses_mocked(mocker, sample_user, sample_branch):
    from services.reports_query_service import ReportsQueryService as R

    mocker.patch("utils.branching.get_accessible_warehouse_ids", return_value=[sample_branch.id])
    assert isinstance(R.fetch_inventory_reconciliation_warehouses(None, sample_user), list)
    mocker.patch("utils.branching.get_accessible_warehouse_ids", return_value=[])
    assert isinstance(R.fetch_inventory_reconciliation_warehouses(None, sample_user), list)


def test_inventory_warehouses_variants(mocker, db_session, sample_tenant, sample_user, sample_branch):
    from services.reports_query_service import ReportsQueryService as R

    mocker.patch("utils.branching.get_accessible_warehouse_ids", return_value=[sample_branch.id])
    assert isinstance(R.fetch_inventory_warehouses(sample_tenant.id, None, sample_user), list)
    mocker.patch("utils.branching.get_accessible_warehouse_ids", return_value=[])
    assert isinstance(R.fetch_inventory_warehouses(sample_tenant.id, None, sample_user, ordered=False), list)


def test_inventory_products_with_category(db_session, sample_tenant):
    from models import ProductCategory
    from services.reports_query_service import ReportsQueryService as R

    cat = ProductCategory(tenant_id=sample_tenant.id, name="R5Cat")
    db_session.add(cat)
    db_session.flush()
    assert isinstance(R.fetch_inventory_products(cat.id, True, {}), list)


def test_partners_report_unscoped(db_session, sample_tenant, sample_user, sample_branch, sample_supplier):
    from datetime import datetime

    from models import Purchase
    from services.reports_query_service import ReportsQueryService as R

    po = Purchase(
        tenant_id=sample_tenant.id,
        purchase_number=f"R5U-{sample_tenant.id}",
        supplier_id=sample_supplier.id,
        supplier_name="Sup",
        branch_id=sample_branch.id,
        purchase_date=datetime.now(),
        total_amount=Decimal("50"),
        amount=Decimal("50"),
        amount_aed=Decimal("50"),
        currency="ILS",
        status="confirmed",
        user_id=sample_user.id,
    )
    db_session.add(po)
    db_session.flush()
    out = R.build_partners_report(None, None, None, None)
    assert "suppliers_summary" in out


def test_supplier_fragment_fifo_path(db_session, sample_tenant, sample_branch, sample_user, sample_supplier):
    from datetime import datetime

    from models import Payment, Purchase
    from services.reports_query_service import ReportsQueryService as R

    po = Purchase(
        tenant_id=sample_tenant.id,
        purchase_number=f"R5E-{sample_tenant.id}",
        supplier_id=sample_supplier.id,
        supplier_name="Sup",
        branch_id=sample_branch.id,
        purchase_date=datetime.now(),
        total_amount=Decimal("200"),
        amount=Decimal("200"),
        amount_aed=Decimal("200"),
        currency="ILS",
        status="confirmed",
        user_id=sample_user.id,
    )
    db_session.add(po)
    db_session.flush()
    db_session.add(
        Payment(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            payment_number="R5E-U1",
            payment_type="supplier",
            direction="outgoing",
            supplier_id=sample_supplier.id,
            amount=Decimal("30"),
            amount_aed=Decimal("30"),
            currency="ILS",
            payment_method="cash",
            payment_confirmed=True,
            payment_date=datetime.now(),
            user_id=sample_user.id,
        )
    )
    db_session.flush()
    out = R.build_supplier_fragment_data(sample_supplier.id, sample_tenant.id, sample_branch.id)
    assert out["allocation_exact"] is False
    assert out["invoices"]
