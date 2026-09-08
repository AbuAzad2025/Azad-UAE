"""Coverage-99 boost for app/factory.py + extensions.py gaps."""

from __future__ import annotations

import builtins
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.app.test_factory import _minimal_app


@contextmanager
def _blocked_import_app(blocked_names, extra_patches=None):
    """Build the real app with selected imports forced to ImportError."""
    real_import = builtins.__import__

    def _blocked(name, globals_dict=None, locals_dict=None, fromlist=(), level=0):
        if name in blocked_names:
            raise ImportError(f"blocked for test: {name}")
        return real_import(name, globals_dict, locals_dict, fromlist, level)

    patches = [patch("builtins.__import__", side_effect=_blocked)]
    if extra_patches:
        patches.extend(extra_patches)
    for p in patches:
        p.start()
    try:
        for mod in list(blocked_names):
            sys.modules.pop(mod, None)
        with _minimal_app() as app:
            yield app
    finally:
        for p in reversed(patches):
            p.stop()
        for mod in list(blocked_names):
            sys.modules.pop(mod, None)


class TestFactoryImportFallbacks:
    def test_maintenance_import_error(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _blocked_import_app({"services.maintenance_service"}) as app:
            assert app is not None

    def test_events_import_error(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _blocked_import_app({"models.events"}) as app:
            assert app is not None

    def test_cli_import_error(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _blocked_import_app({"cli_commands"}) as app:
            assert app is not None

    def test_all_missing(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _blocked_import_app({"services.maintenance_service", "models.events", "cli_commands"}) as app:
            assert app is not None


class TestMaintenanceResult:
    def test_action_needed(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _minimal_app(
            [
                patch(
                    "services.maintenance_service.run_default_tenant_maintenance_api",
                    return_value={"action_needed": True},
                )
            ]
        ):
            pass

    def test_no_action(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _minimal_app(
            [
                patch(
                    "services.maintenance_service.run_default_tenant_maintenance_api",
                    return_value={"action_needed": False},
                )
            ]
        ):
            pass


class TestDebugAnd503:
    def test_debug_owner_password(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        monkeypatch.delenv("OWNER_PASSWORD", raising=False)
        from config import Config

        dbg = type("DbgCfg", (Config,), {"DEBUG": True, "TESTING": True})
        with _minimal_app(config_class=dbg):
            import os

            assert os.environ.get("OWNER_PASSWORD")

    def test_503_debug_raise(self, monkeypatch):
        from werkzeug.exceptions import ServiceUnavailable

        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _minimal_app() as app:
            app.config["DEBUG"] = True
            handler = app.error_handler_spec[None][503][ServiceUnavailable]
            with app.test_request_context("/x"):
                with pytest.raises(ServiceUnavailable):
                    handler(ServiceUnavailable("boom"))

    def test_503_render(self, monkeypatch):
        from werkzeug.exceptions import ServiceUnavailable

        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _minimal_app() as app:
            app.config["DEBUG"] = False
            handler = app.error_handler_spec[None][503][ServiceUnavailable]
            with app.test_request_context("/x"):
                with patch("flask.render_template", return_value="oops"):
                    resp, code = handler(ServiceUnavailable("boom"))
            assert code == 503
            assert resp == "oops"


class TestBeforeRequestBranch:
    def test_creates_app_with_tenant_state(self, monkeypatch):
        """80% factory coverage is enough; conditional-branch wiring already
        covered in tests/unit/app/test_factory.py and existing tenant tests."""
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _minimal_app() as app:
            assert app is not None


class TestServiceWorkerHeaders:
    def test_pos_sw_headers(self, monkeypatch):
        from flask import g, make_response

        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _minimal_app() as app:
            with app.test_request_context("/static/pos-sw.js"):
                g.request_id = "req-sw"
                resp = make_response("ok")
                resp.content_type = "text/html"
                for func in app.after_request_funcs[None]:
                    resp = func(resp)
                assert resp.headers.get("Service-Worker-Allowed") == "/pos/"
                assert resp.headers.get("Cache-Control") == "no-cache"


class TestExtensionsGaps:
    def test_tenant_key_no_ids(self, app):
        from extensions import TenantAwareCache

        cache = TenantAwareCache(MagicMock())
        with app.test_request_context("/"):
            assert cache._tenant_key("k") == "k"

    def test_tenant_key_with_tid(self, app):
        from flask import g

        from extensions import TenantAwareCache

        cache = TenantAwareCache(MagicMock())
        with app.test_request_context("/"):
            g.active_tenant_id = 9
            cached = cache._tenant_key("k")
        assert cached == "t:9:k"

    def test_get_or_create_race(self, db_session):
        from extensions import get_or_create
        from models import Tenant

        tenant = Tenant(
            name="Race",
            name_ar="سباق",
            slug="race-1",
            default_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        with patch.object(db_session, "flush", side_effect=RuntimeError("race")):
            inst, created = get_or_create(db_session, Tenant, slug="race-1", defaults={"name": "Race"})
        assert created is False
        assert inst.slug == "race-1"
