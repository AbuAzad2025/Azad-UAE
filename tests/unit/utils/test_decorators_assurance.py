from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from werkzeug.exceptions import Forbidden, NotFound


def _user(**kwargs):
    user = MagicMock()
    user.is_authenticated = kwargs.get('is_authenticated', True)
    user.is_owner = kwargs.get('is_owner', False)
    user.has_permission = MagicMock(return_value=kwargs.get('has_permission', True))
    user.is_super_admin = MagicMock(return_value=kwargs.get('is_super_admin', False))
    role = MagicMock()
    role.slug = kwargs.get('role_slug', 'seller')
    user.role = role
    return user


@pytest.fixture
def deco_ctx(app, mocker):
    mocker.patch('utils.decorators.url_for', return_value='/login')
    mocker.patch('utils.decorators.flash')
    with app.test_request_context('/dashboard'):
        yield


class TestBranchScopeHelpers:
    def test_branch_scope_id_delegates(self, mocker):
        mocker.patch('utils.decorators.current_user', MagicMock())
        mocker.patch('utils.decorators.branch_scope_id_for', return_value=7)
        from utils.decorators import branch_scope_id

        assert branch_scope_id() == 7

    def test_report_branch_scope_id_delegates(self, mocker):
        mocker.patch('utils.decorators.current_user', MagicMock())
        mocker.patch('utils.decorators.report_branch_scope_id_for', return_value=3)
        from utils.decorators import report_branch_scope_id

        assert report_branch_scope_id() == 3


class TestPermissionRequired:
    def test_redirects_when_unauthenticated(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import permission_required

        @permission_required('manage_sales')
        def view():
            return 'ok'

        resp = view()
        assert resp.status_code == 302
        assert resp.location == '/login'

    def test_global_owner_bypasses(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user())
        mocker.patch('utils.decorators.is_global_owner_user', return_value=True)
        from utils.decorators import permission_required

        @permission_required('manage_sales')
        def view():
            return 'allowed'

        assert view() == 'allowed'

    def test_aborts_without_permission(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(has_permission=False))
        mocker.patch('utils.decorators.is_global_owner_user', return_value=False)
        from utils.decorators import permission_required

        @permission_required('manage_sales')
        def view():
            return 'ok'

        with pytest.raises(Forbidden):
            view()

    def test_allows_with_permission(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(has_permission=True))
        mocker.patch('utils.decorators.is_global_owner_user', return_value=False)
        from utils.decorators import permission_required

        @permission_required('manage_sales')
        def view():
            return 'ok'

        assert view() == 'ok'


class TestAnyPermissionRequired:
    def test_redirects_when_unauthenticated(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import any_permission_required

        @any_permission_required('manage_sales')
        def view():
            return 'ok'

        resp = view()
        assert resp.status_code == 302

    def test_global_owner_bypasses(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user())
        mocker.patch('utils.decorators.is_global_owner_user', return_value=True)
        from utils.decorators import any_permission_required

        @any_permission_required('manage_sales')
        def view():
            return 'owner'

        assert view() == 'owner'

    def test_any_code_grants_access(self, deco_ctx, mocker):
        user = _user()
        user.has_permission.side_effect = lambda code: code == 'view_reports'
        mocker.patch('utils.decorators.current_user', user)
        mocker.patch('utils.decorators.is_global_owner_user', return_value=False)
        from utils.decorators import any_permission_required

        @any_permission_required('manage_sales', 'view_reports', '')
        def view():
            return 'ok'

        assert view() == 'ok'

    def test_aborts_when_none_match(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(has_permission=False))
        mocker.patch('utils.decorators.is_global_owner_user', return_value=False)
        from utils.decorators import any_permission_required

        @any_permission_required('a', 'b')
        def view():
            return 'ok'

        with pytest.raises(Forbidden):
            view()


class TestAdminRequired:
    def test_owner_path_unauthenticated_404(self, app, mocker):
        mocker.patch('utils.decorators.url_for', return_value='/login')
        mocker.patch('utils.decorators.flash')
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import admin_required

        @admin_required
        def view():
            return 'ok'

        with app.test_request_context('/owner/settings'):
            with pytest.raises(NotFound):
                view()

    def test_redirects_non_owner_path(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import admin_required

        @admin_required
        def view():
            return 'ok'

        resp = view()
        assert resp.status_code == 302

    def test_aborts_non_admin(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user())
        mocker.patch('utils.decorators.is_admin_surface_user', return_value=False)
        from utils.decorators import admin_required

        @admin_required
        def view():
            return 'ok'

        with pytest.raises(Forbidden):
            view()

    def test_super_admin_required_delegates(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user())
        mocker.patch('utils.decorators.is_admin_surface_user', return_value=True)
        from utils.decorators import super_admin_required

        @super_admin_required
        def view():
            return 'admin'

        assert view() == 'admin'


class TestSellerOrAbove:
    def test_redirects_unauthenticated_non_owner_path(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import seller_or_above

        @seller_or_above
        def view():
            return 'ok'

        resp = view()
        assert resp.status_code == 302

    def test_owner_path_unauthenticated_404(self, app, mocker):
        mocker.patch('utils.decorators.url_for', return_value='/login')
        mocker.patch('utils.decorators.flash')
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import seller_or_above

        @seller_or_above
        def view():
            return 'ok'

        with app.test_request_context('/owner/sales'):
            with pytest.raises(NotFound):
                view()

    def test_aborts_low_role(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='viewer'))
        from utils.decorators import seller_or_above

        @seller_or_above
        def view():
            return 'ok'

        with pytest.raises(Forbidden):
            view()

    def test_allows_seller(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='seller'))
        from utils.decorators import seller_or_above

        @seller_or_above
        def view():
            return 'ok'

        assert view() == 'ok'


class TestOwnerRequired:
    def test_unauthenticated_404(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import owner_required

        @owner_required
        def view():
            return 'ok'

        with pytest.raises(NotFound):
            view()

    def test_non_owner_404(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user())
        mocker.patch('utils.decorators.is_global_owner_user', return_value=False)
        from utils.decorators import owner_required

        @owner_required
        def view():
            return 'ok'

        with pytest.raises(NotFound):
            view()

    def test_owner_allowed(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_owner=True))
        mocker.patch('utils.decorators.is_global_owner_user', return_value=True)
        from utils.decorators import owner_required

        @owner_required
        def view():
            return 'owner'

        assert view() == 'owner'


class TestOwnerOnly:
    def test_unauthenticated_403(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import owner_only

        @owner_only
        def view():
            return 'ok'

        with pytest.raises(Forbidden):
            view()

    def test_non_owner_403(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_owner=False))
        from utils.decorators import owner_only

        @owner_only
        def view():
            return 'ok'

        with pytest.raises(Forbidden):
            view()

    def test_owner_passes(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_owner=True))
        from utils.decorators import owner_only

        @owner_only
        def view():
            return 'owner'

        assert view() == 'owner'


class TestCompanyAdminRequired:
    def test_redirects_unauthenticated_non_owner_path(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import company_admin_required

        @company_admin_required
        def view():
            return 'ok'

        resp = view()
        assert resp.status_code == 302

    def test_owner_path_unauthenticated_404(self, app, mocker):
        mocker.patch('utils.decorators.url_for', return_value='/login')
        mocker.patch('utils.decorators.flash')
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import company_admin_required

        @company_admin_required
        def view():
            return 'ok'

        with app.test_request_context('/owner/tenant'):
            with pytest.raises(NotFound):
                view()

    def test_wrong_role_aborts(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='seller', is_super_admin=False))
        mocker.patch('utils.decorators.is_global_owner_user', return_value=False)
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
        from utils.decorators import company_admin_required

        @company_admin_required
        def view():
            return 'ok'

        with pytest.raises(Forbidden):
            view()

    def test_global_owner_aborts_404(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='super_admin', is_super_admin=True))
        mocker.patch('utils.decorators.is_global_owner_user', return_value=True)
        from utils.decorators import company_admin_required

        @company_admin_required
        def view():
            return 'ok'

        with pytest.raises(NotFound):
            view()

    def test_missing_tenant_aborts(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='manager', is_super_admin=False))
        mocker.patch('utils.decorators.is_global_owner_user', return_value=False)
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=None)
        from utils.decorators import company_admin_required

        @company_admin_required
        def view():
            return 'ok'

        with pytest.raises(Forbidden):
            view()

    def test_manager_with_tenant_allowed(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='manager', is_super_admin=False))
        mocker.patch('utils.decorators.is_global_owner_user', return_value=False)
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
        from utils.decorators import company_admin_required

        @company_admin_required
        def view():
            return 'admin'

        assert view() == 'admin'


class TestOwnerOrCompanyAdmin:
    def test_redirects_when_unauthenticated(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import owner_or_company_admin

        @owner_or_company_admin
        def view():
            return 'ok'

        resp = view()
        assert resp.status_code == 302

    def test_owner_path_unauthenticated_404(self, app, mocker):
        mocker.patch('utils.decorators.url_for', return_value='/login')
        mocker.patch('utils.decorators.flash')
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import owner_or_company_admin

        @owner_or_company_admin
        def view():
            return 'ok'

        with app.test_request_context('/owner/api'):
            with pytest.raises(NotFound):
                view()

    def test_global_owner_allowed(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user())
        mocker.patch('utils.decorators.is_global_owner_user', return_value=True)
        from utils.decorators import owner_or_company_admin

        @owner_or_company_admin
        def view():
            return 'owner'

        assert view() == 'owner'

    def test_company_admin_allowed(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='super_admin', is_super_admin=True))
        mocker.patch('utils.decorators.is_global_owner_user', return_value=False)
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=2)
        from utils.decorators import owner_or_company_admin

        @owner_or_company_admin
        def view():
            return 'company'

        assert view() == 'company'

    def test_other_role_aborts(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='seller', is_super_admin=False))
        mocker.patch('utils.decorators.is_global_owner_user', return_value=False)
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
        from utils.decorators import owner_or_company_admin

        @owner_or_company_admin
        def view():
            return 'ok'

        with pytest.raises(Forbidden):
            view()


class TestBranchManagerRequired:
    def test_unauthenticated_404(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import branch_manager_required

        @branch_manager_required
        def view():
            return 'ok'

        with pytest.raises(NotFound):
            view()

    def test_branch_manager_allowed(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='branch_manager'))
        from utils.decorators import branch_manager_required

        @branch_manager_required
        def view():
            return 'bm'

        assert view() == 'bm'

    def test_other_role_aborts(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='seller'))
        from utils.decorators import branch_manager_required

        @branch_manager_required
        def view():
            return 'ok'

        with pytest.raises(Forbidden):
            view()


class TestAccountantRequired:
    def test_unauthenticated_404(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(is_authenticated=False))
        from utils.decorators import accountant_required

        @accountant_required
        def view():
            return 'ok'

        with pytest.raises(NotFound):
            view()

    def test_accountant_allowed(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='accountant'))
        from utils.decorators import accountant_required

        @accountant_required
        def view():
            return 'acct'

        assert view() == 'acct'

    def test_super_admin_allowed(self, deco_ctx, mocker):
        user = _user(role_slug='viewer')
        user.is_super_admin.return_value = True
        mocker.patch('utils.decorators.current_user', user)
        from utils.decorators import accountant_required

        @accountant_required
        def view():
            return 'sa'

        assert view() == 'sa'

    def test_seller_aborts(self, deco_ctx, mocker):
        mocker.patch('utils.decorators.current_user', _user(role_slug='seller'))
        from utils.decorators import accountant_required

        @accountant_required
        def view():
            return 'ok'

        with pytest.raises(Forbidden):
            view()
