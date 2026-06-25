from __future__ import annotations

from contextlib import ExitStack, contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query, app_factory, bypass_permission_auth, mock_user, unauthenticated_client


@contextmanager
def _main_patches(**kwargs):
    with ExitStack() as stack:
        stack.enter_context(patch('routes.main.render_template', return_value='ok'))
        stack.enter_context(patch('routes.main.get_active_tenant_id', return_value=1))
        stack.enter_context(patch('routes.main.branch_scope_id', return_value=kwargs.get('branch_scope')))
        stack.enter_context(patch('utils.tenanting.tenant_query', return_value=_chain_query(count=5)))
        stack.enter_context(patch('routes.main.get_visible_products_query', return_value=_chain_query(count=10)))
        stack.enter_context(patch('routes.main.StockService.get_low_stock_products', return_value=kwargs.get('low_stock', [])))
        stack.enter_context(patch('routes.main.StockService.get_out_of_stock_products', return_value=kwargs.get('out_of_stock', [])))
        stack.enter_context(patch('routes.main.db.session'))
        stack.enter_context(patch('extensions.db.session'))
        yield


@pytest.fixture
def main_client(app_factory, bypass_permission_auth):
    from routes.main import main_bp
    app = app_factory(main_bp)
    return app.test_client()


def _scalar_query_result(value):
    q = MagicMock()
    q.filter.return_value = q
    q.join.return_value = q
    q.first.return_value = value
    q.scalar.return_value = value
    q.all.return_value = value if isinstance(value, list) else []
    q.order_by.return_value.limit.return_value.all.return_value = value if isinstance(value, list) else []
    return q


class TestMainRedirect:
    def test_app_redirects_to_dashboard(self, main_client):
        resp = main_client.get('/app', follow_redirects=False)
        assert resp.status_code == 302
        assert 'dashboard' in resp.headers['Location']


def _dashboard_query_side_effect(can_profit=False):
    calls = {'n': 0}

    def _query(*args, **kwargs):
        calls['n'] += 1
        q = MagicMock()
        q.filter.return_value = q
        q.join.return_value = q
        q.select_from.return_value = q
        if can_profit and calls['n'] == 3:
            q.scalar.return_value = Decimal('75')
        elif calls['n'] in (1, 2) or (can_profit and calls['n'] > 4 and calls['n'] % 2 == 1):
            q.first.return_value = (2, Decimal('500'))
        else:
            q.scalar.return_value = Decimal('250')
        q.all.return_value = []
        return q

    return _query


class TestMainDashboard:
    def test_dashboard_renders(self, main_client, bypass_permission_auth):
        bypass_permission_auth.can_see_costs.return_value = False
        with _main_patches(), \
             patch('routes.main.db.session.query', side_effect=_dashboard_query_side_effect()), \
             patch('routes.main.Sale.query', _scalar_query_result([])):
            resp = main_client.get('/dashboard')
        assert resp.status_code == 200

    def test_dashboard_low_stock_error(self, main_client):
        with _main_patches(), \
             patch('routes.main.StockService.get_low_stock_products', side_effect=RuntimeError('stock fail')), \
             patch('routes.main.db.session.query', side_effect=_dashboard_query_side_effect()), \
             patch('routes.main.Sale.query', _scalar_query_result([])):
            resp = main_client.get('/dashboard')
        assert resp.status_code == 200

    def test_dashboard_seller_stats(self, main_client, bypass_permission_auth):
        bypass_permission_auth.is_seller.return_value = True
        with _main_patches(), \
             patch('routes.main.db.session.query', side_effect=_dashboard_query_side_effect()), \
             patch('routes.main.Sale.query', _scalar_query_result([])):
            resp = main_client.get('/dashboard')
        assert resp.status_code == 200

    def test_dashboard_liquidity_section(self, main_client, bypass_permission_auth):
        bypass_permission_auth.can_see_costs.return_value = True
        account = MagicMock(id=7)
        inv_account = MagicMock(id=8)
        with _main_patches(), \
             patch('routes.main.db.session.query', side_effect=_dashboard_query_side_effect(can_profit=True)), \
             patch('routes.main.Sale.query', _scalar_query_result([])), \
             patch('routes.main.GLAccount.query') as gaq, \
             patch('routes.main.get_gl_account_by_code', return_value=inv_account), \
             patch('utils.gl_tenant.active_tenant_id', return_value=1):
            gaq.filter.return_value.all.return_value = [account]
            resp = main_client.get('/dashboard')
        assert resp.status_code == 200

    def test_dashboard_failure_returns_500(self, main_client):
        with _main_patches(), patch('utils.tenanting.tenant_query', side_effect=RuntimeError('boom')):
            resp = main_client.get('/dashboard')
        assert resp.status_code == 500

    def test_dashboard_requires_login(self, main_client):
        with _main_patches(), unauthenticated_client(main_client):
            resp = main_client.get('/dashboard')
        assert resp.status_code == 401


class TestMainProfile:
    def test_my_profile_renders(self, main_client, bypass_permission_auth):
        tenant = MagicMock()
        with patch('routes.main.render_template', return_value='ok'), \
             patch('routes.main.db.session') as sess, \
             patch('routes.main.db.session.query', return_value=_scalar_query_result((2, Decimal('500')))), \
             patch('routes.main.Sale.query') as sale_q:
            sess.get.return_value = tenant
            sale_q.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
            resp = main_client.get('/my-profile')
        assert resp.status_code == 200

    def test_profile_update_fields(self, main_client, bypass_permission_auth):
        with patch('utils.sanitizer.InputSanitizer.sanitize_text', return_value='New Name'), \
             patch('routes.main.db.session') as sess:
            resp = main_client.post('/my-profile/update', data={'full_name': 'New Name'}, follow_redirects=False)
        assert resp.status_code == 302
        sess.commit.assert_called()

    def test_profile_duplicate_email(self, main_client, bypass_permission_auth):
        existing = MagicMock()
        with patch('utils.sanitizer.InputSanitizer.sanitize_email', return_value='dup@test.com'), \
             patch('routes.main.User.query') as uq:
            uq.filter.return_value.first.return_value = existing
            resp = main_client.post('/my-profile/update', data={'email': 'dup@test.com'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_profile_password_change_success(self, main_client, bypass_permission_auth):
        bypass_permission_auth.password_hash = 'hash'
        with patch('werkzeug.security.check_password_hash', return_value=True), \
             patch('werkzeug.security.generate_password_hash', return_value='newhash'), \
             patch('utils.password_validator.PasswordValidator.validate', return_value=(True, [])), \
             patch('utils.session_security.rotate_session'), \
             patch('routes.main.db.session'):
            resp = main_client.post('/my-profile/update', data={
                'current_password': 'old',
                'new_password': 'Str0ng!Pass',
                'confirm_password': 'Str0ng!Pass',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_profile_password_wrong_current(self, main_client, bypass_permission_auth):
        with patch('werkzeug.security.check_password_hash', return_value=False):
            resp = main_client.post('/my-profile/update', data={
                'current_password': 'wrong',
                'new_password': 'Str0ng!Pass',
                'confirm_password': 'Str0ng!Pass',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_profile_password_mismatch(self, main_client, bypass_permission_auth):
        with patch('werkzeug.security.check_password_hash', return_value=True):
            resp = main_client.post('/my-profile/update', data={
                'current_password': 'old',
                'new_password': 'Str0ng!Pass',
                'confirm_password': 'Other!Pass',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_profile_weak_password(self, main_client, bypass_permission_auth):
        with patch('werkzeug.security.check_password_hash', return_value=True), \
             patch('utils.password_validator.PasswordValidator.validate', return_value=(False, ['too short'])):
            resp = main_client.post('/my-profile/update', data={
                'current_password': 'old',
                'new_password': 'weak',
                'confirm_password': 'weak',
            }, follow_redirects=False)
        assert resp.status_code == 302

    def test_profile_update_exception(self, main_client):
        with patch('utils.sanitizer.InputSanitizer.sanitize_text', side_effect=RuntimeError('fail')), \
             patch('routes.main.db.session') as sess:
            sess.rollback = MagicMock()
            resp = main_client.post('/my-profile/update', data={'full_name': 'X'}, follow_redirects=False)
        assert resp.status_code == 302


class TestTenantPublicProfile:
    def test_tenant_profile_active(self, main_client):
        tenant = MagicMock()
        tenant.is_active = True
        tenant.is_suspended = False
        with patch('models.tenant.Tenant.query') as tq, \
             patch('models.branch.Branch.query') as bq, \
             patch('routes.main.render_template', return_value='ok'), \
             patch('utils.auth_helpers.is_global_owner_user', return_value=False):
            tq.filter_by.return_value.first_or_404.return_value = tenant
            bq.filter_by.return_value.order_by.return_value.all.return_value = []
            resp = main_client.get('/tenant/acme-corp')
        assert resp.status_code == 200

    def test_tenant_profile_suspended(self, main_client):
        tenant = MagicMock()
        tenant.is_active = False
        tenant.is_suspended = True
        tenant.suspension_reason = 'billing'
        with patch('models.tenant.Tenant.query') as tq, \
             patch('routes.main.render_template', return_value='suspended'):
            tq.filter_by.return_value.first_or_404.return_value = tenant
            resp = main_client.get('/tenant/suspended-co')
        assert resp.status_code == 503
