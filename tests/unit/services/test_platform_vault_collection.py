"""Platform vault collection — accrued (accounting) vs collected (owner-confirmed).

Covers:
- confirm_settlement_paid stamps collected_at/confirmed_by and writes a
  tenant-less vault PaymentTransaction (platform treasury).
- Re-confirming an already-paid fee raises (settled-only filter = idempotent).
- record_platform_receipt writes vault evidence for platform donations only,
  once (idempotent), and ignores tenant/non-completed donations.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest


def _settled_fee(**kwargs):
    fee = MagicMock()
    fee.id = kwargs.get("id", 7)
    fee.fee_amount_aed = kwargs.get("fee_amount_aed", Decimal("25"))
    fee.status = "settled"
    fee.collected_at = None
    fee.confirmed_by = None
    return fee


class TestConfirmCollectionEvidence:
    def test_stamps_collector_and_writes_tenantless_txn(self, app, mocker):
        fee = _settled_fee()
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [fee]
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
        vault = MagicMock()
        vault.transactions = []
        mocker.patch(
            "services.azad_platform_fee_service.PaymentVault.get_platform_vault",
            return_value=vault,
        )
        mocker.patch("utils.helpers.generate_number", return_value="009")
        mocker.patch("services.azad_platform_fee_service.db.session")
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            result = AzadPlatformFeeService.confirm_settlement_paid(7, confirmed_by=42)
        assert result["count"] == 1
        assert fee.status == "paid"
        assert fee.confirmed_by == 42
        assert fee.collected_at is not None
        assert len(vault.transactions) == 1
        txn = vault.transactions[0]
        assert txn.tenant_id is None
        assert txn.payment_status == "completed"

    def test_reconfirm_paid_raises(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = []
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context(), pytest.raises(ValueError, match="No settled fees"):
            AzadPlatformFeeService.confirm_settlement_paid(7, confirmed_by=42)


class TestPlatformDonationReceipt:
    def _donation(self, **kwargs):
        d = MagicMock()
        d.id = kwargs.get("id", 11)
        d.tenant_id = kwargs.get("tenant_id", None)
        d.status = kwargs.get("status", "completed")
        d.amount_usd = kwargs.get("amount_usd", Decimal("50"))
        d.amount_crypto = Decimal("0.001")
        d.payment_method = "crypto"
        d.crypto_type = "btc"
        d.final_wallet_address = "bc1qtest"
        d.wallet_address = None
        d.donor_name = "Donor"
        d.customer_name = None
        d.donor_email = None
        d.customer_email = None
        d.ip_address = "127.0.0.1"
        d.user_agent = "ua"
        return d

    def test_platform_donation_writes_receipt_once(self, app, mocker):
        from services.donation_gl_service import DonationGLService

        donation = self._donation()
        vault = MagicMock()
        vault.transactions = []
        mocker.patch(
            "services.donation_gl_service.PaymentVault.get_platform_vault",
            return_value=vault,
        )
        mocker.patch(
            "services.donation_gl_service.PaymentTransaction.query",
        )
        # first call: no existing txn
        mocker.patch(
            "services.donation_gl_service.PaymentTransaction.query.filter_by",
            return_value=MagicMock(first=MagicMock(return_value=None)),
        )
        mocker.patch("services.donation_gl_service.db.session")
        with app.app_context():
            assert DonationGLService.record_platform_receipt(donation) is True
        assert len(vault.transactions) == 1
        assert vault.transactions[0].tenant_id is None
        assert vault.transactions[0].transaction_id == "DONATION-11"

    def test_second_call_is_noop(self, app, mocker):
        from services.donation_gl_service import DonationGLService

        donation = self._donation()
        vault = MagicMock()
        vault.transactions = []
        mocker.patch(
            "services.donation_gl_service.PaymentVault.get_platform_vault",
            return_value=vault,
        )
        mocker.patch(
            "services.donation_gl_service.PaymentTransaction.query.filter_by",
            return_value=MagicMock(first=MagicMock(return_value=MagicMock())),
        )
        mocker.patch("services.donation_gl_service.db.session")
        with app.app_context():
            assert DonationGLService.record_platform_receipt(donation) is True
        assert vault.transactions == []

    def test_tenant_donation_ignored(self, app):
        from services.donation_gl_service import DonationGLService

        with app.app_context():
            assert DonationGLService.record_platform_receipt(self._donation(tenant_id=2)) is False

    def test_pending_donation_ignored(self, app):
        from services.donation_gl_service import DonationGLService

        with app.app_context():
            assert DonationGLService.record_platform_receipt(self._donation(status="pending")) is False
