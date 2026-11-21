"""Coverage gaps in app/bootstrap.py and app/factory.py.

These exercise the *reporting* branches that never fire on a healthy boot:
an incomplete schema, a broken manifest probe, and the scheduler/upload
fallbacks in the factory.  None of them is allowed to abort startup, which is
the property the assertions pin.
"""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

import pytest

from app import bootstrap as bs
from tests.unit.app.test_factory import _minimal_app


@pytest.fixture(autouse=True)
def _clear_integrity_flags(monkeypatch):
    """The session app fixture sets SKIP_SYSTEM_INTEGRITY=1; these tests need it off."""
    monkeypatch.delenv("SKIP_SYSTEM_INTEGRITY", raising=False)
    monkeypatch.delenv("AUTO_MIGRATE", raising=False)
    monkeypatch.delenv("SKIP_BOOT_PROVISIONING", raising=False)
    yield


class TestVerifySchemaIncompletePaths:
    """app/bootstrap.py lines 126-153: missing tables, AUTO_MIGRATE branches."""

    @pytest.fixture
    def partial_inspector(self):
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["tenants", "users"]
        return inspector

    def test_missing_tables_without_auto_migrate_refuses(self, app, monkeypatch, partial_inspector):
        with (
            app.app_context(),
            patch("sqlalchemy.inspect", return_value=partial_inspector),
            patch.object(bs, "_is_migration_command", return_value=False),
        ):
            assert bs.verify_schema() is False

    def test_auto_migrate_success_fills_schema(self, app, monkeypatch, partial_inspector):
        monkeypatch.setenv("AUTO_MIGRATE", "1")
        complete = MagicMock()
        complete.get_table_names.return_value = list(bs.CORE_TABLES)
        with (
            app.app_context(),
            patch("sqlalchemy.inspect", side_effect=[partial_inspector, complete]),
            patch("flask_migrate.upgrade") as upgrade,
            patch.object(bs, "_is_migration_command", return_value=False),
        ):
            assert bs.verify_schema() is True
        upgrade.assert_called_once_with()

    def test_auto_migrate_still_missing_returns_false(self, app, monkeypatch, partial_inspector):
        monkeypatch.setenv("AUTO_MIGRATE", "1")
        with (
            app.app_context(),
            patch("sqlalchemy.inspect", return_value=partial_inspector),
            patch("flask_migrate.upgrade"),
            patch.object(bs, "_is_migration_command", return_value=False),
        ):
            assert bs.verify_schema() is False

    def test_auto_migrate_failure_returns_false(self, app, monkeypatch, partial_inspector):
        monkeypatch.setenv("AUTO_MIGRATE", "1")
        with (
            app.app_context(),
            patch("sqlalchemy.inspect", return_value=partial_inspector),
            patch("flask_migrate.upgrade", side_effect=RuntimeError("migration failed")),
            patch.object(bs, "_is_migration_command", return_value=False),
        ):
            assert bs.verify_schema() is False


class TestCredentialStateNoOwner:
    """app/bootstrap.py line 170: the no-owner warning path."""

    def test_no_owner_is_reported_not_created(self, app):
        query = MagicMock()
        query.filter_by.return_value.count.return_value = 0
        with app.app_context(), patch("models.user.User.query", query):
            assert bs.check_credential_state() is None


class TestVerifySeedManifestBuckets:
    """app/bootstrap.py lines 232-245, 250-251, 266, 280-288."""

    def test_every_bucket_is_reported(self, app):
        from utils.seed_manifest import SeedSet

        seed_sets = (
            SeedSet(
                key="no-probe", label="x", scope="platform", seeder="utils.system_init.seed", expected=1, source="x"
            ),
            SeedSet(
                key="broken-probe",
                label="x",
                scope="platform",
                seeder="x",
                expected=1,
                source="x",
                verify="no.such.probe",
            ),
            SeedSet(
                key="unrunnable", label="x", scope="platform", seeder="x", expected=1, source="x", verify="probe.raise"
            ),
            SeedSet(
                key="no-expectation",
                label="x",
                scope="platform",
                seeder=None,
                expected=None,
                source="x",
                verify="probe.ok",
            ),
            SeedSet(
                key="tenant-unmeasured",
                label="x",
                scope="tenant",
                seeder="x",
                expected=10,
                source="x",
                verify="probe.ok",
            ),
            SeedSet(
                key="satisfied", label="x", scope="platform", seeder="x", expected=1, source="x", verify="probe.ok"
            ),
            SeedSet(
                key="violated", label="x", scope="platform", seeder="x", expected=99, source="x", verify="probe.ok"
            ),
        )

        def _boom():
            raise RuntimeError("probe failed")

        probes = {"probe.ok": lambda: 5, "probe.raise": _boom}

        with (
            app.app_context(),
            patch("utils.seed_manifest.ALL_SEED_SETS", seed_sets),
            patch.object(bs, "_resolve", side_effect=lambda dotted: probes.get(dotted)),
            patch("utils.seed_manifest_probe.count_active_tenants", return_value=0),
            patch.object(bs, "_is_migration_command", return_value=False),
        ):
            assert bs.verify_seed_manifest() is None


class TestResolveDottedPath:
    """app/bootstrap.py lines 296-301."""

    def test_no_module_path_returns_none(self):
        assert bs._resolve("just_an_attribute") is None

    def test_valid_dotted_path_resolves(self):
        assert bs._resolve("utils.seed_manifest.ALL_SEED_SETS")

    def test_missing_attribute_returns_none(self):
        assert bs._resolve("utils.seed_manifest.DOES_NOT_EXIST") is None

    def test_missing_module_returns_none(self):
        assert bs._resolve("no_such_module_xyz.attr") is None


class TestIsolatedTransactionWithoutTransaction:
    """app/bootstrap.py line 329->exit: nothing to roll back."""

    def test_clear_with_no_active_transaction(self, app):
        from extensions import db

        session = MagicMock()
        session.get_transaction.return_value = None
        with patch.object(db, "session", session):
            with bs._isolated_transaction(app):
                pass
        session.rollback.assert_not_called()


class TestFactoryFallbackBranches:
    """app/factory.py - the branches that never fire on a healthy boot."""

    def test_upload_read_error_falls_back(self, monkeypatch, tmp_path):
        from config import Config

        class UploadConfig(Config):
            UPLOAD_ROOT = str(tmp_path)

        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with _minimal_app(config_class=UploadConfig) as app:
            with app.test_request_context("/"):
                with patch("os.path.isfile", side_effect=OSError("unreadable")):
                    with patch.object(app, "logger") as logger, contextlib.suppress(Exception):
                        app.send_static_file("uploads/probe.png")
            logger.warning.assert_called_once()

    def test_celery_process_skips_scheduler(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with patch("app.factory._running_in_celery_process", return_value=True), _minimal_app() as app:
            assert "auto_approval_scheduler" not in app.extensions

    def test_scheduler_disabled_by_config(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        monkeypatch.setenv("DISABLE_AUTO_APPROVAL_SCHEDULER", "1")
        with patch("app.factory._running_in_celery_process", return_value=False), _minimal_app() as app:
            assert "auto_approval_scheduler" not in app.extensions

    def test_scheduler_start_failure_is_not_fatal(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        monkeypatch.delenv("DISABLE_AUTO_APPROVAL_SCHEDULER", raising=False)
        with (
            patch("app.factory._running_in_celery_process", return_value=False),
            patch("services.auto_approval_service.schedule_auto_approval", side_effect=RuntimeError("no scheduler")),
            _minimal_app() as app,
        ):
            assert "auto_approval_scheduler" not in app.extensions

    def test_query_profiler_opt_in(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        monkeypatch.setenv("QUERY_PROFILE", "1")
        with patch("utils.query_profiler.enable_profiling") as profiling, _minimal_app() as app:
            assert app is not None
        profiling.assert_called_once()

    def test_schema_not_ready_skips_seeding(self, monkeypatch):
        monkeypatch.setenv("SKIP_SYSTEM_INTEGRITY", "1")
        with patch("app.bootstrap.verify_schema", return_value=False), _minimal_app() as app:
            assert app.extensions.get("schema_ready") is False

    def test_maintenance_failure_is_not_fatal(self, monkeypatch):
        with (
            patch.object(bs, "_is_migration_command", return_value=False),
            patch("services.maintenance_service.run_default_tenant_maintenance_api", side_effect=RuntimeError("boom")),
            _minimal_app() as app,
        ):
            assert app is not None
