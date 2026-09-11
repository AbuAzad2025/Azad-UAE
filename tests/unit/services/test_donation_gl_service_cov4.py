"""Cov4: donation_gl_service — posted/status/amount/tenant/rate/post/vault arcs."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.donation_gl_service import DonationGLService


def _donation(**kw):
    base = {"id": 1, "gl_posted": False, "status": "completed", "amount_usd": Decimal("10"),
            "tenant_id": None, "payment_method": "card", "donor_name": "Ali",
            "customer_name": None, "amount_crypto": Decimal("0"), "crypto_type": None}
    base.update(kw)
    return SimpleNamespace(**base)


def test_post_already_posted():
    assert DonationGLService.post_completed_donation(_donation(gl_posted=True)) is True


def test_post_not_completed():
    assert DonationGLService.post_completed_donation(_donation(status="pending")) is False


def test_post_zero_amount():
    assert DonationGLService.post_completed_donation(_donation(amount_usd=Decimal("0"))) is False
    assert DonationGLService.post_completed_donation(_donation(amount_usd=None)) is False


def test_post_no_tenant_returns_false():
    assert DonationGLService.post_completed_donation(_donation(tenant_id=None)) is False


def _make_donation(db_session, sample_tenant, **kw):
    from models.donation import Donation

    params = {"tenant_id": sample_tenant.id, "amount_usd": Decimal("25"),
              "status": "completed", "payment_method": "card", "donor_name": "Sara"}
    params.update(kw)
    d = Donation(**params)
    db_session.add(d)
    db_session.flush()
    return d


def test_post_success_with_rate_fallback(db_session, sample_tenant):
    d = _make_donation(db_session, sample_tenant)
    with patch(
        "services.exchange_rate_service.ExchangeRateService.resolve_exchange_rate_for_transaction",
        side_effect=RuntimeError("no rate"),
    ), patch("services.donation_gl_service.post_or_fail", return_value=None) as p:
        assert DonationGLService.post_completed_donation(d) is True
        assert d.gl_posted is True
        p.assert_called_once()


def test_post_success_with_live_rate(db_session, sample_tenant):
    d = _make_donation(db_session, sample_tenant, amount_usd=Decimal("5"),
                       donor_name=None, customer_name="C1", payment_method="cash")
    with patch(
        "services.exchange_rate_service.ExchangeRateService.resolve_exchange_rate_for_transaction",
        return_value={"rate": "3.67"},
    ), patch("services.donation_gl_service.post_or_fail", return_value=None):
        assert DonationGLService.post_completed_donation(d) is True


def test_post_failure_reraises(db_session, sample_tenant):
    d = _make_donation(db_session, sample_tenant, amount_usd=Decimal("5"))
    with patch(
        "services.exchange_rate_service.ExchangeRateService.resolve_exchange_rate_for_transaction",
        return_value={"rate": "3.67"},
    ), patch("services.donation_gl_service.post_or_fail", side_effect=RuntimeError("gl down")):
        with pytest.raises(RuntimeError, match="gl down"):
            DonationGLService.post_completed_donation(d)


def test_vault_accounts_plain_passthrough(db_session, sample_tenant):
    from services.gl_service import GLService

    GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
    vault = SimpleNamespace(donation_debit_account="1150", donation_credit_account="4200")
    assert DonationGLService._vault_accounts(vault, sample_tenant.id) == ("1150", "4200")
    vault2 = SimpleNamespace(donation_debit_account=None, donation_credit_account=None)
    debit, credit = DonationGLService._vault_accounts(vault2, sample_tenant.id)
    assert credit == "4200"
    assert debit != "1110"  # default 1120 is a real account here, no liquidity fallback


def test_vault_accounts_liquidity_fallback_cash_and_bank(db_session, sample_tenant):
    from services.gl_service import GLService

    GLService.ensure_core_accounts(tenant_id=sample_tenant.id)
    with patch(
        "services.donation_gl_service.GLService.get_default_liquidity_account",
        return_value="1111",
    ) as g:
        vault = SimpleNamespace(donation_debit_account="1110", donation_credit_account="4200")
        assert DonationGLService._vault_accounts(vault, sample_tenant.id) == ("1111", "4200")
        g.assert_called_once_with("cash", tenant_id=sample_tenant.id)
    with patch(
        "services.donation_gl_service.GLService.get_default_liquidity_account",
        return_value="1120",
    ):
        # 1100 is a header account -> header branch -> bank liquidity kind
        vault_h = SimpleNamespace(donation_debit_account="1100", donation_credit_account="4200")
        debit, _ = DonationGLService._vault_accounts(vault_h, sample_tenant.id)
        assert debit == "1120"


def test_record_platform_receipt_guards():
    assert DonationGLService.record_platform_receipt(_donation(tenant_id=5)) is False
    assert DonationGLService.record_platform_receipt(_donation(status="pending")) is False


def test_record_platform_receipt_no_vault(app):
    with app.app_context(), patch(
        "services.donation_gl_service.PaymentVault.get_platform_vault", return_value=None
    ):
        with pytest.raises(ValueError, match="Platform vault"):
            DonationGLService.record_platform_receipt(_donation())


def test_record_platform_receipt_zero_amount(app):
    vault = MagicMock()
    vault.transactions = []
    with app.app_context(), patch(
        "services.donation_gl_service.PaymentVault.get_platform_vault", return_value=vault
    ), patch(
        "services.donation_gl_service.PaymentTransaction.query.filter_by",
        return_value=MagicMock(first=MagicMock(return_value=None)),
    ):
        assert DonationGLService.record_platform_receipt(_donation(amount_usd=Decimal("0"))) is False


def test_record_platform_receipt_field_fallbacks(app):
    vault = MagicMock()
    vault.transactions = []
    donation = _donation(payment_method=None, donor_name=None, crypto_type=None,
                         amount_crypto=None, id=77)
    donation.donor_email = None
    donation.customer_email = None
    donation.final_wallet_address = None
    donation.wallet_address = None
    donation.ip_address = None
    donation.user_agent = None
    with app.app_context(), patch(
        "services.donation_gl_service.PaymentVault.get_platform_vault", return_value=vault
    ), patch(
        "services.donation_gl_service.PaymentTransaction.query.filter_by",
        return_value=MagicMock(first=MagicMock(return_value=None)),
    ), patch("services.donation_gl_service.db.session"):
        assert DonationGLService.record_platform_receipt(donation) is True
    txn = vault.transactions[0]
    assert txn.transaction_id == "DONATION-77"
    assert txn.payment_method == "donation"
    assert txn.crypto_currency == "DONATION"
    assert txn.is_verified is True
