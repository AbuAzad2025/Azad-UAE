"""Every maintenance money movement must reach the customer statement with the right sign."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.customer_statement_service import CustomerStatementService


def _order(db_session, tenant, customer, user, number="MORD-RET-1"):
    from models.maintenance import MaintenanceOrder

    order = MaintenanceOrder(
        tenant_id=tenant.id,
        order_number=number,
        customer_id=customer.id,
        received_by=user.id,
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        amount_aed=Decimal("100"),
        currency="AED",
        base_currency="AED",
        exchange_rate=Decimal("1"),
        status="closed",
    )
    db_session.add(order)
    db_session.flush()
    return order


def _kwargs(customer, tenant, **kw):
    params = {
        "record_id": customer.id,
        "date_from": None,
        "date_to": None,
        "transaction_type": "all",
        "default_currency": "AED",
        "tenant_id": tenant.id,
        "branch_id": None,
    }
    params.update(kw)
    return params


def test_maintenance_return_credits_and_refund_debits_the_statement(
    db_session, sample_tenant, sample_customer, sample_user
):
    from models.maintenance import MaintenanceInvoice, MaintenanceReceipt, MaintenanceReturn

    order = _order(db_session, sample_tenant, sample_customer, sample_user)
    db_session.add_all(
        [
            MaintenanceInvoice(
                tenant_id=sample_tenant.id,
                order_id=order.id,
                invoice_number="MINV-RET-1",
                invoice_date=datetime(2026, 5, 1, tzinfo=UTC),
                total_amount=Decimal("100"),
                amount=Decimal("100"),
                amount_aed=Decimal("100"),
                currency="AED",
                base_currency="AED",
                exchange_rate=Decimal("1"),
                posted=True,
            ),
            MaintenanceReceipt(
                tenant_id=sample_tenant.id,
                order_id=order.id,
                receipt_number="PT-PAY-1",
                receipt_date=datetime(2026, 5, 1, tzinfo=UTC),
                amount=Decimal("100"),
                payment_mode="cash",
                cashier_id=sample_user.id,
            ),
            MaintenanceReturn(
                tenant_id=sample_tenant.id,
                order_id=order.id,
                return_number="MRET-1",
                return_date=datetime(2026, 5, 2, tzinfo=UTC),
                returned_by=sample_user.id,
                total_value=Decimal("30"),
                total_value_aed=Decimal("30"),
                posted=True,
            ),
            MaintenanceReceipt(
                tenant_id=sample_tenant.id,
                order_id=order.id,
                receipt_number="PT-REFUND-1",
                receipt_date=datetime(2026, 5, 3, tzinfo=UTC),
                amount=Decimal("30"),
                payment_mode="cash",
                cashier_id=sample_user.id,
                is_refund=True,
            ),
        ]
    )
    db_session.flush()

    ctx = CustomerStatementService.build_statement_context(**_kwargs(sample_customer, sample_tenant))

    ret = next(t for t in ctx["transactions"] if t["type"] == "maintenance_return")
    assert ret["credit"] == pytest.approx(30.0)
    assert ret["debit"] == 0

    refund = next(t for t in ctx["transactions"] if t["reference"] == "PT-REFUND-1")
    # A refund is money paid OUT: it debits the balance, never credits it.
    assert refund["debit"] == pytest.approx(30.0)
    assert refund["credit"] == 0

    # Invoice -100, payment +100, return +30, refund -30 => 0.
    assert ctx["final_balance"] == pytest.approx(0.0)


def test_date_to_applies_to_maintenance_returns(db_session, sample_tenant, sample_customer, sample_user):
    from models.maintenance import MaintenanceReturn

    order = _order(db_session, sample_tenant, sample_customer, sample_user)
    db_session.add(
        MaintenanceReturn(
            tenant_id=sample_tenant.id,
            order_id=order.id,
            return_number="MRET-DATE-1",
            return_date=datetime(2026, 5, 2, tzinfo=UTC),
            returned_by=sample_user.id,
            total_value=Decimal("50"),
            total_value_aed=Decimal("50"),
            posted=True,
        )
    )
    db_session.flush()

    before = CustomerStatementService.build_statement_context(
        **_kwargs(sample_customer, sample_tenant, date_to="2026-05-01")
    )
    after = CustomerStatementService.build_statement_context(
        **_kwargs(sample_customer, sample_tenant, date_to="2026-05-31")
    )
    assert not any(t["type"] == "maintenance_return" for t in before["transactions"])
    assert any(t["type"] == "maintenance_return" for t in after["transactions"])
    assert after["final_balance"] == pytest.approx(50.0)
