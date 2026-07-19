"""Read-only GL mapping readiness validation for Phase 1F.

This module reports whether tenants are ready for dynamic GL mapping. It does
not create, update, delete, seed, backfill, or resolve posting accounts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import sqlalchemy as sa

from extensions import db
from models import Branch, GLAccountMapping, Tenant
from models._constants import (
    GL_CONCEPT_REGISTRY,
    REQUIRED_GL_CONCEPTS,
    VALID_GL_CONCEPT_CODES,
    RESOLUTION_MODE_MAPPING,
)
from models.gl import GLAccount

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


def _concept_meta(concept_code: str) -> dict[str, Any]:
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
        return (
            "Map the concept to a postable detail account, not a header/group account."
        )
    if "duplicate" in issue.lower():
        return "Keep one approved mapping for this tenant/concept scope and remove the duplicate after finance review."
    return "Review and correct the GL mapping manually."


def _is_mapping_owned(concept_code: str) -> bool:
    """Return True if the concept should be resolved via GLAccountMapping."""
    meta = GL_CONCEPT_REGISTRY.get(concept_code, {})
    return (
        meta.get("resolution_mode", RESOLUTION_MODE_MAPPING) == RESOLUTION_MODE_MAPPING
    )


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


# ------------------------------------------------------------------
# ------------------------------------------------------------------

# Each rule defines how to discover a postable GL account candidate for a
# concept when the legacy code did not yield a safe proposal.
DISCOVERY_RULES: dict[str, dict[str, object]] = {
    "CASH": {
        "name_exact": ["cash", "cashbox", "petty cash", "till"],
        "name_partial": ["cashbox", "cash drawer", "cash register", "petty"],
        "expected_types": ["asset"],
        "parent_code_hint": "1110",
        "description": "Postable cash or cashbox account (not header).",
    },
    "BANK": {
        "name_exact": ["bank", "checking", "savings"],
        "name_partial": ["bank", "checking", "savings", "deposit"],
        "expected_types": ["asset"],
        "parent_code_hint": "1120",
        "description": "Postable bank account (not header).",
    },
    "VAT_INPUT": {
        "name_exact": ["vat input", "input vat", "vat recoverable", "vat refundable"],
        "name_partial": ["vat input", "input vat", "vat recoverable", "vat refundable"],
        "expected_types": ["asset", "liability"],
        "parent_code_hint": "1170",
        "description": "VAT input / recoverable account.",
    },
    "COGS_REVERSAL": {
        "name_exact": ["cogs reversal", "cost reversal", "cogs return"],
        "name_partial": ["cogs reversal", "cost reversal", "inventory adjustment"],
        "expected_types": ["expense", "revenue"],
        "description": "Contra-COGS or inventory adjustment account for returns.",
    },
    "CUSTOMS_DUTY": {
        "name_exact": ["customs duty", "customs", "import duty", "tariff"],
        "name_partial": ["customs", "duty", "import tax", "tariff", "clearance"],
        "expected_types": ["expense", "asset"],
        "description": "Customs / import duty account for landed costs.",
    },
    "FREIGHT_IN": {
        "name_exact": ["freight in", "freight-in", "shipping in", "landing cost"],
        "name_partial": [
            "freight",
            "shipping in",
            "transport in",
            "landing cost",
            "landed cost",
        ],
        "expected_types": ["expense", "asset"],
        "description": "Freight / shipping-in account for landed costs.",
    },
    "FX_GAIN": {
        "name_exact": [
            "foreign exchange gain",
            "fx gain",
            "exchange gain",
            "currency gain",
        ],
        "name_partial": ["foreign exchange gain", "fx gain", "exchange gain"],
        "expected_types": ["revenue"],
        "description": "Foreign exchange gain account (revenue).",
    },
    "FX_LOSS": {
        "name_exact": [
            "foreign exchange loss",
            "fx loss",
            "exchange loss",
            "currency loss",
        ],
        "name_partial": ["foreign exchange loss", "fx loss", "exchange loss"],
        "expected_types": ["expense"],
        "description": "Foreign exchange loss account (expense).",
    },
    "INVENTORY_ADJUSTMENT_GAIN": {
        "name_exact": [
            "inventory adjustment gain",
            "inventory gain",
            "stock adjustment gain",
        ],
        "name_partial": ["inventory adjustment gain", "inventory gain", "stock gain"],
        "expected_types": ["revenue", "expense"],
        "description": "Inventory adjustment gain (positive adjustment).",
    },
    "INVENTORY_ADJUSTMENT_LOSS": {
        "name_exact": [
            "inventory adjustment loss",
            "inventory loss",
            "stock adjustment loss",
        ],
        "name_partial": [
            "inventory adjustment loss",
            "inventory loss",
            "stock loss",
            "inventory adjustment",
        ],
        "expected_types": ["expense"],
        "description": "Inventory adjustment loss (negative adjustment / shrinkage).",
    },
    "SALES_DISCOUNT": {
        "name_exact": [
            "sales discount",
            "discount given",
            "discounts given",
            "trade discount",
        ],
        "name_partial": [
            "sales discount",
            "discount given",
            "discounts given",
            "trade discount",
        ],
        "expected_types": ["expense", "revenue"],
        "description": "Sales discount or discount given account.",
    },
    "SALES_RETURNS": {
        "name_exact": [
            "sales return",
            "sales returns",
            "return sales",
            "revenue returns",
        ],
        "name_partial": [
            "sales return",
            "return sales",
            "revenue return",
            "sales returns",
        ],
        "expected_types": ["revenue"],
        "description": "Sales returns (contra-revenue) account.",
    },
}


DISCOVERY_RULES.update(
    {
        "DEFERRED_CHEQUES_PAYABLE": {
            "name_exact": ["deferred cheques payable", "pdc payable"],
            "name_partial": ["deferred cheque", "pdc payable", "cheques payable"],
            "expected_types": ["liability"],
            "description": "Issued post-dated / deferred cheques payable.",
        },
        "PARTNER_CURRENT_ACCOUNT": {
            "name_exact": ["partner current account", "partners current account"],
            "name_partial": ["partner current", "partners current"],
            "expected_types": ["equity", "liability", "asset"],
            "description": "Partner current account.",
        },
        "MERCHANT_CURRENT_ACCOUNT": {
            "name_exact": ["merchant current account", "merchants payable"],
            "name_partial": [
                "merchant current",
                "merchant payable",
                "merchants payable",
            ],
            "expected_types": ["liability", "asset"],
            "description": "Merchant current account / merchant payable bridge.",
        },
        "SHIPPING_REVENUE": {
            "name_exact": ["shipping revenue", "delivery revenue"],
            "name_partial": ["shipping revenue", "delivery revenue", "shipping"],
            "expected_types": ["revenue"],
            "description": "Shipping / delivery revenue.",
        },
        "MISC_EXPENSE": {
            "name_exact": ["miscellaneous expense", "misc expense"],
            "name_partial": ["miscellaneous", "misc expense"],
            "expected_types": ["expense"],
            "description": "Miscellaneous expense fallback.",
        },
        "COMMISSION_EXPENSE": {
            "name_exact": ["commission expense", "partner commission expense"],
            "name_partial": ["commission", "partner commission"],
            "expected_types": ["expense"],
            "description": "Commission expense.",
        },
        "EMPLOYEE_ADVANCES": {
            "name_exact": ["employee advances", "salary advances"],
            "name_partial": ["employee advance", "salary advance"],
            "expected_types": ["asset"],
            "description": "Employee advances asset account.",
        },
        "PAYROLL_EXPENSE": {
            "name_exact": ["payroll expense", "salaries and wages", "salary expense"],
            "name_partial": ["payroll", "salary", "wages"],
            "expected_types": ["expense"],
            "description": "Payroll / salaries expense.",
        },
        "PAYROLL_PAYABLE": {
            "name_exact": ["payroll payable", "salary payable", "salaries payable"],
            "name_partial": ["payroll payable", "salary payable"],
            "expected_types": ["liability"],
            "description": "Payroll payable / salary deductions payable.",
        },
        "BANK_FEES": {
            "name_exact": ["bank fees", "bank charges"],
            "name_partial": ["bank fee", "bank charge"],
            "expected_types": ["expense"],
            "description": "Bank fees and reconciliation charges.",
        },
        "BANK_INTEREST_INCOME": {
            "name_exact": ["bank interest income", "interest income"],
            "name_partial": ["bank interest", "interest income", "other revenue"],
            "expected_types": ["revenue"],
            "description": "Bank interest income.",
        },
        "DONATION_REVENUE": {
            "name_exact": ["donation revenue", "donation income"],
            "name_partial": ["donation", "service revenue"],
            "expected_types": ["revenue"],
            "description": "Donation revenue.",
        },
        "FIXED_ASSET_ASSET": {
            "name_exact": ["fixed asset", "equipment"],
            "name_partial": ["fixed asset", "equipment", "furniture", "vehicle"],
            "expected_types": ["asset"],
            "parent_code_hint": "1200",
            "description": "Fixed asset cost account.",
        },
        "DEPRECIATION_EXPENSE": {
            "name_exact": ["depreciation expense"],
            "name_partial": ["depreciation expense", "depreciation"],
            "expected_types": ["expense"],
            "description": "Depreciation expense.",
        },
        "ACCUMULATED_DEPRECIATION": {
            "name_exact": ["accumulated depreciation"],
            "name_partial": ["accumulated depreciation"],
            "expected_types": ["asset"],
            "parent_code_hint": "1200",
            "description": "Accumulated depreciation contra-asset account.",
        },
        "FIXED_ASSET_GAIN": {
            "name_exact": ["fixed asset disposal gain", "asset disposal gain"],
            "name_partial": ["asset disposal gain", "other revenue"],
            "expected_types": ["revenue"],
            "description": "Gain on fixed asset disposal.",
        },
        "FIXED_ASSET_LOSS": {
            "name_exact": ["fixed asset disposal loss", "asset disposal loss"],
            "name_partial": ["asset disposal loss", "miscellaneous"],
            "expected_types": ["expense"],
            "description": "Loss on fixed asset disposal.",
        },
    }
)


@dataclass(frozen=True)
class GLMappingCandidateDiscoveryRow:
    """Read-only candidate discovery report row for Phase 1G.1.

    This dataclass never triggers inserts, updates, or deletes.
    """

    tenant_id: int
    tenant_name: str
    concept_code: str
    candidate_gl_account_id: int | None
    candidate_gl_account_code: str | None
    candidate_gl_account_name: str | None
    candidate_reason: str
    confidence: str
    status: str
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
            GLAccountMapping.query.filter_by(tenant_id=tenant.id)
            .order_by(
                GLAccountMapping.concept_code.asc(),
                GLAccountMapping.branch_id.asc().nullsfirst(),
                GLAccountMapping.id.asc(),
            )
            .all()
        )

        rows: list[GLMappingValidationRow] = []
        rows.extend(
            GLMappingValidationService._validate_required_defaults(
                tenant, mappings, include_ready
            )
        )
        rows.extend(
            GLMappingValidationService._validate_existing_mappings(tenant, mappings)
        )
        # Add liquidity readiness validation
        rows.extend(GLMappingValidationService._validate_liquidity_readiness(tenant))
        return rows

    @staticmethod
    def _validate_liquidity_readiness(
        tenant: Tenant,
    ) -> list[GLMappingValidationRow]:
        """Read-only validate cash and bank readiness for every active branch."""
        rows: list[GLMappingValidationRow] = []
        tenant_name = (
            tenant.name or tenant.name_en or tenant.name_ar or f"Tenant {tenant.id}"
        )

        checks = (
            ("cash", "CASH_READINESS"),
            ("bank", "BANK_READINESS"),
        )

        active_branches = Branch.query.filter_by(
            tenant_id=tenant.id,
            is_active=True,
        ).all()

        for branch in active_branches:
            for liquidity_kind, concept_code in checks:
                account = (
                    GLAccount.query.filter_by(
                        tenant_id=tenant.id,
                        branch_id=branch.id,
                        liquidity_kind=liquidity_kind,
                        is_active=True,
                    )
                    .filter(GLAccount.is_header.is_(False))
                    .first()
                )

                if account is not None:
                    continue

                rows.append(
                    GLMappingValidationRow(
                        tenant_id=tenant.id,
                        tenant_name=tenant_name,
                        concept_code=concept_code,
                        expected_legacy_code=None,
                        status="missing",
                        issue=(
                            f"Branch {branch.code} ({branch.name}) has no "
                            f"active postable {liquidity_kind} liquidity account."
                        ),
                        severity="critical",
                        recommended_fix=(
                            f"Create or activate an active postable "
                            f"{liquidity_kind} GL account for branch {branch.code}."
                        ),
                    )
                )

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
            rows = GLMappingValidationService.validate_all_tenants(
                include_ready=include_ready
            )
        else:
            rows = [
                row.to_dict()
                for row in GLMappingValidationService.validate_tenant(
                    tenant_id,
                    include_ready=include_ready,
                )
            ]

        critical_count = sum(
            1
            for row in rows
            if row["severity"] == "critical" and row["status"] != "ready"
        )
        warning_count = sum(
            1
            for row in rows
            if row["severity"] == "warning" and row["status"] != "ready"
        )
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

        rows: list[dict[str, Any]] = []
        for tenant in tenants:
            rows.extend(GLMappingValidationService._preview_seed_for_tenant(tenant))

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
            if not _is_mapping_owned(concept_code):
                continue
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
                GLAccount.query.filter_by(tenant_id=tenant.id, code=legacy_code)
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
                issues = GLMappingValidationService._account_issues(tenant, candidate)
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
                first_issue = (
                    candidate_issues[0]
                    if candidate_issues
                    else "Candidate account is invalid."
                )
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

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------

    DISCOVERY_FIELDS = (
        "tenant_id",
        "tenant_name",
        "concept_code",
        "candidate_gl_account_id",
        "candidate_gl_account_code",
        "candidate_gl_account_name",
        "candidate_reason",
        "confidence",
        "status",
        "recommended_fix",
    )

    @staticmethod
    def discover_candidates(
        tenant_id: int | None = None,
    ) -> dict[str, object]:
        """Return a read-only candidate discovery report for GL concept gaps.

        For every concept that was NOT safely proposed in Phase 1G, this
        method searches the tenant's existing chart of accounts for likely
        postable candidates using name patterns, account types, and parent
        relationships.  It never writes to the database.
        """
        if tenant_id is None:
            tenants = Tenant.query.order_by(Tenant.id.asc()).all()
        else:
            tenant = Tenant.query.filter_by(id=tenant_id).first()
            tenants = [tenant] if tenant else []

        rows: list[dict[str, Any]] = []
        for tenant in tenants:
            rows.extend(GLMappingValidationService._discover_for_tenant(tenant))

        candidate_found = sum(1 for r in rows if r["status"] == "candidate_found")
        owner_selection = sum(
            1 for r in rows if r["status"] == "owner_selection_required"
        )
        manual_creation = sum(
            1 for r in rows if r["status"] == "manual_creation_required"
        )

        # Required summary breakdowns
        total_concepts_checked = len(DISCOVERY_RULES) * len(tenants)

        candidate_count_by_concept: dict[str, int] = defaultdict(int)
        for r in rows:
            if r["status"] == "candidate_found":
                candidate_count_by_concept[r["concept_code"]] += 1

        # Per-tenant analysis
        tenant_status: dict[int, dict[str, bool]] = defaultdict(
            lambda: {
                "has_owner_selection": False,
                "has_manual_creation": False,
                "has_all_candidates": True,
            }
        )
        for r in rows:
            tid = r["tenant_id"]
            if r["status"] == "owner_selection_required":
                tenant_status[tid]["has_owner_selection"] = True
                tenant_status[tid]["has_all_candidates"] = False
            if r["status"] == "manual_creation_required":
                tenant_status[tid]["has_manual_creation"] = True
                tenant_status[tid]["has_all_candidates"] = False

        tenants_with_complete_candidates = [
            tid for tid, s in tenant_status.items() if s["has_all_candidates"]
        ]
        tenants_requiring_owner_selection = [
            tid for tid, s in tenant_status.items() if s["has_owner_selection"]
        ]
        tenants_requiring_new_gl_account = [
            tid for tid, s in tenant_status.items() if s["has_manual_creation"]
        ]

        concepts_unresolvable = sorted(
            {
                r["concept_code"]
                for r in rows
                if r["status"] == "manual_creation_required"
            }
        )

        return {
            "discovery_type": "candidate_discovery",
            "total_concepts_checked": total_concepts_checked,
            "candidate_found_count": candidate_found,
            "owner_selection_required_count": owner_selection,
            "manual_creation_required_count": manual_creation,
            "candidate_count_by_concept": dict(candidate_count_by_concept),
            "tenants_with_complete_candidates": tenants_with_complete_candidates,
            "tenants_requiring_owner_selection": tenants_requiring_owner_selection,
            "tenants_requiring_new_gl_account": tenants_requiring_new_gl_account,
            "concepts_unresolvable": concepts_unresolvable,
            "report_fields": list(GLMappingValidationService.DISCOVERY_FIELDS),
            "rows": rows,
        }

    @staticmethod
    def _discover_for_tenant(
        tenant: Tenant,
    ) -> list[dict[str, object]]:
        """Discover candidate accounts for every concept gap in one tenant."""
        rows: list[GLMappingCandidateDiscoveryRow] = []

        # First, know which concepts were ALREADY safely proposed in Phase 1G
        preview_rows = GLMappingValidationService._preview_seed_for_tenant(tenant)
        proposed_concepts = {
            r["concept_code"] for r in preview_rows if r["status"] == "proposed"
        }

        for concept_code in sorted(DISCOVERY_RULES):
            if concept_code in proposed_concepts:
                # Already safely proposed; skip discovery
                continue

            rule = DISCOVERY_RULES[concept_code]
            candidates = GLMappingValidationService._find_candidates(
                tenant, concept_code, rule
            )

            if not candidates:
                rows.append(
                    GLMappingCandidateDiscoveryRow(
                        tenant_id=tenant.id,
                        tenant_name=_tenant_name(tenant),
                        concept_code=concept_code,
                        candidate_gl_account_id=None,
                        candidate_gl_account_code=None,
                        candidate_gl_account_name=None,
                        candidate_reason="No postable candidate found using discovery rules.",
                        confidence="none",
                        status="manual_creation_required",
                        recommended_fix="Create a new GL account for this concept, then run the seed preview again.",
                    )
                )
                continue

            if len(candidates) > 1:
                for candidate, reason, confidence in candidates:
                    rows.append(
                        GLMappingCandidateDiscoveryRow(
                            tenant_id=tenant.id,
                            tenant_name=_tenant_name(tenant),
                            concept_code=concept_code,
                            candidate_gl_account_id=candidate.id,
                            candidate_gl_account_code=candidate.code,
                            candidate_gl_account_name=candidate.name,
                            candidate_reason=reason,
                            confidence=confidence,
                            status="owner_selection_required",
                            recommended_fix="Multiple valid candidates found. Finance owner must select one before seeding.",
                        )
                    )
            else:
                candidate, reason, confidence = candidates[0]
                rows.append(
                    GLMappingCandidateDiscoveryRow(
                        tenant_id=tenant.id,
                        tenant_name=_tenant_name(tenant),
                        concept_code=concept_code,
                        candidate_gl_account_id=candidate.id,
                        candidate_gl_account_code=candidate.code,
                        candidate_gl_account_name=candidate.name,
                        candidate_reason=reason,
                        confidence=confidence,
                        status="candidate_found",
                        recommended_fix="Approve and run the seed command to persist this mapping.",
                    )
                )

        return [row.to_dict() for row in rows]

    @staticmethod
    def _find_candidates(
        tenant: Tenant,
        concept_code: str,
        rule: dict[str, Any],
    ) -> list[tuple[GLAccount, str, str]]:
        """Search for postable GL account candidates for a concept.

        Returns a list of (account, reason, confidence) tuples.
        Candidates are filtered to same tenant, active, not header.
        """
        candidates: list[tuple[GLAccount, str, str]] = []
        seen_ids: set[int] = set()

        expected_types = rule.get("expected_types", [])
        name_exact = rule.get("name_exact", [])
        name_partial = rule.get("name_partial", [])
        parent_code_hint = rule.get("parent_code_hint")

        def _is_postable(acct: GLAccount) -> bool:
            return acct.tenant_id == tenant.id and acct.is_active and not acct.is_header

        # --- Strategy 1: exact name match (highest confidence) ---
        for pattern in name_exact:
            for account in GLAccount.query.filter_by(tenant_id=tenant.id).all():
                if account.id in seen_ids:
                    continue
                if not _is_postable(account):
                    continue
                if expected_types and account.type not in expected_types:
                    continue
                account_name_lower = (account.name or "").lower()
                if account_name_lower == pattern.lower():
                    candidates.append(
                        (account, f"Exact name match: '{account.name}'", "high")
                    )
                    seen_ids.add(account.id)

        # --- Strategy 2: partial name match (medium confidence) ---
        for pattern in name_partial:
            for account in GLAccount.query.filter_by(tenant_id=tenant.id).all():
                if account.id in seen_ids:
                    continue
                if not _is_postable(account):
                    continue
                if expected_types and account.type not in expected_types:
                    continue
                account_name_lower = (account.name or "").lower()
                if pattern.lower() in account_name_lower:
                    candidates.append(
                        (
                            account,
                            f"Partial name match: '{account.name}' contains '{pattern}'",
                            "medium",
                        )
                    )
                    seen_ids.add(account.id)

        # --- Strategy 3: parent code hint → search children (medium/high confidence) ---
        if parent_code_hint:
            parent = GLAccount.query.filter_by(
                tenant_id=tenant.id, code=parent_code_hint
            ).first()
            if parent:
                for child in parent.children:
                    if child.id in seen_ids:
                        continue
                    if not _is_postable(child):
                        continue
                    if expected_types and child.type not in expected_types:
                        continue
                    candidates.append(
                        (
                            child,
                            f"Child of parent {parent.code} ({parent.name}): '{child.name}'",
                            "high",
                        )
                    )
                    seen_ids.add(child.id)

        # Sort: high confidence first, then by account code
        confidence_order = {"high": 0, "medium": 1, "low": 2}
        candidates.sort(key=lambda x: (confidence_order.get(x[2], 3), x[0].code))
        return candidates

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
            if not _is_mapping_owned(concept_code):
                continue
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

            issues = GLMappingValidationService._mapping_issues(
                tenant, default_mappings[0]
            )
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
        ignored_non_mapping_mapping_ids: set[int] = set()

        # First pass: count mappings and identify non-mapping-owned ones for warnings
        for mapping in mappings:
            if mapping.branch_id is None:
                seen_defaults[mapping.concept_code] += 1
            else:
                seen_branch_overrides[(mapping.concept_code, mapping.branch_id)] += 1

            # Identify non-mapping-owned mappings for exact one warning per mapping
            if not _is_mapping_owned(mapping.concept_code):
                ignored_non_mapping_mapping_ids.add(mapping.id)

        # Flag stale mappings for non-mapping-owned concepts as warnings (exactly one per mapping)
        for mapping in mappings:
            if mapping.id in ignored_non_mapping_mapping_ids:
                rows.append(
                    _row(
                        tenant,
                        mapping.concept_code,
                        "warning",
                        f"Concept '{mapping.concept_code}' is {GL_CONCEPT_REGISTRY.get(mapping.concept_code, {}).get('resolution_mode', 'unknown')}-owned; its mapping is stale and will be ignored during posting.",
                        severity="warning",
                        recommended_fix="Remove this mapping after finance review; the concept is resolved via a different mechanism.",
                    )
                )

        seen_defaults_filtered: dict[str, int] = defaultdict(int)
        seen_branch_overrides_filtered: dict[tuple[str, int], int] = defaultdict(int)

        for mapping in mappings:
            if mapping.id in ignored_non_mapping_mapping_ids:
                continue  # Skip ignored non-mapping-owned mappings
            if mapping.branch_id is None:
                seen_defaults_filtered[mapping.concept_code] += 1
            else:
                seen_branch_overrides_filtered[
                    (mapping.concept_code, mapping.branch_id)
                ] += 1

        # Check for duplicates in tenant-level mappings (excluding ignored non-mapping-owned)
        for concept_code, count in seen_defaults_filtered.items():
            if count > 1 and concept_code not in REQUIRED_GL_CONCEPTS:
                rows.append(
                    _row(
                        tenant,
                        concept_code,
                        "invalid",
                        "Duplicate tenant-level GL concept mappings exist.",
                    )
                )

        # Check for duplicates in branch-level mappings (excluding ignored non-mapping-owned)
        for (concept_code, _branch_id), count in seen_branch_overrides_filtered.items():
            if count > 1:
                rows.append(
                    _row(
                        tenant,
                        concept_code,
                        "invalid",
                        "Duplicate branch override GL concept mappings exist.",
                    )
                )

        # Process mappings for validation issues, but skip non-mapping-owned concepts to avoid duplicate warnings
        for mapping in mappings:
            # Skip validation for non-mapping-owned concepts to prevent duplicate warnings
            # (they were already warned about above as stale mappings)
            if not _is_mapping_owned(mapping.concept_code):
                continue
            # Skip required concepts without branch_id (they're handled in _validate_required_defaults)
            if (
                mapping.concept_code in REQUIRED_GL_CONCEPTS
                and mapping.branch_id is None
            ):
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
            branch = (
                mapping.branch or Branch.query.filter_by(id=mapping.branch_id).first()
            )
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


def discover_candidates_gl_mapping(
    tenant_id: int | None = None,
) -> dict[str, object]:
    """Read-only candidate discovery for GL concept mapping gaps.

    This function NEVER writes to the database.
    """
    return GLMappingValidationService.discover_candidates(tenant_id=tenant_id)
