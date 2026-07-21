from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from cli_commands import (
    register_backup_commands,
    register_build_assets_command,
    register_cli_commands,
    register_stock_commands,
)


@pytest.fixture
def cli_app():
    app = Flask(__name__)
    register_cli_commands(app)
    return app


class TestBuildAssetsCommand:
    def test_build_assets_invokes_script(self, cli_app):
        with patch("utils.build_assets.build_all") as build_all:
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["build-assets"])
        assert result.exit_code == 0
        build_all.assert_called_once()


class TestStockCommands:
    def test_reconcile_stock_dry_run(self, cli_app):
        with patch(
            "services.stock_service.StockService.reconcile_stock",
            return_value={
                "created": 1,
                "updated": 2,
                "errors": 0,
                "total_pws": 10,
            },
        ) as reconcile:
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["reconcile-stock"])
        assert result.exit_code == 0
        reconcile.assert_called_once_with(tenant_id=None, commit=False)
        assert "Dry run" in result.output

    def test_reconcile_stock_commit(self, cli_app):
        with patch(
            "services.stock_service.StockService.reconcile_stock",
            return_value={
                "created": 0,
                "updated": 1,
                "errors": 0,
                "total_pws": 5,
            },
        ):
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["reconcile-stock", "--tenant-id", "3", "--commit"])
        assert result.exit_code == 0
        assert "Dry run" not in result.output


class TestBackupCommands:
    def test_backup_success(self, cli_app):
        with patch(
            "services.backup_service.BackupService.create_backup",
            return_value={
                "success": True,
                "filename": "backup.zip",
            },
        ):
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["backup"])
        assert result.exit_code == 0
        assert "backup.zip" in result.output

    def test_backup_failure(self, cli_app):
        with patch(
            "services.backup_service.BackupService.create_backup",
            return_value={"success": False},
        ):
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["backup", "--scope", "tenant", "--tenant-id", "1"])
        assert result.exit_code != 0


class TestRegisterFunctions:
    def test_individual_registrars(self):
        app = Flask(__name__)
        register_build_assets_command(app)
        register_stock_commands(app)
        register_backup_commands(app)
        assert "build-assets" in app.cli.commands
        assert "reconcile-stock" in app.cli.commands
        assert "backup" in app.cli.commands

    def test_all_commands_registered(self):
        app = Flask(__name__)
        register_cli_commands(app)
        assert "build-assets" in app.cli.commands
        assert "reconcile-stock" in app.cli.commands
        assert "backup" in app.cli.commands
        assert "reset-platform-db" in app.cli.commands
        assert "seed-demo" in app.cli.commands
        assert "sanitize-legacy-industries" in app.cli.commands


class TestResetPlatformDb:
    """Lines 58-93 — reset-platform-db command: --yes guard, table drop, migration, bootstrap."""

    def test_refuses_without_yes_flag(self, cli_app):
        runner = cli_app.test_cli_runner()
        result = runner.invoke(args=["reset-platform-db"])
        assert result.exit_code != 0
        assert "--yes" in result.output

    def test_reset_with_yes_executes_pipeline(self, cli_app):
        mock_engine = MagicMock()
        mock_insp = MagicMock()
        mock_insp.get_table_names.return_value = ["users", "tenants"]
        with (
            patch("extensions.db") as mock_db,
            patch("sqlalchemy.inspect", return_value=mock_insp),
            patch("flask_migrate.upgrade") as upgrade,
            patch("utils.system_init.ensure_clean_platform") as bootstrap,
            patch("models.tenant.Tenant") as tenant_cls,
        ):
            mock_db.engine = mock_engine
            mock_engine.begin.return_value.__enter__ = MagicMock()
            mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)
            tenant_cls.query.count.return_value = 0
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["reset-platform-db", "--yes"])
        assert result.exit_code == 0
        assert "Dropping all tables" in result.output
        upgrade.assert_called_once()
        bootstrap.assert_called_once()

    def test_reset_inspepector_assertion(self, cli_app):
        with (
            patch("extensions.db") as mock_db,
            patch("sqlalchemy.inspect", return_value=None),
        ):
            mock_db.engine = MagicMock()
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["reset-platform-db", "--yes"])
        assert result.exit_code != 0


class TestSeedDemo:
    """Lines 96-113 — seed-demo command: existing tenant, --force, fresh seed."""

    def test_existing_tenant_without_force_returns_early(self, cli_app):
        mock_tenant = MagicMock()
        with patch("models.tenant.Tenant") as tenant_cls:
            tenant_cls.query.filter_by.return_value.first.return_value = mock_tenant
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["seed-demo"])
        assert result.exit_code == 0
        assert "already exists" in result.output

    def test_seed_demo_no_existing_tenant_proceeds(self, cli_app):
        with (
            patch("models.tenant.Tenant") as tenant_cls,
            patch("app.create_app") as create_app,
            patch("cli_commands._do_seed_demo") as do_seed,
        ):
            tenant_cls.query.filter_by.return_value.first.return_value = None
            mock_app = MagicMock()
            create_app.return_value = mock_app
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["seed-demo"])
        assert result.exit_code == 0
        do_seed.assert_called_once()

    def test_seed_demo_with_force_proceeds(self, cli_app):
        mock_tenant = MagicMock()
        with (
            patch("models.tenant.Tenant") as tenant_cls,
            patch("app.create_app") as create_app,
            patch("cli_commands._do_seed_demo") as do_seed,
        ):
            tenant_cls.query.filter_by.return_value.first.return_value = mock_tenant
            create_app.return_value = MagicMock()
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["seed-demo", "--force"])
        assert result.exit_code == 0
        assert "--force" in result.output
        do_seed.assert_called_once()


class TestSanitizeLegacyIndustries:
    """Lines 860-914 — sanitize-legacy-industries: dry run, commit, GL alignment."""

    def test_dry_run_reports_nulls(self, cli_app):
        with (
            patch("extensions.db") as mock_db,
            patch("models.tenant.Tenant") as tenant_cls,
            patch(
                "services.tenant_provisioning.provision_tenant_gl",
                return_value={
                    "created_accounts": 0,
                    "skipped_accounts": 5,
                    "created_mappings": 0,
                    "skipped_mappings": 3,
                },
            ),
        ):
            mock_session = MagicMock()
            mock_db.session = mock_session
            mock_session.execute.side_effect = lambda q, *a, **k: MagicMock(scalar=MagicMock(return_value=2))
            tenant = MagicMock(id=1, name="Test", slug="test")
            tenant_cls.query.all.return_value = [tenant]
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["sanitize-legacy-industries"])
        assert result.exit_code == 0
        assert "Dry run" in result.output

    def test_commit_persists_and_aligns(self, cli_app):
        with (
            patch("extensions.db") as mock_db,
            patch("models.tenant.Tenant") as tenant_cls,
            patch(
                "services.tenant_provisioning.provision_tenant_gl",
                return_value={
                    "created_accounts": 2,
                    "skipped_accounts": 1,
                    "created_mappings": 1,
                    "skipped_mappings": 0,
                },
            ),
        ):
            mock_session = MagicMock()
            mock_db.session = mock_session
            mock_session.execute.side_effect = lambda q, *a, **k: MagicMock(scalar=MagicMock(return_value=1))
            tenant = MagicMock(id=1, name="T1", slug="t1")
            tenant_cls.query.all.return_value = [tenant]
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["sanitize-legacy-industries", "--commit"])
        assert result.exit_code == 0
        assert "Backfilled" in result.output
        assert "+2" in result.output

    def test_gl_alignment_error_handled(self, cli_app):
        with (
            patch("extensions.db") as mock_db,
            patch("models.tenant.Tenant") as tenant_cls,
            patch(
                "services.tenant_provisioning.provision_tenant_gl",
                side_effect=RuntimeError("GL fail"),
            ),
        ):
            mock_session = MagicMock()
            mock_db.session = mock_session
            mock_session.execute.side_effect = lambda q, *a, **k: MagicMock(scalar=MagicMock(return_value=0))
            tenant = MagicMock(id=5, name="Err", slug="err")
            tenant_cls.query.all.return_value = [tenant]
            runner = cli_app.test_cli_runner()
            result = runner.invoke(args=["sanitize-legacy-industries", "--commit"])
        assert result.exit_code == 0
        assert "ERROR" in result.output
