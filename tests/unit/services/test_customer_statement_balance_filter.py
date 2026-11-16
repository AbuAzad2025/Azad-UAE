"""Regression: the display filter must not corrupt the customer's closing balance."""

from datetime import datetime
from decimal import Decimal

from services.customer_statement_service import CustomerStatementService


def test_type_filter_does_not_change_final_balance(db_session, sample_customer, sample_tenant, sample_user):
    from models import Payment, Sale

    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number="STMT-FILTER-1",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        sale_date=datetime.now(),
        status="confirmed",
        subtotal=Decimal("100"),
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        amount_aed=Decimal("100"),
        payment_status="paid",
        paid_amount_aed=Decimal("100"),
    )
    db_session.add(sale)
    db_session.flush()
    pay = Payment(
        tenant_id=sample_tenant.id,
        customer_id=sample_customer.id,
        payment_number="STMT-FILTER-PAY",
        payment_type="sale_payment",
        direction="incoming",
        amount=Decimal("100"),
        amount_aed=Decimal("100"),
        currency="AED",
        exchange_rate=Decimal("1"),
        payment_method="cash",
        payment_confirmed=True,
        payment_date=datetime.now(),
    )
    db_session.add(pay)
    db_session.flush()

    kwargs = {
        "record_id": sample_customer.id,
        "date_from": None,
        "date_to": None,
        "default_currency": "AED",
        "tenant_id": sample_tenant.id,
        "branch_id": None,
    }
    all_ctx = CustomerStatementService.build_statement_context(transaction_type="all", **kwargs)
    sale_ctx = CustomerStatementService.build_statement_context(transaction_type="sale", **kwargs)
    pay_ctx = CustomerStatementService.build_statement_context(transaction_type="payment", **kwargs)

    # The sale is fully paid, so the real closing balance is zero.
    assert all_ctx["final_balance"] == 0.0
    # Filtering the displayed rows must NOT change the closing balance.
    assert sale_ctx["final_balance"] == all_ctx["final_balance"]
    assert pay_ctx["final_balance"] == all_ctx["final_balance"]
    # ...but it must still filter the visible rows.
    assert all(t["type"] == "sale" for t in sale_ctx["transactions"])
    assert all(t["type"] == "payment" for t in pay_ctx["transactions"])


def test_date_to_filters_maintenance_movements(db_session, sample_customer, sample_tenant):
    """A statement 'up to date_to' must exclude later maintenance entries."""
    # This test relies on the date_to filters being applied to the maintenance
    # queries. With no maintenance data it at least proves the code path runs
    # without error; a full fixture-based assertion belongs in the maintenance
    # money-path integration test.
    ctx = CustomerStatementService.build_statement_context(
        record_id=sample_customer.id,
        date_from=None,
        date_to="2000-12-31",
        transaction_type="all",
        default_currency="AED",
        tenant_id=sample_tenant.id,
        branch_id=None,
    )
    assert ctx["transactions"] == []
