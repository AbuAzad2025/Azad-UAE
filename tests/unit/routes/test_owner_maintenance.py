"""Unit tests for routes/owner/maintenance.py — company-admin maintenance APIs.

The company_admin_required guard runs for real: it blocks anonymous users AND
platform owners with 404, requires a company-admin role + active tenant.
Service layer functions are mocked at the routes.owner.maintenance namespace;
the confirm-string contract is exercised for real.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def platform_owner_client(client, db_session):
    """Real platform owner (is_owner + tenant_id=None) via real login."""
    from models import Role, User

    unique = str(uuid.uuid4())[:8]
    role = db_session.query(Role).filter_by(slug="owner").first()
    if not role:
        role = Role(name="Owner", slug="owner", is_active=True)
        db_session.add(role)
        db_session.flush()
    user = User(
        username=f"powner-{unique}",
        email=f"powner-{unique}@example.com",
        full_name="Platform Owner",
        tenant_id=None,
        role_id=role.id,
        is_owner=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=False,
    )
    return client


@pytest.fixture
def no_perm_client(client, db_session, sample_tenant):
    """Authenticated tenant user whose role is not a company-admin role."""
    from models import Role, User

    unique = str(uuid.uuid4())[:8]
    role = Role(name=f"Seller {unique}", slug=f"seller_{unique}", is_active=True)
    db_session.add(role)
    db_session.flush()
    user = User(
        username=f"seller-{unique}",
        email=f"seller-{unique}@example.com",
        full_name="Seller",
        tenant_id=sample_tenant.id,
        role_id=role.id,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=False,
    )
    return client


@pytest.fixture(autouse=True)
def _audit(mocker):
    return mocker.patch("routes.owner.maintenance.LoggingCore.log_audit")


_FIX = "/owner/maintenance/fix-cost-centers"
_GL = "/owner/maintenance/rebuild-gl-tree"
_TENANT = "/owner/maintenance/fix-default-tenant"
_BACKUP = "/owner/maintenance/regenerate-default-backup"
_FULL = "/owner/maintenance/run-default-tenant-maintenance"
_CLEAN = "/owner/maintenance/cleanup-test-dbs"


class TestCompanyAdminGuardContract:
    """Real guard: anonymous 404, non-owner 404, platform owner allowed in.

    These endpoints are platform-global. rebuild-gl-tree rewrites the chart of
    accounts for every active tenant, fix-cost-centers issues DDL, and
    cleanup-test-dbs drops databases.

    They were gated by @company_admin_required, which permits super_admin and
    manager roles holding an active tenant while abort(404)-ing the actual
    platform owner. So a single tenant manager could rewrite every tenant's
    general ledger, and the owner could not reach their own tool. @owner_required
    inverts that correctly, and these assertions follow.

    tests/unit/routes/test_maintenance.py covers the same contract; this file
    exists separately and previously encoded the old behaviour too.
    """

    def test_anonymous_gets_404(self, client):
        assert client.post(_FIX, data={}).status_code == 404

    def test_non_owner_gets_404(self, no_perm_client):
        assert no_perm_client.post(_FIX, data={}).status_code == 404

    def test_platform_owner_is_allowed(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.fix_cost_centers_index_api",
            return_value={"dropped_index": True, "deleted_rows": 0},
        )
        resp = platform_owner_client.post(_FIX, data={"confirm": "FIX_COST_CENTERS"})
        assert resp.status_code == 200

    def test_company_admin_is_denied(self, auth_client, mocker):
        # The regression this pins: a tenant-scoped company admin must not reach
        # a platform-wide action.
        called = mocker.patch(
            "routes.owner.maintenance.fix_cost_centers_index_api",
            return_value={"dropped_index": True, "deleted_rows": 0},
        )
        resp = auth_client.post(_FIX, data={"confirm": "FIX_COST_CENTERS"})
        assert resp.status_code == 404
        called.assert_not_called()


class TestConfirmStringContract:
    @pytest.mark.parametrize(
        ("url", "confirm"),
        [
            (_FIX, "FIX_COST_CENTERS"),
            (_GL, "REBUILD_GL_TREE"),
            (_TENANT, "FIX_DEFAULT_TENANT"),
            (_BACKUP, "REGENERATE_DEFAULT_BACKUP"),
            (_FULL, "RUN_DEFAULT_TENANT_MAINTENANCE"),
            (_CLEAN, "CLEANUP_TEST_DBS"),
        ],
    )
    def test_missing_or_wrong_confirm_returns_400(self, platform_owner_client, url, confirm):
        assert platform_owner_client.post(url, data={}).status_code == 400
        resp = platform_owner_client.post(url, data={"confirm": f"{confirm}_WRONG"})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False


class TestHappyPaths:
    def test_fix_cost_centers(self, platform_owner_client, mocker):
        service = mocker.patch(
            "routes.owner.maintenance.fix_cost_centers_index_api",
            return_value={"dropped_index": True, "deleted_rows": 2},
        )
        resp = platform_owner_client.post(_FIX, data={"confirm": "FIX_COST_CENTERS"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        service.assert_called_once_with()

    def test_rebuild_gl_tree_passes_cleanup_flag(self, platform_owner_client, mocker):
        service = mocker.patch(
            "routes.owner.maintenance.rebuild_gl_tree_api",
            return_value={"tenants": [{"created": 3, "updated": 1}]},
        )
        resp = platform_owner_client.post(_GL, data={"confirm": "REBUILD_GL_TREE", "cleanup_extra": "on"})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert resp.get_json()["success"] is True
        assert data["result"]["tenants"][0]["created"] == 3
        service.assert_called_once_with(cleanup_extra=True)

    def test_fix_default_tenant_dry_run(self, platform_owner_client, mocker):
        service = mocker.patch(
            "routes.owner.maintenance.fix_default_tenant_metadata_api",
            return_value={"patched": ["tenants.x"], "action_needed": True},
        )
        resp = platform_owner_client.post(_TENANT, data={"confirm": "FIX_DEFAULT_TENANT", "dry_run": "on"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        service.assert_called_once_with(dry_run=True)

    def test_regenerate_default_backup(self, platform_owner_client, mocker):
        service = mocker.patch(
            "routes.owner.maintenance.regenerate_default_backup_api",
            return_value="default_tenant.sql.gz",
        )
        resp = platform_owner_client.post(_BACKUP, data={"confirm": "REGENERATE_DEFAULT_BACKUP"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        service.assert_called_once_with(dry_run=False)

    def test_run_full_maintenance_dry_run(self, platform_owner_client, mocker):
        service = mocker.patch(
            "routes.owner.maintenance.run_default_tenant_maintenance_api",
            return_value={"patched": [], "backup_regenerated": None},
        )
        resp = platform_owner_client.post(
            _FULL,
            data={"confirm": "RUN_DEFAULT_TENANT_MAINTENANCE", "dry_run": "on"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        service.assert_called_once_with(dry_run=True)

    def test_cleanup_test_dbs(self, platform_owner_client, mocker):
        service = mocker.patch(
            "routes.owner.maintenance.cleanup_test_databases_api",
            return_value={"dropped": ["azad_repro"], "failed": []},
        )
        resp = platform_owner_client.post(_CLEAN, data={"confirm": "CLEANUP_TEST_DBS"})
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert resp.get_json()["success"] is True
        assert data["result"]["dropped"] == ["azad_repro"]
        service.assert_called_once_with(dry_run=False)


class TestFailurePath:
    def test_service_exception_returns_500(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.fix_cost_centers_index_api",
            side_effect=RuntimeError("db offline"),
        )
        resp = platform_owner_client.post(_FIX, data={"confirm": "FIX_COST_CENTERS"})
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False
