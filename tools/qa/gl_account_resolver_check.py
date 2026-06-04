"""Phase 1J QA checks for the dynamic GL account resolver.

Default mode checks only the disabled feature-flag safety path and does not
start Flask or touch the database.

Optional simulation mode starts the app and temporarily sets the in-memory app
config flag to exercise resolver lookups. It does not write data or modify the
real feature flag setting.

Run:
    python tools/qa/gl_account_resolver_check.py
    python tools/qa/gl_account_resolver_check.py --simulate-enabled --tenant-id 1 --concept-code AR
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
        description="Read-only QA checks for Phase 1J GL account resolver.",
    )
    parser.add_argument("--simulate-enabled", action="store_true")
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument("--concept-code", default=None)
    parser.add_argument("--branch-id", type=int, default=None)
    args = parser.parse_args()

    from services.gl_account_resolver import (
        GLMappingError,
        is_dynamic_gl_mapping_enabled,
        resolve_gl_account,
    )

    if not args.simulate_enabled:
        enabled = is_dynamic_gl_mapping_enabled()
        result = resolve_gl_account(tenant_id=0, concept_code="AR")
        report = {
            "mode": "disabled_flag_safety",
            "enabled": enabled,
            "resolver_result_is_none": result is None,
            "ready": (not enabled) and result is None,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ready"] else 1

    if args.tenant_id is None or not args.concept_code:
        parser.error("--simulate-enabled requires --tenant-id and --concept-code")

    from app import create_app

    app = create_app()
    with app.app_context():
        app.config["ENABLE_DYNAMIC_GL_MAPPING"] = True
        try:
            account = resolve_gl_account(
                tenant_id=args.tenant_id,
                concept_code=args.concept_code,
                branch_id=args.branch_id,
            )
            report = {
                "mode": "simulate_enabled",
                "ready": True,
                "tenant_id": args.tenant_id,
                "concept_code": args.concept_code,
                "branch_id": args.branch_id,
                "resolved_account_id": account.id if account else None,
                "resolved_account_code": account.code if account else None,
                "resolved_account_name": account.name if account else None,
            }
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        except GLMappingError as exc:
            report = {
                "mode": "simulate_enabled",
                "ready": False,
                "tenant_id": exc.tenant_id,
                "concept_code": exc.concept_code,
                "branch_id": exc.branch_id,
                "issue": exc.issue,
                "message": exc.message,
            }
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
