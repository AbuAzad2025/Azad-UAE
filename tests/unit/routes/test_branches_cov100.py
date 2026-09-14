"""Gap100 for routes/branches.py — missing-tenant guard arcs (lines 26-27, 41-42)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.unit.routes.conftest import _chain_query


@pytest.fixture
def branches_cov100_client(app_factory, bypass_admin_auth):
    from routes.branches import branches_bp
    from routes.owner.blueprint import owner_bp

    app = app_factory(branches_bp, owner_bp)
    return app.test_client()


def _mock_branch(branch_id=1):
    from unittest.mock import MagicMock

    branch = MagicMock()
    branch.id = branch_id
    branch.code = "BR01"
    branch.name = "Main Branch"
    branch.tenant_id = 1
    return branch


class TestBranchesMissingTenantGuards:
    def test_index_without_active_tenant_redirects(self, branches_cov100_client):
        with (
            patch("routes.branches.get_active_tenant_id", return_value=None),
            patch("routes.branches.render_template", return_value="ok"),
        ):
            resp = branches_cov100_client.get("/branches/")
        assert resp.status_code == 302
        assert "/owner/" in resp.headers["Location"] or "tenants" in resp.headers["Location"]

    def test_create_without_active_tenant_redirects(self, branches_cov100_client):
        with (
            patch("routes.branches.get_active_tenant_id", return_value=None),
            patch("routes.branches.render_template", return_value="ok"),
            patch(
                "routes.branches.tenant_query",
                return_value=_chain_query(all=[_mock_branch()]),
            ),
        ):
            resp = branches_cov100_client.get("/branches/create")
        assert resp.status_code == 302
        assert "/owner/" in resp.headers["Location"] or "tenants" in resp.headers["Location"]
