"""Read-only GL mapping readiness validation for Phase 1F.

This module reports whether tenants are ready for dynamic GL mapping. It does
not create, update, delete, seed, backfill, or resolve posting accounts.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Iterable

import sqlalchemy as sa

from extensions import db
from models import Branch, GLAccountMapping, Tenant
from models.gl import (
    GL_CONCEPT_REGISTRY,
    GLAccount,
    REQUIRED_GL_CONCEPTS,
    VALID_GL_CONCEPT_CODES,
)


REPORT_FIELDS = (
    "tenant_id",
    "tenant_name",
    "concept_code",
    "expected_legacy_code",
    "status",
    "issue",
    "severity",
    "recommended_fix",
)


@dataclass(frozen=True)
class GLMappingValidationRow:
    tenant_id: int
    tenant_name: str
    concept_code: str
    expected_legacy_code: str | None
    status: str
    issue: str
    severity: str
    recommended_fix: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _tenant_name(tenant: Tenant) -> str:
    return tenant.name or tenant.name_en or tenant.name_ar or f"Tenant {tenant.id}"


def _concept_meta(concept_code: str) -> dict[str, object]:
    return GL_CONCEPT_REGISTRY.get(
        concept_code,
        {"legacy_code": None, "required": False},
    )


def _severity_for(concept_code: str) -> str:
    return "critical" if concept_code in REQUIRED_GL_CONCEPTS else "warning"


def _recommended_fix(status: str, issue: str) -> str:
    if status == "ready":
        return "No action required."
    if status == "missing":
        return "Assign an existing valid tenant GL account to this concept; do not guess the mapping."
    if "tenant" in issue.lower():
        return "Replace the mapping with an account or branch that belongs to the same tenant."
    if "inactive" in issue.lower():
        return "Map the concept to an active GL account or reactivate the intended account after finance approval."
    if "header" in issue.lower():
        return "Map the concept to a postable detail account, not a header/group account."
    if "duplicate" in issue.lower():
        return "Keep one approved mapping for this tenant/concept scope and remove the duplicate after finance review."
    return "Review and correct the GL mapping manually."


def _row(
    tenant: Tenant,
    concept_code: str,
    status: str,
    issue: str,
    severity: str | None = None,
    recommended_fix: str | None = None,
) -> GLMappingValidationRow:
    meta = _concept_meta(concept_code)
    return GLMappingValidationRow(
        tenant_id=tenant.id,
        tenant_name=_tenant_name(tenant),
        concept_code=concept_code,
        expected_legacy_code=meta.get("legacy_code"),
        status=status,
        issue=issue,
        severity=severity or _severity_for(concept_code),
        recommended_fix=recommended_fix or _recommended_fix(status, issue),
    )


@dataclass(frozen=True)
class GLMappingSeedPreviewRow:
    """Read-only preview of what GL mapping seed *would* propose for a tenant.

    This dataclass never triggers inserts, updates, or deletes.
    """

    tenant_id: int
    tenant_name: str
    concept_code: str
    expected_legacy_code: str | None
    proposed_gl_account_id: int | None
    proposed_gl_account_code: str | None
    proposed_gl_account_name: str | None
    status: str
    issue: str
    severity: str
    recommended_fix: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class GLMappingValidationService:
    """Read-only validator for GLAccountMapping readiness."""

    @staticmethod
    def validate_all_tenants(include_ready: bool = True) -> list[dict[str, object]]:
        tenants = Tenant.query.order_by(Tenant.id.asc()).all()
        rows: list[GLMappingValidationRow] = []
        for tenant in tenants:
            rows.extend(
                GLMappingValidationService.validate_tenant(
                    tenant.id,
                    include_ready=include_ready,
                )
            )
        return [row.to_dict() for row in rows]

    @staticmethod
    def validate_tenant(
        tenant_id: int,
        include_ready: bool = True,
    ) -> list[GLMappingValidationRow]:
        tenant = Tenant.query.filter_by(id=tenant_id).first()
        if not tenant:
            return [
                GLMappingValidationRow(
                    tenant_id=tenant_id,
                    tenant_name="",
                    concept_code="",
                    expected_legacy_code=None,
                    status="invalid",
                    issue="Tenant does not exist.",
                    severity="critical",
                    recommended_fix="Use an existing tenant id and rerun the dry-run validation.",
                )
            ]

        mappings = (
            GLAccountMapping.query
            .filter_by(tenant_id=tenant.id)
            .order_by(
                GLAccountMapping.concept_code.asc(),
                GLAccountMapping.branch_id.asc().nullsfirst(),
                GLAccountMapping.id.asc(),
            )
            .all()
        )

        rows: list[GLMappingValidationRow] = []
        rows.extend(GLMappingValidationService._validate_required_defaults(tenant, mappings, include_ready))
        rows.extend(GLMappingValidationService._validate_existing_mappings(tenant, mappings))
        return rows

    @staticmethod
    def dry_run(
        tenant_id: int | None = None,
        include_ready: bool = True,
    ) -> dict[str, object]:
        if not sa.inspect(db.engine).has_table("gl_account_mappings"):
            return {
                "ready": False,
                "critical_count": 1,
                "warning_count": 0,
                "report_fields": list(REPORT_FIELDS),
                "rows": [
                    GLMappingValidationRow(
                        tenant_id=tenant_id or 0,
                        tenant_name="",
                        concept_code="",
                        expected_legacy_code=None,
                        status="invalid",
                        issue="GL mapping table does not exist. Apply the Phase 1E schema migration before validation.",
                        severity="critical",
                        recommended_fix="Run the approved additive Phase 1E migration, then rerun this dry-run validation.",
                    ).to_dict()
                ],
            }

        if tenant_id is None:
            rows = GLMappingValidationService.validate_all_tenants(include_ready=include_ready)
        else:
            rows = [
                row.to_dict()
                for row in GLMappingValidationService.validate_tenant(
                    tenant_id,
                    include_ready=include_ready,
                )
            ]

        critical_count = sum(1 for row in rows if row["severity"] == "critical" and row["status"] != "ready")
        warning_count = sum(1 for row in rows if row["severity"] == "warning" and row["status"] != "ready")
        return {
            "ready": critical_count == 0,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "report_fields": list(REPORT_FIELDS),
            "rows": rows,
        }

    # ------------------------------------------------------------------
    # Phase 1G – Safe Seed Preview (read-only, never writes to DB)
    # ------------------------------------------------------------------

    PREVIEW_FIELDS = (
        "tenant_id",
        "tenant_name",
        "concept_code",
        "expected_legacy_code",
        "proposed_gl_account_id",
        "proposed_gl_account_code",
        "proposed_gl_account_name",
        "status",
        "issue",
        "severity",
        "recommended_fix",
    )

    @staticmethod
    def preview_seed(
        tenant_id: int | None = None,
    ) -> dict[str, object]:
        """Return a read-only preview of proposed GL mappings per tenant.

        This method NEVER inserts, updates, deletes, seeds, or backfills data.
        It only reports what *would* be proposed by matching legacy codes to
        existing tenant GL accounts.
        """
        if tenant_id is None:
            tenants = Tenant.query.order_by(Tenant.id.asc()).all()
        else:
            tenant = Tenant.query.filter_by(id=tenant_id).first()
            tenants = [tenant] if tenant else []

        rows: list[dict[str, object]] = []
        for tenant in tenants:
            rows.extend(
                GLMappingValidationService._preview_seed_for_tenant(tenant)
            )

        proposed_count = sum(1 for r in rows if r["status"] == "proposed")
        manual_count = sum(1 for r in rows if r["status"] == "manual_required")
        invalid_count = sum(1 for r in rows if r["status"] == "invalid_candidate")

        return {
            "preview_type": "safe_seed_preview",
            "proposed_count": proposed_count,
            "manual_required_count": manual_count,
            "invalid_candidate_count": invalid_count,
            "report_fields": list(GLMappingValidationService.PREVIEW_FIELDS),
            "rows": rows,
        }

    @staticmethod
    def _preview_seed_for_tenant(
        tenant: Tenant,
    ) -> list[dict[str, object]]:
        """Build preview rows for a single tenant by matching legacy codes."""
        rows: list[GLMappingSeedPreviewRow] = []

        for concept_code in sorted(GL_CONCEPT_REGISTRY):
            meta = GL_CONCEPT_REGISTRY[concept_code]
            legacy_code = meta.get("legacy_code")
            is_required = meta.get("required", False)

            # No legacy code hint → manual mapping required
            if not legacy_code:
                rows.append(
                    GLMappingSeedPreviewRow(
                        tenant_id=tenant.id,
                        tenant_name=_tenant_name(tenant),
                        concept_code=concept_code,
                        expected_legacy_code=None,
                        proposed_gl_account_id=None,
                        proposed_gl_account_code=None,
                        proposed_gl_account_name=None,
                        status="manual_required",
                        issue="No legacy code hint defined for this concept.",
                        severity="critical" if is_required else "warning",
                        recommended_fix="Manually create a GL mapping for this concept after reviewing the tenant's chart of accounts.",
                    )
                )
                continue

            # Find candidate GL accounts in this tenant with the legacy code
            candidates = (
                GLAccount.query
                .filter_by(tenant_id=tenant.id, code=legacy_code)
                .order_by(GLAccount.id.asc())
                .all()
            )

            if not candidates:
                rows.append(
                    GLMappingSeedPreviewRow(
                        tenant_id=tenant.id,
                        tenant_name=_tenant_name(tenant),
                        concept_code=concept_code,
                        expected_legacy_code=legacy_code,
                        proposed_gl_account_id=None,
                        proposed_gl_account_code=None,
                        proposed_gl_account_name=None,
                        status="manual_required",
                        issue=f"No GL account with code '{legacy_code}' found in tenant's chart.",
                        severity="critical" if is_required else "warning",
                        recommended_fix="Create the GL account or map this concept to an existing account manually.",
                    )
                )
                continue

            # Validate each candidate; pick the first valid one
            chosen_candidate = None
            candidate_issues: list[str] = []
            for candidate in candidates:
                issues = GLMappingValidationService._account_issues(
                    tenant, candidate
                )
                if not issues:
                    chosen_candidate = candidate
                    break
                candidate_issues.extend(issues)

            if chosen_candidate:
                rows.append(
                    GLMappingSeedPreviewRow(
                        tenant_id=tenant.id,
                        tenant_name=_tenant_name(tenant),
                        concept_code=concept_code,
                        expected_legacy_code=legacy_code,
                        proposed_gl_account_id=chosen_candidate.id,
                        proposed_gl_account_code=chosen_candidate.code,
                        proposed_gl_account_name=chosen_candidate.name,
                        status="proposed",
                        issue="Safe candidate found by legacy code match.",
                        severity="info",
                        recommended_fix="Approve and run the seed command to persist this mapping.",
                    )
                )
            else:
                # Report the first invalid candidate with its issues
                first_invalid = candidates[0]
                first_issue = candidate_issues[0] if candidate_issues else "Candidate account is invalid."
                rows.append(
                    GLMappingSeedPreviewRow(
                        tenant_id=tenant.id,
                        tenant_name=_tenant_name(tenant),
                        concept_code=concept_code,
                        expected_legacy_code=legacy_code,
                        proposed_gl_account_id=first_invalid.id,
                        proposed_gl_account_code=first_invalid.code,
                        proposed_gl_account_name=first_invalid.name,
                        status="invalid_candidate",
                        issue=first_issue,
                        severity="critical" if is_required else "warning",
                        recommended_fix="Correct the GL account (activate, de-header, or fix tenant ownership) then re-run preview.",
                    )
                )

        return [row.to_dict() for row in rows]

    @staticmethod
    def _account_issues(tenant: Tenant, account: GLAccount) -> list[str]:
        """Return a list of validation issues for a candidate GL account."""
        issues: list[str] = []
        if account.tenant_id != tenant.id:
            issues.append("Account belongs to a different tenant.")
        if not account.is_active:
            issues.append("Account is inactive.")
        if account.is_header:
            issues.append("Account is a header/group account and is not postable.")
        return issues

    @staticmethod
    def _validate_required_defaults(
        tenant: Tenant,
        mappings: Iterable[GLAccountMapping],
        include_ready: bool,
    ) -> list[GLMappingValidationRow]:
        rows: list[GLMappingValidationRow] = []
        defaults_by_concept: dict[str, list[GLAccountMapping]] = defaultdict(list)
        for mapping in mappings:
            if mapping.branch_id is None:
                defaults_by_concept[mapping.concept_code].append(mapping)

        for concept_code in sorted(REQUIRED_GL_CONCEPTS):
            default_mappings = defaults_by_concept.get(concept_code, [])
            if not default_mappings:
                rows.append(
                    _row(
                        tenant,
                        concept_code,
                        "missing",
                        "Required tenant-level GL concept mapping is missing.",
                        severity="critical",
                    )
                )
                continue

            if len(default_mappings) > 1:
                rows.append(
                    _row(
                        tenant,
                        concept_code,
                        "invalid",
                        "Duplicate tenant-level GL concept mappings exist.",
                        severity="critical",
                    )
                )
                continue

            issues = GLMappingValidationService._mapping_issues(tenant, default_mappings[0])
            if issues:
                rows.extend(
                    _row(tenant, concept_code, "invalid", issue, severity="critical")
                    for issue in issues
                )
            elif include_ready:
                rows.append(
                    _row(
                        tenant,
                        concept_code,
                        "ready",
                        "Required tenant-level GL concept mapping is valid.",
                        severity="info",
                    )
                )
        return rows

    @staticmethod
    def _validate_existing_mappings(
        tenant: Tenant,
        mappings: Iterable[GLAccountMapping],
    ) -> list[GLMappingValidationRow]:
        rows: list[GLMappingValidationRow] = []
        seen_defaults: dict[str, int] = defaultdict(int)
        seen_branch_overrides: dict[tuple[str, int], int] = defaultdict(int)

        for mapping in mappings:
            if mapping.branch_id is None:
                seen_defaults[mapping.concept_code] += 1
            else:
                seen_branch_overrides[(mapping.concept_code, mapping.branch_id)] += 1

        for concept_code, count in seen_defaults.items():
            if count > 1 and concept_code not in REQUIRED_GL_CONCEPTS:
                rows.append(
                    _row(
                        tenant,
                        concept_code,
                        "invalid",
                        "Duplicate tenant-level GL concept mappings exist.",
                    )
                )

        for (concept_code, _branch_id), count in seen_branch_overrides.items():
            if count > 1:
                rows.append(
                    _row(
                        tenant,
                        concept_code,
                        "invalid",
                        "Duplicate branch override GL concept mappings exist.",
                    )
                )

        for mapping in mappings:
            if mapping.concept_code in REQUIRED_GL_CONCEPTS and mapping.branch_id is None:
                continue
            for issue in GLMappingValidationService._mapping_issues(tenant, mapping):
                rows.append(_row(tenant, mapping.concept_code, "invalid", issue))
        return rows

    @staticmethod
    def _mapping_issues(tenant: Tenant, mapping: GLAccountMapping) -> list[str]:
        issues: list[str] = []
        if mapping.concept_code not in VALID_GL_CONCEPT_CODES:
            issues.append("Mapping uses an unknown GL concept code.")

        account = mapping.gl_account
        if account is None:
            issues.append("Mapped GL account does not exist.")
        else:
            if account.tenant_id != tenant.id:
                issues.append("Mapped GL account belongs to a different tenant.")
            if not account.is_active:
                issues.append("Mapped GL account is inactive.")
            if account.is_header:
                issues.append("Mapped GL account is a header/group account.")

        if mapping.branch_id is not None:
            branch = mapping.branch or Branch.query.filter_by(id=mapping.branch_id).first()
            if branch is None:
                issues.append("Branch override references a missing branch.")
            elif branch.tenant_id != tenant.id:
                issues.append("Branch override belongs to a different tenant.")

        if not mapping.is_active:
            issues.append("GL concept mapping is inactive.")

        return issues


def dry_run_gl_mapping_validation(
    tenant_id: int | None = None,
    include_ready: bool = True,
) -> dict[str, object]:
    return GLMappingValidationService.dry_run(
        tenant_id=tenant_id,
        include_ready=include_ready,
    )


def preview_seed_gl_mapping(
    tenant_id: int | None = None,
) -> dict[str, object]:
    """Read-only preview of what GL concept mappings would be proposed.

    This function NEVER writes to the database.
    """
    return GLMappingValidationService.preview_seed(tenant_id=tenant_id)
