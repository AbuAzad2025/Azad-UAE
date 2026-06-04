"""Read-only QA checks for Phase 1K dynamic GL posting resolution.

This script does not create journal entries and does not write data. It only
exercises account resolution for posting-line metadata with the feature flag
disabled and then temporarily enabled in memory.

Run:
    python tools/qa/gl_dynamic_posting_resolution_check.py
    python tools/qa/gl_dynamic_posting_resolution_check.py --tenant-id 1
"""
from __future__ import annotations

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


def _tenant_id_or_first(explicit_tenant_id):
    if explicit_tenant_id is not None:
        return explicit_tenant_id

    from models import Tenant

    tenant = Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).first()
    if not tenant:
        raise RuntimeError("No active tenant found for read-only GL posting resolution QA.")
    return tenant.id


def _missing_tenant_id():
    from sqlalchemy import func
    from models import Tenant
    from extensions import db

    max_id = db.session.query(func.coalesce(func.max(Tenant.id), 0)).scalar() or 0
    return int(max_id) + 100000


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only QA checks for Phase 1K dynamic GL posting resolution.",
    )
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument("--branch-id", type=int, default=None)
    args = parser.parse_args()

    from app import create_app
    from services.gl_account_resolver import GLMappingError, resolve_gl_account
    from services.gl_service import GLService

    app = create_app()
    report = {"checks": []}

    with app.app_context():
        original_flag = app.config.get("ENABLE_DYNAMIC_GL_MAPPING", False)
        tenant_id = _tenant_id_or_first(args.tenant_id)
        report["tenant_id"] = tenant_id
        report["branch_id"] = args.branch_id

        try:
            app.config["ENABLE_DYNAMIC_GL_MAPPING"] = False
            legacy_account = GLService._resolve_journal_line_account(
                {"account_code": "1130", "concept_code": "AR"},
                tenant_id=tenant_id,
                branch_id=args.branch_id,
                ensure_core=False,
            )
            report["checks"].append({
                "name": "legacy_path_flag_false",
                "ready": legacy_account is not None,
                "resolved_account_id": legacy_account.id if legacy_account else None,
                "resolved_account_code": legacy_account.code if legacy_account else None,
            })

            app.config["ENABLE_DYNAMIC_GL_MAPPING"] = True
            dynamic_account = GLService._resolve_journal_line_account(
                {"account_code": "1130", "concept_code": "AR"},
                tenant_id=tenant_id,
                branch_id=args.branch_id,
                ensure_core=False,
            )
            report["checks"].append({
                "name": "dynamic_path_flag_true",
                "ready": dynamic_account is not None,
                "resolved_account_id": dynamic_account.id if dynamic_account else None,
                "resolved_account_code": dynamic_account.code if dynamic_account else None,
            })

            try:
                resolve_gl_account(
                    tenant_id=_missing_tenant_id(),
                    concept_code="AR",
                    branch_id=args.branch_id,
                )
                missing_mapping_ready = False
                missing_mapping_issue = "Expected GLMappingError was not raised."
            except GLMappingError as exc:
                missing_mapping_ready = "No active GL account mapping" in exc.issue
                missing_mapping_issue = exc.issue
            report["checks"].append({
                "name": "missing_mapping_fails_clearly",
                "ready": missing_mapping_ready,
                "issue": missing_mapping_issue,
            })

            try:
                GLService._resolve_journal_line_account(
                    {"account_code": "2120"},
                    tenant_id=tenant_id,
                    branch_id=args.branch_id,
                    ensure_core=False,
                )
                unmapped_legacy_ready = False
                unmapped_legacy_issue = "Expected GLMappingError was not raised."
            except GLMappingError as exc:
                unmapped_legacy_ready = "No approved GL concept" in exc.issue
                unmapped_legacy_issue = exc.issue
            report["checks"].append({
                "name": "dynamic_path_blocks_unmapped_legacy_code",
                "ready": unmapped_legacy_ready,
                "issue": unmapped_legacy_issue,
            })
        finally:
            app.config["ENABLE_DYNAMIC_GL_MAPPING"] = original_flag

    report["ready"] = all(check["ready"] for check in report["checks"])
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
