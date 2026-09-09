import click


def register_build_assets_command(app):
    @app.cli.command("build-assets")
    def build_assets():
        """Minify, hash, and compress static assets."""
        from utils.build_assets import build_all

        build_all()


def register_stock_commands(app):
    @app.cli.command("reconcile-stock")
    @click.option(
        "--tenant-id",
        type=int,
        default=None,
        help="Tenant ID to reconcile (default: all)",
    )
    @click.option("--commit", is_flag=True, help="Persist changes to database")
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
    @app.cli.command("backup")
    @click.option("--scope", default="system", help="Backup scope: system, tenant, branch, store")
    @click.option("--tenant-id", type=int, default=None, help="Tenant ID for tenant scope")
    @click.option("--branch-id", type=int, default=None, help="Branch ID for branch scope")
    def backup_cmd(scope, tenant_id, branch_id):
        """Run a manual backup."""
        from services.backup_service import BackupService

        result = BackupService.create_backup(
            description=f"CLI backup ({scope})",
            scope=scope,
            tenant_id=tenant_id,
            branch_id=branch_id,
        )
        if result and result.get("success"):
            click.echo(f"Backup created: {result.get('filename')}")
        else:
            click.echo(f"Backup failed: {result}")
            raise click.ClickException("Backup failed")


def register_restore_drill_command(app):
    @app.cli.command("restore-drill")
    @click.option(
        "--source",
        type=click.Choice(["auto", "local", "offsite"]),
        default="auto",
        help="Artifact source: auto tries offsite then falls back to local.",
    )
    @click.option("--filename", default=None, help="Drill a specific local backup filename instead of the newest.")
    def restore_drill_cmd(source, filename):
        """Restore latest backup into a scratch DB and sanity-check row counts.

        Scratch database name comes from RESTORE_DRILL_DB (never the live DB).
        Cron example (daily 03:15):
            15 3 * * * cd /path/to/Azad-UAE && flask restore-drill >> logs/restore_drill.log 2>&1
        """
        from services.restore_drill import RestoreDrillService

        result = RestoreDrillService.run_drill(source=source, filename=filename)
        status = "PASSED" if result.get("ok") else "FAILED"
        click.echo(
            f"Restore drill {status} (origin={result.get('artifact_origin')}, "
            f"duration={result.get('duration_seconds')}s)"
        )
        for table, count in sorted((result.get("counts") or {}).items()):
            click.echo(f"  {table}: {count} rows")
        if not result.get("ok"):
            for err in result.get("errors") or []:
                click.echo(f"ERROR: {err}")
            raise click.ClickException("Restore drill failed")


def register_reset_platform_db_command(app):
    @app.cli.command("reset-platform-db")
    @click.option("--yes", is_flag=True, help="Confirm destructive wipe of all data")
    def reset_platform_db(yes):
        """Wipe database and bootstrap clean SaaS platform (owner + roles, no tenants)."""
        if not yes:
            raise click.ClickException("Refusing to wipe DB without --yes")

        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy import text

        from extensions import db

        click.echo("Dropping all tables...")
        engine = db.engine
        insp = sa_inspect(engine)
        assert insp is not None, "SQLAlchemy inspector unavailable"
        with engine.begin() as conn:
            for table in insp.get_table_names():
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))

        click.echo("Creating schema from squashed baseline migration (explicit, no db.create_all)...")
        from flask_migrate import upgrade

        upgrade()

        click.echo("Bootstrapping clean platform (owner + roles)...")
        from utils.system_init import ensure_clean_platform

        ensure_clean_platform(app)

        from models.tenant import Tenant

        tenant_count = Tenant.query.count()
        click.echo(
            f"Done. Tenants in database: {tenant_count} (clean baseline -- tenants are provisioned from the Owner panel)"
        )
        click.echo("Create further tenants from Owner panel when ready.")


def register_sanitize_command(app):
    @app.cli.command("sanitize-legacy-industries")
    @click.option(
        "--commit",
        is_flag=True,
        help="Persist changes to the database (default: dry run)",
    )
    def sanitize_legacy_industries(commit):
        """Backfill legacy NULL business_type/industry and align GL ledgers for all tenants.

        1. Backfill: set business_type='general' and industry='retail' ONLY where currently NULL
           (direct SQL UPDATE).
        2. Retroactive ledger alignment: re-run the idempotent provision_tenant_gl for every tenant
           so missing industry GL accounts are seeded without duplicating existing entries.

        Dry run by default — nothing is written until --commit is supplied.
        """
        from sqlalchemy import text

        from extensions import db
        from models.tenant import Tenant
        from services.tenant_provisioning import provision_tenant_gl

        bt_null = db.session.execute(text("SELECT COUNT(*) FROM tenants WHERE business_type IS NULL")).scalar() or 0
        ind_null = db.session.execute(text("SELECT COUNT(*) FROM tenants WHERE industry IS NULL")).scalar() or 0

        if commit:
            db.session.execute(text("UPDATE tenants SET business_type = 'general' WHERE business_type IS NULL"))
            db.session.execute(text("UPDATE tenants SET industry = 'retail' WHERE industry IS NULL"))
            db.session.commit()
            click.echo(
                f"Backfilled business_type='general' on {bt_null} tenant(s); industry='retail' on {ind_null} tenant(s)."
            )
        else:
            click.echo(
                f"Dry run: would set business_type='general' on {bt_null} NULL row(s); "
                f"industry='retail' on {ind_null} NULL row(s). Use --commit to persist."
            )

        tenants = Tenant.query.all()
        click.echo(f"Aligning GL ledgers for {len(tenants)} tenant(s) (idempotent)...")
        for t in tenants:
            try:
                result = provision_tenant_gl(t.id)
                db.session.commit()
                label = getattr(t, "name", None) or getattr(t, "slug", None) or t.id
                click.echo(
                    f"  tenant {t.id} ({label}): GL accounts +{result.get('created_accounts', 0)} "
                    f"(skipped {result.get('skipped_accounts', 0)}), "
                    f"mappings +{result.get('created_mappings', 0)} "
                    f"(skipped {result.get('skipped_mappings', 0)})"
                )
            except Exception as e:
                db.session.rollback()
                click.echo(f"  tenant {t.id}: ERROR - {e}")
        click.echo("Done.")


def register_cli_commands(app):
    register_build_assets_command(app)
    register_stock_commands(app)
    register_backup_commands(app)
    register_restore_drill_command(app)
    register_reset_platform_db_command(app)
    register_sanitize_command(app)
