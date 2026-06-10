"""CLI wrapper around GLProvisioningService for local development.

Registry-driven GL chart provisioning — replaces legacy GLAccountingSetupService.

Usage:
    python scripts/seed/run_gl_accounting_setup.py --plan
    python scripts/seed/run_gl_accounting_setup.py --plan --tenant-id 2
    python scripts/seed/run_gl_accounting_setup.py --execute --tenant-id 2
    python scripts/seed/run_gl_accounting_setup.py --execute
    python scripts/seed/run_gl_accounting_setup.py --validate
"""
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

from dotenv import load_dotenv
load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GL chart provisioning — registry-driven, idempotent.",
    )
    parser.add_argument(
        "--tenant-id",
        type=int,
        default=None,
        help="Target one tenant. Omit to process all tenants.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Show read-only plan (default behaviour).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually create accounts and mappings. Use with care.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run readiness validation after setup.",
    )
    args = parser.parse_args()

    if args.execute and not args.plan:
        print("=" * 60)
        print(" DRY-RUN PREVIEW (review before --execute)")
        print("=" * 60)
        args.plan = True

    from app import create_app
    from services.gl_provisioning_service import GLProvisioningService
    from models import Tenant

    app = create_app()
    with app.app_context():
        tenant_ids = [args.tenant_id] if args.tenant_id else [
            t.id for t in Tenant.query.filter_by(is_active=True).all()
        ]

        if args.plan:
            print("=" * 60)
            print(" PROVISION PLAN")
            print("=" * 60)
            for tid in tenant_ids:
                missing_accs = GLProvisioningService.get_missing_accounts(tid)
                missing_maps = GLProvisioningService.get_missing_mappings(tid)
                tenant = Tenant.query.get(tid)
                print(f"\nTenant {tid}: {tenant.name if tenant else '?'}")
                print(f"  Industry: {tenant.business_type if tenant else '?'}")
                if missing_accs:
                    print(f"  Missing accounts ({len(missing_accs)}):")
                    for a in missing_accs[:10]:
                        print(f"    + {a.code} {a.name_ar}")
                    if len(missing_accs) > 10:
                        print(f"    ... and {len(missing_accs) - 10} more")
                else:
                    print("  All base + industry accounts present.")
                if missing_maps:
                    print(f"  Missing mappings ({len(missing_maps)}):")
                    for m in missing_maps[:10]:
                        print(f"    + {m.concept_code} -> {m.account_code}")
                    if len(missing_maps) > 10:
                        print(f"    ... and {len(missing_maps) - 10} more")
                else:
                    print("  All concept mappings present.")

        if args.execute:
            print("\n" + "=" * 60)
            print(" EXECUTING PROVISIONING")
            print("=" * 60)
            for tid in tenant_ids:
                result = GLProvisioningService.provision_tenant(tid)
                tenant = Tenant.query.get(tid)
                print(f"\nTenant {tid}: {tenant.name if tenant else '?'}")
                print(f"  Created accounts: {result.created_accounts}")
                print(f"  Created mappings: {result.created_mappings}")
                print(f"  Skipped accounts: {result.skipped_accounts}")
                print(f"  Skipped mappings: {result.skipped_mappings}")
                if result.errors:
                    print(f"  Errors: {len(result.errors)}")
                    for err in result.errors:
                        print(f"    ! {err}")

        if args.validate:
            print("\n" + "=" * 60)
            print(" VALIDATION")
            print("=" * 60)
            all_ok = True
            for tid in tenant_ids:
                report = GLProvisioningService.validate_tenant_chart(tid)
                tenant = Tenant.query.get(tid)
                print(f"\nTenant {tid}: {tenant.name if tenant else '?'}")
                print(f"  Accounts OK: {report['accounts_ok']}")
                print(f"  Mappings OK: {report['mappings_ok']}")
                if report['missing_accounts']:
                    print(f"  Missing accounts: {len(report['missing_accounts'])}")
                if report['missing_mappings']:
                    print(f"  Missing mappings: {len(report['missing_mappings'])}")
                if report['errors']:
                    print(f"  Errors: {report['errors']}")
                    all_ok = False
                if not report['accounts_ok'] or not report['mappings_ok']:
                    all_ok = False
            return 0 if all_ok else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
