import click


def register_build_assets_command(app):
    @app.cli.command('build-assets')
    def build_assets():
        """Minify, hash, and compress static assets."""
        from utils.build_assets import build_all
        build_all()

def register_stock_commands(app):
    @app.cli.command('reconcile-stock')
    @click.option('--tenant-id', type=int, default=None, help='Tenant ID to reconcile (default: all)')
    @click.option('--commit', is_flag=True, help='Persist changes to database')
    def reconcile_stock(tenant_id, commit):
        """Reconcile ProductWarehouseStock with StockMovement and sync current_stock."""
        from services.stock_service import StockService
        result = StockService.reconcile_stock(tenant_id=tenant_id, commit=commit)
        click.echo(f"Created PWS records: {result['created']}")
        click.echo(f"Updated PWS/products: {result['updated']}")
        click.echo(f"Errors: {result['errors']}")
        click.echo(f"Total PWS records: {result['total_pws']}")
        if not commit:
            click.echo("Dry run — use --commit to persist.")
        return result

def register_backup_commands(app):
    @app.cli.command('backup')
    @click.option('--scope', default='system', help='Backup scope: system, tenant, branch, store')
    @click.option('--tenant-id', type=int, default=None, help='Tenant ID for tenant scope')
    @click.option('--branch-id', type=int, default=None, help='Branch ID for branch scope')
    def backup_cmd(scope, tenant_id, branch_id):
        """Run a manual backup."""
        from services.backup_service import BackupService
        result = BackupService.create_backup(
            manual=True,
            description=f"CLI backup ({scope})",
            scope=scope,
            tenant_id=tenant_id,
            branch_id=branch_id,
        )
        if result and result.get('success'):
            click.echo(f"Backup created: {result.get('filename')}")
        else:
            click.echo(f"Backup failed: {result}")
            raise click.ClickException("Backup failed")

def register_reset_platform_db_command(app):
    @app.cli.command('reset-platform-db')
    @click.option('--yes', is_flag=True, help='Confirm destructive wipe of all data')
    def reset_platform_db(yes):
        """Wipe database and bootstrap clean SaaS platform (owner + roles, no tenants)."""
        if not yes:
            raise click.ClickException('Refusing to wipe DB without --yes')

        from extensions import db
        from sqlalchemy import inspect as sa_inspect, text

        click.echo('Dropping all tables...')
        engine = db.engine
        with engine.begin() as conn:
            for table in sa_inspect(engine).get_table_names():
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))

        click.echo('Creating schema from models...')
        db.create_all()

        click.echo('Bootstrapping clean platform (no tenant seeds)...')
        from utils.system_init import ensure_clean_platform
        ensure_clean_platform(app)

        click.echo('Stamping Alembic heads...')
        from flask_migrate import stamp
        stamp()

        from models.tenant import Tenant
        tenant_count = Tenant.query.count()
        click.echo(f'Done. Tenants in database: {tenant_count} (expected 0)')
        click.echo('Create tenants from Owner panel when ready.')


def register_cli_commands(app):
    register_build_assets_command(app)
    register_stock_commands(app)
    register_backup_commands(app)
    register_reset_platform_db_command(app)
