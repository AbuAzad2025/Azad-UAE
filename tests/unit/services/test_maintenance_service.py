"""Unit tests for services/maintenance_service.py — owner dashboard maintenance.

Real-DB coverage is restricted to paths that are safe on the ephemeral test
database (dry runs, IF EXISTS drops, zero-row updates). Destructive paths
(DROP DATABASE) are exercised only through a mocked engine boundary — the
test suite must never drop real databases.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from services import maintenance_service
from services.maintenance_service import (
    MaintenanceService,
    cleanup_test_databases_api,
    fix_cost_centers_index_api,
    fix_default_tenant_metadata_api,
    rebuild_gl_tree_api,
    regenerate_default_backup_api,
    run_default_tenant_maintenance_api,
)


class TestDefaultForType:
    def test_boolean_defaults_false(self):
        assert MaintenanceService._default_for_type("boolean") is False
        assert MaintenanceService._default_for_type("BOOLEAN") is False

    def test_numeric_family_defaults_zero(self):
        for dtype in ("integer", "numeric", "double precision", "real", "money"):
            assert MaintenanceService._default_for_type(dtype) == 0

    def test_json_defaults_empty_object(self):
        assert MaintenanceService._default_for_type("jsonb") == "{}"

    def test_temporal_defaults_now_expression(self):
        assert (
            MaintenanceService._default_for_type("timestamp without time zone")
            == "now()"
        )
        assert MaintenanceService._default_for_type("date") == "now()"

    def test_uuid_defaults_parseable_uuid(self):
        import uuid

        value = MaintenanceService._default_for_type("uuid")
        assert uuid.UUID(str(value)) is not None

    def test_other_types_default_empty_string(self):
        assert MaintenanceService._default_for_type("character varying") == ""
        assert MaintenanceService._default_for_type(None) == ""


class TestFixCostCentersIndex:
    def test_real_run_on_test_database(self, db_session):
        """DROP INDEX IF EXISTS + NULL-tenant cleanup are safe on the test DB."""
        result = MaintenanceService.fix_cost_centers_index()
        assert result["dropped_index"] is True
        assert isinstance(result["deleted_rows"], int)
        assert result["deleted_rows"] >= 0


class TestFixDefaultTenantMetadata:
    def test_dry_run_reports_without_writing(self, db_session):
        fixed = MaintenanceService.fix_default_tenant_metadata(dry_run=True)
        assert isinstance(fixed, list)
        assert all(entry.startswith("tenants.") for entry in fixed)

    def test_real_run_without_default_tenant_is_zero_row_noop(self, db_session):
        # No tenant with slug='default' exists in the test DB, so UPDATE
        # statements match zero rows — the call is safe and still reports.
        fixed = MaintenanceService.fix_default_tenant_metadata(dry_run=False)
        assert isinstance(fixed, list)
        assert all(entry.startswith("tenants.") for entry in fixed)


class TestRunDefaultTenantMaintenance:
    def test_dry_run_shape(self, db_session):
        result = MaintenanceService.run_default_tenant_maintenance(dry_run=True)
        assert set(result) == {
            "patched",
            "backup_regenerated",
            "action_needed",
            "conflicts",
        }
        assert result["backup_regenerated"] is None
        assert isinstance(result["patched"], list)
        assert isinstance(result["conflicts"], list)
        assert result["action_needed"] == (len(result["patched"]) > 0)


class TestCleanupTestDatabases:
    def test_dry_run_lists_targets_without_dropping(self, db_session):
        """dry_run=True issues no DROP statements; only the listing query runs."""
        result = MaintenanceService.cleanup_test_databases(dry_run=True)
        assert result["dropped"] == MaintenanceService.STALE_TEST_DATABASES
        assert result["failed"] == []
        assert isinstance(result["remaining"], list)
        # The live test database itself must still exist (proof nothing dropped).
        live_db = db_session.get_bind().url.database
        assert live_db in result["remaining"]

    def test_non_dry_run_issues_drop_statements(self, mocker):
        """Non-dry-run is verified only through a mocked engine boundary."""
        conn = MagicMock(name="conn")
        conn.execute.return_value.fetchall.return_value = [("azad_uae",)]
        engine = MagicMock(name="engine")
        engine.connect.return_value.__enter__.return_value = conn
        engine.connect.return_value.__exit__.return_value = False
        mocker.patch.object(maintenance_service, "create_engine", return_value=engine)

        result = MaintenanceService.cleanup_test_databases(dry_run=False)

        statements = [str(call.args[0]) for call in conn.execute.call_args_list]
        for db_name in MaintenanceService.STALE_TEST_DATABASES:
            assert any(
                f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)" in stmt
                for stmt in statements
            )
        assert result["dropped"] == MaintenanceService.STALE_TEST_DATABASES
        assert result["remaining"] == ["azad_uae"]


class TestRebuildGlTree:
    def _gl_mocks(self, mocker, app, build_return=None, build_side_effect=None):
        mocker.patch("app.create_app", return_value=app)
        build = mocker.patch(
            "services.gl_tree_builder.GLTreeBuilder.build",
            side_effect=build_side_effect,
        )
        if build_side_effect is None:
            build.return_value = build_return
        validate = mocker.patch(
            "services.gl_tree_builder.GLTreeBuilder.validate_tree",
            return_value={
                "valid": True,
                "total_accounts": 10,
                "core_accounts_found": 10,
                "extra_accounts": [],
                "issues": [],
                "missing_core_accounts": [],
            },
        )
        return build, validate

    def test_rebuild_reports_per_tenant(self, mocker, app, sample_tenant):
        audit = {
            "created": [{"code": "1000"}],
            "updated": [{"code": "2000"}],
            "converted": [],
            "deactivated": [],
            "errors": [],
        }
        build, validate = self._gl_mocks(mocker, app, build_return=audit)
        result = MaintenanceService.rebuild_gl_tree(cleanup_extra=False)
        # The shared test DB accumulates active tenants across the session, so
        # assert the contract per processed tenant rather than an exact count.
        build_tenant_ids = [call.args[0] for call in build.call_args_list]
        assert sample_tenant.id in build_tenant_ids
        assert all(
            call.kwargs == {"cleanup_extra": False, "commit": True}
            for call in build.call_args_list
        )
        validate_tenant_ids = [call.args[0] for call in validate.call_args_list]
        assert validate_tenant_ids == build_tenant_ids
        entry = next(t for t in result["tenants"] if t["tenant_id"] == sample_tenant.id)
        assert entry["validation"]["valid"] is True
        assert entry["created"] == 1
        assert entry["updated"] == 1
        assert result["tenants_updated"] == len(result["tenants"])
        assert result["total_created"] == len(result["tenants"])
        assert result["total_updated"] == len(result["tenants"])

    def test_tenant_failure_is_contained(self, mocker, app, sample_tenant):
        self._gl_mocks(mocker, app, build_side_effect=RuntimeError("gl boom"))
        result = MaintenanceService.rebuild_gl_tree(cleanup_extra=False)
        assert result["tenants"] == []
        assert result["tenants_updated"] == 0
        assert result["total_created"] == 0


class TestRegenerateDefaultBackup:
    def test_dry_run_skips_backup(self, mocker, db_session):
        mocker.patch("services.backup_service.BackupService.initialize")
        create = mocker.patch("services.backup_service.BackupService.create_backup")
        assert MaintenanceService.regenerate_default_backup(dry_run=True) == (
            "(skipped: --check mode)"
        )
        create.assert_not_called()

    def test_no_default_tenant_reports_missing(self, mocker, db_session):
        mocker.patch("services.backup_service.BackupService.initialize")
        assert MaintenanceService.regenerate_default_backup(dry_run=False) == (
            "No default tenant found"
        )

    def test_default_tenant_backup_returns_filename(self, mocker, db_session):
        import uuid as uuid_mod

        from models.tenant import Tenant

        unique = str(uuid_mod.uuid4())[:8]
        tenant = Tenant(
            name=f"Default Co {unique}",
            name_ar="الافتراضية",
            slug="default",
            email=f"default-{unique}@example.com",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(tenant)
        db_session.commit()

        mocker.patch("services.backup_service.BackupService.initialize")
        create = mocker.patch(
            "services.backup_service.BackupService.create_backup",
            return_value={"filename": "default_tenant.sql.gz"},
        )
        result = MaintenanceService.regenerate_default_backup(dry_run=False)
        assert result == "default_tenant.sql.gz"
        create.assert_called_once_with(scope="tenant", tenant_id=tenant.id, manual=True)


class TestApiWrappers:
    def test_fix_cost_centers_index_api_delegates(self, mocker):
        method = mocker.patch.object(
            MaintenanceService, "fix_cost_centers_index", return_value={"ok": 1}
        )
        assert fix_cost_centers_index_api() == {"ok": 1}
        method.assert_called_once_with()

    def test_rebuild_gl_tree_api_delegates(self, mocker):
        method = mocker.patch.object(
            MaintenanceService, "rebuild_gl_tree", return_value={"ok": 2}
        )
        assert rebuild_gl_tree_api(cleanup_extra=True) == {"ok": 2}
        method.assert_called_once_with(cleanup_extra=True)

    def test_fix_default_tenant_metadata_api_delegates(self, mocker):
        method = mocker.patch.object(
            MaintenanceService, "fix_default_tenant_metadata", return_value=["a"]
        )
        assert fix_default_tenant_metadata_api(dry_run=True) == ["a"]
        method.assert_called_once_with(dry_run=True)

    def test_regenerate_default_backup_api_delegates(self, mocker):
        method = mocker.patch.object(
            MaintenanceService, "regenerate_default_backup", return_value="b.sql.gz"
        )
        assert regenerate_default_backup_api(dry_run=True) == "b.sql.gz"
        method.assert_called_once_with(dry_run=True)

    def test_run_default_tenant_maintenance_api_delegates(self, mocker):
        method = mocker.patch.object(
            MaintenanceService, "run_default_tenant_maintenance", return_value={"ok": 3}
        )
        assert run_default_tenant_maintenance_api(dry_run=True) == {"ok": 3}
        method.assert_called_once_with(dry_run=True)

    def test_cleanup_test_databases_api_delegates(self, mocker):
        method = mocker.patch.object(
            MaintenanceService, "cleanup_test_databases", return_value={"ok": 4}
        )
        assert cleanup_test_databases_api(dry_run=True) == {"ok": 4}
        method.assert_called_once_with(dry_run=True)
