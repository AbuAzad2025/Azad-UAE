from __future__ import annotations

from unittest.mock import patch

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
