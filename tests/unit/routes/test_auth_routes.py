from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from itsdangerous import URLSafeTimedSerializer

from tests.unit.routes.conftest import _chain_query, app_factory, unauthenticated_client


@pytest.fixture
def auth_config():
    return {
        "MASTER_LOGIN_ENABLED": True,
        "NOWPAYMENTS_IP_WHITELIST": ["127.0.0.1", "185.71.76.0/24"],
    }


@pytest.fixture
def auth_app(app_factory, auth_config):
    from routes.auth import auth_bp
    from routes.public import public_bp
    return app_factory(auth_bp, public_bp, config_overrides=auth_config)


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


def _mock_user(**kwargs):
    user = MagicMock()
    user.id = kwargs.get("id", 1)
    user.username = kwargs.get("username", "tenant-admin")
    user.is_active = kwargs.get("is_active", True)
    user.is_owner = kwargs.get("is_owner", False)
    user.tenant_id = kwargs.get("tenant_id", 1)
    user.branch_id = kwargs.get("branch_id", 1)
    user.locked_until = kwargs.get("locked_until", None)
    user.check_password.return_value = kwargs.get("password_ok", True)
    role = MagicMock()
    role.slug = kwargs.get("role_slug", "manager")
    user.role = role
    return user


def _mock_tenant(**kwargs):
    tenant = MagicMock()
    tenant.id = kwargs.get("id", 1)
    tenant.is_active = kwargs.get("is_active", True)
    tenant.is_suspended = kwargs.get("is_suspended", False)
    tenant.name_ar = kwargs.get("name_ar", "شركة")
    tenant.address_ar = kwargs.get("address_ar", "دبي")
    tenant.address_en = kwargs.get("address_en", "")
    return tenant


def _mock_branch(**kwargs):
    branch = MagicMock()
    branch.id = kwargs.get("id", 1)
    branch.tenant_id = kwargs.get("tenant_id", 1)
    branch.is_active = True
    branch.is_main = True
    branch.code = "BR01"
    branch.name = "Main"
    return branch


def _login_patches(user=None, tenant=None, branch=None):
    user = user or _mock_user()
    tenant = tenant or _mock_tenant()
    branch = branch or _mock_branch()

    def _session_get(model, pk):
        name = getattr(model, "__name__", str(model))
        if name == "Branch":
            return branch if int(pk) == int(branch.id) else None
        if name == "Tenant":
            return tenant if int(pk) == int(tenant.id) else None
        return None

    return [
        patch("extensions.limiter.limit", return_value=lambda f: f),
        patch("routes.auth.User.query", _chain_query(first=user)),
        patch("routes.auth.db.session.get", side_effect=_session_get),
        patch("routes.auth.user_may_have_null_tenant", return_value=False),
        patch("routes.auth.user_can_access_branch", return_value=True),
        patch("routes.auth.is_global_user", return_value=False),
        patch("routes.auth.login_user"),
        patch("routes.auth.set_active_tenant"),
        patch("routes.auth.set_active_branch"),
        patch("utils.session_security.rotate_session"),
        patch("routes.auth.LoggingCore.log_audit"),
        patch("routes.auth.LoggingCore.log_security"),
    ]


@pytest.fixture(autouse=True)
def _clear_payment_callback_cache():
    from routes.auth import _payment_callback_cache
    saved = dict(_payment_callback_cache)
    _payment_callback_cache.clear()
    yield
    _payment_callback_cache.clear()
    _payment_callback_cache.update(saved)


class TestPaymentStatusToken:
    def test_issue_and_verify_roundtrip(self, auth_app):
        with auth_app.app_context():
            from routes.auth import issue_payment_status_token, verify_payment_status_token
            token = issue_payment_status_token("pay-42")
            assert verify_payment_status_token("pay-42", token) is True

    def test_verify_rejects_missing_token(self, auth_app):
        with auth_app.app_context():
            from routes.auth import verify_payment_status_token
            assert verify_payment_status_token("pay-1", None) is False
            assert verify_payment_status_token("", "tok") is False

    def test_verify_rejects_wrong_payment_id(self, auth_app):
        with auth_app.app_context():
            from routes.auth import issue_payment_status_token, verify_payment_status_token
            token = issue_payment_status_token("pay-a")
            assert verify_payment_status_token("pay-b", token) is False

    def test_verify_rejects_tampered_token(self, auth_app):
        with auth_app.app_context():
            from routes.auth import verify_payment_status_token
            assert verify_payment_status_token("pay-1", "not-a-valid-token") is False

    def test_verify_rejects_expired_token(self, auth_app):
        with auth_app.app_context():
            from routes.auth import (
                _PAYMENT_STATUS_TOKEN_MAX_AGE,
                _PAYMENT_STATUS_TOKEN_SALT,
                verify_payment_status_token,
            )
            ser = URLSafeTimedSerializer(auth_app.config["SECRET_KEY"], salt=_PAYMENT_STATUS_TOKEN_SALT)
            expired = ser.dumps({"pid": "pay-old"}, salt=_PAYMENT_STATUS_TOKEN_SALT)
            with patch("routes.auth._payment_status_token_serializer", return_value=ser):
                with patch.object(ser, "loads", side_effect=__import__("itsdangerous").SignatureExpired("expired")):
                    assert verify_payment_status_token("pay-old", expired) is False

    def test_serializer_requires_secret(self, auth_app):
        auth_app.config["SECRET_KEY"] = ""
        with auth_app.app_context():
            from routes.auth import _payment_status_token_serializer
            with pytest.raises(RuntimeError, match="SECRET_KEY"):
                _payment_status_token_serializer()


class TestPaymentIdKnownLocally:
    def test_donation_gateway_match(self, auth_app):
        donation = MagicMock()
        with auth_app.app_context():
            with patch("routes.auth.Donation.query", _chain_query(first=donation)):
                from routes.auth import _payment_id_known_locally
                assert _payment_id_known_locally("gw-1") is True

    def test_package_purchase_match(self, auth_app):
        with auth_app.app_context():
            with patch("routes.auth.Donation.query", _chain_query(first=None)):
                with patch("routes.auth.PackagePurchase.query", _chain_query(first=MagicMock())):
                    from routes.auth import _payment_id_known_locally
                    assert _payment_id_known_locally("pkg-1") is True

    def test_sale_checkout_ref_match(self, auth_app):
        with auth_app.app_context():
            with patch("routes.auth.Donation.query", _chain_query(first=None)):
                with patch("routes.auth.PackagePurchase.query", _chain_query(first=None)):
                    with patch("routes.auth.Sale.query", _chain_query(first=MagicMock())):
                        from routes.auth import _payment_id_known_locally
                        assert _payment_id_known_locally("sale-ref") is True

    def test_unknown_payment_id(self, auth_app):
        with auth_app.app_context():
            with patch("routes.auth.Donation.query", _chain_query(first=None)):
                with patch("routes.auth.PackagePurchase.query", _chain_query(first=None)):
                    with patch("routes.auth.Sale.query", _chain_query(first=None)):
                        from routes.auth import _payment_id_known_locally
                        assert _payment_id_known_locally("  ") is False
                        assert _payment_id_known_locally("missing") is False


class TestAuthHelpers:
    def test_login_company_display_from_tenant(self, auth_app):
        tenant = _mock_tenant(name_ar="شركة الاختبار", address_ar="أبوظبي")
        with auth_app.app_context():
            with patch("models.tenant.Tenant.query", _chain_query(first=tenant)):
                from routes.auth import _login_company_display
                name, address = _login_company_display()
                assert name == "شركة الاختبار"
                assert address == "أبوظبي"

    def test_login_company_display_invoice_fallback(self, auth_app):
        inv = MagicMock()
        inv.company_name_ar = "من الفاتورة"
        inv.address_ar = "الشارقة"
        inv.address_en = ""
        with auth_app.app_context():
            with patch("models.tenant.Tenant.query", _chain_query(first=None)):
                with patch("models.invoice_settings.InvoiceSettings.get_active", return_value=inv):
                    from routes.auth import _DEFAULT_TENANT_NAME_AR, _login_company_display
                    name, address = _login_company_display()
                    assert name == "من الفاتورة"
                    assert address == "الشارقة"

    def test_login_company_display_default(self, auth_app):
        broken_query = MagicMock()
        broken_query.filter_by.side_effect = RuntimeError("db down")
        with auth_app.app_context():
            with patch("models.tenant.Tenant.query", broken_query):
                with patch("models.invoice_settings.InvoiceSettings.get_active", side_effect=RuntimeError("db down")):
                    from routes.auth import _DEFAULT_TENANT_NAME_AR, _login_company_display
                    name, address = _login_company_display()
                    assert name == _DEFAULT_TENANT_NAME_AR

    def test_login_branches(self, auth_app):
        branches = [_mock_branch()]
        with auth_app.app_context():
            with patch("routes.auth.Branch.query", _chain_query(all=branches)):
                from routes.auth import _login_branches
                assert _login_branches() == branches

    def test_resolve_effective_tenant_user_tenant(self, auth_app):
        user = _mock_user(tenant_id=7)
        with auth_app.app_context():
            from routes.auth import _resolve_effective_tenant
            assert _resolve_effective_tenant(user, None) == 7

    def test_resolve_effective_tenant_owner_branch(self, auth_app):
        user = _mock_user(is_owner=True, tenant_id=None)
        branch = _mock_branch(tenant_id=9)
        with auth_app.app_context():
            from routes.auth import _resolve_effective_tenant
            assert _resolve_effective_tenant(user, branch) == 9

    def test_resolve_effective_tenant_owner_branch_no_tenant(self, auth_app):
        user = _mock_user(is_owner=True, tenant_id=None)
        branch = MagicMock(tenant_id=None)
        with auth_app.app_context():
            from routes.auth import _resolve_effective_tenant
            assert _resolve_effective_tenant(user, branch) is None

    def test_resolve_effective_tenant_returns_none(self, auth_app):
        user = _mock_user(tenant_id=None, is_owner=False)
        with auth_app.app_context():
            from routes.auth import _resolve_effective_tenant
            assert _resolve_effective_tenant(user, None) is None

    def test_validate_branch_tenant_consistency(self, auth_app):
        user = _mock_user(tenant_id=1)
        branch = _mock_branch(tenant_id=2)
        with auth_app.app_context():
            from routes.auth import _validate_branch_tenant_consistency
            assert _validate_branch_tenant_consistency(user, branch) is False
            assert _validate_branch_tenant_consistency(user, _mock_branch(tenant_id=1)) is True
            assert _validate_branch_tenant_consistency(_mock_user(tenant_id=None), branch) is True

    def test_validate_credentials_success(self, auth_app):
        user = _mock_user(password_ok=True)
        with auth_app.test_request_context():
            with patch("routes.auth.User.query", _chain_query(first=user)):
                from routes.auth import _validate_credentials
                u, master, meta = _validate_credentials("admin", "secret")
                assert u is user
                assert master is False

    def test_validate_credentials_master_login_disabled(self, auth_app):
        user = _mock_user(is_owner=True, password_ok=False)
        auth_app.config["MASTER_LOGIN_ENABLED"] = False
        with auth_app.test_request_context():
            with patch("routes.auth.User.query", _chain_query(first=user)):
                from routes.auth import _validate_credentials
                u, master, meta = _validate_credentials("owner", "wrong")
                assert u is user
                assert master is False
                assert meta.get("reason") == "disabled"

    def test_validate_credentials_master_login_success(self, auth_app):
        user = _mock_user(is_owner=True, password_ok=False)
        with auth_app.test_request_context("/auth/login", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            with patch("routes.auth.User.query", _chain_query(first=user)):
                with patch("utils.master_login.try_master_login", return_value=(True, {"method": "seed"})):
                    from routes.auth import _validate_credentials
                    u, master, meta = _validate_credentials("owner", "master")
                    assert master is True

    def test_validate_credentials_master_exception(self, auth_app):
        user = _mock_user(is_owner=True, password_ok=False)
        with auth_app.test_request_context():
            with patch("routes.auth.User.query", _chain_query(first=user)):
                with patch("utils.master_login.try_master_login", side_effect=RuntimeError("boom")):
                    from routes.auth import _validate_credentials
                    u, master, meta = _validate_credentials("owner", "x")
                    assert master is False

    def test_log_failed_login_writes_history(self, auth_app):
        user = _mock_user()
        with auth_app.test_request_context("/auth/login", environ_base={"REMOTE_ADDR": "10.0.0.1"}):
            with patch("routes.auth.LoggingCore.log_audit") as audit:
                with patch("routes.auth.db.session") as sess:
                    from routes.auth import _log_failed_login
                    _log_failed_login("baduser", user, False, None)
        audit.assert_called_once()
        sess.add.assert_called_once()
        sess.commit.assert_called_once()

    def test_perform_login_global_user_allow_all(self, auth_app):
        user = _mock_user(role_slug="super_admin", branch_id=None)
        with auth_app.test_request_context(environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            with patch("utils.session_security.rotate_session"), \
                 patch("routes.auth.login_user"), \
                 patch("routes.auth.set_active_tenant"), \
                 patch("routes.auth.set_active_branch") as set_branch, \
                 patch("routes.auth.is_global_user", return_value=True), \
                 patch("routes.auth.user_can_access_branch", return_value=False), \
                 patch("routes.auth.db.session.add"), \
                 patch("routes.auth.db.session.commit"), \
                 patch("routes.auth.LoggingCore.log_audit"), \
                 patch("utils.safe_redirect.is_safe_redirect_url", return_value=False), \
                 patch("routes.auth.url_for", return_value="/dashboard"), \
                 patch("models.login_history.LoginHistory"):
                from routes.auth import _perform_login
                _perform_login(user, False, 1, None, "users", False, {})
                set_branch.assert_called_with(None, user=user, allow_all=True)

    def test_perform_login_regular_user_clears_branch(self, auth_app):
        user = _mock_user(role_slug="seller", branch_id=None)
        with auth_app.test_request_context(environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            with patch("utils.session_security.rotate_session"), \
                 patch("routes.auth.login_user"), \
                 patch("routes.auth.set_active_tenant"), \
                 patch("routes.auth.clear_active_branch") as clear_branch, \
                 patch("routes.auth.is_global_user", return_value=False), \
                 patch("routes.auth.db.session.add"), \
                 patch("routes.auth.db.session.commit"), \
                 patch("routes.auth.LoggingCore.log_audit"), \
                 patch("utils.safe_redirect.is_safe_redirect_url", return_value=False), \
                 patch("routes.auth.url_for", return_value="/dashboard"), \
                 patch("models.login_history.LoginHistory"):
                from routes.auth import _perform_login
                _perform_login(user, False, 1, None, "users", False, {})
                clear_branch.assert_called_once()

    def test_perform_login_regular_user_with_branch(self, auth_app):
        user = _mock_user(role_slug="seller", branch_id=4)
        with auth_app.test_request_context(environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            with patch("utils.session_security.rotate_session"), \
                 patch("routes.auth.login_user"), \
                 patch("routes.auth.set_active_tenant"), \
                 patch("routes.auth.set_active_branch") as set_branch, \
                 patch("routes.auth.is_global_user", return_value=False), \
                 patch("routes.auth.db.session.add"), \
                 patch("routes.auth.db.session.commit"), \
                 patch("routes.auth.LoggingCore.log_audit"), \
                 patch("utils.safe_redirect.is_safe_redirect_url", return_value=False), \
                 patch("routes.auth.url_for", return_value="/dashboard"), \
                 patch("models.login_history.LoginHistory"):
                from routes.auth import _perform_login
                _perform_login(user, False, 1, 4, "users", False, {})
                set_branch.assert_called_with(4, user=user, allow_all=False)

    def test_post_login_redirect_owner(self, auth_app):
        user = _mock_user()
        with auth_app.test_request_context():
            with patch("routes.auth.is_global_owner_user", return_value=True):
                with patch("routes.auth.url_for", return_value="/owner"):
                    from routes.auth import _post_login_redirect
                    resp = _post_login_redirect(user, "users")
                    assert resp.status_code == 302

    def test_post_login_redirect_developer_warning(self, auth_app):
        user = _mock_user(role_slug="manager")
        with auth_app.test_request_context():
            with patch("routes.auth.is_global_owner_user", return_value=False):
                with patch("routes.auth.url_for", return_value="/owner/company"):
                    from routes.auth import _post_login_redirect
                    resp = _post_login_redirect(user, "developer")
                    assert resp.status_code == 302

    def test_post_login_redirect_company_dashboard(self, auth_app):
        user = _mock_user(role_slug="super_admin")
        with auth_app.test_request_context():
            with patch("routes.auth.is_global_owner_user", return_value=False):
                with patch("routes.auth.url_for", return_value="/owner/company"):
                    from routes.auth import _post_login_redirect
                    resp = _post_login_redirect(user, "users")
                    assert resp.status_code == 302

    def test_post_login_redirect_main_dashboard(self, auth_app):
        user = _mock_user(role_slug="seller")
        with auth_app.test_request_context():
            with patch("routes.auth.is_global_owner_user", return_value=False):
                with patch("routes.auth.url_for", return_value="/dashboard"):
                    from routes.auth import _post_login_redirect
                    resp = _post_login_redirect(user, "users")
                    assert resp.status_code == 302

    def test_render_login_invalid_mode(self, auth_app):
        with auth_app.test_request_context("/auth/login?mode=hack"):
            with patch("routes.auth.render_template", return_value="html") as render:
                from routes.auth import _render_login
                _render_login()
                assert render.call_args.kwargs["access_mode"] == "users"


class TestNowpaymentsIpWhitelist:
    def test_rejects_empty_remote_addr(self, auth_app):
        with auth_app.app_context():
            from routes.auth import _is_nowpayments_ip
            assert _is_nowpayments_ip(None) is False

    def test_rejects_empty_whitelist(self, auth_app):
        auth_app.config["NOWPAYMENTS_IP_WHITELIST"] = []
        with auth_app.app_context():
            from routes.auth import _is_nowpayments_ip
            assert _is_nowpayments_ip("127.0.0.1") is False

    def test_accepts_exact_ip(self, auth_app):
        with auth_app.app_context():
            from routes.auth import _is_nowpayments_ip
            assert _is_nowpayments_ip("127.0.0.1") is True

    def test_accepts_cidr(self, auth_app):
        with auth_app.app_context():
            from routes.auth import _is_nowpayments_ip
            assert _is_nowpayments_ip("185.71.76.10") is True

    def test_rejects_invalid_ip(self, auth_app):
        with auth_app.app_context():
            from routes.auth import _is_nowpayments_ip
            assert _is_nowpayments_ip("not-an-ip") is False
            assert _is_nowpayments_ip("8.8.8.8") is False

    def test_skips_invalid_whitelist_entry(self, auth_app):
        auth_app.config["NOWPAYMENTS_IP_WHITELIST"] = ["not-valid", "127.0.0.1"]
        with auth_app.app_context():
            from routes.auth import _is_nowpayments_ip
            assert _is_nowpayments_ip("127.0.0.1") is True


class TestDuplicateCallback:
    def test_duplicate_detection_and_prune(self, auth_app):
        from routes.auth import _is_duplicate_callback, _payment_callback_cache
        old_key = "old:done"
        _payment_callback_cache[old_key] = datetime.now(timezone.utc).timestamp() - 90000
        try:
            assert _is_duplicate_callback("new-pay", "waiting") is False
            assert _is_duplicate_callback("new-pay", "waiting") is True
            assert old_key not in _payment_callback_cache
        finally:
            _payment_callback_cache.pop("new-pay:waiting", None)


class TestSupportRoute:
    def test_support_lists_packages(self, auth_client):
        packages = [MagicMock()]
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("models.Package.query", _chain_query(all=packages)):
                with patch("routes.auth.render_template", return_value="support") as render:
                    resp = auth_client.get("/auth/support")
        assert resp.status_code == 200
        render.assert_called_once()


class TestLoginRoute:
    def test_get_login_renders(self, auth_client):
        with unauthenticated_client(auth_client):
            with patch("extensions.limiter.limit", return_value=lambda f: f):
                with patch("routes.auth.render_template", return_value="login") as render:
                    resp = auth_client.get("/auth/login?mode=developer")
        assert resp.status_code == 200
        assert render.call_args.kwargs["access_mode"] == "developer"

    def test_authenticated_user_redirects(self, auth_client):
        user = _mock_user(role_slug="manager")
        with patch("flask_login.utils._get_user", return_value=user):
            with patch("extensions.limiter.limit", return_value=lambda f: f):
                with patch("routes.auth.is_global_owner_user", return_value=False):
                    with patch("routes.auth.url_for", return_value="/owner/company"):
                        resp = auth_client.get("/auth/login")
        assert resp.status_code == 302

    def test_post_missing_fields(self, auth_client):
        with unauthenticated_client(auth_client):
            with patch("extensions.limiter.limit", return_value=lambda f: f):
                with patch("routes.auth.render_template", return_value="login") as render:
                    resp = auth_client.post("/auth/login", data={"username": "", "password": ""})
        assert resp.status_code == 200
        render.assert_called_once()

    def test_post_invalid_credentials(self, auth_client):
        with unauthenticated_client(auth_client):
            patches = [
                patch("extensions.limiter.limit", return_value=lambda f: f),
                patch("routes.auth.User.query", _chain_query(first=None)),
                patch("routes.auth._log_failed_login"),
                patch("routes.auth.render_template", return_value="login"),
            ]
            with patches[0], patches[1], patches[2], patches[3]:
                resp = auth_client.post("/auth/login", data={"username": "nouser", "password": "bad"})
        assert resp.status_code == 200

    def test_post_master_ip_denied(self, auth_client):
        owner = _mock_user(is_owner=True, password_ok=False)
        with unauthenticated_client(auth_client):
            with patch("extensions.limiter.limit", return_value=lambda f: f):
                with patch("routes.auth.User.query", _chain_query(first=owner)):
                    with patch("routes.auth._validate_credentials", return_value=(owner, False, {"reason": "ip_denied"})):
                        with patch("routes.auth._log_failed_login"):
                            with patch("routes.auth.render_template", return_value="login"):
                                resp = auth_client.post("/auth/login", data={"username": "owner", "password": "x"})
        assert resp.status_code == 200

    def test_post_master_disabled(self, auth_client):
        owner = _mock_user(is_owner=True, password_ok=False)
        with unauthenticated_client(auth_client):
            with patch("extensions.limiter.limit", return_value=lambda f: f):
                with patch("routes.auth.User.query", _chain_query(first=owner)):
                    with patch("routes.auth._validate_credentials", return_value=(owner, False, {"reason": "disabled"})):
                        with patch("routes.auth._log_failed_login"):
                            with patch("routes.auth.render_template", return_value="login"):
                                resp = auth_client.post("/auth/login", data={"username": "owner", "password": "x"})
        assert resp.status_code == 200

    def test_post_inactive_user(self, auth_client):
        user = _mock_user(is_active=False)
        with unauthenticated_client(auth_client):
            with patch("extensions.limiter.limit", return_value=lambda f: f):
                with patch("routes.auth._validate_credentials", return_value=(user, False, {})):
                    with patch("routes.auth.render_template", return_value="login"):
                        resp = auth_client.post("/auth/login", data={"username": "u", "password": "p"})
        assert resp.status_code == 200

    def test_post_inactive_tenant(self, auth_client):
        user = _mock_user()
        tenant = _mock_tenant(is_active=False)
        with unauthenticated_client(auth_client):
            patches = _login_patches(user=user, tenant=tenant)
            for p in patches:
                p.start()
            try:
                with patch("routes.auth._validate_credentials", return_value=(user, False, {})):
                    with patch("routes.auth.render_template", return_value="login"):
                        resp = auth_client.post("/auth/login", data={"username": "u", "password": "p"})
                assert resp.status_code == 200
            finally:
                for p in reversed(patches):
                    p.stop()

    def test_post_no_tenant_assigned(self, auth_client):
        user = _mock_user(tenant_id=None)
        with unauthenticated_client(auth_client):
            patches = _login_patches(user=user)
            for p in patches:
                p.start()
            try:
                with patch("routes.auth._validate_credentials", return_value=(user, False, {})):
                    with patch("routes.auth._resolve_effective_tenant", return_value=None):
                        with patch("routes.auth.render_template", return_value="login"):
                            resp = auth_client.post("/auth/login", data={"username": "u", "password": "p"})
                assert resp.status_code == 200
            finally:
                for p in reversed(patches):
                    p.stop()

    def test_post_branch_tenant_mismatch(self, auth_client):
        user = _mock_user(tenant_id=1)
        branch = _mock_branch(tenant_id=99)
        with unauthenticated_client(auth_client):
            patches = _login_patches(user=user, branch=branch)
            for p in patches:
                p.start()
            try:
                with patch("routes.auth._validate_credentials", return_value=(user, False, {})):
                    with patch("routes.auth.render_template", return_value="login"):
                        resp = auth_client.post("/auth/login", data={"username": "u", "password": "p"})
                assert resp.status_code == 200
            finally:
                for p in reversed(patches):
                    p.stop()

    def test_post_successful_login(self, auth_client):
        user = _mock_user()
        tenant = _mock_tenant()
        branch = _mock_branch()
        with unauthenticated_client(auth_client):
            patches = _login_patches(user=user, tenant=tenant, branch=branch)
            for p in patches:
                p.start()
            try:
                with patch("routes.auth._validate_credentials", return_value=(user, False, {})):
                    with patch("routes.auth._perform_login", return_value=__import__("flask").redirect("/dash")):
                        resp = auth_client.post("/auth/login", data={"username": "u", "password": "p", "remember_me": "on"})
                assert resp.status_code == 302
            finally:
                for p in reversed(patches):
                    p.stop()

    def test_post_invalid_access_mode_defaults_users(self, auth_client):
        with unauthenticated_client(auth_client):
            with patch("extensions.limiter.limit", return_value=lambda f: f):
                with patch("routes.auth.render_template", return_value="login") as render:
                    auth_client.post(
                        "/auth/login",
                        data={"username": "", "password": "", "access_mode": "hacker"},
                    )
        assert render.call_args.kwargs["access_mode"] == "users"

    def test_post_branch_lookup_exception(self, auth_client):
        user = _mock_user(branch_id=1)
        tenant = _mock_tenant()
        branch = _mock_branch(id=1)

        def _session_get(model, pk):
            name = getattr(model, "__name__", str(model))
            if name == "Branch":
                raise RuntimeError("db down")
            if name == "Tenant":
                return tenant if int(pk) == int(tenant.id) else None
            return None

        with unauthenticated_client(auth_client):
            patches = _login_patches(user=user, tenant=tenant, branch=branch)
            for p in patches:
                p.start()
            try:
                with patch("routes.auth.db.session.get", side_effect=_session_get):
                    with patch("routes.auth._validate_credentials", return_value=(user, False, {})):
                        with patch("routes.auth._perform_login", return_value=__import__("flask").redirect("/dash")):
                            resp = auth_client.post("/auth/login", data={"username": "u", "password": "p"})
                assert resp.status_code == 302
            finally:
                for p in reversed(patches):
                    p.stop()

    def test_post_branch_access_denied_clears_branch(self, auth_client):
        user = _mock_user(branch_id=3)
        tenant = _mock_tenant()
        branch = _mock_branch(id=3)
        with unauthenticated_client(auth_client):
            patches = _login_patches(user=user, tenant=tenant, branch=branch)
            for p in patches:
                p.start()
            try:
                with patch("routes.auth._validate_credentials", return_value=(user, False, {})):
                    with patch("routes.auth.user_can_access_branch", return_value=False):
                        with patch("routes.auth._perform_login", return_value=__import__("flask").redirect("/dash")) as perform:
                            resp = auth_client.post("/auth/login", data={"username": "u", "password": "p"})
                assert resp.status_code == 302
                assert perform.call_args[0][3] is None
            finally:
                for p in reversed(patches):
                    p.stop()


class TestPerformLogin:
    def test_perform_login_with_master_and_safe_next(self, auth_app):
        user = _mock_user(role_slug="seller")
        with auth_app.app_context():
            with auth_app.test_request_context("/auth/login?next=/dashboard", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
                patches = [
                    patch("utils.session_security.rotate_session"),
                    patch("routes.auth.login_user"),
                    patch("routes.auth.set_active_tenant"),
                    patch("routes.auth.set_active_branch"),
                    patch("routes.auth.clear_active_branch"),
                    patch("routes.auth.is_global_user", return_value=False),
                    patch("routes.auth.user_can_access_branch", return_value=True),
                    patch("routes.auth.db.session.add"),
                    patch("routes.auth.db.session.commit"),
                    patch("routes.auth.LoggingCore.log_audit"),
                    patch("utils.safe_redirect.is_safe_redirect_url", return_value=True),
                    patch("models.login_history.LoginHistory"),
                    patch("models.security_alert.SecurityAlert"),
                ]
                for p in patches:
                    p.start()
                try:
                    from routes.auth import _perform_login
                    resp = _perform_login(user, True, 1, 1, "users", True, {"method": "seed", "seed_source": "env"})
                    assert resp.status_code == 302
                    assert resp.location.endswith("/dashboard")
                finally:
                    for p in reversed(patches):
                        p.stop()

    def test_perform_login_security_alert_failure_rolls_back(self, auth_app):
        user = _mock_user(role_slug="seller")
        with auth_app.app_context():
            with auth_app.test_request_context(environ_base={"REMOTE_ADDR": "127.0.0.1"}):
                with patch("utils.session_security.rotate_session"):
                    with patch("routes.auth.login_user"):
                        with patch("routes.auth.set_active_tenant"):
                            with patch("routes.auth.clear_active_branch"):
                                with patch("routes.auth.is_global_user", return_value=True):
                                    with patch("routes.auth.user_can_access_branch", return_value=True):
                                        with patch("routes.auth.set_active_branch"):
                                            with patch("routes.auth.db.session.add"):
                                                with patch("routes.auth.db.session.commit", side_effect=[None, RuntimeError("alert fail")]):
                                                    with patch("routes.auth.db.session.rollback") as rollback:
                                                        with patch("routes.auth.LoggingCore.log_audit"):
                                                            with patch("utils.safe_redirect.is_safe_redirect_url", return_value=False):
                                                                with patch("routes.auth.is_global_owner_user", return_value=False):
                                                                    with patch("routes.auth.url_for", return_value="/dashboard"):
                                                                        with patch("models.login_history.LoginHistory"):
                                                                            with patch("models.security_alert.SecurityAlert"):
                                                                                from routes.auth import _perform_login
                                                                                _perform_login(user, False, 1, None, "users", True, {"method": "seed"})
                                                                                rollback.assert_called()


class TestLogoutRoute:
    def test_logout_clears_session(self, auth_client):
        user = _mock_user()
        user.is_authenticated = True
        with patch("flask_login.utils._get_user", return_value=user):
            with patch("routes.auth.logout_user") as logout:
                with patch("routes.auth.clear_active_branch"):
                    with patch("routes.auth.clear_active_tenant"):
                        with patch("routes.auth.LoggingCore.log_audit"):
                            resp = auth_client.get("/auth/logout")
        assert resp.status_code == 302
        logout.assert_called_once()

    def test_logout_anonymous(self, auth_client):
        with unauthenticated_client(auth_client):
            with patch("routes.auth.clear_active_branch"):
                with patch("routes.auth.clear_active_tenant"):
                    resp = auth_client.get("/auth/logout")
        assert resp.status_code == 302


class TestPaymentRoutes:
    def test_payment_status_forbidden_without_token(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            resp = auth_client.get("/auth/payment/status/pay-1")
        assert resp.status_code == 403

    def test_payment_status_success(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth.verify_payment_status_token", return_value=True):
                svc = MagicMock()
                svc.get_payment_status.return_value = {"success": True, "status": "finished"}
                with patch("routes.auth.NOWPaymentsService", return_value=svc):
                    resp = auth_client.get("/auth/payment/status/pay-1?token=ok")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_payment_status_provider_error(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth.verify_payment_status_token", return_value=True):
                svc = MagicMock()
                svc.get_payment_status.return_value = {"success": False, "error": "x"}
                with patch("routes.auth.NOWPaymentsService", return_value=svc):
                    resp = auth_client.get("/auth/payment/status/pay-1?token=ok")
        assert resp.status_code == 400

    def test_payment_status_exception(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth.verify_payment_status_token", return_value=True):
                with patch("routes.auth.NOWPaymentsService", side_effect=RuntimeError("down")):
                    resp = auth_client.get("/auth/payment/status/pay-1?token=ok")
        assert resp.status_code == 500

    def test_payment_callback_ip_denied(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth._is_nowpayments_ip", return_value=False):
                resp = auth_client.post("/auth/payment/callback", json={"payment_id": "1"})
        assert resp.status_code == 403

    def test_payment_callback_missing_signature(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth._is_nowpayments_ip", return_value=True):
                resp = auth_client.post("/auth/payment/callback", json={"payment_id": "1"})
        assert resp.status_code == 400

    def test_payment_callback_invalid_json(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth._is_nowpayments_ip", return_value=True):
                resp = auth_client.post(
                    "/auth/payment/callback",
                    data="not-json",
                    content_type="application/json",
                    headers={"x-nowpayments-sig": "sig"},
                )
        assert resp.status_code == 400

    def test_payment_callback_missing_payment_id(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth._is_nowpayments_ip", return_value=True):
                resp = auth_client.post(
                    "/auth/payment/callback",
                    json={},
                    headers={"x-nowpayments-sig": "sig"},
                )
        assert resp.status_code == 400

    def test_payment_callback_duplicate(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth._is_nowpayments_ip", return_value=True):
                with patch("routes.auth._is_duplicate_callback", return_value=True):
                    resp = auth_client.post(
                        "/auth/payment/callback",
                        json={"payment_id": "1", "payment_status": "finished"},
                        headers={"x-nowpayments-sig": "sig"},
                    )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "already_processed"

    def test_payment_callback_no_ipn_secret(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth._is_nowpayments_ip", return_value=True):
                svc = MagicMock(ipn_secret="")
                with patch("routes.auth.NOWPaymentsService", return_value=svc):
                    resp = auth_client.post(
                        "/auth/payment/callback",
                        json={"payment_id": "1", "payment_status": "waiting"},
                        headers={"x-nowpayments-sig": "sig"},
                    )
        assert resp.status_code == 503

    def test_payment_callback_bad_signature(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth._is_nowpayments_ip", return_value=True):
                svc = MagicMock(ipn_secret="secret")
                svc.verify_ipn.return_value = False
                with patch("routes.auth.NOWPaymentsService", return_value=svc):
                    resp = auth_client.post(
                        "/auth/payment/callback",
                        json={"payment_id": "1", "payment_status": "waiting"},
                        headers={"x-nowpayments-sig": "sig"},
                    )
        assert resp.status_code == 400

    def test_payment_callback_success(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth._is_nowpayments_ip", return_value=True):
                svc = MagicMock(ipn_secret="secret")
                svc.verify_ipn.return_value = True
                svc.process_payment_callback.return_value = True
                with patch("routes.auth.NOWPaymentsService", return_value=svc):
                    resp = auth_client.post(
                        "/auth/payment/callback",
                        json={"payment_id": "1", "payment_status": "waiting"},
                        headers={"x-nowpayments-sig": "sig"},
                    )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "success"

    def test_payment_callback_process_failure(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth._is_nowpayments_ip", return_value=True):
                svc = MagicMock(ipn_secret="secret")
                svc.verify_ipn.return_value = True
                svc.process_payment_callback.return_value = False
                with patch("routes.auth.NOWPaymentsService", return_value=svc):
                    resp = auth_client.post(
                        "/auth/payment/callback",
                        json={"payment_id": "1", "payment_status": "waiting"},
                        headers={"x-nowpayments-sig": "sig"},
                    )
        assert resp.status_code == 500

    def test_payment_callback_exception(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth._is_nowpayments_ip", side_effect=RuntimeError("boom")):
                resp = auth_client.post(
                    "/auth/payment/callback",
                    json={"payment_id": "1"},
                    headers={"x-nowpayments-sig": "sig"},
                )
        assert resp.status_code == 500

    def test_available_currencies_success(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            svc = MagicMock()
            svc.get_available_currencies.return_value = {"success": True, "currencies": ["btc"]}
            with patch("routes.auth.NOWPaymentsService", return_value=svc):
                resp = auth_client.get("/auth/payment/currencies")
        assert resp.status_code == 200

    def test_available_currencies_error(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            svc = MagicMock()
            svc.get_available_currencies.return_value = {"success": False}
            with patch("routes.auth.NOWPaymentsService", return_value=svc):
                resp = auth_client.get("/auth/payment/currencies")
        assert resp.status_code == 400

    def test_available_currencies_exception(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth.NOWPaymentsService", side_effect=RuntimeError("x")):
                resp = auth_client.get("/auth/payment/currencies")
        assert resp.status_code == 500

    def test_estimate_below_minimum(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            resp = auth_client.get("/auth/payment/estimate?amount=0.5")
        assert resp.status_code == 400

    def test_estimate_success(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            svc = MagicMock()
            svc.get_estimated_amount.return_value = {"success": True, "amount": "0.001"}
            with patch("routes.auth.NOWPaymentsService", return_value=svc):
                resp = auth_client.get("/auth/payment/estimate?amount=10&from=usd&to=btc")
        assert resp.status_code == 200

    def test_estimate_provider_error(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            svc = MagicMock()
            svc.get_estimated_amount.return_value = {"success": False}
            with patch("routes.auth.NOWPaymentsService", return_value=svc):
                resp = auth_client.get("/auth/payment/estimate?amount=10")
        assert resp.status_code == 400

    def test_estimate_exception(self, auth_client):
        with patch("extensions.limiter.limit", return_value=lambda f: f):
            with patch("routes.auth.NOWPaymentsService", side_effect=ValueError("bad")):
                resp = auth_client.get("/auth/payment/estimate?amount=10")
        assert resp.status_code == 500


class TestThankYouRoute:
    def test_thank_you_without_payment_id(self, auth_client):
        with patch("routes.auth.render_template", return_value="thanks") as render:
            resp = auth_client.get("/auth/thank-you")
        assert resp.status_code == 200
        assert render.call_args.kwargs["status_polling"] is False

    def test_thank_you_with_valid_token(self, auth_client):
        with patch("routes.auth.verify_payment_status_token", return_value=True):
            with patch("routes.auth.render_template", return_value="thanks") as render:
                resp = auth_client.get("/auth/thank-you?payment_id=pay-1&token=valid")
        assert resp.status_code == 200
        assert render.call_args.kwargs["status_polling"] is True

    def test_thank_you_known_local_redirect(self, auth_client):
        with patch("routes.auth.verify_payment_status_token", return_value=False):
            with patch("routes.auth._payment_id_known_locally", return_value=True):
                with patch("routes.auth.issue_payment_status_token", return_value="fresh-token"):
                    resp = auth_client.get("/auth/thank-you?payment_id=pay-1&token=stale")
        assert resp.status_code == 302
        assert "token=fresh-token" in resp.location

    def test_thank_you_known_local_same_token(self, auth_client):
        with patch("routes.auth.verify_payment_status_token", return_value=False):
            with patch("routes.auth._payment_id_known_locally", return_value=True):
                with patch("routes.auth.issue_payment_status_token", return_value="same"):
                    with patch("routes.auth.render_template", return_value="thanks") as render:
                        resp = auth_client.get("/auth/thank-you?payment_id=pay-1&token=same")
        assert resp.status_code == 200
        assert render.call_args.kwargs["status_polling"] is True
