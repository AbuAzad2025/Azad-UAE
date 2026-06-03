"""
Rebuild GL Accounts Tree for All Tenants
---
تجديد شجرة الحسابات المحاسبية لجميع المستأجرين باستخدام GLTreeBuilder
هذه العملية تقوم:
1. بإنشاء أو تصحيح جميع الحسابات الأساسية (58 حساب)
2. بالتحقق من سلامة الشجرة بعد التحديث
3. بإيقاف الحسابات الزائدة (إذا طلبت)
"""

import os
import sys
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set environment variables
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Tenant
from services.gl_tree_builder import GLTreeBuilder


def rebuild_gl_tree(cleanup_extra=False):
    """إعادة بناء شجرة الحسابات لجميع المستأجرين."""
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild GL account tree for all tenants")
    parser.add_argument("--cleanup", action="store_true", help="Deactivate extra accounts not in core tree")
    args = parser.parse_args()
    
    rebuild_gl_tree(cleanup_extra=args.cleanup)

