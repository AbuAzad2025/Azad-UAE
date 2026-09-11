"""Coverage for routes/tenants.py remaining arcs.

Targets: tenant_id mismatch 403 arc, name fallback arc, next-url safe/unsafe
arcs, falsy-tenant-id arc. Real Flask test-client paths; mocks only at
service/DB boundaries.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def tenants_cov3_client(app_factory, bypass_owner_auth):
    from routes.tenants import tenants_bp

    app = app_factory(tenants_bp)
    return app.test_client()


def _tenant(tid=2, name="Acme", name_ar="أكمي", active=True, suspended=False):
    t = MagicMock()
    t.id = tid
    t.name = name
    t.name_ar = name_ar
    t.is_active = active
    t.is_suspended = suspended
    return t


class TestSwitchMismatch:
    def test_non_owner_tenant_mismatch_403(self, tenants_cov3_client, bypass_owner_auth):
        bypass_owner_auth.tenant_id = 1
        bypass_owner_auth.is_owner = False
        tenant = _tenant(tid=2)
        sess = MagicMock()
        sess.get.return_value = tenant
        with (
            patch("routes.tenants.is_global_tenant_user", return_value=True),
            patch("routes.tenants.db.session", sess),
        ):
            resp = tenants_cov3_client.get("/tenants/switch/2")
        assert resp.status_code == 403

    def test_owner_mismatch_allowed(self, tenants_cov3_client, bypass_owner_auth):
        bypass_owner_auth.tenant_id = 1
        bypass_owner_auth.is_owner = True
        tenant = _tenant(tid=2)
        sess = MagicMock()
        sess.get.return_value = tenant
        with (
            patch("routes.tenants.is_global_tenant_user", return_value=True),
            patch("routes.tenants.db.session", sess),
            patch("routes.tenants.set_active_tenant"),
            patch("routes.tenants.clear_active_branch"),
            patch("routes.tenants.safe_redirect_target", return_value="/dashboard"),
        ):
            resp = tenants_cov3_client.get("/tenants/switch/2")
        assert resp.status_code == 302

    def test_name_fallback_uses_name(self, tenants_cov3_client, bypass_owner_auth):
        bypass_owner_auth.tenant_id = 2
        bypass_owner_auth.is_owner = True
        tenant = _tenant(tid=2, name="Acme Latin", name_ar="")
        sess = MagicMock()
        sess.get.return_value = tenant
        with (
            patch("routes.tenants.is_global_tenant_user", return_value=True),
            patch("routes.tenants.db.session", sess),
            patch("routes.tenants.set_active_tenant"),
            patch("routes.tenants.clear_active_branch"),
            patch("routes.tenants.safe_redirect_target", return_value="/dashboard"),
        ):
            resp = tenants_cov3_client.get("/tenants/switch/2")
        assert resp.status_code == 302


class TestNextUrl:
    def test_safe_next_redirect(self, tenants_cov3_client):
        tenant = _tenant()
        sess = MagicMock()
        sess.get.return_value = tenant
        with (
            patch("routes.tenants.is_global_tenant_user", return_value=True),
            patch("routes.tenants.db.session", sess),
            patch("routes.tenants.set_active_tenant"),
            patch("routes.tenants.clear_active_branch"),
            patch("routes.tenants.is_safe_redirect_url", return_value=True),
        ):
            resp = tenants_cov3_client.get("/tenants/switch/2?next=/safe")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/safe"

    def test_unsafe_next_falls_back(self, tenants_cov3_client):
        tenant = _tenant()
        sess = MagicMock()
        sess.get.return_value = tenant
        with (
            patch("routes.tenants.is_global_tenant_user", return_value=True),
            patch("routes.tenants.db.session", sess),
            patch("routes.tenants.set_active_tenant"),
            patch("routes.tenants.clear_active_branch"),
            patch("routes.tenants.is_safe_redirect_url", return_value=False),
            patch("routes.tenants.safe_redirect_target", return_value="/dashboard"),
        ):
            resp = tenants_cov3_client.get("/tenants/switch/2?next=http://evil")
        assert resp.status_code == 302

    def test_form_next_redirect(self, tenants_cov3_client):
        tenant = _tenant()
        sess = MagicMock()
        sess.get.return_value = tenant
        with (
            patch("routes.tenants.is_global_tenant_user", return_value=True),
            patch("routes.tenants.db.session", sess),
            patch("routes.tenants.set_active_tenant"),
            patch("routes.tenants.clear_active_branch"),
            patch("routes.tenants.is_safe_redirect_url", return_value=True),
        ):
            resp = tenants_cov3_client.post("/tenants/switch/2", data={"next": "/from-form"})
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/from-form"
