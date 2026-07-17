"""Azad platform fee — percentage tiers, idempotency, GL accrual."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


def _online_sale(**kwargs):
    sale = MagicMock()
    sale.id = kwargs.get("id", 1)
    sale.tenant_id = kwargs.get("tenant_id", 1)
    sale.sale_number = kwargs.get("sale_number", "S-100")
    sale.source = kwargs.get("source", "online_store")
    sale.checkout_payment_method = kwargs.get("checkout_payment_method", "online_pay")
    sale.checkout_gateway_ref = kwargs.get("checkout_gateway_ref", "GW-1")
    sale.amount_aed = kwargs.get("amount_aed", Decimal("1000"))
    sale.total_amount = sale.amount_aed
    sale.branch_id = 1
    return sale


class TestOnlineStoreDetection:
    """is_online_store_transaction — channel and gateway guards."""

    @pytest.mark.parametrize(
        "source,method,ref,expected",
        [
            ("online_store", "online_pay", "", True),
            ("online_store", "cash", "NP-123", True),
            ("pos", "online_pay", "", False),
            ("online_store", "cash", "", False),
        ],
    )
    def test_detection_matrix(self, source, method, ref, expected):
        from services.azad_platform_fee_service import AzadPlatformFeeService

        sale = _online_sale(
            source=source, checkout_payment_method=method, checkout_gateway_ref=ref
        )
        assert AzadPlatformFeeService.is_online_store_transaction(sale) is expected


class TestFeeCalculations:
    """Percentage math and payment-tier base amounts."""

    def test_base_amount_prefers_payment_aed(self):
        from services.azad_platform_fee_service import AzadPlatformFeeService

        sale = _online_sale(amount_aed=Decimal("500"))
        payment = MagicMock(amount_aed=Decimal("750"))
        assert AzadPlatformFeeService._base_amount_aed(sale, payment) == Decimal(
            "750.000"
        )

    def test_get_rate_from_system_settings(self, mocker):
        settings = MagicMock(azad_platform_fee_rate=Decimal("2.50"))
        mocker.patch("models.SystemSettings.get_current", return_value=settings)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        rate_decimal, rate_percent = AzadPlatformFeeService._get_rate(1)
        assert rate_percent == Decimal("2.50")
        assert rate_decimal == Decimal("0.0250")

    def test_idempotency_key_includes_gateway_ref(self):
        from services.azad_platform_fee_service import AzadPlatformFeeService

        sale = _online_sale()
        key = AzadPlatformFeeService._idempotency_key(sale, gateway_reference="NP-99")
        assert key == "store-online:1:1:NP-99"


class TestRecordStoreOnlineFee:
    """record_store_online_fee — accrual, duplicates, missing vault."""

    def test_skips_non_online_sale(self, app):
        from services.azad_platform_fee_service import AzadPlatformFeeService

        sale = _online_sale(source="pos")
        with app.app_context():
            assert AzadPlatformFeeService.record_store_online_fee(sale) is None

    def test_returns_existing_on_duplicate_key(self, app, mocker):
        existing = MagicMock(id=99)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = existing
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)

        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            result = AzadPlatformFeeService.record_store_online_fee(_online_sale())
        assert result is existing

    def test_skips_zero_base_amount(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)

        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            result = AzadPlatformFeeService.record_store_online_fee(
                _online_sale(amount_aed=Decimal("0")),
            )
        assert result is None

    def test_raises_when_platform_vault_missing(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
        mocker.patch(
            "services.azad_platform_fee_service.PaymentVault.get_platform_vault",
            return_value=None,
        )
        settings = MagicMock(azad_platform_fee_rate=Decimal("1"))
        mocker.patch("models.SystemSettings.get_current", return_value=settings)

        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            with pytest.raises(ValueError, match="Platform vault"):
                AzadPlatformFeeService.record_store_online_fee(_online_sale())

    def test_accrues_fee_and_posts_gl(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
        mocker.patch(
            "services.azad_platform_fee_service.PaymentVault.get_platform_vault",
            return_value=MagicMock(id=5),
        )
        settings = MagicMock(azad_platform_fee_rate=Decimal("1"))
        mocker.patch("models.SystemSettings.get_current", return_value=settings)
        mocker.patch(
            "services.azad_platform_fee_service.GLService.ensure_core_accounts"
        )
        mock_post = mocker.patch("services.azad_platform_fee_service.post_or_fail")
        mocker.patch("services.azad_platform_fee_service.db.session")

        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            fee = AzadPlatformFeeService.record_store_online_fee(
                _online_sale(amount_aed=Decimal("1000"))
            )

        assert fee is not None
        assert fee.fee_amount_aed == Decimal("10.000")
        mock_post.assert_called_once()
        lines = mock_post.call_args[0][0]
        assert lines[0]["debit"] == Decimal("10.000")
        assert lines[1]["credit"] == Decimal("10.000")


class TestPlatformFeeReporting:
    """Summary, settlement, and payout confirmation."""

    def test_get_accrued_summary_scoped_by_tenant(self, mocker):
        row = MagicMock(tenant_id=1, total=Decimal("45.5"))
        session = mocker.patch("services.azad_platform_fee_service.db.session")
        session.query.return_value.filter.return_value.filter.return_value.group_by.return_value.all.return_value = [
            row
        ]

        from services.azad_platform_fee_service import AzadPlatformFeeService

        result = AzadPlatformFeeService.get_accrued_summary(tenant_id=1)
        assert result[0]["tenant_id"] == 1
        assert result[0]["total_fee_aed"] == Decimal("45.500")

    def test_get_settlement_report_filters_dates(self, mocker):
        fee = MagicMock(fee_amount_aed=Decimal("10"))
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value.all.return_value = [fee]
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)

        from services.azad_platform_fee_service import AzadPlatformFeeService

        dt_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
        dt_to = datetime(2026, 6, 1, tzinfo=timezone.utc)
        report = AzadPlatformFeeService.get_settlement_report(
            tenant_id=1, date_from=dt_from, date_to=dt_to
        )
        assert report["count"] == 1
        assert report["total_fee_aed"] == Decimal("10.000")

    def test_confirm_settlement_paid_rejects_missing_fees(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = []
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)

        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            with pytest.raises(ValueError, match="No settled fees"):
                AzadPlatformFeeService.confirm_settlement_paid([1])

    def test_missing_tenant_id_raises(self, app):
        from services.azad_platform_fee_service import AzadPlatformFeeService

        sale = _online_sale()
        sale.tenant_id = None
        with app.app_context():
            with pytest.raises(ValueError, match="tenant_id"):
                AzadPlatformFeeService.record_store_online_fee(sale)

    def test_zero_fee_amount_skips(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
        settings = MagicMock(azad_platform_fee_rate=Decimal("0"))
        mocker.patch("models.SystemSettings.get_current", return_value=settings)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            assert (
                AzadPlatformFeeService.record_store_online_fee(_online_sale()) is None
            )

    def test_settle_fees_posts_gl(self, app, mocker):
        fee = MagicMock(
            id=1, fee_amount_aed=Decimal("10"), status="accrued", gl_posted=True
        )
        mock_q = MagicMock()
        mock_q.filter_by.return_value.all.return_value = [fee]
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
        mocker.patch(
            "services.azad_platform_fee_service._resolve_main_branch", return_value=1
        )
        mock_post = mocker.patch("services.azad_platform_fee_service.post_or_fail")
        mocker.patch("services.azad_platform_fee_service.db.session")
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            results = AzadPlatformFeeService.settle_fees(1)
        assert results[0]["tenant_id"] == 1
        assert fee.status == "settled"
        mock_post.assert_called_once()

    def test_settle_fees_skips_empty(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.all.return_value = []
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            assert AzadPlatformFeeService.settle_fees([1, 2]) == []

    def test_confirm_settlement_paid_success(self, app, mocker):
        fee = MagicMock(fee_amount_aed=Decimal("25"), status="settled")
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [fee]
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
        vault = MagicMock()
        vault.transactions = []
        mocker.patch(
            "services.azad_platform_fee_service.PaymentVault.get_platform_vault",
            return_value=vault,
        )
        mocker.patch("utils.helpers.generate_number", return_value="001")
        mocker.patch("services.azad_platform_fee_service.db.session")
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            result = AzadPlatformFeeService.confirm_settlement_paid(1)
        assert result["count"] == 1
        assert fee.status == "paid"

    def test_base_amount_from_sale_when_no_payment(self):
        from services.azad_platform_fee_service import AzadPlatformFeeService

        sale = _online_sale(amount_aed=Decimal("500"))
        assert AzadPlatformFeeService._base_amount_aed(sale, None) == Decimal("500.000")

    def test_settle_fees_skips_zero_total(self, app, mocker):
        fee = MagicMock(fee_amount_aed=Decimal("0"), status="accrued", gl_posted=True)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.all.return_value = [fee]
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            assert AzadPlatformFeeService.settle_fees(1) == []

    def test_confirm_settlement_paid_zero_total(self, app, mocker):
        fee = MagicMock(fee_amount_aed=Decimal("0"), status="settled")
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [fee]
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
        mocker.patch(
            "services.azad_platform_fee_service.PaymentVault.get_platform_vault",
            return_value=MagicMock(),
        )
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            with pytest.raises(ValueError, match="zero"):
                AzadPlatformFeeService.confirm_settlement_paid(1)

    def test_confirm_settlement_paid_missing_vault(self, app, mocker):
        fee = MagicMock(fee_amount_aed=Decimal("10"), status="settled")
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [fee]
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFee.query", mock_q)
        mocker.patch(
            "services.azad_platform_fee_service.PaymentVault.get_platform_vault",
            return_value=None,
        )
        from services.azad_platform_fee_service import AzadPlatformFeeService

        with app.app_context():
            with pytest.raises(ValueError, match="Platform vault"):
                AzadPlatformFeeService.confirm_settlement_paid(1)
