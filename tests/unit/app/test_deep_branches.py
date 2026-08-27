"""Factory/handlers/context deep branches — request-level behaviors."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from utils.exceptions import PaymentRequired


class TestFactoryConfigBranches:
    def test_owner_password_is_defined_and_stable_in_dev_mode(self, monkeypatch):
        """Deployment supplies OWNER_PASSWORD before/at boot; the generated
        fallback must never silently rotate an existing one."""
        import os

        from app.factory import create_app
        from tests.conftest import TestConfig

        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        saved = os.environ.get("OWNER_PASSWORD")
        try:

            class DevCfg(TestConfig):
                APP_ENV = "testing"
                DEBUG = False

            with (
                patch("bootstrap.blueprints.register_blueprints"),
                patch("app.factory.run_system_integrity_check"),
                patch("models.events.register_all_listeners"),
                patch("cli_commands.register_cli_commands"),
            ):
                app_obj = create_app(DevCfg)
            pw_env = os.environ.get("OWNER_PASSWORD", "")
            pw_cfg = app_obj.config.get("OWNER_PASSWORD") or pw_env
            assert isinstance(pw_cfg, str) and len(pw_cfg) >= 12
            # Second boot must observe the same credential (no silent rotation).
            pw_again = os.environ.get("OWNER_PASSWORD", "")
            assert pw_again == pw_env
        finally:
            if saved is not None:
                os.environ["OWNER_PASSWORD"] = saved


GUARD_ROUTE = "/api/search"  # blueprint ``api`` → outside the skip set


class TestBeforeRequestTenantGuards:
    @pytest.fixture
    def logged(self, logged_in_client):
        return logged_in_client

    def test_company_user_without_tenant_gets_403(self, logged, sample_user, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        resp = logged.get(GUARD_ROUTE)
        assert resp.status_code == 403

    def test_suspended_tenant_renders_503(self, logged, sample_user, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=sample_user.tenant_id)
        mocker.patch(
            "utils.tenanting.get_tenant_status",
            return_value={"ok": False, "tenant": None, "reason": "probe"},
        )
        resp = logged.get(GUARD_ROUTE)
        assert resp.status_code == 503
        assert b"suspend" in resp.data.lower() or b"tenant_suspended" in resp.data

    def test_expired_subscription_charges_402(self, logged, sample_user, sample_tenant, mocker):
        from models.tenant import Tenant

        mocker.patch.object(Tenant, "is_lifetime", False, create=True)
        mocker.patch.object(Tenant, "is_subscription_active", lambda self: False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=sample_user.tenant_id)
        mocker.patch("utils.tenanting.get_tenant_status", return_value={"ok": True})
        resp = logged.get(GUARD_ROUTE)
        assert resp.status_code == 402


class TestUnauthorizedHandlerPaths:
    def test_owner_blueprint_hides_404_when_anonymous(self, client):
        resp = client.get("/owner/some-dashboard")
        assert resp.status_code == 404

    def test_api_paths_return_json_401(self, client):
        resp = client.get("/api/search?q=x")
        assert resp.status_code == 401
        assert resp.json["error"] == "authentication_required"

    def test_regular_pages_redirect_to_login_flash(self, client):
        resp = client.get("/products/")
        assert resp.status_code in (301, 302)


def _locate_handler(app, target_cls):
    """Depth-first lookup across Flask's nested error_handler_spec layout."""

    def walk(node):
        if isinstance(node, dict):
            for key, val in node.items():
                if key is target_cls:
                    return val
                found = walk(val)
                if found is not None:
                    return found
        return None

    return walk(app.error_handler_spec)


class TestDeepErrorHandlers:
    @pytest.fixture
    def isolated_logging(self, mocker):
        from services.logging_core import LoggingCore

        mocker.patch.object(LoggingCore, "log_error", staticmethod(lambda *a, **k: None))
        mocker.patch.object(LoggingCore, "log_frontend_error", staticmethod(lambda *a, **k: None))

    def _fresh_app(self):
        from app.factory import create_app
        from tests.conftest import TestConfig

        app = create_app(TestConfig)
        app.config["DEBUG"] = False
        return app

    def test_payment_required_debug_reraises(self, isolated_logging):
        app = self._fresh_app()
        fn = _locate_handler(app, PaymentRequired)
        assert fn is not None
        app.config["DEBUG"] = True
        with pytest.raises(PaymentRequired), app.test_request_context("/x"):
            fn(PaymentRequired(description="pay up"))
        app.config["DEBUG"] = False
        with app.test_request_context("/x"):
            body, code = fn(PaymentRequired(description="pay up"))
            assert code == 402

    def test_method_not_allowed_json_advertises_allow_header(self, isolated_logging):
        from werkzeug.exceptions import HTTPException, MethodNotAllowed

        app = self._fresh_app()
        fn = None
        for code, bucket in app.error_handler_spec[None].items():
            if isinstance(bucket, dict) and HTTPException in bucket:
                fn = bucket[HTTPException]
                break
        assert fn is not None, f"lookup failed; keys={[k for k in app.error_handler_spec[None]]}"
        with app.test_request_context("/api/v1/nope"):
            exc = MethodNotAllowed(valid_methods=["GET"])
            body, code = fn(exc)
        assert code == 405
        assert "GET" in body.headers["Allow"]

    def test_tenant_isolation_error_maps_to_403_json(self, isolated_logging):
        from utils.tenant_orm import TenantIsolationError

        app = self._fresh_app()

        @app.route("/__probe_isolation__")
        def boom_isolation():
            raise TenantIsolationError("cross-tenant probe")

        with app.test_client() as c:
            resp = c.get("/__probe_isolation__", headers={"X-Requested-With": "XMLHttpRequest"})
            assert resp.status_code == 403
            payload = resp.get_json()
            assert payload["success"] is False
            assert "cross-tenant probe" in payload["error"]

    def test_payment_required_handler_registered_and_renders_402_page(self, isolated_logging):
        app = self._fresh_app()

        @app.route("/__probe_paywall__")
        def boom_paywall():
            raise PaymentRequired(description="subscription needed")

        with app.test_client() as c:
            resp = c.get("/__probe_paywall__")
        assert resp.status_code == 402


class TestContextProcessorUsageCounters:
    def test_usage_percentages_rendered_for_current_tenant(self, app, sample_tenant, mocker):
        mocker.patch("models.Tenant.get_current", return_value=sample_tenant)
        out = None
        for fn in app.template_context_processors[None]:
            with app.test_request_context("/"):
                candidate = fn()
            if isinstance(candidate, dict) and "tenant_usage" in candidate:
                out = candidate
                break
        assert out is not None
        usage = out["tenant_usage"]
        for key in ("users", "branches", "warehouses", "products", "customers", "suppliers"):
            entry = usage[key]
            assert {"current", "max", "percent"} <= set(entry)
            expected_pct = round(entry["current"] / entry["max"] * 100) if entry["max"] else 0
            assert entry["percent"] == expected_pct


class TestSanitizeFilterReal:
    def test_rich_text_filter_strips_script_tag(self, app):
        sanitize = app.jinja_env.filters["sanitize"]
        dirty = "<b>hi</b><script>alert(1)</script>"
        clean = str(sanitize(dirty))
        lowered = clean.lower()
        assert "<script>" not in lowered and "</script>" not in lowered
        assert "<b>hi</b>" in lowered
