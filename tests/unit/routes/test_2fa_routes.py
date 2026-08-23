"""Route tests for TOTP two-factor authentication (/auth/verify-2fa, /auth/2fa/*).

pyotp/qrcode are exercised through the service boundary; route-level tests
compute codes with real pyotp against secrets provisioned via UserService.
"""

from unittest.mock import MagicMock, patch

import pyotp
import pytest

from utils.decorators import TWO_FACTOR_SESSION_KEY


@pytest.fixture(autouse=True)
def _app_ctx(app):
    with app.app_context():
        yield


def _provision_and_enable(user):
    from services.user_service import UserService

    secret = UserService.generate_totp_secret(user)
    UserService.enable_two_factor(user)
    return secret


def _current_code(secret):
    return pyotp.TOTP(secret).now()


class TestLoginTwoFactorGate:
    def test_enrolled_user_redirected_to_challenge(self, client, sample_user):
        _provision_and_enable(sample_user)

        resp = client.post(
            "/auth/login",
            data={"username": sample_user.username, "password": "password123"},
        )

        assert resp.status_code == 302
        assert "/auth/verify-2fa" in resp.headers.get("Location", "")

    def test_pending_user_cannot_reach_protected_pages_yet(self, client, sample_user):
        _provision_and_enable(sample_user)
        client.post(
            "/auth/login",
            data={"username": sample_user.username, "password": "password123"},
        )

        resp = client.get("/auth/2fa/setup")

        assert resp.status_code == 302
        assert "/auth/login" in resp.headers.get("Location", "")

    def test_wrong_code_keeps_challenge_open(self, client, sample_user):
        _provision_and_enable(sample_user)
        client.post(
            "/auth/login",
            data={"username": sample_user.username, "password": "password123"},
        )

        resp = client.post("/auth/verify-2fa", data={"code": "000000"})

        assert resp.status_code == 200
        assert "غير صحيح".encode() in resp.data

    def test_correct_code_completes_login(self, client, sample_user):
        secret = _provision_and_enable(sample_user)
        client.post(
            "/auth/login",
            data={"username": sample_user.username, "password": "password123"},
        )

        resp = client.post("/auth/verify-2fa", data={"code": _current_code(secret)})

        assert resp.status_code == 302
        assert "/auth/verify-2fa" not in resp.headers.get("Location", "")
        setup_page = client.get("/auth/2fa/setup")
        assert setup_page.status_code == 200

    def test_expired_pending_returns_to_login(self, client, sample_user):
        import time

        secret = _provision_and_enable(sample_user)
        client.post(
            "/auth/login",
            data={"username": sample_user.username, "password": "password123"},
        )
        with client.session_transaction() as sess:
            pending = dict(sess["pending_2fa"])
            pending["issued_at"] = time.time() - 400
            sess["pending_2fa"] = pending

        resp = client.post("/auth/verify-2fa", data={"code": _current_code(secret)})

        assert resp.status_code == 302
        assert "/auth/login" in resp.headers.get("Location", "")

    def test_verify_without_pending_redirects_to_login(self, client):
        resp = client.get("/auth/verify-2fa")

        assert resp.status_code == 302
        assert "/auth/login" in resp.headers.get("Location", "")

    def test_master_key_login_bypasses_challenge(self, client, sample_owner, mocker):
        from services.user_service import UserService

        UserService.generate_totp_secret(sample_owner)
        UserService.enable_two_factor(sample_owner)
        mocker.patch("utils.master_login.try_master_login", return_value=(True, {"method": "date"}))

        with patch.dict(client.application.config, {"MASTER_LOGIN_ENABLED": True}):
            resp = client.post(
                "/auth/login",
                data={"username": sample_owner.username, "password": "master-secret"},
            )

        assert resp.status_code == 302
        assert "/auth/verify-2fa" not in resp.headers.get("Location", "")
        assert client.get("/auth/2fa/setup").status_code == 200


class TestTwofactorSetupRoutes:
    def test_setup_requires_login(self, client):
        resp = client.get("/auth/2fa/setup")

        assert resp.status_code == 302
        assert "/auth/login" in resp.headers.get("Location", "")

    def test_setup_provisions_qr_and_secret(self, auth_client, sample_user, db_session):
        resp = auth_client.get("/auth/2fa/setup")

        assert resp.status_code == 200
        assert b"data:image/png;base64," in resp.data
        db_session.refresh(sample_user)
        assert sample_user.totp_secret

    def test_enable_with_valid_code(self, auth_client, sample_user, db_session):
        auth_client.get("/auth/2fa/setup")
        code = _current_code(sample_user.totp_secret)

        resp = auth_client.post("/auth/2fa/enable", data={"code": code})

        assert resp.status_code == 302
        db_session.refresh(sample_user)
        assert sample_user.two_factor_enabled is True

    def test_enable_with_invalid_code_rejected(self, auth_client, sample_user, db_session):
        auth_client.get("/auth/2fa/setup")

        resp = auth_client.post("/auth/2fa/enable", data={"code": "000000"})

        assert resp.status_code == 302
        assert "/auth/2fa/setup" in resp.headers.get("Location", "")
        db_session.refresh(sample_user)
        assert sample_user.two_factor_enabled is False

    def test_disable_with_password_clears_enrollment(self, auth_client, sample_user, db_session):
        _provision_and_enable(sample_user)

        resp = auth_client.post("/auth/2fa/disable", data={"password": "password123"})

        assert resp.status_code == 302
        db_session.refresh(sample_user)
        assert sample_user.two_factor_enabled is False
        assert sample_user.totp_secret is None

    def test_disable_with_wrong_password_keeps_enrollment(self, auth_client, sample_user, db_session):
        _provision_and_enable(sample_user)

        resp = auth_client.post("/auth/2fa/disable", data={"password": "wrong-password"})

        assert resp.status_code == 302
        db_session.refresh(sample_user)
        assert sample_user.two_factor_enabled is True


class TestTwoFactorRequiredDecorator:
    def _probe_response(self, app_factory, mock_user, marker_set):
        from flask import Blueprint

        from routes.auth import auth_bp
        from utils.decorators import two_factor_required

        probe_bp = Blueprint("tfa_probe", __name__)

        @probe_bp.route("/tfa-probe")
        @two_factor_required
        def probe():
            return "probe-ok"

        app = app_factory(probe_bp, auth_bp)
        patches = [patch("flask_login.utils._get_user", return_value=mock_user)]
        for p in patches:
            p.start()
        try:
            client = app.test_client()
            if marker_set:
                with client.session_transaction() as sess:
                    sess[TWO_FACTOR_SESSION_KEY] = True
            return client.get("/tfa-probe")
        finally:
            for p in reversed(patches):
                p.stop()

    def test_enrolled_session_without_marker_redirected(self, app_factory, mock_user):
        mock_user.two_factor_enabled = True

        resp = self._probe_response(app_factory, mock_user, marker_set=False)

        assert resp.status_code == 302
        assert "/auth/verify-2fa" in resp.headers.get("Location", "")

    def test_enrolled_session_with_marker_passes(self, app_factory, mock_user):
        mock_user.two_factor_enabled = True

        resp = self._probe_response(app_factory, mock_user, marker_set=True)

        assert resp.status_code == 200
        assert b"probe-ok" in resp.data

    def test_non_bool_flag_is_ignored_mock_safety(self, app_factory, mock_user):
        mock_user.two_factor_enabled = MagicMock()

        resp = self._probe_response(app_factory, mock_user, marker_set=False)

        assert resp.status_code == 200
