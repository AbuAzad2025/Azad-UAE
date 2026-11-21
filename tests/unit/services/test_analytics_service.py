"""Regression tests for the analytics/AR aggregation query counts.

Both services used to issue one SQL query per customer/sale (N+1).  These
tests count the actual statements emitted by the service call and assert the
count does not grow with the number of rows, while also pinning the exact
aggregated result shape (base-currency, Decimal-exact sums).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from flask_babel import gettext
from sqlalchemy import event

from extensions import db
from models import Customer, Payment, Sale
from services.analytics_service import AnalyticsService
from services.ar_reconciliation_service import ARReconciliationService


@contextmanager
def _count_statements():
    """Yield a mutable counter of SQL statements executed on the default engine."""
    engine = db.engine
    counter = {"n": 0}

    def _before(cursor, connection, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def _make_customer(db_session, tenant_id, name=None):
    customer = Customer(
        tenant_id=tenant_id,
        name=name or f"Cust-{uuid.uuid4().hex[:8]}",
        customer_type="regular",
        is_active=True,
    )
    db_session.add(customer)
    db_session.flush()
    return customer


def _make_sale(db_session, tenant_id, customer_id, seller_id, amount, **kwargs):
    amt = Decimal(str(amount))
    sale = Sale(
        tenant_id=tenant_id,
        sale_number=f"AN-{uuid.uuid4().hex[:12]}",
        customer_id=customer_id,
        seller_id=seller_id,
        total_amount=amt,
        amount=amt,
        amount_aed=amt,
        is_active=True,
        sale_date=kwargs.get("sale_date") or datetime.now(UTC),
        status=kwargs.get("status", "confirmed"),
        branch_id=kwargs.get("branch_id"),
    )
    db_session.add(sale)
    db_session.flush()
    return sale


def _make_payment(db_session, tenant_id, sale_id, amount, **kwargs):
    amt = Decimal(str(amount))
    payment = Payment(
        tenant_id=tenant_id,
        payment_number=f"PAY-{uuid.uuid4().hex[:12]}",
        payment_type="sale",
        direction="incoming",
        sale_id=sale_id,
        amount=amt,
        amount_aed=amt,
        payment_method=kwargs.get("payment_method", "cash"),
        payment_confirmed=kwargs.get("payment_confirmed", True),
        rejection_reason=kwargs.get("rejection_reason"),
    )
    db_session.add(payment)
    db_session.flush()
    return payment


# --- #1: customer insights -------------------------------------------------


def test_customer_insights_query_count_is_constant(db_session, sample_tenant, sample_user):
    def seed(count):
        for _ in range(count):
            customer = _make_customer(db_session, sample_tenant.id)
            _make_sale(db_session, sample_tenant.id, customer.id, sample_user.id, "100.000")
        db_session.commit()

    seed(1)
    with _count_statements() as small:
        AnalyticsService.get_customer_insights(sample_tenant.id)

    seed(5)
    with _count_statements() as large:
        AnalyticsService.get_customer_insights(sample_tenant.id)

    assert small["n"] == large["n"], "query count grew with the customer count (N+1 regression)"
    assert small["n"] <= 2, "expected a single aggregate SELECT for all customers"


def test_customer_insights_preserves_result_shape_and_last_sale_semantics(db_session, sample_tenant, sample_user):
    customer = _make_customer(db_session, sample_tenant.id, name="Shape Customer")
    today = datetime.now(UTC)
    old = today - timedelta(days=40)
    _make_sale(db_session, sample_tenant.id, customer.id, sample_user.id, "100.500", sale_date=old)
    _make_sale(db_session, sample_tenant.id, customer.id, sample_user.id, "200.250", sale_date=old)
    # A newer, non-confirmed sale: the original "last sale" lookup ignored the
    # status, so days_since_last must follow this one while the sums do not.
    _make_sale(
        db_session,
        sample_tenant.id,
        customer.id,
        sample_user.id,
        "999.000",
        status="pending",
        sale_date=today,
    )
    db_session.commit()

    rows = AnalyticsService.get_customer_insights(sample_tenant.id)
    row = next(r for r in rows if r["name"] == "Shape Customer")

    assert set(row) == {
        "name",
        "lifetime_value",
        "sales_count",
        "avg_sale",
        "days_since_last",
        "status",
    }
    assert row["sales_count"] == 2
    assert row["lifetime_value"] == pytest.approx(300.75)
    assert row["avg_sale"] == pytest.approx(150.375)
    assert row["days_since_last"] == 0
    assert row["status"] == gettext("نشط")


def test_customer_insights_branch_scope_uses_only_branch_sales(db_session, sample_tenant, sample_user, sample_branch):
    in_branch = _make_customer(db_session, sample_tenant.id, name="In Branch")
    other = _make_customer(db_session, sample_tenant.id, name="Other Branch")
    _make_sale(
        db_session,
        sample_tenant.id,
        in_branch.id,
        sample_user.id,
        "50.000",
        branch_id=sample_branch.id,
    )
    _make_sale(db_session, sample_tenant.id, in_branch.id, sample_user.id, "900.000")
    _make_sale(db_session, sample_tenant.id, other.id, sample_user.id, "700.000")
    db_session.commit()

    rows = AnalyticsService.get_customer_insights(sample_tenant.id, branch_id=sample_branch.id)
    assert [r["name"] for r in rows] == ["In Branch"]
    assert rows[0]["lifetime_value"] == pytest.approx(50.0)
    assert rows[0]["sales_count"] == 1


# --- #2: AR unpaid aggregation --------------------------------------------


def test_ops_unpaid_query_count_is_constant(db_session, sample_tenant, sample_user):
    customer = _make_customer(db_session, sample_tenant.id)

    def seed(count):
        for _ in range(count):
            sale = _make_sale(db_session, sample_tenant.id, customer.id, sample_user.id, "100.000")
            _make_payment(db_session, sample_tenant.id, sale.id, "10.000")
        db_session.commit()

    seed(1)
    with _count_statements() as small:
        ARReconciliationService._ops_unpaid(sample_tenant.id, None, ("regular",))

    seed(5)
    with _count_statements() as large:
        ARReconciliationService._ops_unpaid(sample_tenant.id, None, ("regular",))

    assert small["n"] == large["n"], "query count grew with the sale count (N+1 regression)"
    assert small["n"] <= 3, "expected one grouped payment aggregate plus the sales query"


def test_ops_unpaid_aggregates_effective_payments_in_base_currency(db_session, sample_tenant, sample_user):
    customer = _make_customer(db_session, sample_tenant.id)
    # Fully/partly paid by effective payments.
    s1 = _make_sale(db_session, sample_tenant.id, customer.id, sample_user.id, "100.100")
    _make_payment(db_session, sample_tenant.id, s1.id, "40.050")
    s2 = _make_sale(db_session, sample_tenant.id, customer.id, sample_user.id, "200.200")
    _make_payment(
        db_session,
        sample_tenant.id,
        s2.id,
        "50.050",
        payment_method="cheque",
        payment_confirmed=False,
        rejection_reason=None,
    )
    # A rejected cheque has no effect.
    s3 = _make_sale(db_session, sample_tenant.id, customer.id, sample_user.id, "300.300")
    _make_payment(
        db_session,
        sample_tenant.id,
        s3.id,
        "20.000",
        payment_method="cheque",
        payment_confirmed=False,
        rejection_reason="bounced",
    )
    # Overpaid sale contributes nothing (negative dues are dropped).
    s4 = _make_sale(db_session, sample_tenant.id, customer.id, sample_user.id, "10.000")
    _make_payment(db_session, sample_tenant.id, s4.id, "15.000")
    db_session.commit()

    total = ARReconciliationService._ops_unpaid(sample_tenant.id, None, ("regular",))
    assert isinstance(total, Decimal)
    assert total == Decimal("510.500")
