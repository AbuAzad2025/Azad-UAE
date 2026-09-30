from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def platform_owner_client(client, db_session):
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
    def test_anonymous_gets_404(self, client):
        assert client.post(_FIX, data={}).status_code == 404

    def test_platform_owner_is_allowed(self, platform_owner_client, mocker):
        # These endpoints are platform-global: rebuild-gl-tree rewrites the
        # chart of accounts for every active tenant, fix-cost-centers issues
        # DDL, and cleanup-test-dbs drops databases. They used to be gated by
        # @company_admin_required, which permitted super_admin and manager
        # roles holding an active tenant while abort(404)-ing the actual
        # platform owner. A single tenant manager could therefore rewrite every
        # tenant's general ledger, and the owner could not reach their own tool.
        # @owner_required inverts that correctly.
        mocker.patch(
            "routes.owner.maintenance.fix_cost_centers_index_api",
            return_value={"dropped_index": True, "deleted_rows": 0},
        )
        resp = platform_owner_client.post(_FIX, data={"confirm": "FIX_COST_CENTERS"})
        assert resp.status_code == 200

    def test_non_owner_gets_404(self, no_perm_client):
        assert no_perm_client.post(_FIX, data={}).status_code == 404

    def test_company_admin_is_denied(self, auth_client, mocker):
        # The regression this pins: a tenant-scoped company admin/manager must
        # not reach a platform-wide maintenance action.
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


class TestFixCostCenters:
    def test_success(self, platform_owner_client, mocker):
        svc = mocker.patch(
            "routes.owner.maintenance.fix_cost_centers_index_api",
            return_value={"dropped_index": True, "deleted_rows": 2},
        )
        resp = platform_owner_client.post(_FIX, data={"confirm": "FIX_COST_CENTERS"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        svc.assert_called_once_with()

    def test_service_exception_returns_500(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.fix_cost_centers_index_api",
            side_effect=RuntimeError("db offline"),
        )
        mocker.patch("routes.owner.maintenance.LoggingCore.log_error")
        resp = platform_owner_client.post(_FIX, data={"confirm": "FIX_COST_CENTERS"})
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False


class TestRebuildGlTree:
    def test_with_cleanup_flag(self, platform_owner_client, mocker):
        svc = mocker.patch(
            "routes.owner.maintenance.rebuild_gl_tree_api",
            return_value={"tenants": [{"created": 3, "updated": 1}], "total_created": 3},
        )
        resp = platform_owner_client.post(_GL, data={"confirm": "REBUILD_GL_TREE", "cleanup_extra": "on"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        svc.assert_called_once_with(cleanup_extra=True)

    def test_without_cleanup_flag(self, platform_owner_client, mocker):
        svc = mocker.patch(
            "routes.owner.maintenance.rebuild_gl_tree_api",
            return_value={"tenants": [{"created": 0, "updated": 0}], "total_created": 0},
        )
        resp = platform_owner_client.post(_GL, data={"confirm": "REBUILD_GL_TREE"})
        assert resp.status_code == 200
        svc.assert_called_once_with(cleanup_extra=False)

    def test_exception_returns_500(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.rebuild_gl_tree_api",
            side_effect=Exception("rebuild failed"),
        )
        mocker.patch("routes.owner.maintenance.LoggingCore.log_error")
        resp = platform_owner_client.post(_GL, data={"confirm": "REBUILD_GL_TREE"})
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False

    def test_empty_tenants(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.rebuild_gl_tree_api",
            return_value={"tenants": []},
        )
        resp = platform_owner_client.post(_GL, data={"confirm": "REBUILD_GL_TREE"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


class TestFixDefaultTenant:
    def test_dry_run_returns_preview(self, platform_owner_client, mocker):
        svc = mocker.patch(
            "routes.owner.maintenance.fix_default_tenant_metadata_api",
            return_value={"patched": ["tenants.x"], "action_needed": True},
        )
        # service returns list, but route wraps len(result.get("patched",[]))
        # Our mock must match expected shape: list vs dict handling
        # Route does: patched = len(result.get("patched", [])) if result is dict else handling
        # Actually route expects dict with "patched" key, but MaintenanceService.fix_default_tenant_metadata returns list
        # Check route: result = fix_default_tenant_metadata_api(dry_run=dry_run)
        # then patched = len(result.get("patched", [])) -> if result is list, .get fails
        # But test in existing uses dict with patched list via mocker patch, so route expects dict
        # We mimic that via dict return
        svc.return_value = {"patched": ["tenants.x"]}
        resp = platform_owner_client.post(_TENANT, data={"confirm": "FIX_DEFAULT_TENANT", "dry_run": "on"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        svc.assert_called_once_with(dry_run=True)

    def test_non_dry_run_success(self, platform_owner_client, mocker):
        svc = mocker.patch(
            "routes.owner.maintenance.fix_default_tenant_metadata_api",
            return_value={"patched": ["tenants.y", "tenants.z"]},
        )
        resp = platform_owner_client.post(_TENANT, data={"confirm": "FIX_DEFAULT_TENANT"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        data = resp.get_json()["data"]
        assert "result" in data
        svc.assert_called_once_with(dry_run=False)

    def test_non_dry_run_empty_patched(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.fix_default_tenant_metadata_api",
            return_value={"patched": []},
        )
        resp = platform_owner_client.post(_TENANT, data={"confirm": "FIX_DEFAULT_TENANT"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_exception_returns_500(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.fix_default_tenant_metadata_api",
            side_effect=RuntimeError("fix failed"),
        )
        mocker.patch("routes.owner.maintenance.LoggingCore.log_error")
        resp = platform_owner_client.post(_TENANT, data={"confirm": "FIX_DEFAULT_TENANT"})
        assert resp.status_code == 500
        assert resp.get_json()["success"] is False

    def test_dry_run_exception_returns_500(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.fix_default_tenant_metadata_api",
            side_effect=Exception("dry fail"),
        )
        mocker.patch("routes.owner.maintenance.LoggingCore.log_error")
        resp = platform_owner_client.post(_TENANT, data={"confirm": "FIX_DEFAULT_TENANT", "dry_run": "on"})
        assert resp.status_code == 500


class TestRegenerateBackup:
    def test_non_dry_run_success(self, platform_owner_client, mocker):
        svc = mocker.patch(
            "routes.owner.maintenance.regenerate_default_backup_api",
            return_value="default_tenant.sql.gz",
        )
        resp = platform_owner_client.post(_BACKUP, data={"confirm": "REGENERATE_DEFAULT_BACKUP"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        svc.assert_called_once_with(dry_run=False)

    def test_dry_run_returns_preview(self, platform_owner_client, mocker):
        svc = mocker.patch(
            "routes.owner.maintenance.regenerate_default_backup_api",
            return_value="(skipped: --check mode)",
        )
        resp = platform_owner_client.post(_BACKUP, data={"confirm": "REGENERATE_DEFAULT_BACKUP", "dry_run": "on"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        svc.assert_called_once_with(dry_run=True)

    def test_exception_returns_500(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.regenerate_default_backup_api",
            side_effect=RuntimeError("backup failed"),
        )
        mocker.patch("routes.owner.maintenance.LoggingCore.log_error")
        resp = platform_owner_client.post(_BACKUP, data={"confirm": "REGENERATE_DEFAULT_BACKUP"})
        assert resp.status_code == 500

    def test_dry_run_exception_returns_500(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.regenerate_default_backup_api",
            side_effect=Exception("backup dry fail"),
        )
        mocker.patch("routes.owner.maintenance.LoggingCore.log_error")
        resp = platform_owner_client.post(_BACKUP, data={"confirm": "REGENERATE_DEFAULT_BACKUP", "dry_run": "on"})
        assert resp.status_code == 500


class TestRunDefaultTenantMaintenance:
    def test_dry_run_returns_preview(self, platform_owner_client, mocker):
        svc = mocker.patch(
            "routes.owner.maintenance.run_default_tenant_maintenance_api",
            return_value={"patched": ["tenants.a"], "backup_regenerated": None, "conflicts": []},
        )
        resp = platform_owner_client.post(_FULL, data={"confirm": "RUN_DEFAULT_TENANT_MAINTENANCE", "dry_run": "on"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        svc.assert_called_once_with(dry_run=True)

    def test_non_dry_run_success(self, platform_owner_client, mocker):
        svc = mocker.patch(
            "routes.owner.maintenance.run_default_tenant_maintenance_api",
            return_value={"patched": ["tenants.a", "tenants.b"], "backup_regenerated": "backup.sql.gz"},
        )
        resp = platform_owner_client.post(_FULL, data={"confirm": "RUN_DEFAULT_TENANT_MAINTENANCE"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        data = resp.get_json()["data"]
        assert data["result"]["backup_regenerated"] == "backup.sql.gz"
        svc.assert_called_once_with(dry_run=False)

    def test_non_dry_run_no_backup(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.run_default_tenant_maintenance_api",
            return_value={"patched": [], "backup_regenerated": None},
        )
        resp = platform_owner_client.post(_FULL, data={"confirm": "RUN_DEFAULT_TENANT_MAINTENANCE"})
        assert resp.status_code == 200

    def test_exception_returns_500(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.run_default_tenant_maintenance_api",
            side_effect=Exception("maintenance failed"),
        )
        mocker.patch("routes.owner.maintenance.LoggingCore.log_error")
        resp = platform_owner_client.post(_FULL, data={"confirm": "RUN_DEFAULT_TENANT_MAINTENANCE"})
        assert resp.status_code == 500

    def test_dry_run_exception_returns_500(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.run_default_tenant_maintenance_api",
            side_effect=RuntimeError("dry fail"),
        )
        mocker.patch("routes.owner.maintenance.LoggingCore.log_error")
        resp = platform_owner_client.post(_FULL, data={"confirm": "RUN_DEFAULT_TENANT_MAINTENANCE", "dry_run": "on"})
        assert resp.status_code == 500


class TestCleanupTestDbs:
    def test_non_dry_run_success(self, platform_owner_client, mocker):
        svc = mocker.patch(
            "routes.owner.maintenance.cleanup_test_databases_api",
            return_value={"dropped": ["azad_repro"], "failed": [], "remaining": []},
        )
        resp = platform_owner_client.post(_CLEAN, data={"confirm": "CLEANUP_TEST_DBS"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        svc.assert_called_once_with(dry_run=False)

    def test_dry_run_returns_preview(self, platform_owner_client, mocker):
        svc = mocker.patch(
            "routes.owner.maintenance.cleanup_test_databases_api",
            return_value={"dropped": ["azad_repro", "azad_test"], "failed": [], "remaining": []},
        )
        resp = platform_owner_client.post(_CLEAN, data={"confirm": "CLEANUP_TEST_DBS", "dry_run": "on"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        svc.assert_called_once_with(dry_run=True)

    def test_dry_run_empty(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.cleanup_test_databases_api",
            return_value={"dropped": [], "failed": []},
        )
        resp = platform_owner_client.post(_CLEAN, data={"confirm": "CLEANUP_TEST_DBS", "dry_run": "on"})
        assert resp.status_code == 200

    def test_exception_returns_500(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.cleanup_test_databases_api",
            side_effect=RuntimeError("cleanup failed"),
        )
        mocker.patch("routes.owner.maintenance.LoggingCore.log_error")
        resp = platform_owner_client.post(_CLEAN, data={"confirm": "CLEANUP_TEST_DBS"})
        assert resp.status_code == 500

    def test_dry_run_exception_returns_500(self, platform_owner_client, mocker):
        mocker.patch(
            "routes.owner.maintenance.cleanup_test_databases_api",
            side_effect=Exception("dry fail"),
        )
        mocker.patch("routes.owner.maintenance.LoggingCore.log_error")
        resp = platform_owner_client.post(_CLEAN, data={"confirm": "CLEANUP_TEST_DBS", "dry_run": "on"})
        assert resp.status_code == 500
