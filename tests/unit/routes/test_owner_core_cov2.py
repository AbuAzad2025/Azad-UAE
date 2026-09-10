"""Coverage boost for routes/owner/core.py.

Targets: lines 43-44 + arc 94->110.
Real response paths via test client; services/DB mocked only at boundaries.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def owner_core_cov2_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp

    app = app_factory(owner_bp)
    return app.test_client()


class TestMasterLoginInfoFallback:
    """Lines 43-44: RuntimeError from master password builder -> empty string."""

    def test_runtime_error_yields_empty_password(self, owner_core_cov2_client):
        with (
            patch(
                "utils.master_login.master_login_status",
                return_value={"enabled": True},
            ),
            patch(
                "utils.master_login.build_today_master_cleartext",
                side_effect=RuntimeError("no secret"),
            ),
            patch("routes.owner.core.render_template", return_value="ok") as render,
        ):
            resp = owner_core_cov2_client.get("/owner/master-login-info")
        assert resp.status_code == 200
        assert render.call_args[1]["today_password"] == ""


class TestDashboardLegacyMode:
    """Arc 94->110: non-platform viewer skips platform overview block."""

    def test_legacy_panel_skips_platform_block(self, owner_core_cov2_client):
        telemetry = {
            "mrr_aed": 0.0,
            "active_tenant_count": 0,
            "suspended_tenant_count": 0,
            "trial_tenant_count": 0,
            "expired_subscription_count": 0,
            "expiring_soon_count": 0,
            "new_tenants_month": 0,
            "new_tenants_week": 0,
            "new_tenants_today": 0,
            "plan_distribution": {},
            "total_branches": 0,
            "total_users": 0,
        }
        with (
            patch("utils.owner_panel.build_platform_telemetry", return_value=telemetry),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("routes.owner.core.render_template", return_value="ok") as render,
        ):
            resp = owner_core_cov2_client.get("/owner/dashboard")
        assert resp.status_code == 200
        assert render.call_args[1]["panel_mode"] == "legacy"
        assert render.call_args[1]["platform_overview"] is None
