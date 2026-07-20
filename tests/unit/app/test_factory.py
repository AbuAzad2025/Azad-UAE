from __future__ import annotations

import builtins
import importlib
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import Forbidden


@contextmanager
def _minimal_app(extra_patches=None, config_class=None):
    patches = [
        patch("bootstrap.blueprints.register_blueprints"),
        patch("app.factory.register_error_handlers"),
        patch("app.factory.register_context_processors"),
        patch("app.factory.LoggingCore.setup"),
        patch("app.factory.LoggingCore.schedule_cleanup"),
        patch("app.factory.run_system_integrity_check"),
        patch("models.events.register_all_listeners", side_effect=ImportError),
        patch("cli_commands.register_cli_commands", side_effect=ImportError),
    ]
    if extra_patches:
        patches.extend(extra_patches)
    for p in patches:
        p.start()
    try:
        from app.factory import create_app
        from config import Config

        yield create_app(config_class or Config)
    finally:
        for p in reversed(patches):
            p.stop()


class TestFactoryRoutes:
    def test_favicon_route(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _minimal_app([patch("app.factory.send_from_directory", return_value="ico")]) as app:
            with app.test_client() as client:
                resp = client.get("/favicon.ico")
            assert resp.status_code == 200

    def test_chrome_devtools_metadata(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _minimal_app() as app:
            with app.test_client() as client:
                resp = client.get("/.well-known/appspecific/com.chrome.devtools.json")
            assert resp.status_code == 204

    def test_storefront_redirect_skips_admin_paths(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _minimal_app() as app:
            with app.test_request_context("/admin/dashboard"):
                for func in app.before_request_funcs[None]:
                    assert func() is None

    def test_security_headers_on_response(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        from flask import make_response, g

        with _minimal_app() as app:
            with app.test_request_context("/"):
                g.request_id = "req-1"
                resp = make_response("ok")
                resp.content_type = "text/html"
                for func in app.after_request_funcs[None]:
                    resp = func(resp)
                assert resp.headers.get("X-Content-Type-Options") == "nosniff"
                assert resp.headers.get("X-Request-Id") == "req-1"

    def test_is_migration_command(self):
        from app.integrity import _is_migration_command
        import sys

        with patch.object(sys, "argv", ["flask", "db", "upgrade"]):
            assert _is_migration_command() is True

    def test_unauthorized_owner_path_aborts_404(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        from werkzeug.exceptions import NotFound

        with _minimal_app() as app:
            handler = app.login_manager.unauthorized_callback
            with app.test_request_context("/owner/dashboard"):
                with pytest.raises(NotFound):
                    handler()

    def test_storefront_custom_domain_redirect(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        store = MagicMock(store_slug="shop-1")
        extras = [
            patch(
                "services.store_service.StoreService.get_store_by_host",
                return_value=store,
            ),
            patch(
                "services.store_service.StoreService.is_store_publicly_available",
                return_value=True,
            ),
            patch("flask.url_for", return_value="/s/shop-1"),
        ]
        with _minimal_app(extras) as app:
            with app.test_request_context("/catalog"):
                for func in app.before_request_funcs[None]:
                    if func.__name__ == "storefront_custom_domain_redirect":
                        resp = func()
                        assert resp is not None

    def test_cli_commands_registration_warning(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _minimal_app(
            [
                patch(
                    "cli_commands.register_cli_commands",
                    side_effect=RuntimeError("cli broken"),
                )
            ]
        ) as app:
            assert app is not None

    def test_production_hsts_header(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        from flask import make_response, g

        with _minimal_app() as app:
            app.config["APP_ENV"] = "production"
            app.debug = False
            with app.test_request_context("/"):
                g.request_id = "req-2"
                resp = make_response("ok")
                resp.content_type = "text/html"
                for func in app.after_request_funcs[None]:
                    resp = func(resp)
                assert "Strict-Transport-Security" in resp.headers

    def test_load_user_returns_user(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        user = MagicMock()
        with _minimal_app([patch("app.factory.db.session.get", return_value=user)]) as app:
            loader = app.login_manager._user_callback
            assert loader("7") is user

    def test_unauthorized_non_owner_redirects_to_login(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        extras = [
            patch("app.factory.url_for", return_value="/auth/login"),
            patch("app.factory.flash"),
        ]
        with _minimal_app(extras) as app:
            handler = app.login_manager.unauthorized_callback
            with app.test_request_context("/dashboard"):
                resp = handler()
            assert resp.status_code == 302

    def test_storefront_no_redirect_when_store_unavailable(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        store = MagicMock(store_slug="shop-1")
        extras = [
            patch(
                "services.store_service.StoreService.get_store_by_host",
                return_value=store,
            ),
            patch(
                "services.store_service.StoreService.is_store_publicly_available",
                return_value=False,
            ),
        ]
        with _minimal_app(extras) as app:
            with app.test_request_context("/catalog"):
                for func in app.before_request_funcs[None]:
                    if func.__name__ == "storefront_custom_domain_redirect":
                        assert func() is None

    def test_before_request_tenant_suspended(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        user = MagicMock(is_authenticated=True)
        extras = [
            patch("app.factory.LoggingCore.set_trace_id"),
            patch("utils.i18n.get_current_language", return_value="ar"),
            patch("utils.i18n.is_rtl", return_value=True),
            patch("flask_login.current_user", user),
            patch("utils.tenanting.get_active_tenant_id", return_value=1),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch(
                "utils.tenanting.get_tenant_status",
                return_value={
                    "ok": False,
                    "tenant": MagicMock(),
                    "reason": "suspended",
                },
            ),
            patch("flask.render_template", return_value="suspended"),
        ]
        with _minimal_app(extras) as app:
            from flask import Blueprint

            sales_bp = Blueprint("sales", __name__, url_prefix="/sales")

            @sales_bp.route("/")
            def sales_index():
                return "ok"

            app.register_blueprint(sales_bp)
            with app.test_request_context("/sales/"):
                for func in app.before_request_funcs[None]:
                    if func.__name__ == "before_request":
                        resp = func()
                        assert resp is not None
                        assert resp[1] == 503

    def test_compress_import_unavailable(self, monkeypatch):
        mod_name = "app.factory"
        saved = sys.modules.pop(mod_name, None)
        try:
            real_import = builtins.__import__

            def blocked(name, globals_dict=None, locals_dict=None, fromlist=(), level=0):
                if name == "flask_compress":
                    raise ImportError("blocked for test")
                return real_import(name, globals_dict, locals_dict, fromlist, level)

            with patch("builtins.__import__", side_effect=blocked):
                mod = importlib.import_module(mod_name)
            assert mod.COMPRESS_AVAILABLE is False
        finally:
            if saved is not None:
                sys.modules[mod_name] = saved
            else:
                sys.modules.pop(mod_name, None)
            importlib.import_module(mod_name)

    def test_dev_mode_auto_generates_owner_password(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        monkeypatch.delenv("OWNER_PASSWORD", raising=False)
        with patch("config.load_dotenv"), _minimal_app() as app:
            pwd = app.config.get("OWNER_PASSWORD")
            assert pwd
            assert pwd == __import__("os").environ.get("OWNER_PASSWORD")

    def test_before_request_aborts_without_tenant(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        user = MagicMock(is_authenticated=True)
        extras = [
            patch("app.factory.LoggingCore.set_trace_id"),
            patch("utils.i18n.get_current_language", return_value="ar"),
            patch("utils.i18n.is_rtl", return_value=True),
            patch("flask_login.current_user", user),
            patch("utils.tenanting.get_active_tenant_id", return_value=None),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
        ]
        with _minimal_app(extras) as app:
            from flask import Blueprint

            sales_bp = Blueprint("sales", __name__, url_prefix="/sales")

            @sales_bp.route("/")
            def sales_index():
                return "ok"

            app.register_blueprint(sales_bp)
            with app.test_request_context("/sales/"):
                for func in app.before_request_funcs[None]:
                    if func.__name__ == "before_request":
                        with pytest.raises(Forbidden):
                            func()
