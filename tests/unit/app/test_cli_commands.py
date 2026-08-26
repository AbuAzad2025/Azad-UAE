from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from cli_commands import (
    register_backup_commands,
    register_build_assets_command,
    register_cli_commands,
    register_restore_drill_command,
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


class TestRestoreDrillCommand:
    """flask restore-drill — service is mocked; scratch-db steps never run here."""

    @pytest.fixture
    def drill_app(self):
        app = Flask(__name__)
        register_restore_drill_command(app)
        return app

    def test_registered_alongside_backup(self):
        app = Flask(__name__)
        register_cli_commands(app)
        assert "restore-drill" in app.cli.commands
        assert "backup" in app.cli.commands

    def test_success_prints_counts(self, drill_app):
        drill_result = {
            "ok": True,
            "artifact_origin": "offsite",
            "duration_seconds": 1.5,
            "counts": {"purchases": 2, "sales": 7, "users": 3},
            "errors": [],
        }
        with patch(
            "services.restore_drill.RestoreDrillService.run_drill",
            return_value=drill_result,
        ) as run_drill:
            runner = drill_app.test_cli_runner()
            result = runner.invoke(args=["restore-drill"])
        assert result.exit_code == 0
        assert "PASSED" in result.output
        assert "users: 3 rows" in result.output
        assert "sales: 7 rows" in result.output
        run_drill.assert_called_once_with(source="auto", filename=None)

    def test_failure_exits_nonzero_and_lists_errors(self, drill_app):
        drill_result = {
            "ok": False,
            "artifact_origin": "local",
            "duration_seconds": 0.4,
            "counts": {},
            "errors": ["restore: pg_restore not found"],
        }
        with patch(
            "services.restore_drill.RestoreDrillService.run_drill",
            return_value=drill_result,
        ):
            runner = drill_app.test_cli_runner()
            result = runner.invoke(args=["restore-drill"])
        assert result.exit_code != 0
        assert "FAILED" in result.output
        assert "pg_restore not found" in result.output

    def test_options_forwarded_to_service(self, drill_app):
        with patch(
            "services.restore_drill.RestoreDrillService.run_drill",
            return_value={"ok": True, "counts": {}, "errors": [], "duration_seconds": 0},
        ) as run_drill:
            runner = drill_app.test_cli_runner()
            result = runner.invoke(args=["restore-drill", "--source", "local", "--filename", "x.tar.gz"])
        assert result.exit_code == 0
        run_drill.assert_called_once_with(source="local", filename="x.tar.gz")

    def test_invalid_source_rejected(self, drill_app):
        runner = drill_app.test_cli_runner()
        result = runner.invoke(args=["restore-drill", "--source", "ftp"])
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


class TestSeedPackagesCommand:
    """flask seed-packages — real idempotent upsert against the test database."""

    def test_creates_then_updates_idempotently(self, app):
        runner = app.test_cli_runner()
        first = runner.invoke(args=["seed-packages"])
        assert first.exit_code == 0, f"{first.output}\nEXC={first.exception!r}"
        assert "created=['basic', 'pro', 'enterprise']" in first.output
        assert "updated=[]" in first.output

        second = runner.invoke(args=["seed-packages"])
        assert second.exit_code == 0, f"{second.output}\nEXC={second.exception!r}"
        assert "created=[]" in second.output
        assert "updated=['basic', 'pro', 'enterprise']" in second.output


class TestSeedDemoIntegration:
    """Real end-to-end execution of the demo seeder against the test database.

    Covers the command wrapper, the full seeding pipeline (branches,
    warehouses, users, products, partners, customers, suppliers, sales via
    SaleService, purchases via PurchaseService/PaymentService, expenses,
    salary advances, POS sessions, returns via ReturnService) and the
    destructive re-seed wipe path.
    """

    def _demo_counts(self, app):
        from models import PosSession, SalaryAdvance
        from models.branch import Branch
        from models.cash_box import CashBox
        from models.customer import Customer
        from models.expense import Expense
        from models.partner import Partner
        from models.product import Product
        from models.sale import Sale
        from models.supplier import Supplier
        from models.tenant import Tenant
        from models.tenant_store import TenantStore
        from models.user import User
        from models.warehouse import Warehouse

        with app.app_context():
            tenant = Tenant.query.filter_by(slug="demo").one()
            tid = tenant.id
            summary = {
                "business_type": tenant.business_type,
                "enable_pos": tenant.enable_pos,
                "enable_payroll": tenant.enable_payroll,
                "store_slug": TenantStore.query.filter_by(tenant_id=tid).one().store_slug,
                "admin_ok": User.query.filter_by(username="demo_admin").one().check_password("Demo@2026"),
                "branches": Branch.query.filter_by(tenant_id=tid).count(),
                "warehouses": Warehouse.query.filter_by(tenant_id=tid).count(),
                "cashboxes": CashBox.query.filter_by(tenant_id=tid).count(),
                "products": Product.query.filter_by(tenant_id=tid).count(),
                "partners": Partner.query.filter_by(tenant_id=tid).count(),
                "customers": Customer.query.filter_by(tenant_id=tid).count(),
                "suppliers": Supplier.query.filter_by(tenant_id=tid).count(),
                "sales": Sale.query.filter_by(tenant_id=tid).count(),
                "expenses": Expense.query.filter_by(tenant_id=tid).count(),
                "pos_sessions": PosSession.query.filter_by(tenant_id=tid).count(),
                "advances": SalaryAdvance.query.filter_by(tenant_id=tid).count(),
                "users": User.query.filter_by(tenant_id=tid).count(),
            }
        return summary

    def test_01_full_seed_builds_complete_demo_dataset(self, app):
        runner = app.test_cli_runner()
        result = runner.invoke(args=["seed-demo"])
        assert result.exit_code == 0, f"{result.output}\nEXC={result.exception!r}"
        assert "Demo tenant seeded successfully" in result.output

        s = self._demo_counts(app)
        assert s["business_type"] == "multi_branch_retail"
        assert s["enable_pos"] is True
        assert s["enable_payroll"] is True
        assert s["store_slug"] == "demo"
        assert s["admin_ok"] is True
        assert s["branches"] == 4
        assert s["warehouses"] == 4
        assert s["cashboxes"] == 4
        assert s["products"] >= 17
        assert s["partners"] == 5
        assert s["customers"] == 5
        assert s["suppliers"] == 5
        assert s["expenses"] == 3
        assert s["pos_sessions"] == 2
        assert s["advances"] >= 1
        assert s["users"] == 11
        assert s["sales"] >= 3

    def test_02_returns_posted_through_return_service(self, app):
        from models import ProductReturn
        from models.tenant import Tenant

        with app.app_context():
            tenant = Tenant.query.filter_by(slug="demo").one()
            returns = ProductReturn.query.filter_by(tenant_id=tenant.id).count()
        assert returns >= 1

    def test_03_customer_balances_recomputed_from_sales(self, app):
        from decimal import Decimal

        from models.customer import Customer
        from models.tenant import Tenant

        with app.app_context():
            tenant = Tenant.query.filter_by(slug="demo").one()
            balances = [c.balance for c in Customer.query.filter_by(tenant_id=tenant.id).all()]
        assert balances and all(isinstance(b, Decimal) for b in balances)

    def test_04_second_run_without_force_short_circuits(self, app):
        from models.product import Product
        from models.tenant import Tenant

        with app.app_context():
            before = Product.query.filter_by(tenant_id=Tenant.query.filter_by(slug="demo").first().id).count()
        runner = app.test_cli_runner()
        result = runner.invoke(args=["seed-demo"])
        assert result.exit_code == 0, result.output
        assert "already exists" in result.output
        assert "re-seeding with --force" not in result.output
        with app.app_context():
            after = Product.query.filter_by(tenant_id=Tenant.query.filter_by(slug="demo").first().id).count()
        assert after == before

    def test_05_direct_reseed_wipes_existing_demo_data(self, app, capsys):
        import cli_commands
        from models.branch import Branch
        from models.product import Product
        from models.tenant import Tenant

        with app.app_context():
            cli_commands._do_seed_demo(app)
        captured = capsys.readouterr().out
        assert "Dropping existing demo data..." in captured
        assert "Old demo data removed." in captured
        assert "Demo tenant seeded successfully" in captured

        with app.app_context():
            tenant = Tenant.query.filter_by(slug="demo").one()
            assert Branch.query.filter_by(tenant_id=tenant.id).count() == 4
            skus = [p.sku for p in Product.query.filter_by(tenant_id=tenant.id).all()]
        assert any(sku.startswith("DEMO-MAIN-") for sku in skus)
