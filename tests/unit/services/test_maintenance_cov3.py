"""Coverage boost for services/maintenance_service.py.

Targets: fix_cost_centers_index error path, rebuild_gl_tree cleanup_extra /
errors / invalid-tree / no-change paths, _default_for_type decimal+float,
fix_default_tenant_metadata skip-default + now() write, regenerate backup
manifest + str fallbacks, run_default_tenant_maintenance non-dry-run with
conflicts, cleanup failure path. Real calls; engine mocked only at boundary.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestFixCostCentersIndexError:
    def test_drop_failure_still_deletes(self, mocker):
        from services import maintenance_service as ms
        from services.maintenance_service import MaintenanceService

        conn = MagicMock(name="conn")
        delete_result = MagicMock(rowcount=3)
        conn.execute.side_effect = [RuntimeError("no idx"), delete_result]
        engine = MagicMock(name="engine")
        engine.begin.return_value.__enter__.return_value = conn
        engine.begin.return_value.__exit__.return_value = False
        mocker.patch.object(ms, "create_engine", return_value=engine)
        result = MaintenanceService.fix_cost_centers_index()
        assert result["dropped_index"] is False
        assert result["deleted_rows"] == 3


class TestRebuildGlTreeBranches:
    def _mocks(self, mocker, app, build_return, valid=True, extra=None, missing=None):
        mocker.patch("app.create_app", return_value=app)
        build = mocker.patch("services.gl_tree_builder.GLTreeBuilder.build", return_value=build_return)
        validate = mocker.patch(
            "services.gl_tree_builder.GLTreeBuilder.validate_tree",
            return_value={
                "valid": valid,
                "total_accounts": 5,
                "core_accounts_found": 5,
                "extra_accounts": extra or [],
                "issues": [] if valid else [{"code": "X", "issue": "bad"}],
                "missing_core_accounts": missing or [],
            },
        )
        return build, validate

    def test_cleanup_extra_errors_and_invalid_tree(self, mocker, app, sample_tenant, capsys):
        from services.maintenance_service import MaintenanceService

        audit = {
            "created": [],
            "updated": [],
            "converted": [],
            "deactivated": [{"code": "9999"}],
            "errors": [{"code": "E1", "error": "boom"}],
        }
        self._mocks(mocker, app, audit, valid=False, extra=["9999"], missing=["1000"])
        result = MaintenanceService.rebuild_gl_tree(cleanup_extra=True)
        assert result["total_deactivated"] >= 1
        out = capsys.readouterr().out
        assert "Deactivated" in out
        assert "WARNING" in out

    def test_no_change_tenant_not_counted(self, mocker, app, sample_tenant):
        from services.maintenance_service import MaintenanceService

        audit = {"created": [], "updated": [], "converted": [], "deactivated": [], "errors": []}
        self._mocks(mocker, app, audit, valid=True)
        result = MaintenanceService.rebuild_gl_tree(cleanup_extra=False)
        assert result["tenants_updated"] == 0
        assert result["total_created"] == 0


class TestDefaultForTypeExtra:
    def test_decimal_and_float(self):
        from services.maintenance_service import MaintenanceService

        assert MaintenanceService._default_for_type("decimal") == 0
        assert MaintenanceService._default_for_type("float") == 0
        assert MaintenanceService._default_for_type("character varying(50)") == ""


class TestFixDefaultTenantMetadataBranches:
    def test_skips_columns_with_defaults(self, mocker):
        from services import maintenance_service as ms
        from services.maintenance_service import MaintenanceService

        conn = MagicMock(name="conn")
        conn.execute.return_value.fetchall.return_value = [
            ("name", "character varying", "nextval('x')"),
            ("notes", "text", "NULL"),
        ]
        engine = MagicMock(name="engine")
        engine.begin.return_value.__enter__.return_value = conn
        engine.begin.return_value.__exit__.return_value = False
        mocker.patch.object(ms, "create_engine", return_value=engine)
        mocker.patch("services.maintenance_service.assert_known_column")
        mocker.patch("services.maintenance_service.Table")
        mocker.patch("services.maintenance_service.MetaData")
        mocker.patch("services.maintenance_service.select")
        fixed = MaintenanceService.fix_default_tenant_metadata(dry_run=True)
        assert fixed == []

    def test_now_branch_writes_func_now(self, mocker):
        from services import maintenance_service as ms
        from services.maintenance_service import MaintenanceService

        conn = MagicMock(name="conn")
        fetch = MagicMock(fetchall=MagicMock(return_value=[("created_at", "timestamp", None)]))
        cur_result = MagicMock(scalar=MagicMock(return_value=None))
        conn.execute.side_effect = [fetch, cur_result, MagicMock()]
        engine = MagicMock(name="engine")
        engine.begin.return_value.__enter__.return_value = conn
        engine.begin.return_value.__exit__.return_value = False
        mocker.patch.object(ms, "create_engine", return_value=engine)
        mocker.patch("services.maintenance_service.assert_known_column")
        mocker.patch("services.maintenance_service.Table")
        mocker.patch("services.maintenance_service.MetaData")
        mocker.patch("services.maintenance_service.select")
        mocker.patch("services.maintenance_service.update")
        fixed = MaintenanceService.fix_default_tenant_metadata(dry_run=False)
        assert fixed == ["tenants.created_at <- 'now()' (timestamp)"]


class TestRegenerateBackupFallbacks:
    def test_manifest_scope_fallback(self, mocker, db_session):
        import uuid as _uuid

        from models.tenant import Tenant
        from services.maintenance_service import MaintenanceService

        if Tenant.query.filter_by(slug="default").first() is None:
            tenant = Tenant(
                name=f"D {_uuid.uuid4().hex[:4]}",
                name_ar="x",
                slug="default",
                email=f"d-{_uuid.uuid4().hex[:6]}@e.com",
                country="AE",
                subscription_plan="basic",
            )
            db_session.add(tenant)
            db_session.commit()
        mocker.patch("services.backup_service.BackupService.initialize")
        mocker.patch(
            "services.backup_service.BackupService.create_backup", return_value={"manifest": {"backup_scope": "tenant"}}
        )
        assert MaintenanceService.regenerate_default_backup(dry_run=False) == "tenant"

    def test_plain_string_result(self, mocker, db_session):
        import uuid as _uuid

        from models.tenant import Tenant
        from services.maintenance_service import MaintenanceService

        if Tenant.query.filter_by(slug="default").first() is None:
            tenant = Tenant(
                name=f"D {_uuid.uuid4().hex[:4]}",
                name_ar="x",
                slug="default",
                email=f"d2-{_uuid.uuid4().hex[:6]}@e.com",
                country="AE",
                subscription_plan="basic",
            )
            db_session.add(tenant)
            db_session.commit()
        mocker.patch("services.backup_service.BackupService.initialize")
        mocker.patch("services.backup_service.BackupService.create_backup", return_value="/tmp/bak.sql.gz")
        assert MaintenanceService.regenerate_default_backup(dry_run=False) == "/tmp/bak.sql.gz"


class TestRunMaintenanceNonDryRun:
    def test_conflicts_and_backup(self, mocker):
        from services import maintenance_service as ms
        from services.maintenance_service import MaintenanceService

        conn = MagicMock(name="conn")
        conn.execute.return_value.scalar.return_value = 2
        engine = MagicMock(name="engine")
        engine.connect.return_value.__enter__.return_value = conn
        engine.connect.return_value.__exit__.return_value = False
        mocker.patch.object(ms, "create_engine", return_value=engine)
        mocker.patch.object(MaintenanceService, "fix_default_tenant_metadata", return_value=["tenants.x <- '' (text)"])
        mocker.patch.object(MaintenanceService, "regenerate_default_backup", return_value="b.sql.gz")
        result = MaintenanceService.run_default_tenant_maintenance(dry_run=False)
        assert result["conflicts"] != []
        assert result["backup_regenerated"] == "b.sql.gz"
        assert result["action_needed"] is True


class TestCleanupFailure:
    def test_failed_drop_recorded(self, mocker):
        from services import maintenance_service as ms
        from services.maintenance_service import MaintenanceService

        conn = MagicMock(name="conn")

        def _exec(stmt, *a, **k):
            text = str(stmt)
            if "DROP DATABASE" in text and "azadexa_dev" in text:
                raise RuntimeError("in use")
            result = MagicMock()
            result.fetchall.return_value = [("azad_uae_test",)]
            return result

        conn.execute.side_effect = _exec
        engine = MagicMock(name="engine")
        engine.connect.return_value.__enter__.return_value = conn
        engine.connect.return_value.__exit__.return_value = False
        mocker.patch.object(ms, "create_engine", return_value=engine)
        result = MaintenanceService.cleanup_test_databases(dry_run=False)
        assert any(db == "azadexa_dev" for db, _ in result["failed"])
        assert result["remaining"] == ["azad_uae_test"]
