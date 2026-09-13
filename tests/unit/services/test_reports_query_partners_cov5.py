"""Cov5: reports_query_service — partners report entries/else paths + filters."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal


def _mk_product(db_session, sample_tenant, suffix, **kw):
    from models import Product

    params = {
        "tenant_id": sample_tenant.id,
        "name": f"P5-{suffix}",
        "sku": f"SKU-P5-{suffix}",
        "cost_price": Decimal("10"),
        "regular_price": Decimal("50"),
    }
    params.update(kw)
    p = Product(**params)
    db_session.add(p)
    db_session.flush()
    return p


def _mk_customer(db_session, sample_tenant, suffix, ctype="regular"):
    from models import Customer

    c = Customer(tenant_id=sample_tenant.id, name=f"C5-{suffix}", customer_type=ctype)
    db_session.add(c)
    db_session.flush()
    return c


def _mk_sale(db_session, sample_tenant, sample_user, customer, suffix, branch_id=None):
    from datetime import datetime

    from models import Sale

    s = Sale(
        tenant_id=sample_tenant.id,
        sale_number=f"PSALE-{suffix}",
        customer_id=customer.id,
        seller_id=sample_user.id,
        branch_id=branch_id,
        sale_date=datetime.now(),
        status="confirmed",
        subtotal=Decimal("100"),
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        amount_aed=Decimal("100"),
    )
    db_session.add(s)
    db_session.flush()
    return s


def _mk_line(db_session, sale, product, qty="2", total="100"):
    from models import SaleLine

    ln = SaleLine(
        tenant_id=sale.tenant_id,
        sale_id=sale.id,
        product_id=product.id,
        quantity=Decimal(qty),
        unit_price=Decimal("50"),
        line_total=Decimal(total),
    )
    db_session.add(ln)
    db_session.flush()
    return ln


def test_partners_report_entries_path(db_session, sample_tenant, sample_user, sample_branch):
    from models.partner_commission import PartnerCommissionEntry
    from services.reports_query_service import ReportsQueryService

    c1 = _mk_customer(db_session, sample_tenant, "P1", "partner")
    p1 = _mk_product(db_session, sample_tenant, "E1")
    s1 = _mk_sale(db_session, sample_tenant, sample_user, c1, "E1", branch_id=sample_branch.id)
    ln = _mk_line(db_session, s1, p1)
    db_session.add(
        PartnerCommissionEntry(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            sale_id=s1.id,
            sale_line_id=ln.id,
            partner_customer_id=c1.id,
            product_id=p1.id,
            percentage=Decimal("10"),
            currency="AED",
            base_currency="ILS",
            base_amount_aed=Decimal("100"),
            commission_amount_aed=Decimal("10"),
        )
    )
    db_session.flush()
    out = ReportsQueryService.build_partners_report(
        date.today() - timedelta(days=1), None, sample_tenant.id, sample_branch.id
    )
    assert out["partners_data"]
    assert out["partners_data"][0]["partner_share_amount"] == Decimal("10")


def test_partners_report_entries_with_date_to(db_session, sample_tenant, sample_user, sample_branch):
    from models.partner_commission import PartnerCommissionEntry
    from services.reports_query_service import ReportsQueryService

    c1 = _mk_customer(db_session, sample_tenant, "P3", "partner")
    p1 = _mk_product(db_session, sample_tenant, "E3")
    s1 = _mk_sale(db_session, sample_tenant, sample_user, c1, "E3", branch_id=sample_branch.id)
    ln = _mk_line(db_session, s1, p1)
    db_session.add(
        PartnerCommissionEntry(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            sale_id=s1.id,
            sale_line_id=ln.id,
            partner_customer_id=c1.id,
            product_id=p1.id,
            percentage=Decimal("10"),
            currency="AED",
            base_currency="ILS",
            base_amount_aed=Decimal("100"),
            commission_amount_aed=Decimal("10"),
        )
    )
    db_session.flush()
    out = ReportsQueryService.build_partners_report(
        date.today() - timedelta(days=1),
        date.today() + timedelta(days=1),
        sample_tenant.id,
        sample_branch.id,
    )
    assert out["partners_data"]


def test_partners_report_else_path_with_financials_and_suppliers(
    db_session, sample_tenant, sample_user, sample_branch, sample_supplier
):
    from models.product import ProductPartner
    from services.reports_query_service import ReportsQueryService

    c1 = _mk_customer(db_session, sample_tenant, "P2", "partner")
    c2 = _mk_customer(db_session, sample_tenant, "M2", "merchant")
    p1 = _mk_product(db_session, sample_tenant, "S1")
    p2 = _mk_product(db_session, sample_tenant, "S2")
    m1 = _mk_product(
        db_session, sample_tenant, "M1", merchant_customer_id=c2.id, merchant_share=Decimal("20")
    )
    for prod in (p1, p2):
        db_session.add(
            ProductPartner(
                tenant_id=sample_tenant.id,
                product_id=prod.id,
                partner_customer_id=c1.id,
                percentage=Decimal("10"),
            )
        )
    s1 = _mk_sale(db_session, sample_tenant, sample_user, c1, "S1", branch_id=sample_branch.id)
    _mk_line(db_session, s1, p1)
    s2 = _mk_sale(db_session, sample_tenant, sample_user, c2, "S2", branch_id=sample_branch.id)
    _mk_line(db_session, s2, m1, qty="1", total="50")
    db_session.flush()

    from datetime import datetime

    from models import Purchase

    po = Purchase(
        tenant_id=sample_tenant.id,
        purchase_number=f"PSUP-{sample_tenant.id}",
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

    out = ReportsQueryService.build_partners_report(
        date.today() - timedelta(days=1),
        date.today() + timedelta(days=1),
        sample_tenant.id,
        sample_branch.id,
    )
    assert any(r["partner_share_amount"] == Decimal("10") for r in out["partners_data"])
    assert any(r["merchant_share_amount"] == Decimal("10") for r in out["merchants_data"])
    assert out["suppliers_summary"]
