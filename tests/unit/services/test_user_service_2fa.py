"""Unit tests for UserService TOTP two-factor flows (real pyotp round-trips)."""

from __future__ import annotations

from datetime import UTC, datetime

import pyotp
import pytest

from extensions import db
from services.user_service import UserService


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    yield
    db_session.rollback()


class TestTwoFactorRequired:
    def test_false_when_disabled(self, sample_user):
        assert UserService.two_factor_required(sample_user) is False

    def test_true_when_enabled(self, sample_user):
        sample_user.two_factor_enabled = True
        assert UserService.two_factor_required(sample_user) is True

    def test_false_for_none(self):
        assert UserService.two_factor_required(None) is False


class TestGenerateTotpSecret:
    def test_generates_persisted_base32_secret(self, sample_user):
        secret = UserService.generate_totp_secret(sample_user)
        db.session.refresh(sample_user)

        assert secret
        assert sample_user.totp_secret == secret
        assert pyotp.TOTP(secret).now().isdigit()

    def test_regeneration_rotates_secret(self, sample_user):
        first = UserService.generate_totp_secret(sample_user)
        second = UserService.generate_totp_secret(sample_user)

        assert first != second


class TestProvisioningUri:
    def test_uri_contains_scheme_secret_and_issuer(self, sample_user):
        secret = UserService.generate_totp_secret(sample_user)

        uri = UserService.totp_provisioning_uri(sample_user)

        assert uri and uri.startswith("otpauth://totp/")
        assert secret in uri
        assert "AZAD" in uri

    def test_uri_none_without_secret(self, sample_user):
        sample_user.totp_secret = None

        assert UserService.totp_provisioning_uri(sample_user) is None


class TestQrDataUri:
    def test_png_data_uri_generated(self, sample_user):
        UserService.generate_totp_secret(sample_user)

        data_uri = UserService.two_factor_qr_data_uri(sample_user)

        assert data_uri is not None
        assert data_uri.startswith("data:image/png;base64,")


class TestVerifyTotp:
    def _provision(self, sample_user) -> str:
        return UserService.generate_totp_secret(sample_user)

    def test_current_code_accepted(self, sample_user):
        secret = self._provision(sample_user)

        assert UserService.verify_totp(sample_user, pyotp.TOTP(secret).now()) is True

    def test_previous_window_code_accepted_for_clock_drift(self, sample_user):
        secret = self._provision(sample_user)
        now_ts = datetime.now(UTC).timestamp()
        previous_window_start = (int(now_ts) // 30) * 30 - 30
        drifted_code = pyotp.TOTP(secret).at(datetime.fromtimestamp(previous_window_start, tz=UTC))

        assert UserService.verify_totp(sample_user, drifted_code) is True

    def test_wrong_code_rejected(self, sample_user):
        secret = self._provision(sample_user)
        current = pyotp.TOTP(secret).now()
        wrong = str((int(current) + 1) % 1000000).zfill(6)

        assert UserService.verify_totp(sample_user, wrong) is False

    def test_garbage_and_empty_rejected(self, sample_user):
        self._provision(sample_user)

        for bad in ("", None, "abcdef", "12345", "1234567890", "12 34"):
            assert UserService.verify_totp(sample_user, bad) is False

    def test_rejected_without_secret(self, sample_user):
        sample_user.totp_secret = None

        assert UserService.verify_totp(sample_user, "123456") is False


class TestEnableDisableFlows:
    def test_enable_sets_flag(self, db_session, sample_user):
        UserService.generate_totp_secret(sample_user)

        UserService.enable_two_factor(sample_user)

        db.session.refresh(sample_user)
        assert sample_user.two_factor_enabled is True

    def test_disable_clears_flag_and_secret(self, db_session, sample_user):
        UserService.generate_totp_secret(sample_user)
        UserService.enable_two_factor(sample_user)

        UserService.disable_two_factor(sample_user)

        db.session.refresh(sample_user)
        assert sample_user.two_factor_enabled is False
        assert sample_user.totp_secret is None
