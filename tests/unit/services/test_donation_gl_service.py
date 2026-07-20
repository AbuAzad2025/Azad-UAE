from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from models.donation import Donation
from services.donation_gl_service import DonationGLService


class TestVaultAccounts:
    def test_defaults_when_no_vault(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        mocker.patch(
            "services.donation_gl_service.GLService.get_default_liquidity_account",
            return_value="1111",
        )
        debit, credit = DonationGLService._vault_accounts(None, sample_tenant.id)
        assert credit == "4200"
        assert debit == "1111"

    def test_cash_debit_resolves_cash_liquidity(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        vault = MagicMock()
        vault.donation_debit_account = "1110"
        vault.donation_credit_account = "4200"
        mock_liq = mocker.patch(
            "services.donation_gl_service.GLService.get_default_liquidity_account",
            return_value="1110",
        )
        debit, credit = DonationGLService._vault_accounts(vault, sample_tenant.id)
        mock_liq.assert_called_with("cash", tenant_id=sample_tenant.id)
        assert debit == "1110"
        assert credit == "4200"

    def test_bank_debit_resolves_bank_liquidity(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        vault = MagicMock()
        vault.donation_debit_account = "1120"
        vault.donation_credit_account = "4200"
        mock_liq = mocker.patch(
            "services.donation_gl_service.GLService.get_default_liquidity_account",
            return_value="1120",
        )
        debit, credit = DonationGLService._vault_accounts(vault, sample_tenant.id)
        mock_liq.assert_called_with("bank", tenant_id=sample_tenant.id)
        assert debit == "1120"

    def test_custom_accounts_from_vault(self, db_session, sample_tenant, sample_gl_accounts):
        from models import GLAccount

        GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="4100").first()
        vault = MagicMock()
        vault.donation_debit_account = "4100"
        vault.donation_credit_account = "4200"
        debit, credit = DonationGLService._vault_accounts(vault, sample_tenant.id)
        assert debit == "4100"
        assert credit == "4200"


class TestPostCompletedDonation:
    def test_already_posted_returns_true(self, db_session, sample_tenant):
        donation = Donation(
            tenant_id=sample_tenant.id,
            amount_usd=Decimal("100"),
            payment_method="card",
            status="completed",
            gl_posted=True,
        )
        db_session.add(donation)
        db_session.flush()
        assert DonationGLService.post_completed_donation(donation) is True

    def test_non_completed_returns_false(self, db_session, sample_tenant):
        donation = Donation(
            tenant_id=sample_tenant.id,
            amount_usd=Decimal("100"),
            payment_method="card",
            status="pending",
        )
        assert DonationGLService.post_completed_donation(donation) is False

    def test_zero_amount_returns_false(self, db_session, sample_tenant):
        donation = Donation(
            tenant_id=sample_tenant.id,
            amount_usd=Decimal("0"),
            payment_method="card",
            status="completed",
        )
        assert DonationGLService.post_completed_donation(donation) is False

    def test_no_tenant_skips_posting(self, db_session, app):
        donation = Donation(
            tenant_id=None,
            amount_usd=Decimal("50"),
            payment_method="card",
            status="completed",
        )
        with app.app_context():
            assert DonationGLService.post_completed_donation(donation) is False

    def test_successful_posting(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        donation = Donation(
            tenant_id=sample_tenant.id,
            amount_usd=Decimal("100"),
            payment_method="card",
            status="completed",
            donor_name="Test Donor",
        )
        db_session.add(donation)
        db_session.flush()
        vault = MagicMock()
        vault.donation_debit_account = "4101"
        vault.donation_credit_account = "4500"
        mocker.patch(
            "services.donation_gl_service.PaymentVault.get_tenant_vault",
            return_value=vault,
        )
        mocker.patch(
            "services.donation_gl_service.ExchangeRateService.resolve_exchange_rate_for_transaction",
            return_value={"rate": Decimal("3.67")},
        )
        entry = MagicMock(id=99)
        post = mocker.patch(
            "services.donation_gl_service.post_or_fail",
            return_value=entry,
        )
        result = DonationGLService.post_completed_donation(donation)
        assert result is True
        assert donation.gl_posted is True
        post.assert_called_once()
        lines = post.call_args[0][0]
        assert lines[0]["debit"] == Decimal("367.000")
        assert lines[1]["credit"] == Decimal("367.000")

    def test_exchange_rate_fallback(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        donation = Donation(
            tenant_id=sample_tenant.id,
            amount_usd=Decimal("10"),
            payment_method="bank",
            status="completed",
        )
        db_session.add(donation)
        db_session.flush()
        vault = MagicMock()
        vault.donation_debit_account = "4101"
        vault.donation_credit_account = "4500"
        mocker.patch(
            "services.donation_gl_service.PaymentVault.get_tenant_vault",
            return_value=vault,
        )
        mocker.patch(
            "services.donation_gl_service.PaymentVault.get_platform_vault",
            return_value=None,
        )
        mocker.patch(
            "services.donation_gl_service.ExchangeRateService.resolve_exchange_rate_for_transaction",
            side_effect=RuntimeError("api down"),
        )
        mocker.patch("services.donation_gl_service.post_or_fail", return_value=MagicMock(id=1))
        assert DonationGLService.post_completed_donation(donation) is True

    def test_posting_failure_reraises(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        donation = Donation(
            tenant_id=sample_tenant.id,
            amount_usd=Decimal("25"),
            payment_method="card",
            status="completed",
        )
        db_session.add(donation)
        db_session.flush()
        vault = MagicMock()
        vault.donation_debit_account = "4101"
        vault.donation_credit_account = "4500"
        mocker.patch(
            "services.donation_gl_service.PaymentVault.get_tenant_vault",
            return_value=vault,
        )
        mocker.patch(
            "services.donation_gl_service.ExchangeRateService.resolve_exchange_rate_for_transaction",
            return_value={"rate": Decimal("3.67")},
        )
        mocker.patch(
            "services.donation_gl_service.post_or_fail",
            side_effect=ValueError("unbalanced"),
        )
        with pytest.raises(ValueError, match="unbalanced"):
            DonationGLService.post_completed_donation(donation)
