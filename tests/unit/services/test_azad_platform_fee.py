"""Azad platform fee unification (P1) — fee accrual on ALL online-store channels.

Covers: COD / bank_transfer / e_wallet confirmed orders generating valid,
idempotent AzadPlatformFee records with balanced GL entries, plus the owner
toggle (SystemSettings.azad_platform_fee_include_offline).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


def _store_sale(**kwargs):
    sale = MagicMock()
    sale.id = kwargs.get("id", 42)
    sale.tenant_id = kwargs.get("tenant_id", 7)
    sale.sale_number = kwargs.get("sale_number", "S-200")
    sale.source = kwargs.get("source", "online_store")
    sale.checkout_payment_method = kwargs.get("checkout_payment_method", "cod")
    sale.checkout_gateway_ref = kwargs.get("checkout_gateway_ref", "")
    sale.amount_aed = kwargs.get("amount_aed", Decimal("500"))
    sale.total_amount = sale.amount_aed
    sale.branch_id = 1
    return sale


def _patch_common(mocker, *, offline=True, existing=None):
    mock_q = MagicMock()
    mock_q.filter_by.return_value.first.return_value = existing
    mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
    mocker.patch(
        "services.azad_platform_fee_service.PaymentVault.get_platform_vault",
        return_value=MagicMock(id=9),
    )
    settings = MagicMock(
        azad_platform_fee_rate=Decimal("1"),
        azad_platform_fee_include_offline=offline,
    )
    mocker.patch("models.SystemSettings.get_current", return_value=settings)
    mocker.patch("services.azad_platform_fee_service.GLService.ensure_core_accounts")
    mock_post = mocker.patch("services.azad_platform_fee_service.post_or_fail")
    mock_session = mocker.patch("services.azad_platform_fee_service.db.session")
    return mock_post, mock_session


class TestOfflineChannelAccrual:
    """Every confirmed online-store sale accrues the platform fee, any channel."""

    def test_cod_order_accrues_fee_with_balanced_gl(self, app, mocker):
        mock_post, mock_session = _patch_common(mocker, offline=True)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            fee = AzadPlatformFeeService.record_store_online_fee(_store_sale(checkout_payment_method="cod"))

        assert fee is not None
        assert fee.payment_channel == "cod"
        assert fee.rate_percent == Decimal("1")
        assert fee.base_amount_aed == Decimal("500.000")
        assert fee.fee_amount_aed == Decimal("5.000")
        assert fee.status == "accrued"
        assert fee.gl_posted is True
        mock_session.add.assert_called_once()
        mock_post.assert_called_once()
        lines = mock_post.call_args[0][0]
        debit_total = sum(line.get("debit", Decimal("0")) for line in lines)
        credit_total = sum(line.get("credit", Decimal("0")) for line in lines)
        assert debit_total == credit_total == Decimal("5.000")

    def test_bank_transfer_order_accrues_fee(self, app, mocker):
        mock_post, mock_session = _patch_common(mocker, offline=True)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            fee = AzadPlatformFeeService.record_store_online_fee(
                _store_sale(checkout_payment_method="bank_transfer", amount_aed=Decimal("1000"))
            )

        assert fee is not None
        assert fee.payment_channel == "bank_transfer"
        assert fee.fee_amount_aed == Decimal("10.000")
        mock_session.add.assert_called_once()
        mock_post.assert_called_once()

    def test_e_wallet_order_accrues_fee(self, app, mocker):
        mock_post, _ = _patch_common(mocker, offline=True)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            fee = AzadPlatformFeeService.record_store_online_fee(_store_sale(checkout_payment_method="e_wallet"))

        assert fee is not None
        assert fee.payment_channel == "e_wallet"
        assert fee.fee_amount_aed == Decimal("5.000")
        mock_post.assert_called_once()

    def test_idempotent_for_repeated_confirmation(self, app, mocker):
        existing = MagicMock(id=77, idempotency_key="store-online:7:42:sale")
        mock_post, mock_session = _patch_common(mocker, offline=True, existing=existing)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            fee = AzadPlatformFeeService.record_store_online_fee(_store_sale())

        assert fee is existing
        mock_session.add.assert_not_called()
        mock_post.assert_not_called()

    def test_toggle_off_skips_offline_channels(self, app, mocker):
        mock_post, mock_session = _patch_common(mocker, offline=False)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            assert AzadPlatformFeeService.record_store_online_fee(_store_sale(checkout_payment_method="cod")) is None

        mock_session.add.assert_not_called()
        mock_post.assert_not_called()

    def test_toggle_off_keeps_online_gateway_channel(self, app, mocker):
        mock_post, _ = _patch_common(mocker, offline=False)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            fee = AzadPlatformFeeService.record_store_online_fee(
                _store_sale(checkout_payment_method="online_pay", checkout_gateway_ref="GW-9")
            )

        assert fee is not None
        mock_post.assert_called_once()

    def test_non_store_sale_never_accrues(self, app, mocker):
        mock_post, mock_session = _patch_common(mocker, offline=True)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            assert AzadPlatformFeeService.record_store_online_fee(_store_sale(source="pos")) is None

        mock_session.add.assert_not_called()
        mock_post.assert_not_called()


class TestConfirmOrderRecordsFee:
    """confirm_order records the fee for COD orders even without mark_paid."""

    def test_confirm_cod_order_records_fee_without_payment(self, app, mocker):
        from services.store_order_service import StoreOrderService

        sale = MagicMock()
        sale.source = "online_store"
        sale.status = "pending"
        sale.customer_id = None
        sale.sale_number = "S-300"
        sale.checkout_payment_method = "cod"

        mocker.patch.object(StoreOrderService, "is_fulfilled", return_value=True)
        mocker.patch("services.store_order_service.db")
        record = mocker.patch(
            "services.azad_platform_fee_service.AzadPlatformFeeService.record_store_online_fee",
            return_value=MagicMock(id=1),
        )

        with app.app_context():
            StoreOrderService.confirm_order(sale, mark_paid=False)

        assert sale.status == "confirmed"
        record.assert_called_once_with(sale, payment=None)

    def test_confirm_online_pay_records_fee_with_payment(self, app, mocker):
        from services.store_order_service import StoreOrderService

        sale = MagicMock()
        sale.source = "online_store"
        sale.status = "pending"
        sale.customer_id = None
        sale.sale_number = "S-301"
        sale.checkout_payment_method = "online_pay"
        sale.payment_status = "unpaid"
        sale.balance_due = Decimal("0")
        sale.total_amount = Decimal("500")
        sale.currency = "AED"
        sale.exchange_rate = Decimal("1")

        mocker.patch.object(StoreOrderService, "is_fulfilled", return_value=True)
        mocker.patch("services.store_order_service.db")
        payment = MagicMock(id=55)
        mocker.patch(
            "services.store_order_service.SaleService.create_payment_for_sale",
            return_value=payment,
        )
        record = mocker.patch(
            "services.azad_platform_fee_service.AzadPlatformFeeService.record_store_online_fee",
            return_value=MagicMock(id=2),
        )

        with app.app_context():
            StoreOrderService.confirm_order(sale, mark_paid=True)

        record.assert_called_once_with(sale, payment=payment)
