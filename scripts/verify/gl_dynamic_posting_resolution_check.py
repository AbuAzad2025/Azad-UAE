"""Read-only QA checks for Phase 1K dynamic GL posting resolution.

This script does not create journal entries and does not write data. It only
exercises account resolution for posting-line metadata with the feature flag
disabled and then temporarily enabled in memory.

Run:
    python scripts/verify/gl_dynamic_posting_resolution_check.py
    python scripts/verify/gl_dynamic_posting_resolution_check.py --tenant-id 1
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

from dotenv import load_dotenv

load_dotenv()


ACTIVE_POSTING_FILES = (
    "services/sale_service.py",
    "services/purchase_service.py",
    "services/payment_service.py",
    "routes/payments.py",
    "services/return_service.py",
    "services/stock_service.py",
    "models/cheque.py",
    "services/commission_gl_service.py",
    "services/payroll_service.py",
    "services/bank_reconciliation_service.py",
    "services/donation_gl_service.py",
    "models/fixed_asset.py",
    "routes/expenses.py",
)

PHASE_1K1_DYNAMIC_CONCEPTS = (
    "DEFERRED_CHEQUES_PAYABLE",
    "PARTNER_CURRENT_ACCOUNT",
    "MERCHANT_CURRENT_ACCOUNT",
    "SHIPPING_REVENUE",
    "MISC_EXPENSE",
    "COMMISSION_EXPENSE",
    "EMPLOYEE_ADVANCES",
    "PAYROLL_EXPENSE",
    "PAYROLL_PAYABLE",
    "BANK_FEES",
    "BANK_INTEREST_INCOME",
    "DONATION_REVENUE",
    "FIXED_ASSET_ASSET",
    "DEPRECIATION_EXPENSE",
    "ACCUMULATED_DEPRECIATION",
    "FIXED_ASSET_GAIN",
    "FIXED_ASSET_LOSS",
)


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


def _string_key_positions(dict_node):
    positions = {}
    for index, key in enumerate(dict_node.keys):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            positions[key.value] = index
    return positions


def _constant_string(value_node):
    if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
        return value_node.value
    return None


def _static_posting_concept_coverage(valid_concepts):
    """Read-only AST check for active auto-posting dictionaries.

    The check intentionally allows explicit configured-account postings, such
    as tenant expense category accounts, when they carry the
    ``explicit_account_allowed`` marker.
    """
    missing_concept = []
    invalid_concept = []

    for relative_path in ACTIVE_POSTING_FILES:
        full_path = os.path.join(PROJECT_ROOT, relative_path)
        with open(full_path, "r", encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=relative_path)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue

            key_positions = _string_key_positions(node)
            has_account_key = bool({"account", "account_code"} & set(key_positions))
            if not has_account_key:
                continue

            concept_index = key_positions.get("concept_code")
            has_explicit_marker = "explicit_account_allowed" in key_positions

            if concept_index is None and not has_explicit_marker:
                missing_concept.append({
                    "file": relative_path,
                    "line": node.lineno,
                    "issue": "posting account dictionary has no concept_code",
                })
                continue

            if concept_index is not None:
                concept_value = node.values[concept_index]
                concept = _constant_string(concept_value)
                if concept is not None and concept not in valid_concepts:
                    invalid_concept.append({
                        "file": relative_path,
                        "line": node.lineno,
                        "concept_code": concept,
                        "issue": "concept_code is not in GL_CONCEPT_REGISTRY",
                    })

    return {
        "name": "static_active_posting_concept_coverage",
        "ready": not missing_concept and not invalid_concept,
        "checked_files": list(ACTIVE_POSTING_FILES),
        "missing_concept_count": len(missing_concept),
        "invalid_concept_count": len(invalid_concept),
        "missing_concept": missing_concept,
        "invalid_concept": invalid_concept,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only QA checks for Phase 1K dynamic GL posting resolution.",
    )
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument("--branch-id", type=int, default=None)
    args = parser.parse_args()

    from app import create_app
    from models._constants import VALID_GL_CONCEPT_CODES
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

            explicit_fixture = resolve_gl_account(
                tenant_id=tenant_id,
                concept_code="MISC_EXPENSE",
                branch_id=args.branch_id,
            )
            explicit_account = GLService._resolve_journal_line_account(
                {
                    "account_code": explicit_fixture.code,
                    "concept_code": None,
                    "explicit_account_allowed": True,
                },
                tenant_id=tenant_id,
                branch_id=args.branch_id,
                ensure_core=False,
            )
            report["checks"].append({
                "name": "dynamic_path_validates_explicit_configured_account",
                "ready": explicit_account.id == explicit_fixture.id,
                "resolved_account_id": explicit_account.id,
                "resolved_account_code": explicit_account.code,
            })

            dynamic_concept_checks = []
            for concept_code in PHASE_1K1_DYNAMIC_CONCEPTS:
                try:
                    account = resolve_gl_account(
                        tenant_id=tenant_id,
                        concept_code=concept_code,
                        branch_id=args.branch_id,
                    )
                    dynamic_concept_checks.append({
                        "concept_code": concept_code,
                        "ready": account is not None,
                        "resolved_account_code": account.code if account else None,
                        "resolved_account_id": account.id if account else None,
                    })
                except GLMappingError as exc:
                    dynamic_concept_checks.append({
                        "concept_code": concept_code,
                        "ready": False,
                        "issue": exc.issue,
                    })

            report["checks"].append({
                "name": "phase_1k1_dynamic_concepts_resolve",
                "ready": all(check["ready"] for check in dynamic_concept_checks),
                "concepts": dynamic_concept_checks,
            })

            report["checks"].append(
                _static_posting_concept_coverage(VALID_GL_CONCEPT_CODES)
            )
        finally:
            app.config["ENABLE_DYNAMIC_GL_MAPPING"] = original_flag

    report["ready"] = all(check["ready"] for check in report["checks"])
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
