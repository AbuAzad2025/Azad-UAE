from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import app_factory, bypass_admin_auth, mock_user, unauthenticated_client


@pytest.fixture
def tenants_client(app_factory, bypass_admin_auth):
    from routes.tenants import tenants_bp
    app = app_factory(tenants_bp)
    return app.test_client()


def _active_tenant(tid=2, name='Acme', name_ar='أكمي'):
    tenant = MagicMock()
    tenant.id = tid
    tenant.name = name
    tenant.name_ar = name_ar
    tenant.is_active = True
    tenant.is_suspended = False
    return tenant


class TestTenantsAuth:
    def test_switch_requires_login(self, tenants_client):
        with unauthenticated_client(tenants_client):
            resp = tenants_client.get('/tenants/switch/1')
        assert resp.status_code == 401

    def test_switch_forbidden_for_regular_user(self, tenants_client):
        with patch('routes.tenants.is_global_tenant_user', return_value=False):
            resp = tenants_client.get('/tenants/switch/1')
        assert resp.status_code == 403


class TestTenantsSwitch:
    def test_switch_clear_tenant(self, tenants_client, bypass_admin_auth):
        with patch('routes.tenants.is_global_tenant_user', return_value=True), \
             patch('routes.tenants.set_active_tenant') as set_tenant, \
             patch('routes.tenants.clear_active_branch') as clear_branch, \
             patch('routes.tenants.safe_redirect_target', return_value='/dashboard'):
            resp = tenants_client.get('/tenants/switch/0')
        assert resp.status_code == 302
        set_tenant.assert_called_once_with(None, user=bypass_admin_auth)
        clear_branch.assert_called_once()

    def test_switch_to_active_tenant(self, tenants_client, bypass_admin_auth):
        tenant = _active_tenant()
        session = MagicMock()
        with patch('routes.tenants.is_global_tenant_user', return_value=True), \
             patch('routes.tenants.db.session', session), \
             patch('routes.tenants.set_active_tenant') as set_tenant, \
             patch('routes.tenants.clear_active_branch'), \
             patch('routes.tenants.safe_redirect_target', return_value='/dashboard'):
            session.get.return_value = tenant
            resp = tenants_client.get('/tenants/switch/2')
        assert resp.status_code == 302
        set_tenant.assert_called_once_with(2, user=bypass_admin_auth)

    def test_switch_missing_tenant(self, tenants_client):
        session = MagicMock()
        with patch('routes.tenants.is_global_tenant_user', return_value=True), \
             patch('routes.tenants.db.session', session), \
             patch('routes.tenants.safe_redirect_target', return_value='/dashboard'):
            session.get.return_value = None
            resp = tenants_client.get('/tenants/switch/99')
        assert resp.status_code == 302

    def test_switch_inactive_tenant(self, tenants_client):
        tenant = _active_tenant()
        tenant.is_active = False
        session = MagicMock()
        with patch('routes.tenants.is_global_tenant_user', return_value=True), \
             patch('routes.tenants.db.session', session), \
             patch('routes.tenants.safe_redirect_target', return_value='/dashboard'):
            session.get.return_value = tenant
            resp = tenants_client.get('/tenants/switch/2')
        assert resp.status_code == 302

    def test_switch_suspended_tenant(self, tenants_client):
        tenant = _active_tenant()
        tenant.is_suspended = True
        session = MagicMock()
        with patch('routes.tenants.is_global_tenant_user', return_value=True), \
             patch('routes.tenants.db.session', session), \
             patch('routes.tenants.safe_redirect_target', return_value='/dashboard'):
            session.get.return_value = tenant
            resp = tenants_client.get('/tenants/switch/2')
        assert resp.status_code == 302

    def test_switch_post_method(self, tenants_client, bypass_admin_auth):
        tenant = _active_tenant()
        session = MagicMock()
        with patch('routes.tenants.is_global_tenant_user', return_value=True), \
             patch('routes.tenants.db.session', session), \
             patch('routes.tenants.set_active_tenant'), \
             patch('routes.tenants.clear_active_branch'), \
             patch('routes.tenants.safe_redirect_target', return_value='/dashboard'):
            session.get.return_value = tenant
            resp = tenants_client.post('/tenants/switch/2')
        assert resp.status_code == 302
