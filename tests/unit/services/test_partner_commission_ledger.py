"""Sale commissions must be visible in the partner's own ledger and statement."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest


def _seed_commission(db_session, tenant, user, *, sale_date=date(2026, 5, 10)):
    from models import Customer, Partner, PartnerCommissionEntry, Sale

    partner = Partner(
        tenant_id=tenant.id,
        code="P-COMM",
        name="شريك عمولة",
        share_percentage=Decimal("50"),
        current_balance=Decimal("0"),
    )
    customer = Customer(
        tenant_id=tenant.id,
        name="عميل شريك",
        customer_type="partner",
        partner_id=None,
    )
    db_session.add_all([partner, customer])
    db_session.flush()
    customer.partner_id = partner.id

    sale = Sale(
        tenant_id=tenant.id,
        sale_number="S-COMM-1",
        customer_id=customer.id,
        seller_id=user.id,
        sale_date=datetime.combine(sale_date, datetime.min.time(), tzinfo=UTC),
        subtotal=Decimal("1000"),
        total_amount=Decimal("1000"),
        amount=Decimal("1000"),
        amount_aed=Decimal("1000"),
        balance_due=Decimal("0"),
        currency="AED",
        status="confirmed",
        branch_id=None,
    )
    db_session.add(sale)
    db_session.flush()

    entry = PartnerCommissionEntry(
        tenant_id=tenant.id,
        sale_id=sale.id,
        partner_customer_id=customer.id,
        percentage=Decimal("5"),
        base_amount_aed=Decimal("1000"),
        commission_amount_aed=Decimal("50"),
    )
    db_session.add(entry)
    db_session.flush()
    return partner, customer, sale, entry


def test_commission_reaches_partner_ledger_once(db_session, mocker, sample_tenant, sample_user):
    from models import PartnerTransaction
    from services.commission_gl_service import post_sale_commissions
    from services.partner_service import PartnerService

    partner, _customer, sale, _entry = _seed_commission(db_session, sample_tenant, sample_user)

    mocker.patch("services.commission_gl_service.GLService.ensure_core_accounts")
    mocker.patch("services.commission_gl_service.GLService.get_account_code_for_concept", return_value="6160")
    post = mocker.patch("services.commission_gl_service.post_or_fail", return_value=mocker.MagicMock(id=1))

    post_sale_commissions(sale)
    post_sale_commissions(sale)  # replay must not double-credit

    txs = PartnerTransaction.query.filter_by(
        tenant_id=sample_tenant.id,
        partner_id=partner.id,
        reference_type="sale_commission",
        reference_id=sale.id,
    ).all()
    assert len(txs) == 1
    assert txs[0].transaction_type == "sale_commission"
    assert Decimal(str(txs[0].amount_base)) == Decimal("50.000")
    assert txs[0].transaction_type_label == "عمولة مبيعات"
    assert post.call_count == 2  # the GL posting itself is not made idempotent here

    assert Decimal(str(partner.current_balance)) == Decimal("50.000")

    stmt = PartnerService.get_partner_statement(partner.id, date(2026, 5, 1), date(2026, 5, 31))
    assert len(stmt["transactions"]) == 1
    assert stmt["transactions"][0].transaction_type == "sale_commission"
    assert stmt["closing_balance"] == pytest.approx(50.0)


def test_commission_for_unlinked_customer_is_not_lost_from_the_ledger(db_session, mocker, sample_tenant, sample_user):
    """A partner customer with no company-level Partner has no ledger to post to."""
    from models import PartnerTransaction
    from services.commission_gl_service import post_sale_commissions

    partner, _customer, sale, _entry = _seed_commission(db_session, sample_tenant, sample_user)
    _customer.partner_id = None
    db_session.flush()

    mocker.patch("services.commission_gl_service.GLService.ensure_core_accounts")
    mocker.patch("services.commission_gl_service.GLService.get_account_code_for_concept", return_value="6160")
    mocker.patch("services.commission_gl_service.post_or_fail", return_value=mocker.MagicMock(id=2))

    post_sale_commissions(sale)

    assert PartnerTransaction.query.filter_by(partner_id=partner.id, reference_id=sale.id).count() == 0
