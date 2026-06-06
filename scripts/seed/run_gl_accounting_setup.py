"""CLI wrapper around GLAccountingSetupService for local development.

Thin wrapper – all business logic lives in ``services/gl_accounting_setup.py``.

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
        description="GL accounting setup – plan or execute concept mappings for tenants.",
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
        help="Run Phase-1F readiness validation after setup.",
    )
    args = parser.parse_args()

    if args.execute and not args.plan:
        # When --execute is given without --plan, still show the plan first
        # so the operator can review before confirming.
        print("=" * 60)
        print(" DRY-RUN PREVIEW (review before --execute)")
        print("=" * 60)
        args.plan = True

    from app import create_app
    from services.gl_accounting_setup import GLAccountingSetupService

    app = create_app()
    with app.app_context():
        if args.tenant_id:
            plans = [GLAccountingSetupService.plan(args.tenant_id)]
        else:
            plans = GLAccountingSetupService.plan_all()

        for plan in plans:
            if plan is None:
                continue
            print(f"\nTenant {plan.tenant_id}: {plan.tenant_name}")
            for action in plan.actions:
                if action.action_type == "create_account":
                    print(f"  [CREATE] {action.concept_code:26} -> {action.reason}")
                elif action.action_type == "map_concept":
                    print(
                        f"  [MAP]    {action.concept_code:26} -> "
                        f"{action.gl_account_code} ({action.gl_account_name})"
                    )
                elif action.action_type == "skip":
                    print(f"  [SKIP]   {action.concept_code:26} -> {action.reason}")

        if args.execute:
            print("\n" + "=" * 60)
            print(" EXECUTING SETUP")
            print("=" * 60)
            results = (
                GLAccountingSetupService.execute_all(dry_run=False)
                if args.tenant_id is None
                else [GLAccountingSetupService.execute(args.tenant_id, dry_run=False)]
            )
            for result in results:
                print(f"\nTenant {result.tenant_id}: {result.tenant_name}")
                for acc in result.created_accounts:
                    print(f"  + Account  {acc['code']} {acc['name']} / {acc['name_ar']}")
                for mapping in result.created_mappings:
                    print(f"  + Mapping  {mapping['concept_code']} -> {mapping['gl_account_code']}")
                for skipped in result.skipped_concepts:
                    print(f"  ! Skipped  {skipped['concept_code']} ({skipped['reason']})")
                for err in result.errors:
                    print(f"  ! Error    {err}")

        if args.validate:
            print("\n" + "=" * 60)
            print(" VALIDATION")
            print("=" * 60)
            report = GLAccountingSetupService.validate(tenant_id=args.tenant_id)
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if report.get("ready") else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
