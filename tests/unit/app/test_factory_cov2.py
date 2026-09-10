"""Coverage supplement for app/factory.py residual lines/arcs."""

from __future__ import annotations

import builtins
import sys
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.app.test_factory import _minimal_app


class TestProductionArcCov2:
    def test_production_skips_dev_password_generation(self, monkeypatch):
        """Targets app/factory.py arc 60->69 (production skips OWNER_PASSWORD gen)."""
        import os

        from tests.conftest import TestConfig

        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        monkeypatch.delenv("OWNER_PASSWORD", raising=False)

        class ProdCov2Config(TestConfig):
            DEBUG = False
            APP_ENV = "production"

        # create_app() reloads .env via config._init_env(); block it so the
        # deleted OWNER_PASSWORD stays deleted and the skip is observable.
        with _minimal_app(
            [
                patch("app.factory.assert_production_sanity"),
                patch("config._init_env"),
            ],
            config_class=ProdCov2Config,
        ):
            assert os.environ.get("OWNER_PASSWORD") in (None, "")


class TestMaintenanceImportFallbackCov2:
    def test_maintenance_import_error(self, monkeypatch):
        """Targets app/factory.py lines 106-107 and 117 (ImportError fallback)."""
        monkeypatch.delenv("SKIP_SYSTEM_INTEGRITY", raising=False)
        real_import = builtins.__import__

        def _blocked(name, globals_dict=None, locals_dict=None, fromlist=(), level=0):
            if name == "services.maintenance_service":
                raise ImportError("blocked for cov2 test")
            return real_import(name, globals_dict, locals_dict, fromlist, level)

        with patch("builtins.__import__", side_effect=_blocked):
            sys.modules.pop("services.maintenance_service", None)
            try:
                with _minimal_app():
                    pass
            finally:
                sys.modules.pop("services.maintenance_service", None)


class TestMaintenanceActionNeededCov2:
    def test_maintenance_action_needed(self, monkeypatch):
        """Targets app/factory.py line 113 (action_needed True branch)."""
        monkeypatch.delenv("SKIP_SYSTEM_INTEGRITY", raising=False)
        with _minimal_app(
            [
                patch(
                    "services.maintenance_service.run_default_tenant_maintenance_api",
                    return_value={"action_needed": True, "detail": "cov2"},
                )
            ]
        ):
            pass


class TestDemoTenantGuardCov2:
    def test_demo_tenant_payment_vault_blueprint_aborts_404(self, monkeypatch):
        """Targets app/factory.py line 253 (demo tenant blocked from vault).

        The guard at lines 245-253 sits inside the ``_bp not in _skip``
        block, so only a non-skipped blueprint in ("owner", "payment_vault")
        — i.e. ``payment_vault`` — can reach the abort.
        """
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        demo_tenant = MagicMock()
        user = MagicMock(is_authenticated=True)
        extras = [
            patch("app.factory.LoggingCore.set_trace_id"),
            patch("utils.i18n.get_current_language", return_value="ar"),
            patch("utils.i18n.is_rtl", return_value=True),
            patch("flask_login.current_user", user),
            patch("utils.tenanting.get_active_tenant_id", return_value=7),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.tenanting.get_tenant_status", return_value={"ok": True}),
            patch("app.factory.db.session.get", return_value=demo_tenant),
            patch(
                "services.saas_provisioning_service.SaaSProvisioningService.is_demo_tenant",
                return_value=True,
            ),
        ]
        with _minimal_app(extras) as app:
            from flask import Blueprint

            owner_bp = Blueprint("payment_vault", __name__, url_prefix="/payment_vault")

            @owner_bp.route("/dash")
            def cov2_owner_dash():
                return "ok"

            app.register_blueprint(owner_bp)
            with app.test_request_context("/payment_vault/dash"):
                for func in app.before_request_funcs[None]:
                    if func.__name__ == "before_request":
                        with pytest.raises(NotFound):
                            func()
                        return
                raise AssertionError("before_request hook not found")
