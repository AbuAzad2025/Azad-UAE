from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import (
    _chain_query,
    unauthenticated_client,
)


@pytest.fixture
def branches_client(app_factory, bypass_admin_auth):
    from routes.branches import branches_bp

    app = app_factory(branches_bp)
    return app.test_client()


def _mock_branch(branch_id=1, code="BR01", name="Main Branch"):
    branch = MagicMock()
    branch.id = branch_id
    branch.code = code
    branch.name = name
    branch.tenant_id = 1
    branch.city = "Dubai"
    branch.address = "Sheikh Zayed Rd"
    branch.phone = "+971500000000"
    branch.is_main = True
    branch.prices_include_vat = None
    branch.users = []
    branch.warehouses = []
    branch.sales = []
    return branch


def _base_patches(branches=None, first=None):
    branches = branches if branches is not None else [_mock_branch()]
    return [
        patch("routes.branches.render_template", return_value="ok"),
        patch(
            "routes.branches.tenant_query",
            return_value=_chain_query(all=branches, first=first),
        ),
        patch(
            "routes.branches.tenant_get_or_404",
            side_effect=lambda model, bid: _mock_branch(bid),
        ),
        patch("routes.branches.db.session"),
        patch("services.gl_service.GLService.ensure_core_accounts"),
        patch("utils.tenant_limits.check_branches_limit"),
    ]


class TestBranchesIndex:
    def test_index_returns_200(self, branches_client):
        with (
            patch("routes.branches.render_template", return_value="index") as render,
            patch(
                "routes.branches.tenant_query",
                return_value=_chain_query(all=[_mock_branch()]),
            ),
        ):
            resp = branches_client.get("/branches/")
        assert resp.status_code == 200
        render.assert_called_once()
        assert render.call_args[0][0] == "branches/index.html"

    def test_index_unauthenticated_401(self, branches_client):
        with unauthenticated_client(branches_client):
            resp = branches_client.get("/branches/")
        assert resp.status_code == 401

    def test_index_non_admin_403(self, branches_client, mock_user):
        with patch("utils.decorators.is_admin_surface_user", return_value=False):
            resp = branches_client.get("/branches/")
        assert resp.status_code == 403


class TestBranchesCreate:
    def test_create_get_renders_form(self, branches_client):
        with patch("routes.branches.render_template", return_value="create") as render:
            resp = branches_client.get("/branches/create")
        assert resp.status_code == 200
        render.assert_called_once_with("branches/create.html")

    def test_create_post_success(self, branches_client):
        patches = _base_patches(first=None)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3] as mock_session,
            patches[4] as gl_sync,
            patches[5],
        ):
            resp = branches_client.post(
                "/branches/create",
                data={
                    "name": "New Branch",
                    "code": "NB01",
                    "city": "Abu Dhabi",
                    "address": "Corniche",
                    "phone": "+971500000001",
                },
            )
        assert resp.status_code == 302
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called()
        mock_session.commit.assert_called_once()
        gl_sync.assert_called_once_with(tenant_id=1)

    def test_create_missing_name_redirects(self, branches_client):
        with (
            patch("routes.branches.flash") as flash,
            patch("routes.branches.tenant_query", return_value=_chain_query()),
        ):
            resp = branches_client.post("/branches/create", data={"code": "X01"})
        assert resp.status_code == 302
        flash.assert_called_once_with("الاسم والكود مطلوبان", "danger")

    def test_create_missing_code_redirects(self, branches_client):
        with (
            patch("routes.branches.flash") as flash,
            patch("routes.branches.tenant_query", return_value=_chain_query()),
        ):
            resp = branches_client.post("/branches/create", data={"name": "Only Name"})
        assert resp.status_code == 302
        flash.assert_called_once_with("الاسم والكود مطلوبان", "danger")

    def test_create_duplicate_code_redirects(self, branches_client):
        existing = _mock_branch(code="DUP")
        with (
            patch("routes.branches.flash") as flash,
            patch(
                "routes.branches.tenant_query",
                return_value=_chain_query(first=existing),
            ),
            patch("utils.tenant_limits.check_branches_limit"),
        ):
            resp = branches_client.post(
                "/branches/create",
                data={"name": "Dup Branch", "code": "DUP"},
            )
        assert resp.status_code == 302
        flash.assert_called_once_with("الكود مستخدم مسبقاً", "danger")

    def test_create_tenant_limit_redirects(self, branches_client):
        from utils.tenant_limits import TenantLimitError

        with (
            patch("routes.branches.flash") as flash,
            patch("routes.branches.tenant_query", return_value=_chain_query(first=None)),
            patch(
                "utils.tenant_limits.check_branches_limit",
                side_effect=TenantLimitError("branches", 2, 2),
            ),
        ):
            resp = branches_client.post(
                "/branches/create",
                data={"name": "Limit Branch", "code": "LIM01"},
            )
        assert resp.status_code == 302
        flash.assert_called_once()

    def test_create_unauthenticated_401(self, branches_client):
        with unauthenticated_client(branches_client):
            resp = branches_client.post("/branches/create", data={"name": "X", "code": "Y"})
        assert resp.status_code == 401

    def test_create_non_admin_403(self, branches_client):
        with patch("utils.decorators.is_admin_surface_user", return_value=False):
            resp = branches_client.post("/branches/create", data={"name": "X", "code": "Y"})
        assert resp.status_code == 403


class TestBranchesEdit:
    def test_edit_get_renders_form(self, branches_client):
        branch = _mock_branch()
        with (
            patch("routes.branches.tenant_get_or_404", return_value=branch),
            patch("routes.branches.render_template", return_value="edit") as render,
        ):
            resp = branches_client.get("/branches/edit/5")
        assert resp.status_code == 200
        render.assert_called_once_with("branches/edit.html", branch=branch)

    def test_edit_post_success(self, branches_client):
        branch = _mock_branch(branch_id=5)
        with (
            patch("routes.branches.tenant_get_or_404", return_value=branch),
            patch("routes.branches.db.session") as mock_session,
            patch("services.gl_service.GLService.ensure_core_accounts") as gl_sync,
        ):
            resp = branches_client.post(
                "/branches/edit/5",
                data={
                    "name": "Updated Branch",
                    "city": "Sharjah",
                    "address": "Al Majaz",
                    "phone": "+971500000002",
                    "is_main": "on",
                    "prices_include_vat": "on",
                },
            )
        assert resp.status_code == 302
        assert branch.name == "Updated Branch"
        assert branch.is_main is True
        assert branch.prices_include_vat is True
        mock_session.flush.assert_called()
        mock_session.commit.assert_called_once()
        gl_sync.assert_called_once_with(tenant_id=1)

    def test_edit_unauthenticated_401(self, branches_client):
        with unauthenticated_client(branches_client):
            resp = branches_client.get("/branches/edit/1")
        assert resp.status_code == 401


class TestBranchesDelete:
    def test_delete_success(self, branches_client):
        branch = _mock_branch()
        with (
            patch("routes.branches.tenant_get_or_404", return_value=branch),
            patch("routes.branches.db.session") as mock_session,
            patch("routes.branches.flash") as flash,
        ):
            resp = branches_client.post("/branches/delete/1")
        assert resp.status_code == 302
        mock_session.delete.assert_called_once_with(branch)
        mock_session.commit.assert_called_once()
        flash.assert_called_once_with("تم حذف الفرع بنجاح", "success")

    def test_delete_with_related_users_blocked(self, branches_client):
        branch = _mock_branch()
        branch.users = [MagicMock()]
        with (
            patch("routes.branches.tenant_get_or_404", return_value=branch),
            patch("routes.branches.flash") as flash,
            patch("routes.branches.db.session") as mock_session,
        ):
            resp = branches_client.post("/branches/delete/1")
        assert resp.status_code == 302
        mock_session.delete.assert_not_called()
        flash.assert_called_once()
        assert "بيانات مرتبطة" in flash.call_args[0][0]

    def test_delete_with_related_warehouses_blocked(self, branches_client):
        branch = _mock_branch()
        branch.warehouses = [MagicMock()]
        with (
            patch("routes.branches.tenant_get_or_404", return_value=branch),
            patch("routes.branches.flash") as flash,
        ):
            resp = branches_client.post("/branches/delete/1")
        assert resp.status_code == 302
        assert "بيانات مرتبطة" in flash.call_args[0][0]

    def test_delete_with_related_sales_blocked(self, branches_client):
        branch = _mock_branch()
        branch.sales = [MagicMock()]
        with (
            patch("routes.branches.tenant_get_or_404", return_value=branch),
            patch("routes.branches.flash") as flash,
        ):
            resp = branches_client.post("/branches/delete/1")
        assert resp.status_code == 302
        assert "بيانات مرتبطة" in flash.call_args[0][0]

    def test_delete_unauthenticated_401(self, branches_client):
        with unauthenticated_client(branches_client):
            resp = branches_client.post("/branches/delete/1")
        assert resp.status_code == 401

    def test_delete_non_admin_403(self, branches_client):
        with patch("utils.decorators.is_admin_surface_user", return_value=False):
            resp = branches_client.post("/branches/delete/1")
        assert resp.status_code == 403
