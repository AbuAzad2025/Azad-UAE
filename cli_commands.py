import click


def register_build_assets_command(app):
    @app.cli.command('build-assets')
    def build_assets():
        """Minify, hash, and compress static assets."""
        from scripts.build_assets import build_all
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

def register_cli_commands(app):
    register_build_assets_command(app)
    register_stock_commands(app)
    register_backup_commands(app)
