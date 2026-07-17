"""Azad subscription fees — renewal cycles, grace skips, payment/waiver."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestSubscriptionPeriods:
    """_period_dates — monthly, yearly, perpetual tiers."""

    @pytest.mark.parametrize(
        "fee_type,expected_days",
        [
            ("monthly", 30),
            ("yearly", 365),
        ],
    )
    def test_finite_period_end(self, fee_type, expected_days):
        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        start = date(2026, 1, 1)
        period_start, period_end = AzadSubscriptionFeeService._period_dates(
            fee_type, start
        )
        assert period_start == start
        assert period_end == start + timedelta(days=expected_days)

    def test_perpetual_has_no_end(self):
        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        _, period_end = AzadSubscriptionFeeService._period_dates(
            "perpetual", date(2026, 6, 1)
        )
        assert period_end is None

    def test_unknown_type_defaults_monthly_window(self):
        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        start = date(2026, 3, 1)
        _, period_end = AzadSubscriptionFeeService._period_dates("custom", start)
        assert period_end == start + timedelta(days=30)


class TestCreateSubscriptionFee:
    """create_subscription_fee — validation, grace skip, GL accrual."""

    def test_rejects_invalid_fee_type(self, app):
        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            with pytest.raises(ValueError, match="Invalid subscription fee_type"):
                AzadSubscriptionFeeService.create_subscription_fee(1, "weekly")

    def test_skips_when_no_amount_configured(self, app, mocker):
        settings = MagicMock(
            subscription_monthly_fee_aed=None,
            subscription_yearly_fee_aed=None,
            subscription_perpetual_fee_aed=None,
        )
        mocker.patch(
            "models.system_settings.SystemSettings.get_current", return_value=settings
        )

        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            result = AzadSubscriptionFeeService.create_subscription_fee(1, "monthly")
        assert result is None

    def test_creates_fee_with_explicit_amount(self, app, mocker):
        mocker.patch(
            "services.azad_subscription_fee_service.GLService.ensure_core_accounts"
        )
        mocker.patch("utils.tax_settings._resolve_main_branch", return_value=1)
        mocker.patch("services.azad_subscription_fee_service.post_or_fail")
        mocker.patch("services.azad_subscription_fee_service.db.session")

        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            fee = AzadSubscriptionFeeService.create_subscription_fee(
                1,
                "yearly",
                amount_aed=Decimal("1200"),
                billing_date=date(2026, 1, 1),
            )
        assert fee.tenant_id == 1
        assert fee.fee_type == "yearly"
        assert fee.amount_aed == Decimal("1200.000")
        assert fee.status == "accrued"
        assert fee.gl_posted is True


class TestRecordPayment:
    """record_payment — accrued -> paid with GL settlement."""

    def test_rejects_missing_fee(self, app, mocker):
        mock_get = mocker.patch("services.azad_subscription_fee_service.db.session.get")
        mock_get.return_value = None

        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            with pytest.raises(ValueError, match="not found"):
                AzadSubscriptionFeeService.record_payment(99)

    def test_rejects_non_accrued_status(self, app, mocker):
        fee = MagicMock(status="paid", amount_aed=Decimal("100"), tenant_id=1)
        mocker.patch(
            "services.azad_subscription_fee_service.db.session.get", return_value=fee
        )

        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            with pytest.raises(ValueError, match="must be accrued"):
                AzadSubscriptionFeeService.record_payment(1)

    def test_records_payment_and_posts_gl(self, app, mocker):
        fee = MagicMock(
            id=5,
            status="accrued",
            amount_aed=Decimal("250"),
            fee_type="monthly",
            tenant_id=1,
        )
        mocker.patch(
            "services.azad_subscription_fee_service.db.session.get", return_value=fee
        )
        mocker.patch(
            "services.azad_subscription_fee_service.GLService.ensure_core_accounts"
        )
        mocker.patch(
            "services.azad_subscription_fee_service.GLService.get_payment_credit_concept",
            return_value="BANK",
        )
        mocker.patch(
            "services.azad_subscription_fee_service.GLService._resolve_journal_line_account",
            return_value=MagicMock(code="1120"),
        )
        mocker.patch("utils.tax_settings._resolve_main_branch", return_value=1)
        mock_post = mocker.patch("services.azad_subscription_fee_service.post_or_fail")

        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            result = AzadSubscriptionFeeService.record_payment(
                5, payment_method="bank_transfer"
            )

        assert result.status == "paid"
        assert result.paid_amount_aed == Decimal("250.000")
        mock_post.assert_called_once()


class TestWaiveFee:
    """waive_fee — cancellation and GL reversal."""

    def test_idempotent_on_already_cancelled(self, app, mocker):
        fee = MagicMock(status="cancelled", tenant_id=1)
        mocker.patch(
            "services.azad_subscription_fee_service.db.session.get", return_value=fee
        )

        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            result = AzadSubscriptionFeeService.waive_fee(3)
        assert result is fee

    def test_waives_accrued_and_reverses_gl(self, app, mocker):
        fee = MagicMock(
            id=7,
            status="accrued",
            gl_posted=True,
            fee_type="monthly",
            tenant_id=1,
            notes="",
        )
        mocker.patch(
            "services.azad_subscription_fee_service.db.session.get", return_value=fee
        )
        mock_reverse = mocker.patch(
            "services.azad_subscription_fee_service.GLService.reverse_entry"
        )

        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            result = AzadSubscriptionFeeService.waive_fee(7, notes="grace period")

        assert result.status == "cancelled"
        mock_reverse.assert_called_once()


class TestSettingsAmount:
    def test_settings_amount_quantizes(self, app, mocker):
        settings = MagicMock(subscription_monthly_fee_aed=Decimal("99.9999"))
        mocker.patch(
            "models.system_settings.SystemSettings.get_current", return_value=settings
        )
        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            amount = AzadSubscriptionFeeService._settings_amount("monthly")
        assert amount == Decimal("100.000")

    def test_settings_amount_unknown_type_returns_none(self, app, mocker):
        settings = MagicMock()
        mocker.patch(
            "models.system_settings.SystemSettings.get_current", return_value=settings
        )
        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            assert AzadSubscriptionFeeService._settings_amount("weekly") is None


class TestRecordPaymentFallbacks:
    def test_record_payment_uses_cash_when_no_credit_concept(self, app, mocker):
        fee = MagicMock(
            id=5,
            status="accrued",
            amount_aed=Decimal("250"),
            fee_type="monthly",
            tenant_id=1,
        )
        mocker.patch(
            "services.azad_subscription_fee_service.db.session.get", return_value=fee
        )
        mocker.patch(
            "services.azad_subscription_fee_service.GLService.ensure_core_accounts"
        )
        mocker.patch(
            "services.azad_subscription_fee_service.GLService.get_payment_credit_concept",
            return_value=None,
        )
        mocker.patch("utils.tax_settings._resolve_main_branch", return_value=1)
        mocker.patch("services.azad_subscription_fee_service.post_or_fail")
        mocker.patch(
            "services.azad_subscription_fee_service.current_app"
        ).logger = MagicMock()
        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            result = AzadSubscriptionFeeService.record_payment(
                5, payment_method="unknown"
            )
        assert result.status == "paid"


class TestWaiveFeeErrors:
    def test_waive_fee_not_found(self, app, mocker):
        mocker.patch(
            "services.azad_subscription_fee_service.db.session.get", return_value=None
        )
        from services.azad_subscription_fee_service import AzadSubscriptionFeeService

        with app.app_context():
            with pytest.raises(ValueError, match="not found"):
                AzadSubscriptionFeeService.waive_fee(404)
