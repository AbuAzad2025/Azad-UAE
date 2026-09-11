"""Cov4: customer_statement_service — scalar coerce + statement filter/balance arcs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from services.customer_statement_service import CustomerStatementService, _scalar_to_decimal


def test_scalar_to_decimal_branches():
    assert _scalar_to_decimal(Decimal("1.5")) == Decimal("1.5")
    assert _scalar_to_decimal(None) == Decimal("0")
    assert _scalar_to_decimal(5) == Decimal("5")
    assert _scalar_to_decimal(2.5) == Decimal("2.5")
    assert _scalar_to_decimal("bogus!!") == Decimal("0")
    assert _scalar_to_decimal(object()) == Decimal("0")


def _base_kwargs(customer, tenant, **kw):
    params = {"record_id": customer.id, "date_from": None, "date_to": None,
              "transaction_type": "all", "default_currency": "AED",
              "tenant_id": tenant.id, "branch_id": None}
    params.update(kw)
    return params


def test_empty_statement(db_session, sample_customer, sample_tenant):
    ctx = CustomerStatementService.build_statement_context(
        **_base_kwargs(sample_customer, sample_tenant))
    assert ctx["transactions"] == []
    assert ctx["final_balance"] == 0.0
    assert ctx["filters"]["transaction_type"] == "all"


def test_sale_with_lines_payments_and_branch_filter(
    db_session, sample_customer, sample_tenant, sample_user, sample_warehouse,
    sample_branch, sample_product,
):
    from models import Sale, SaleLine

    sale = Sale(tenant_id=sample_tenant.id, sale_number="STMT-COV4",
                customer_id=sample_customer.id, seller_id=sample_user.id,
                warehouse_id=sample_warehouse.id, branch_id=sample_branch.id,
                sale_date=datetime.now(), status="confirmed",
                subtotal=Decimal("100"), total_amount=Decimal("100"), amount=Decimal("100"),
                amount_aed=Decimal("100"), payment_status="unpaid")
    db_session.add(sale)
    db_session.flush()
    line = SaleLine(tenant_id=sample_tenant.id, sale_id=sale.id, product_id=sample_product.id,
                    quantity=Decimal("2"), unit_price=Decimal("50"),
                    discount_percent=Decimal("10"), line_total=Decimal("90"))
    db_session.add(line)
    db_session.flush()
    ctx = CustomerStatementService.build_statement_context(
        **_base_kwargs(sample_customer, sample_tenant))
    assert any(t["type"] == "sale" for t in ctx["transactions"])
    sale_t = next(t for t in ctx["transactions"] if t["type"] == "sale")
    assert sale_t["sale"]["lines"][0]["discount_value"] == 10.0
    assert ctx["final_balance"] == 100.0
    # branch mismatch -> filtered out
    ctx2 = CustomerStatementService.build_statement_context(
        **_base_kwargs(sample_customer, sample_tenant, branch_id=999999))
    assert ctx2["transactions"] == []
    # type filter
    ctx3 = CustomerStatementService.build_statement_context(
        **_base_kwargs(sample_customer, sample_tenant, transaction_type="sale"))
    assert all(t["type"] == "sale" for t in ctx3["transactions"])
    ctx4 = CustomerStatementService.build_statement_context(
        **_base_kwargs(sample_customer, sample_tenant, transaction_type="payment"))
    assert ctx4["transactions"] == []


def test_payments_receipts_returns_and_opening(
    db_session, sample_customer, sample_tenant, sample_user,
):
    from datetime import date

    from models import Payment

    pay = Payment(tenant_id=sample_tenant.id, customer_id=sample_customer.id,
                  payment_number="PAY-COV4", reference_number="PAY-COV4",
                  direction="incoming", amount=Decimal("40"), amount_aed=Decimal("40"),
                  payment_method="cash", payment_confirmed=True,
                  payment_date=datetime.now())
    db_session.add(pay)
    out_pay = Payment(tenant_id=sample_tenant.id, customer_id=sample_customer.id,
                      payment_number="PAY-COV4-O", direction="outgoing",
                      amount=Decimal("5"), amount_aed=Decimal("5"),
                      payment_method="cash", payment_confirmed=False,
                      payment_date=datetime.now())
    db_session.add(out_pay)
    db_session.flush()
    ctx = CustomerStatementService.build_statement_context(
        **_base_kwargs(sample_customer, sample_tenant))
    pay_t = [t for t in ctx["transactions"] if t["type"] == "payment"]
    assert len(pay_t) == 2
    incoming = next(t for t in pay_t if t["credit"] == 40.0)
    assert incoming["is_confirmed"] is True
    # date_from triggers opening-balance row + pre-period aggregation arcs
    ctx2 = CustomerStatementService.build_statement_context(
        **_base_kwargs(sample_customer, sample_tenant,
                       date_from=(date.today()).isoformat()))
    assert ctx2["transactions"][0]["type"] == "opening"
    # date_to filter arc
    ctx3 = CustomerStatementService.build_statement_context(
        **_base_kwargs(sample_customer, sample_tenant,
                       date_from="2000-01-01", date_to="2000-12-31"))
    assert all(t["type"] == "opening" for t in ctx3["transactions"])


def test_cheque_payment_pending_counts_via_pending_cheque_arc(
    db_session, sample_customer, sample_tenant,
):
    from models import Payment

    chq = Payment(tenant_id=sample_tenant.id, customer_id=sample_customer.id,
                  payment_number="PAY-CHQ", direction="incoming",
                  amount=Decimal("25"), amount_aed=Decimal("25"),
                  payment_method="cheque", payment_confirmed=False,
                  rejection_reason=None, payment_date=datetime.now())
    db_session.add(chq)
    db_session.flush()
    ctx = CustomerStatementService.build_statement_context(
        **_base_kwargs(sample_customer, sample_tenant))
    chq_t = next(t for t in ctx["transactions"]
                 if t.get("payment", {}).get("payment_number") == "PAY-CHQ")
    assert chq_t["is_confirmed"] is True  # pending-cheque arc
    assert chq_t["balance"] == 25.0


def test_receipt_and_return_arcs(
    db_session, sample_customer, sample_tenant, sample_user, sample_warehouse,
):
    from models import Sale
    from models.product_return import ProductReturn
    from models.receipt import Receipt

    sale = Sale(tenant_id=sample_tenant.id, sale_number="STMT-RET-SALE",
                customer_id=sample_customer.id, seller_id=sample_user.id,
                warehouse_id=sample_warehouse.id, sale_date=datetime.now(),
                status="confirmed", subtotal=Decimal("50"), total_amount=Decimal("50"),
                amount=Decimal("50"), amount_aed=Decimal("50"), payment_status="unpaid")
    db_session.add(sale)
    db_session.flush()
    ret = ProductReturn(tenant_id=sample_tenant.id, return_number="RET-COV4",
                        sale_id=sale.id, customer_id=sample_customer.id,
                        return_date=datetime.now(), total_amount=Decimal("10"),
                        amount_aed=Decimal("10"), status="approved")
    db_session.add(ret)
    rcp = Receipt(tenant_id=sample_tenant.id, receipt_number="RCP-COV4",
                  customer_id=sample_customer.id, amount=Decimal("15"),
                  amount_aed=Decimal("15"), payment_method="cash",
                  payment_confirmed=True, receipt_date=datetime.now())
    db_session.add(rcp)
    db_session.flush()
    ctx = CustomerStatementService.build_statement_context(
        **_base_kwargs(sample_customer, sample_tenant))
    kinds = {t["type"] for t in ctx["transactions"]}
    assert {"sale", "receipt", "return"} <= kinds
    # allocated-receipt skip arc: receipt whose number matches a payment ref
    from models import Payment

    pay = Payment(tenant_id=sample_tenant.id, customer_id=sample_customer.id,
                  payment_number="PAY-AL", reference_number="RCP-COV4",
                  direction="incoming", amount=Decimal("15"), amount_aed=Decimal("15"),
                  payment_method="cash", payment_confirmed=True,
                  payment_date=datetime.now())
    db_session.add(pay)
    db_session.flush()
    ctx2 = CustomerStatementService.build_statement_context(
        **_base_kwargs(sample_customer, sample_tenant))
    assert not any(t["type"] == "receipt" and t["reference"] == "RCP-COV4"
                   for t in ctx2["transactions"])
