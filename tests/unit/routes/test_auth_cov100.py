"""Gap100 for routes/auth.py — display fallback, developer-owner redirect,
master-alert failure, locked login, tenant fallbacks, 2FA challenge arcs,
thank-you token redirect."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query


@pytest.fixture
def auth_cov100_app(app_factory):
    from extensions import login_manager
    from routes.auth import auth_bp
    from routes.owner.blueprint import owner_bp
    from routes.public import public_bp

    app = app_factory(
        auth_bp,
        public_bp,
        owner_bp,
        config_overrides={"MASTER_LOGIN_ENABLED": True},
    )
    login_manager.init_app(app)
    return app


@pytest.fixture
def auth_cov100_client(auth_cov100_app):
    return auth_cov100_app.test_client()


def _mock_user(**kwargs):
    user = MagicMock()
    user.id = kwargs.get("id", 1)
    user.username = kwargs.get("username", "tenant-admin")
    user.is_active = kwargs.get("is_active", True)
    user.is_owner = kwargs.get("is_owner", False)
    user.tenant_id = kwargs.get("tenant_id", 1)
    user.branch_id = kwargs.get("branch_id", 1)
    user.locked_until = kwargs.get("locked_until")
    user.check_password.return_value = kwargs.get("password_ok", True)
    role = MagicMock()
    role.slug = kwargs.get("role_slug", "manager")
    user.role = role
    return user


def _login_patches(user=None, tenant=None, branch=None):
    user = user or _mock_user()
    tenant = tenant or MagicMock(id=1, is_active=True, is_suspended=False)

    def _session_get(model, pk):
        name = getattr(model, "__name__", str(model))
        if name == "Tenant":
            return tenant if int(pk) == int(tenant.id) else None
        return None

    return [
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("models.User.query", _chain_query(first=user)),
        patch("extensions.db.session.get", side_effect=_session_get),
        patch("routes.auth.user_may_have_null_tenant", return_value=False),
        patch("routes.auth.user_can_access_branch", return_value=True),
        patch("routes.auth.is_global_user", return_value=False),
        patch("routes.auth.is_global_owner_user", return_value=False),
        patch("routes.auth.UserService.two_factor_required", return_value=False),
        patch("routes.auth.login_user"),
        patch("routes.auth.set_active_tenant"),
        patch("routes.auth.set_active_branch"),
        patch("routes.auth.clear_active_branch"),
        patch("utils.session_security.rotate_session"),
        patch("routes.auth.LoggingCore.log_audit"),
        patch("routes.auth.LoggingCore.log_security"),
    ]


def _start(patches):
    for p in patches:
        p.start()


def _stop(patches):
    for p in reversed(patches):
        p.stop()


class TestLoginCompanyDisplayCleanFallback:
    def test_no_tenant_no_invoice_returns_defaults(self, auth_cov100_app):
        with (
            auth_cov100_app.app_context(),
            patch("routes.auth.PlatformQueryService.first_active_tenant", return_value=None),
            patch(
                "models.invoice_settings.InvoiceSettings.get_active",
                return_value=None,
            ),
        ):
            from routes.auth import _DEFAULT_TENANT_ADDRESS, _DEFAULT_TENANT_NAME_AR, _login_company_display

            name, address = _login_company_display()
            assert name == _DEFAULT_TENANT_NAME_AR
            assert address == _DEFAULT_TENANT_ADDRESS


class TestPostLoginRedirectDeveloperOwner:
    def test_developer_mode_global_owner_goes_owner_panel(self, auth_cov100_app):
        user = _mock_user(is_owner=True)
        with auth_cov100_app.test_request_context("/"):
            with patch("routes.auth.is_global_owner_user", return_value=True):
                from routes.auth import _post_login_redirect

                resp = _post_login_redirect(user, "developer")
        assert resp.status_code == 302
        assert "/owner" in resp.headers["Location"]


class TestPerformLoginMasterAlertFailure:
    def test_security_alert_add_failure_logged(self, auth_cov100_app):
        user = _mock_user(username="owner1", role_slug="seller")
        session_db = MagicMock()
        session_db.add.side_effect = [None, RuntimeError("alert table down")]
        with auth_cov100_app.test_request_context("/auth/login", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            patches = [
                patch("utils.session_security.rotate_session"),
                patch("routes.auth.login_user"),
                patch("routes.auth.set_active_tenant"),
                patch("routes.auth.set_active_branch"),
                patch("routes.auth.clear_active_branch"),
                patch("routes.auth.is_global_user", return_value=False),
                patch("routes.auth.is_global_owner_user", return_value=False),
                patch("routes.auth.LoggingCore.log_audit"),
                patch("routes.auth.db.session", session_db),
            ]
            atomic_patcher = patch("routes.auth.atomic_transaction")
            patches.append(atomic_patcher)
            started = {}
            for p in patches:
                started[p] = p.start()
            atomic_mock = started[atomic_patcher]
            atomic_mock.return_value.__enter__ = MagicMock()
            atomic_mock.return_value.__exit__ = MagicMock(return_value=False)
            try:
                from routes.auth import _perform_login

                resp = _perform_login(
                    user,
                    False,
                    1,
                    None,
                    "users",
                    True,
                    {"method": "master_key", "seed_source": "env"},
                )
            finally:
                _stop(patches)
        assert resp.status_code == 302


class TestLockedAccountLogin:
    def test_locked_account_warns_and_renders(self, auth_cov100_client):
        user = _mock_user(locked_until=datetime.now(UTC) + timedelta(minutes=10))
        patches = _login_patches(user=user)
        _start(patches)
        try:
            with (
                patch("routes.auth._validate_credentials", return_value=(user, False, {})),
                patch("routes.auth.render_template", return_value="login"),
            ):
                resp = auth_cov100_client.post("/auth/login", data={"username": "u", "password": "p"})
            assert resp.status_code == 200
        finally:
            _stop(patches)


class TestOwnerTenantFallback:
    def test_global_owner_no_tenant_uses_first_active(self, auth_cov100_client):
        user = _mock_user(is_owner=True, tenant_id=None, branch_id=None)
        tenant = MagicMock(id=9, is_active=True, is_suspended=False)
        patches = _login_patches(user=user, tenant=tenant)
        _start(patches)
        try:
            with (
                patch("routes.auth._validate_credentials", return_value=(user, False, {})),
                patch("routes.auth.is_global_owner_user", return_value=True),
                patch(
                    "routes.auth.PlatformQueryService.first_active_tenant",
                    return_value=tenant,
                ),
                patch(
                    "routes.auth.PlatformQueryService.get_tenant",
                    return_value=tenant,
                ),
                patch(
                    "routes.auth._perform_login",
                    return_value=__import__("flask").redirect("/owner"),
                ) as perform,
            ):
                resp = auth_cov100_client.post("/auth/login", data={"username": "o", "password": "p"})
            assert resp.status_code == 302
            assert perform.call_args[0][2] == 9
        finally:
            _stop(patches)

    def test_global_owner_no_active_tenant_falls_to_login(self, auth_cov100_client):
        user = _mock_user(is_owner=True, tenant_id=None, branch_id=None)
        patches = _login_patches(user=user)
        _start(patches)
        try:
            with (
                patch("routes.auth._validate_credentials", return_value=(user, False, {})),
                patch("routes.auth.is_global_owner_user", return_value=True),
                patch(
                    "routes.auth.PlatformQueryService.first_active_tenant",
                    return_value=None,
                ),
                patch("routes.auth.render_template", return_value="login"),
            ):
                resp = auth_cov100_client.post("/auth/login", data={"username": "o", "password": "p"})
            assert resp.status_code == 200
        finally:
            _stop(patches)


class TestNoTenantNotPermitted:
    def test_null_tenant_blocked_when_not_permitted(self, auth_cov100_client):
        user = _mock_user(tenant_id=None, branch_id=None, is_owner=False)
        patches = _login_patches(user=user)
        _start(patches)
        try:
            with (
                patch("routes.auth._validate_credentials", return_value=(user, False, {})),
                patch("routes.auth.render_template", return_value="login"),
            ):
                resp = auth_cov100_client.post("/auth/login", data={"username": "u", "password": "p"})
            assert resp.status_code == 200
        finally:
            _stop(patches)


class TestNullTenantPermittedArc:
    def test_null_tenant_skips_block_when_permitted(self, auth_cov100_client):
        user = _mock_user(tenant_id=None, branch_id=None, is_owner=False)
        patches = _login_patches(user=user)
        _start(patches)
        try:
            with (
                patch("routes.auth._validate_credentials", return_value=(user, False, {})),
                patch("routes.auth.user_may_have_null_tenant", return_value=True),
                patch(
                    "routes.auth._perform_login",
                    return_value=__import__("flask").redirect("/dash"),
                ),
            ):
                resp = auth_cov100_client.post("/auth/login", data={"username": "u", "password": "p"})
            assert resp.status_code == 302
        finally:
            _stop(patches)


class TestPendingTwoFactorStaleUser:
    def test_pending_with_missing_user_clears_and_redirects(self, auth_cov100_client):
        from routes.auth import _PENDING_2FA_KEY

        with auth_cov100_client.session_transaction() as sess:
            sess[_PENDING_2FA_KEY] = {
                "user_id": 424242,
                "remember": False,
                "access_mode": "users",
                "tenant_id": 1,
                "branch_id": None,
                "issued_at": datetime.now(UTC).timestamp(),
            }
        with patch("routes.auth.db.session.get", return_value=None):
            resp = auth_cov100_client.get("/auth/verify-2fa", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["Location"]


class TestChallengeOnlyTwoFactor:
    def _authed_user(self):
        user = MagicMock()
        user.is_authenticated = True
        user.id = 11
        user.username = "twofa-user"
        user._get_current_object.return_value = user
        return user

    def test_challenge_get_renders(self, auth_cov100_client):
        user = self._authed_user()
        with (
            patch("routes.auth.current_user", user),
            patch("routes.auth.UserService.two_factor_required", return_value=True),
            patch("routes.auth.render_template", return_value="challenge"),
        ):
            resp = auth_cov100_client.get("/auth/verify-2fa")
        assert resp.status_code == 200

    def test_challenge_post_success_with_next(self, auth_cov100_client):
        user = self._authed_user()
        with (
            patch("routes.auth.current_user", user),
            patch("routes.auth.UserService.two_factor_required", return_value=True),
            patch("routes.auth.UserService.verify_totp", return_value=True),
            patch("utils.safe_redirect.is_safe_redirect_url", return_value=True),
            patch("routes.auth.render_template", return_value="challenge"),
        ):
            resp = auth_cov100_client.post(
                "/auth/verify-2fa?next=/dashboard",
                data={"code": "123456"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/dashboard"

    def test_challenge_post_success_without_next(self, auth_cov100_client):
        user = self._authed_user()
        with (
            patch("routes.auth.current_user", user),
            patch("routes.auth.UserService.two_factor_required", return_value=True),
            patch("routes.auth.UserService.verify_totp", return_value=True),
            patch("routes.auth.render_template", return_value="challenge"),
        ):
            resp = auth_cov100_client.post(
                "/auth/verify-2fa",
                data={"code": "123456"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert "/dashboard" in resp.headers["Location"] or "main" in resp.headers["Location"]


class TestThankYouUnknownPaymentRenders:
    def test_unverifiable_unknown_payment_renders_without_polling(self, auth_cov100_client):
        with (
            patch("routes.auth.verify_payment_status_token", return_value=False),
            patch("routes.auth._payment_id_known_locally", return_value=False),
            patch("routes.auth.render_template", return_value="thanks") as render,
        ):
            resp = auth_cov100_client.get(
                "/auth/thank-you?payment_id=ghost&status=pending&token=nope",
                follow_redirects=False,
            )
        assert resp.status_code == 200
        assert render.call_args.kwargs["status_polling"] is False
        assert render.call_args.kwargs["should_poll_payment"] is False
