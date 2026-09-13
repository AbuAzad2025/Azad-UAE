"""Cov5: reports_query_service — fetch variants, fragments, top products."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal


def _mk_payment(db_session, sample_tenant, sample_user, supplier_id, suffix, purchase_id=None, branch_id=None):
    from datetime import datetime

    from models import Payment

    p = Payment(
        tenant_id=sample_tenant.id,
        payment_number=f"R5-{suffix}",
        payment_type="supplier",
        direction="outgoing",
        supplier_id=supplier_id,
        purchase_id=purchase_id,
        branch_id=branch_id,
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
    return p


def test_fetch_variants(db_session, sample_tenant, sample_branch):
    from services.reports_query_service import ReportsQueryService as R

    assert isinstance(R.fetch_sales_report(sample_tenant.id, sample_branch.id, None, date.today(), None, None), list)
    assert isinstance(R.fetch_report_customers(sample_tenant.id, sample_branch.id), list)
    assert isinstance(R.fetch_purchases_report(sample_tenant.id, sample_branch.id, None, None, None), list)
    assert R.fetch_purchases_payments(
        sample_tenant.id, sample_branch.id, date.today() - timedelta(days=1), None, None
    ) == ({}, {})
    assert isinstance(R.fetch_receivables_sales(sample_tenant.id, sample_branch.id, None), list)
    assert isinstance(R.fetch_inventory_warehouses(sample_tenant.id, sample_branch.id, None), list)


def test_fetch_purchases_payments_fifo(db_session, sample_tenant, sample_user, sample_supplier):
    from services.reports_query_service import ReportsQueryService as R

    _mk_payment(db_session, sample_tenant, sample_user, sample_supplier.id, "A")
    _mk_payment(db_session, sample_tenant, sample_user, sample_supplier.id, "B")
    by_supplier, _ = R.fetch_purchases_payments(sample_tenant.id, None, None, None, sample_supplier.id)
    assert by_supplier[sample_supplier.id] == [Decimal("30"), Decimal("30")]


def test_build_stock_maps_all_buckets(db_session, sample_tenant, sample_warehouse):
    from services.reports_query_service import ReportsQueryService as R

    day = date.today()
    out = R.build_stock_maps([sample_warehouse.id], sample_tenant.id, day, day, day, day)
    assert len(out) == 4


def test_supplier_fragment_with_payments(
    db_session, sample_tenant, sample_branch, sample_user, sample_supplier, sample_product
):
    from datetime import datetime

    from models import Purchase, PurchaseLine
    from services.reports_query_service import ReportsQueryService as R

    po = Purchase(
        tenant_id=sample_tenant.id,
        purchase_number=f"R5F-{sample_tenant.id}",
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
        PurchaseLine(
            tenant_id=sample_tenant.id,
            purchase_id=po.id,
            product_id=sample_product.id,
            quantity=Decimal("2"),
            unit_cost=Decimal("50"),
            line_total=Decimal("100"),
        )
    )
    _mk_payment(
        db_session, sample_tenant, sample_user, sample_supplier.id, "D", purchase_id=po.id, branch_id=sample_branch.id
    )
    _mk_payment(db_session, sample_tenant, sample_user, sample_supplier.id, "U", branch_id=sample_branch.id)
    db_session.flush()
    out = R.build_supplier_fragment_data(sample_supplier.id, sample_tenant.id, sample_branch.id)
    assert out["allocation_exact"] is True
    assert out["invoices"]


def test_customer_fragments_all_types(db_session, sample_tenant, sample_branch, sample_user, sample_customer):
    from datetime import datetime

    from models import Customer, Product, Sale, SaleLine
    from models.product import ProductPartner
    from services.reports_query_service import ReportsQueryService as R

    partner = Customer(tenant_id=sample_tenant.id, name="R5P", customer_type="partner")
    merchant = Customer(tenant_id=sample_tenant.id, name="R5M", customer_type="merchant")
    db_session.add_all([partner, merchant])
    db_session.flush()
    prod = Product(
        tenant_id=sample_tenant.id,
        name="R5Prod",
        sku="SKU-R5P",
        cost_price=Decimal("5"),
        regular_price=Decimal("20"),
    )
    db_session.add(prod)
    db_session.flush()
    db_session.add(
        ProductPartner(
            tenant_id=sample_tenant.id, product_id=prod.id, partner_customer_id=partner.id, percentage=Decimal("10")
        )
    )
    mprod = Product(
        tenant_id=sample_tenant.id,
        name="R5MProd",
        sku="SKU-R5M",
        cost_price=Decimal("5"),
        regular_price=Decimal("30"),
        merchant_customer_id=merchant.id,
        merchant_share=Decimal("20"),
    )
    db_session.add(mprod)
    db_session.flush()
    for suffix, cust, prd, total in (("A", partner, prod, "100"), ("B", merchant, mprod, "60")):
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f"R5S-{suffix}",
            customer_id=cust.id,
            seller_id=sample_user.id,
            branch_id=sample_branch.id,
            sale_date=datetime.now(),
            status="confirmed",
            subtotal=Decimal(total),
            total_amount=Decimal(total),
            amount=Decimal(total),
            amount_aed=Decimal(total),
        )
        db_session.add(sale)
        db_session.flush()
        db_session.add(
            SaleLine(
                tenant_id=sample_tenant.id,
                sale_id=sale.id,
                product_id=prd.id,
                quantity=Decimal("2"),
                unit_price=Decimal("25"),
                line_total=Decimal(total),
            )
        )
    db_session.flush()
    for ctype, cid in (("regular", sample_customer.id), ("partner", partner.id), ("merchant", merchant.id)):
        out = R.build_customer_fragment_data(cid, ctype, sample_tenant.id, sample_branch.id)
        assert "balance" in out
    merch = R.build_customer_fragment_data(merchant.id, "merchant", sample_tenant.id, sample_branch.id)
    assert any("Merchant:" in p["name"] for p in merch["products"])


def test_top_selling_products(db_session, sample_tenant, sample_branch):
    from services.reports_query_service import ReportsQueryService as R

    assert isinstance(R.fetch_top_selling_products(None, None, sample_tenant.id, sample_branch.id, 10), list)


def test_paid_maps_with_tenant(db_session, sample_tenant):
    from services.reports_query_service import ReportsQueryService as R

    assert R.get_confirmed_sale_paid_map([424242], tenant_id=sample_tenant.id) == {}
    assert R.get_confirmed_supplier_paid_aed(424242, tenant_id=sample_tenant.id) == Decimal("0")


def test_paid_aed_scalar_filters():
    from unittest.mock import MagicMock, patch

    from services import reports_query_service as rq
    from services.reports_query_service import ReportsQueryService as R

    session = MagicMock()
    root = MagicMock()
    root.scalar.return_value = Decimal("10")
    root.filter.return_value = root
    session.query.return_value = root
    with patch.object(rq, "db", MagicMock(session=session)):
        assert R.get_confirmed_sale_paid_aed(1, tenant_id=2, branch_id=3) == Decimal("10")
        assert R.get_confirmed_sale_paid_aed(7) == Decimal("10")
        assert R.get_confirmed_supplier_paid_aed(4, purchase_id=5, tenant_id=2, branch_id=3) == Decimal("10")
        assert R.get_confirmed_supplier_paid_aed(8) == Decimal("10")


def test_fetch_sales_report_with_seller_user_id(db_session, sample_tenant):
    from services.reports_query_service import ReportsQueryService as R

    out = R.fetch_sales_report(sample_tenant.id, None, None, None, None, None, seller_user_id=1)
    assert isinstance(out, list)


def test_fetch_purchases_payments_without_tenant(db_session, sample_tenant, sample_user, sample_supplier):
    from services.reports_query_service import ReportsQueryService as R

    _mk_payment(db_session, sample_tenant, sample_user, sample_supplier.id, "NT")
    by_supplier, _ = R.fetch_purchases_payments(None, None, None, None, None)
    assert by_supplier[sample_supplier.id]


def test_fetch_inventory_warehouses_non_admin():
    from unittest.mock import MagicMock, patch

    from services.reports_query_service import ReportsQueryService as R

    user = MagicMock()
    user.is_admin.return_value = False
    with patch("utils.branching.get_accessible_warehouse_ids", return_value=[]):
        assert isinstance(R.fetch_inventory_warehouses(None, None, user), list)
        assert isinstance(R.fetch_inventory_reconciliation_warehouses(None, user), list)


def test_build_stock_maps_no_date_filters(db_session, sample_tenant, sample_warehouse):
    from services.reports_query_service import ReportsQueryService as R

    out = R.build_stock_maps([sample_warehouse.id], sample_tenant.id, None, None, None, None)
    assert len(out) == 4
