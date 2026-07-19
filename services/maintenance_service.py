"""
Maintenance services for AZADEXA ERP.

Provides internal API endpoints for the Owner Dashboard database maintenance tools.
"""

import os
from sqlalchemy import create_engine, func, select, text, update, Table, MetaData
from extensions import db
from utils.safe_sql import assert_known_column


class MaintenanceService:
    """Database maintenance operations for owner dashboard."""

    @staticmethod
    def fix_cost_centers_index() -> dict:
        """
        Drop old unique index on code and clean up NULL tenant_id cost centers.

        This operation:
        1. Drops the deprecated 'ix_cost_centers_code' index if it exists
        2. Deletes orphaned cost centers that still have NULL tenant_id (legacy data)

        Returns:
            dict: Result with keys 'dropped_index' (bool), 'deleted_rows' (int)
        """
        engine = create_engine(
            os.environ.get(
                "DATABASE_URL",
                "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae",
            )
        )
        result: dict = {"dropped_index": False, "deleted_rows": 0}
        with engine.begin() as conn:
            # Drop old unique index on code
            try:
                conn.execute(text("DROP INDEX IF EXISTS ix_cost_centers_code"))
                result["dropped_index"] = True
                print("✅ Dropped old unique index on code")
            except Exception as e:
                print(f"Note: {e}")

            # Delete existing cost centers (they have NULL tenant_id)
            r = conn.execute(text("DELETE FROM cost_centers WHERE tenant_id IS NULL"))
            result["deleted_rows"] = r.rowcount
            print("✅ Deleted old cost centers with NULL tenant_id")
        return result

    @staticmethod
    def rebuild_gl_tree(cleanup_extra=False):
        """
        Rebuild GL accounts tree for all tenants.

        Args:
            cleanup_extra (bool): If True, deactivate extra accounts not in core tree

        Returns:
            dict: Rebuild report with statistics for all tenants
        """
        from app import create_app
        from models import Tenant
        from services.gl_tree_builder import GLTreeBuilder

        app = create_app()
        with app.app_context():
            # Get all active tenants
            tenants = Tenant.query.filter_by(is_active=True).all()
            print(f"Found {len(tenants)} active tenants")
            print("=" * 80)

            total_created = 0
            total_updated = 0
            total_converted = 0
            total_deactivated = 0
            tenants_updated = 0
            tenant_reports = []

            for tenant in tenants:
                print(
                    f"\nProcessing Tenant: {tenant.name} (ID: {tenant.id}, Slug: {tenant.slug})"
                )
                print("-" * 80)

                try:
                    # Build the GL tree
                    audit_report = GLTreeBuilder.build(
                        tenant.id, cleanup_extra=cleanup_extra, commit=True
                    )

                    # Print results
                    created_count = len(audit_report["created"])
                    updated_count = len(audit_report["updated"])
                    converted_count = len(audit_report["converted"])
                    deactivated_count = len(audit_report["deactivated"])
                    errors_count = len(audit_report["errors"])

                    if (
                        created_count
                        or updated_count
                        or converted_count
                        or deactivated_count
                    ):
                        tenants_updated += 1

                    total_created += created_count
                    total_updated += updated_count
                    total_converted += converted_count
                    total_deactivated += deactivated_count

                    print(f"  Created: {created_count} accounts")
                    print(f"  Updated: {updated_count} accounts")
                    print(f"  Converted: {converted_count} accounts")
                    if cleanup_extra:
                        print(f"  Deactivated: {deactivated_count} extra accounts")

                    if errors_count:
                        print(f"  WARNING: {errors_count} errors!")
                        for err in audit_report["errors"]:
                            print(f"    - {err['code']}: {err['error']}")

                    # Validate the tree
                    validation = GLTreeBuilder.validate_tree(tenant.id)

                    if validation["valid"]:
                        print("  Validation: ✅ Tree is valid!")
                        print(f"  Total accounts: {validation['total_accounts']}")
                        print(
                            f"  Core accounts present: {validation['core_accounts_found']}"
                        )
                        if validation["extra_accounts"]:
                            print(
                                f"  Extra accounts found: {len(validation['extra_accounts'])}"
                            )
                    else:
                        print("  Validation: ❌ Tree has issues!")
                        for issue in validation["issues"]:
                            print(f"    - {issue['code']}: {issue['issue']}")

                        if validation["missing_core_accounts"]:
                            print(
                                f"    - Missing {len(validation['missing_core_accounts'])} core accounts!"
                            )

                    tenant_reports.append(
                        {
                            "tenant_id": tenant.id,
                            "tenant_name": tenant.name,
                            "tenant_slug": tenant.slug,
                            "created": created_count,
                            "updated": updated_count,
                            "converted": converted_count,
                            "deactivated": deactivated_count,
                            "errors": errors_count,
                            "validation": validation,
                        }
                    )

                except Exception as e:
                    db.session.rollback()
                    print(f"  ERROR: Failed to process tenant {tenant.id}: {str(e)}")
                    import traceback

                    traceback.print_exc()

            print("\n" + "=" * 80)
            print("✅ Rebuild Complete!")
            print("=" * 80)
            print(f"  Tenants updated: {tenants_updated}")
            print(f"  Total accounts created: {total_created}")
            print(f"  Total accounts updated: {total_updated}")
            print(f"  Total accounts converted: {total_converted}")
            if cleanup_extra:
                print(f"  Total accounts deactivated: {total_deactivated}")
            print("\nDone!")

            return {
                "tenants_updated": tenants_updated,
                "total_created": total_created,
                "total_updated": total_updated,
                "total_converted": total_converted,
                "total_deactivated": total_deactivated,
                "tenants": tenant_reports,
            }

    # ──────────────────────────────────────────────────────────────────
    # Default Tenant Maintenance
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _default_for_type(data_type: str):
        dt = (data_type or "").lower()
        if "boolean" in dt:
            return False
        if any(
            k in dt
            for k in ("int", "numeric", "decimal", "money", "real", "double", "float")
        ):
            return 0
        if "json" in dt:
            return "{}"
        if any(k in dt for k in ("timestamp", "date", "time")):
            return "now()"
        if "uuid" in dt:
            import uuid

            return str(uuid.uuid4())
        return ""

    @staticmethod
    def fix_default_tenant_metadata(dry_run: bool = False) -> list:
        """
        Fill NOT NULL columns (no DB default) that are NULL on the default tenant row.

        Args:
            dry_run: If True, only report what would be done without making changes

        Returns:
            list: List of columns that were/would be patched
        """
        engine = create_engine(
            os.environ.get(
                "DATABASE_URL",
                "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae",
            )
        )
        fixed = []
        with engine.begin() as conn:
            cols = conn.execute(
                text(
                    "SELECT column_name, data_type, column_default FROM "
                    "information_schema.columns WHERE table_schema='public' "
                    "AND table_name='tenants' AND is_nullable='NO'"
                )
            ).fetchall()
            for name, dtype, default in cols:
                if default is not None and str(default).upper() != "NULL":
                    continue  # DB will supply the default on insert/update
                assert_known_column(engine, "tenants", name)
                tenants_tbl = Table("tenants", MetaData(), autoload_with=engine)
                cur = conn.execute(
                    select(tenants_tbl.c[name])
                    .where(tenants_tbl.c.slug == "default")
                    .limit(1)
                ).scalar()
                if cur is None:
                    val = MaintenanceService._default_for_type(dtype)
                    fixed.append(f"tenants.{name} <- {val!r} ({dtype})")
                    if not dry_run:
                        if isinstance(val, str) and val == "now()":
                            conn.execute(
                                update(tenants_tbl)
                                .where(tenants_tbl.c.slug == "default")
                                .values({name: func.now()})
                            )
                        else:
                            conn.execute(
                                update(tenants_tbl)
                                .where(tenants_tbl.c.slug == "default")
                                .values({name: val})
                            )
        return fixed

    @staticmethod
    def regenerate_default_backup(dry_run: bool = False) -> str:
        """Create a fresh, schema-current scoped backup of the default tenant."""
        from flask import current_app
        from services.backup_service import BackupService

        app = current_app._get_current_object() if current_app else None  # type: ignore[attr-defined]
        if app is None:
            from app import create_app

            app = create_app()
        with app.app_context():
            BackupService.initialize()
            if dry_run:
                return "(skipped: --check mode)"
            # Find default tenant
            from models.tenant import Tenant

            demo = Tenant.query.filter_by(slug="default").first()
            if not demo:
                return "No default tenant found"
            result = BackupService.create_backup(
                scope="tenant", tenant_id=demo.id, manual=True
            )
        if isinstance(result, dict):
            return (
                result.get("filename")
                or result.get("manifest", {}).get("backup_scope")
                or str(result)
            )
        return str(result)

    @staticmethod
    def run_default_tenant_maintenance(dry_run: bool = False) -> dict:
        """
        Run full default tenant maintenance (patch + backup).

        Args:
            dry_run: If True, only report what would be done

        Returns:
            dict: Maintenance result with keys:
                - 'patched': list of columns patched
                - 'backup_regenerated': str or None
                - 'action_needed': bool
                - 'conflicts': list of conflicts
        """

        engine = create_engine(
            os.environ.get(
                "DATABASE_URL",
                "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae",
            )
        )

        # Check for conflicts
        conflicts = []
        with engine.connect() as conn:
            dup_slug = conn.execute(
                text(
                    "SELECT count(*) FROM tenants WHERE slug = 'default' "
                    "AND id <> (SELECT id FROM tenants WHERE slug = 'default' LIMIT 1)"
                )
            ).scalar()
            if dup_slug:
                conflicts.append(f"{dup_slug} other tenant(s) also use slug 'default'")

        fixed = MaintenanceService.fix_default_tenant_metadata(dry_run=dry_run)

        backup_fn = None
        if not dry_run:
            backup_fn = MaintenanceService.regenerate_default_backup(dry_run=dry_run)

        return {
            "patched": fixed,
            "backup_regenerated": backup_fn,
            "action_needed": len(fixed) > 0 or backup_fn is not None,
            "conflicts": conflicts,
        }

    # ──────────────────────────────────────────────────────────────────
    # Test Database Cleanup
    # ──────────────────────────────────────────────────────────────────

    STALE_TEST_DATABASES = [
        "azadexa_dev",
        "azadexa_test",
        "azad_accounting_sys_dev",
        "azad_diag_restore",
        "azad_diag2",
        "azad_repro",
        "azad_verify_live",
        "azad_verify_dry",
        "azad_uae_loadtest",
        "azad_uae_test",
    ]

    @staticmethod
    def cleanup_test_databases(dry_run: bool = False) -> dict:
        """
        Drop stale test databases, keeping only the main production DB.

        Args:
            dry_run: If True, only report what would be dropped

        Returns:
            dict: Results with keys:
                - 'dropped': list of dropped databases
                - 'failed': list of (db, error) tuples
                - 'remaining': list of remaining azad databases
        """
        engine = create_engine(
            os.environ.get(
                "DATABASE_URL",
                "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae",
            ).replace("postgresql+psycopg2", "postgresql"),
            isolation_level="AUTOCOMMIT",
        )
        dropped = []
        failed = []

        with engine.connect() as conn:
            for db in MaintenanceService.STALE_TEST_DATABASES:
                try:
                    if not dry_run:
                        conn.execute(text(f"DROP DATABASE IF EXISTS {db} WITH (FORCE)"))
                    dropped.append(db)
                except Exception as e:
                    failed.append((db, str(e)))

            # List remaining azad databases
            result = conn.execute(
                text("SELECT datname FROM pg_database WHERE datname LIKE '%azad%'")
            ).fetchall()
            remaining = [r[0] for r in result]

        return {
            "dropped": dropped,
            "failed": failed,
            "remaining": remaining,
        }


# Entry points for dashboard API


def fix_cost_centers_index_api():
    """API endpoint for owner dashboard to fix cost centers index."""
    return MaintenanceService.fix_cost_centers_index()


def rebuild_gl_tree_api(cleanup_extra=False):
    """API endpoint for owner dashboard to rebuild GL account tree."""
    return MaintenanceService.rebuild_gl_tree(cleanup_extra=cleanup_extra)


def fix_default_tenant_metadata_api(dry_run=False):
    """API endpoint for owner dashboard to fix default tenant metadata."""
    return MaintenanceService.fix_default_tenant_metadata(dry_run=dry_run)


def regenerate_default_backup_api(dry_run=False):
    """API endpoint for owner dashboard to regenerate default tenant backup."""
    return MaintenanceService.regenerate_default_backup(dry_run=dry_run)


def run_default_tenant_maintenance_api(dry_run=False):
    """API endpoint for owner dashboard to run full default tenant maintenance."""
    return MaintenanceService.run_default_tenant_maintenance(dry_run=dry_run)


def cleanup_test_databases_api(dry_run=False):
    """API endpoint for owner dashboard to cleanup stale test databases."""
    return MaintenanceService.cleanup_test_databases(dry_run=dry_run)
