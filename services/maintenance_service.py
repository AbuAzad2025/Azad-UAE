"""
Maintenance services for AZADEXA ERP.

Provides internal API endpoints for the Owner Dashboard database maintenance tools.
"""

import os
from sqlalchemy import create_engine, text
from extensions import db


class MaintenanceService:
    """Database maintenance operations for owner dashboard."""

    @staticmethod
    def fix_cost_centers_index():
        """
        Drop old unique index on code and clean up NULL tenant_id cost centers.

        This operation:
        1. Drops the deprecated 'ix_cost_centers_code' index if it exists
        2. Deletes orphaned cost centers that still have NULL tenant_id (legacy data)
        """
        engine = create_engine(os.environ.get("DATABASE_URL", "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"))
        with engine.begin() as conn:
            # Drop old unique index on code
            try:
                conn.execute(text('DROP INDEX IF EXISTS ix_cost_centers_code'))
                print('✅ Dropped old unique index on code')
            except Exception as e:
                print(f'Note: {e}')
            
            # Delete existing cost centers (they have NULL tenant_id)
            conn.execute(text('DELETE FROM cost_centers WHERE tenant_id IS NULL'))
            print('✅ Deleted old cost centers with NULL tenant_id')

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
                print(f"\nProcessing Tenant: {tenant.name} (ID: {tenant.id}, Slug: {tenant.slug})")
                print("-" * 80)

                try:
                    # Build the GL tree
                    audit_report = GLTreeBuilder.build(tenant.id, cleanup_extra=cleanup_extra, commit=True)

                    # Print results
                    created_count = len(audit_report['created'])
                    updated_count = len(audit_report['updated'])
                    converted_count = len(audit_report['converted'])
                    deactivated_count = len(audit_report['deactivated'])
                    errors_count = len(audit_report['errors'])

                    if created_count or updated_count or converted_count or deactivated_count:
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
                        for err in audit_report['errors']:
                            print(f"    - {err['code']}: {err['error']}")

                    # Validate the tree
                    validation = GLTreeBuilder.validate_tree(tenant.id)

                    if validation['valid']:
                        print(f"  Validation: ✅ Tree is valid!")
                        print(f"  Total accounts: {validation['total_accounts']}")
                        print(f"  Core accounts present: {validation['core_accounts_found']}")
                        if validation['extra_accounts']:
                            print(f"  Extra accounts found: {len(validation['extra_accounts'])}")
                    else:
                        print(f"  Validation: ❌ Tree has issues!")
                        for issue in validation['issues']:
                            print(f"    - {issue['code']}: {issue['issue']}")

                        if validation['missing_core_accounts']:
                            print(f"    - Missing {len(validation['missing_core_accounts'])} core accounts!")

                    tenant_reports.append({
                        'tenant_id': tenant.id,
                        'tenant_name': tenant.name,
                        'tenant_slug': tenant.slug,
                        'created': created_count,
                        'updated': updated_count,
                        'converted': converted_count,
                        'deactivated': deactivated_count,
                        'errors': errors_count,
                        'validation': validation,
                    })

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
                'tenants_updated': tenants_updated,
                'total_created': total_created,
                'total_updated': total_updated,
                'total_converted': total_converted,
                'total_deactivated': total_deactivated,
                'tenants': tenant_reports,
            }


# Entry points for dashboard API

def fix_cost_centers_index_api():
    """API endpoint for owner dashboard to fix cost centers index."""
    return MaintenanceService.fix_cost_centers_index()


def rebuild_gl_tree_api(cleanup_extra=False):
    """API endpoint for owner dashboard to rebuild GL account tree."""
    return MaintenanceService.rebuild_gl_tree(cleanup_extra=cleanup_extra)
