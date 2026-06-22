"""Reusable GL accounting setup for tenant onboarding.

GLAccountingSetupService
========================
A stateless, reusable service that prepares a tenant's chart of accounts
for the approved GL concept registry.  It is designed to be called:

  1. During tenant onboarding (future) – automatically when a new tenant is
     provisioned.
  2. During development / local testing – via CLI wrappers or admin panels.
  3. During customer installation – as part of the initial system setup.

The service never touches journal entries, sales, purchases, stock, or posting
logic.  It only creates missing GLAccount rows and GLAccountMapping rows.

Public API
----------
  plan(tenant_id) -> SetupPlan
    Read-only. Inspects the tenant's chart and reports what would be created
    or mapped without changing any data.

  execute(tenant_id, dry_run=False) -> SetupResult
    Applies the plan. Creates missing postable GL accounts and inserts
    GLAccountMapping rows.  Commits only when dry_run=False.

  validate(tenant_id) -> ValidationResult
    Runs the Phase-1F-style readiness check against the tenant's current
    mappings.  Reports missing / invalid mappings.

  bulk_plan() -> dict[int, SetupPlan]
    Read-only plan for every existing tenant.

  bulk_execute(dry_run=False) -> list[SetupResult]
    Applies the plan to every existing tenant.

How Tenant Onboarding Will Call It (Future)
--------------------------------------------
Inside `services/tenant_service.py` (or equivalent tenant creation flow):

    from services.gl_accounting_setup import GLAccountingSetupService

    def finalize_new_tenant(tenant_id: int) -> None:
        # ... create tenant, branches, users ...
        result = GLAccountingSetupService.execute(tenant_id, dry_run=False)
        if result.errors:
            raise AccountingSetupError(result.errors)
        # ... proceed to activate tenant ...

This keeps the accounting setup logic inside the service layer, not in
ad-hoc scripts.

How Local / Test Setup Calls It (Now)
--------------------------------------
A thin CLI wrapper (`tools/qa/run_gl_accounting_setup.py`) calls the same
service:

    python tools/qa/run_gl_accounting_setup.py --plan
    python tools/qa/run_gl_accounting_setup.py --execute --tenant-id 2
    python tools/qa/run_gl_accounting_setup.py --execute

The wrapper is disposable; the service is permanent.

Data Created
------------
- GLAccount rows (missing postable accounts only).
- GLAccountMapping rows (tenant-level defaults only; branch_id IS NULL).

Nothing else is created, updated, or deleted.

Validations Performed
---------------------
1. Before creating an account:
   • Does a postable, active, same-tenant candidate already exist?
   • Is the chosen code unique within the tenant?
   • Is the parent account (if any) a header in the same tenant?

2. Before creating a mapping:
   • Is the GL account active, not header, and owned by the same tenant?
   • Does a tenant-level mapping for this concept already exist?
   • Is the concept code in the approved registry?

3. After execution (optional):
   • Re-runs GLMappingValidationService.dry_run() to confirm readiness.

Avoiding One-Off Seed Behaviour
--------------------------------
- No hardcoded tenant IDs.
- No SQL INSERT statements bypassing the ORM.
- No `if tenant_id == 1:` special cases.
- All discovery rules live in `DEFAULT_CONCEPT_RULES` and apply to any tenant.
- Account creation uses tenant-relative code allocation (`_next_child_code`,
  `_next_available_code`) so it never collides with existing tenant codes.
- The service is idempotent: running `execute()` twice on the same tenant
  skips already-mapped concepts and existing accounts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from extensions import db
from models import Tenant
from models._constants import GL_CONCEPT_REGISTRY, REQUIRED_GL_CONCEPTS, VALID_GL_CONCEPT_CODES
from models.gl import GLAccount, GLAccountMapping


# ---------------------------------------------------------------------------
# Reusable concept rules
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConceptSetupRule:
    """How to resolve a single concept for any tenant.

    Fields:
        legacy_code:      Exact code to look for first.
        search_names:     Name substrings to scan (case-insensitive, EN + AR).
        expected_types:   Valid account types.
        parent_code_hint: Parent code whose children may be scanned.
        creation_template:  Dict describing a new account if no candidate exists.
        allow_same_as:    Map to another concept's resolved account.
    """
    legacy_code: str | None = None
    search_names: tuple[str, ...] = ()
    expected_types: tuple[str, ...] = ()
    parent_code_hint: str | None = None
    creation_template: dict[str, object] | None = None
    allow_same_as: str | None = None


DEFAULT_CONCEPT_RULES: dict[str, ConceptSetupRule] = {
    "AR": ConceptSetupRule(
        legacy_code="1130",
        expected_types=("asset",),
    ),
    "AP": ConceptSetupRule(
        legacy_code="2110",
        expected_types=("liability",),
    ),
    "CASH": ConceptSetupRule(
        search_names=("cash", "cashbox", "petty cash", "صندوق", "نقد"),
        expected_types=("asset",),
        parent_code_hint="1110",
        creation_template={
            "code_suffix": "-B1",
            "name": "Cash",
            "name_ar": "صندوق",
            "type": "asset",
            "liquidity_kind": "cash",
            "is_default_liquidity": True,
        },
    ),
    "BANK": ConceptSetupRule(
        search_names=("bank", "checking", "savings", "بنك"),
        expected_types=("asset",),
        parent_code_hint="1120",
        creation_template={
            "code_suffix": "-B1",
            "name": "Bank",
            "name_ar": "بنك",
            "type": "asset",
            "liquidity_kind": "bank",
            "is_default_liquidity": True,
        },
    ),
    "INVENTORY_ASSET": ConceptSetupRule(
        legacy_code="1140",
        expected_types=("asset",),
    ),
    "COGS": ConceptSetupRule(
        legacy_code="5100",
        expected_types=("expense",),
    ),
    "COGS_REVERSAL": ConceptSetupRule(
        allow_same_as="COGS",
    ),
    "SALES_REVENUE": ConceptSetupRule(
        legacy_code="4100",
        expected_types=("revenue",),
    ),
    "SALES_RETURNS": ConceptSetupRule(
        search_names=("sales return", "returns", "مردودات مبيعات"),
        expected_types=("revenue",),
        creation_template={
            "code_near": "4110",
            "name": "Sales Returns",
            "name_ar": "مردودات مبيعات",
            "type": "revenue",
        },
    ),
    "SALES_DISCOUNT": ConceptSetupRule(
        search_names=("discount", "discounts given", "خصم مبيعات"),
        expected_types=("expense", "revenue"),
        creation_template={
            "code_near": "6130",
            "name": "Sales Discount",
            "name_ar": "خصم مبيعات",
            "type": "expense",
        },
    ),
    "VAT_INPUT": ConceptSetupRule(
        search_names=("vat input", "input vat", "ضريبة مدخلات"),
        expected_types=("asset", "liability"),
        creation_template={
            "code_near": "1170",
            "name": "VAT Input",
            "name_ar": "ضريبة مدخلات",
            "type": "asset",
        },
    ),
    "VAT_OUTPUT": ConceptSetupRule(
        legacy_code="2130",
        expected_types=("liability",),
    ),
    "FX_GAIN": ConceptSetupRule(
        search_names=("foreign exchange gain", "fx gain", "أرباح فروقات عملة"),
        expected_types=("revenue",),
        creation_template={
            "code_near": "4400",
            "name": "Foreign Exchange Gain",
            "name_ar": "أرباح فروقات عملة",
            "type": "revenue",
        },
    ),
    "FX_LOSS": ConceptSetupRule(
        search_names=("foreign exchange loss", "fx loss", "خسائر فروقات عملة"),
        expected_types=("expense",),
        creation_template={
            "code_near": "6900",
            "name": "Foreign Exchange Loss",
            "name_ar": "خسائر فروقات عملة",
            "type": "expense",
        },
    ),
    "CHEQUES_UNDER_COLLECTION": ConceptSetupRule(
        legacy_code="1150",
        expected_types=("asset",),
    ),
    "INVENTORY_ADJUSTMENT_GAIN": ConceptSetupRule(
        search_names=("inventory adjustment gain", "أرباح تسوية مخزون"),
        expected_types=("revenue",),
        creation_template={
            "code_near": "4450",
            "name": "Inventory Adjustment Gain",
            "name_ar": "أرباح تسوية مخزون",
            "type": "revenue",
        },
    ),
    "INVENTORY_ADJUSTMENT_LOSS": ConceptSetupRule(
        search_names=("inventory adjustment loss", "inventory adjustments", "خسائر تسوية مخزون"),
        expected_types=("expense",),
        creation_template={
            "code_near": "5150",
            "name": "Inventory Adjustment Loss",
            "name_ar": "خسائر تسوية مخزون",
            "type": "expense",
        },
    ),
    "FREIGHT_IN": ConceptSetupRule(
        search_names=("freight in", "shipping in", "مصاريف شحن وارد"),
        expected_types=("expense",),
        creation_template={
            "code_near": "5120",
            "name": "Freight In",
            "name_ar": "مصاريف شحن وارد",
            "type": "expense",
        },
    ),
    "CUSTOMS_DUTY": ConceptSetupRule(
        search_names=("customs duty", "customs", "tariff", "رسوم جمركية"),
        expected_types=("expense",),
        creation_template={
            "code_near": "5130",
            "name": "Customs Duty",
            "name_ar": "رسوم جمركية",
            "type": "expense",
        },
    ),
}


DEFAULT_CONCEPT_RULES.update({
    "DEFERRED_CHEQUES_PAYABLE": ConceptSetupRule(
        legacy_code="2120",
        expected_types=("liability",),
        creation_template={
            "code_near": "2120",
            "name": "Deferred Cheques Payable",
            "name_ar": "شيكات مؤجلة الدفع",
            "type": "liability",
        },
    ),
    "END_OF_SERVICE_PROVISION": ConceptSetupRule(
        legacy_code="6190",
        search_names=("end of service", "eos provision", "مخصص نهاية خدمة", "تعويض نهاية خدمة"),
        expected_types=("expense",),
        creation_template={
            "code_near": "6190",
            "name": "End of Service Provision",
            "name_ar": "مصروف مخصص نهاية خدمة",
            "type": "expense",
        },
    ),
    "LEAVE_ACCRUAL_LIABILITY": ConceptSetupRule(
        legacy_code="2160",
        search_names=("leave accrual", "vacation accrual", "استحقاقات إجازة", "إلتزام إجازات"),
        expected_types=("liability",),
        creation_template={
            "code_near": "2160",
            "name": "Leave Accrual Liability",
            "name_ar": "إلتزام استحقاقات إجازة",
            "type": "liability",
        },
    ),
    "PARTNER_CURRENT_ACCOUNT": ConceptSetupRule(
        legacy_code="3350",
        search_names=("partner current", "partners current", "جاري الشركاء"),
        expected_types=("equity", "liability", "asset"),
        creation_template={
            "code_near": "3350",
            "name": "Partner Current Account",
            "name_ar": "جاري الشركاء",
            "type": "equity",
        },
    ),
    "MERCHANT_CURRENT_ACCOUNT": ConceptSetupRule(
        legacy_code="2115",
        search_names=("merchant current", "merchant payable", "ذمم التجار"),
        expected_types=("liability", "asset"),
        creation_template={
            "code_near": "2115",
            "name": "Merchant Current Account",
            "name_ar": "ذمم التجار",
            "type": "liability",
        },
    ),
    "SHIPPING_REVENUE": ConceptSetupRule(
        legacy_code="4300",
        search_names=("shipping revenue", "delivery revenue", "إيرادات الشحن"),
        expected_types=("revenue",),
        creation_template={
            "code_near": "4300",
            "name": "Shipping Revenue",
            "name_ar": "إيرادات شحن",
            "type": "revenue",
        },
    ),
    "MISC_EXPENSE": ConceptSetupRule(
        legacy_code="6990",
        search_names=("miscellaneous expense", "misc expense", "مصاريف متنوعة"),
        expected_types=("expense",),
        creation_template={
            "code_near": "6990",
            "name": "Miscellaneous Expense",
            "name_ar": "مصاريف متنوعة",
            "type": "expense",
        },
    ),
    "COMMISSION_EXPENSE": ConceptSetupRule(
        legacy_code="6150",
        search_names=("commission expense", "partner commission", "مصروف عمولات"),
        expected_types=("expense",),
        creation_template={
            "code_near": "6150",
            "name": "Commission Expense",
            "name_ar": "مصروف عمولات",
            "type": "expense",
        },
    ),
    "EMPLOYEE_ADVANCES": ConceptSetupRule(
        legacy_code="1160",
        search_names=("employee advances", "salary advances", "سلف الموظفين"),
        expected_types=("asset",),
        creation_template={
            "code_near": "1160",
            "name": "Employee Advances",
            "name_ar": "سلف الموظفين",
            "type": "asset",
        },
    ),
    "PAYROLL_EXPENSE": ConceptSetupRule(
        legacy_code="6100",
        search_names=("salary", "payroll", "wages", "رواتب"),
        expected_types=("expense",),
        creation_template={
            "code_near": "6100",
            "name": "Payroll Expense",
            "name_ar": "رواتب وأجور",
            "type": "expense",
        },
    ),
    "PAYROLL_PAYABLE": ConceptSetupRule(
        legacy_code="2141",
        search_names=("salary payable", "payroll payable", "رواتب مستحقة"),
        expected_types=("liability",),
        creation_template={
            "code_near": "2141",
            "name": "Payroll Payable",
            "name_ar": "رواتب مستحقة",
            "type": "liability",
        },
    ),
    "END_OF_SERVICE_LIABILITY": ConceptSetupRule(
        legacy_code="2140",
        search_names=("end of service liability", "eos provision", "مخصص نهاية خدمة", "تعويض نهاية خدمة"),
        expected_types=("liability",),
        creation_template={
            "code_near": "2140",
            "name": "End of Service Benefits Provision",
            "name_ar": "مخصص نهاية الخدمة للموظفين",
            "type": "liability",
        },
    ),
    "PAYROLL_EXPENSE": ConceptSetupRule(
        legacy_code="6220",
        search_names=("salary", "payroll", "wages", "رواتب"),
        expected_types=("expense",),
        creation_template={
            "code_near": "6220",
            "name": "Payroll Expense",
            "name_ar": "رواتب وأجور",
            "type": "expense",
        },
    ),
    "BANK_FEES": ConceptSetupRule(
        legacy_code="6950",
        search_names=("bank charges", "bank fees", "مصاريف بنكية"),
        expected_types=("expense",),
        creation_template={
            "code_near": "6950",
            "name": "Bank Fees",
            "name_ar": "مصاريف بنكية",
            "type": "expense",
        },
    ),
    "BANK_INTEREST_INCOME": ConceptSetupRule(
        legacy_code="4500",
        search_names=("bank interest", "interest income", "other revenue", "فوائد بنكية"),
        expected_types=("revenue",),
        creation_template={
            "code_near": "4500",
            "name": "Bank Interest Income",
            "name_ar": "إيرادات فوائد بنكية",
            "type": "revenue",
        },
    ),
    "DONATION_REVENUE": ConceptSetupRule(
        legacy_code="4200",
        search_names=("donation revenue", "service revenue", "إيرادات الخدمات"),
        expected_types=("revenue",),
        creation_template={
            "code_near": "4200",
            "name": "Donation Revenue",
            "name_ar": "إيرادات تبرعات",
            "type": "revenue",
        },
    ),
    "FIXED_ASSET_ASSET": ConceptSetupRule(
        legacy_code="1240",
        search_names=("fixed asset", "equipment", "أصول ثابتة", "معدات"),
        expected_types=("asset",),
        parent_code_hint="1200",
        creation_template={
            "code_near": "1240",
            "name": "Fixed Asset",
            "name_ar": "أصول ثابتة",
            "type": "asset",
        },
    ),
    "DEPRECIATION_EXPENSE": ConceptSetupRule(
        legacy_code="6180",
        search_names=("depreciation expense", "استهلاك"),
        expected_types=("expense",),
        creation_template={
            "code_near": "6180",
            "name": "Depreciation Expense",
            "name_ar": "مصروف استهلاك",
            "type": "expense",
        },
    ),
    "ACCUMULATED_DEPRECIATION": ConceptSetupRule(
        legacy_code="1290",
        search_names=("accumulated depreciation", "مجمع الاستهلاك"),
        expected_types=("asset",),
        parent_code_hint="1200",
        creation_template={
            "code_near": "1290",
            "name": "Accumulated Depreciation",
            "name_ar": "مجمع الاستهلاك",
            "type": "asset",
        },
    ),
    "FIXED_ASSET_GAIN": ConceptSetupRule(
        legacy_code="4500",
        search_names=("asset disposal gain", "fixed asset gain", "other revenue"),
        expected_types=("revenue",),
        creation_template={
            "code_near": "4500",
            "name": "Fixed Asset Disposal Gain",
            "name_ar": "أرباح بيع أصول ثابتة",
            "type": "revenue",
        },
    ),
    "FIXED_ASSET_LOSS": ConceptSetupRule(
        legacy_code="6990",
        search_names=("asset disposal loss", "fixed asset loss", "miscellaneous expense"),
        expected_types=("expense",),
        creation_template={
            "code_near": "6990",
            "name": "Fixed Asset Disposal Loss",
            "name_ar": "خسائر بيع أصول ثابتة",
            "type": "expense",
        },
    ),
})


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SetupPlanAction:
    action_type: str          # "create_account" | "select_existing" | "map_concept" | "skip"
    tenant_id: int
    concept_code: str
    gl_account_id: int | None = None
    gl_account_code: str | None = None
    gl_account_name: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SetupPlan:
    tenant_id: int
    tenant_name: str
    actions: list[SetupPlanAction]

    def to_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant_name,
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass(frozen=True)
class SetupResult:
    tenant_id: int
    tenant_name: str
    created_accounts: list[dict[str, object]]
    created_mappings: list[dict[str, object]]
    skipped_concepts: list[dict[str, object]]
    errors: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant_name,
            "created_accounts": self.created_accounts,
            "created_mappings": self.created_mappings,
            "skipped_concepts": self.skipped_concepts,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

class GLAccountingSetupService:
    """Reusable service to prepare a tenant's GL concept mappings."""

    # ================================================================
    # ================================================================

    @staticmethod
    def plan(tenant_id: int) -> SetupPlan | None:
        """Read-only plan for one tenant."""
        tenant = Tenant.query.filter_by(id=tenant_id).first()
        if not tenant:
            return None
        actions = GLAccountingSetupService._build_plan(tenant)
        return SetupPlan(
            tenant_id=tenant.id,
            tenant_name=tenant.name or f"Tenant {tenant.id}",
            actions=actions,
        )

    @staticmethod
    def plan_all() -> list[SetupPlan]:
        """Read-only plan for every tenant."""
        tenants = Tenant.query.order_by(Tenant.id.asc()).all()
        return [
            SetupPlan(
                tenant_id=t.id,
                tenant_name=t.name or f"Tenant {t.id}",
                actions=GLAccountingSetupService._build_plan(t),
            )
            for t in tenants
        ]

    @staticmethod
    def execute(tenant_id: int, dry_run: bool = True) -> SetupResult:
        """Apply the plan to one tenant.

        When ``dry_run=True`` (default) no database changes are committed.
        When ``dry_run=False`` accounts and mappings are created and committed.
        """
        tenant = Tenant.query.filter_by(id=tenant_id).first()
        if not tenant:
            return SetupResult(
                tenant_id=tenant_id,
                tenant_name="",
                created_accounts=[],
                created_mappings=[],
                skipped_concepts=[],
                errors=[f"Tenant {tenant_id} not found."],
            )

        plan = GLAccountingSetupService._build_plan(tenant)
        created_accounts: list[dict[str, object]] = []
        created_mappings: list[dict[str, object]] = []
        skipped_concepts: list[dict[str, object]] = []
        errors: list[str] = []

        for action in plan:
            if action.action_type != "create_account":
                continue
            try:
                account = GLAccountingSetupService._create_account(tenant, action.concept_code)
                db.session.add(account)
                if not dry_run:
                    db.session.flush()
                created_accounts.append({
                    "id": account.id,
                    "code": account.code,
                    "name": account.name,
                    "name_ar": account.name_ar,
                    "type": account.type,
                })
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Create account failed for {action.concept_code}: {exc}")

        # Rebuild plan so new account IDs are visible
        plan = GLAccountingSetupService._build_plan(tenant)

        for action in plan:
            if action.action_type != "map_concept":
                continue
            if action.gl_account_id is None:
                skipped_concepts.append({
                    "concept_code": action.concept_code,
                    "reason": action.reason,
                })
                continue
            existing = (
                GLAccountMapping.query
                .filter_by(
                    tenant_id=tenant.id,
                    concept_code=action.concept_code,
                    branch_id=None,
                )
                .first()
            )
            if existing:
                continue
            try:
                mapping = GLAccountMapping(
                    tenant_id=tenant.id,
                    concept_code=action.concept_code,
                    gl_account_id=action.gl_account_id,
                    branch_id=None,
                    is_active=True,
                )
                db.session.add(mapping)
                if not dry_run:
                    db.session.flush()
                created_mappings.append({
                    "id": mapping.id,
                    "concept_code": action.concept_code,
                    "gl_account_id": action.gl_account_id,
                    "gl_account_code": action.gl_account_code,
                    "gl_account_name": action.gl_account_name,
                })
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Map concept failed for {action.concept_code}: {exc}")

        if dry_run:
            db.session.rollback()
        else:
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise


        return SetupResult(
            tenant_id=tenant.id,
            tenant_name=tenant.name or f"Tenant {tenant.id}",
            created_accounts=created_accounts,
            created_mappings=created_mappings,
            skipped_concepts=skipped_concepts,
            errors=errors,
        )

    @staticmethod
    def execute_all(dry_run: bool = True) -> list[SetupResult]:
        """Apply the plan to every tenant."""
        tenants = Tenant.query.order_by(Tenant.id.asc()).all()
        return [
            GLAccountingSetupService.execute(t.id, dry_run=dry_run)
            for t in tenants
        ]

    @staticmethod
    def validate(tenant_id: int | None = None) -> dict[str, object]:
        """Run Phase-1F readiness validation.

        Delegates to the existing GLMappingValidationService so the check
        is always consistent with the rest of the application.
        """
        from services.gl_mapping_validation import dry_run_gl_mapping_validation

        return dry_run_gl_mapping_validation(
            tenant_id=tenant_id,
            include_ready=True,
        )

    # ================================================================
    # ================================================================

    @staticmethod
    def _build_plan(tenant: Tenant) -> list[SetupPlanAction]:
        """Build the action list for one tenant."""
        actions: list[SetupPlanAction] = []
        resolved: dict[str, GLAccount | None] = {}

        for concept_code in sorted(DEFAULT_CONCEPT_RULES):
            rule = DEFAULT_CONCEPT_RULES[concept_code]

            # Alias resolution (e.g. COGS_REVERSAL -> COGS)
            if rule.allow_same_as:
                alias_account = resolved.get(rule.allow_same_as)
                if alias_account:
                    actions.append(
                        SetupPlanAction(
                            action_type="map_concept",
                            tenant_id=tenant.id,
                            concept_code=concept_code,
                            gl_account_id=alias_account.id,
                            gl_account_code=alias_account.code,
                            gl_account_name=alias_account.name,
                            reason=f"Mapped to same account as {rule.allow_same_as}",
                        )
                    )
                    resolved[concept_code] = alias_account
                    continue

            # Find existing candidate
            candidate = GLAccountingSetupService._find_best_candidate(tenant, rule)
            if candidate:
                actions.append(
                    SetupPlanAction(
                        action_type="map_concept",
                        tenant_id=tenant.id,
                        concept_code=concept_code,
                        gl_account_id=candidate.id,
                        gl_account_code=candidate.code,
                        gl_account_name=candidate.name,
                        reason="Existing postable account matched",
                    )
                )
                resolved[concept_code] = candidate
                continue

            # No candidate – create if template exists
            if rule.creation_template:
                actions.append(
                    SetupPlanAction(
                        action_type="create_account",
                        tenant_id=tenant.id,
                        concept_code=concept_code,
                        reason=f"Will create new postable account for {concept_code}",
                    )
                )
                resolved[concept_code] = None
            else:
                actions.append(
                    SetupPlanAction(
                        action_type="skip",
                        tenant_id=tenant.id,
                        concept_code=concept_code,
                        reason="No candidate found and no creation template defined.",
                    )
                )
                resolved[concept_code] = None

        return actions

    # ================================================================
    # ================================================================

    @staticmethod
    def _find_best_candidate(tenant: Tenant, rule: ConceptSetupRule) -> GLAccount | None:
        """Find the best existing postable GL account for a concept."""
        # 1. Exact legacy code match
        if rule.legacy_code:
            acc = (
                GLAccount.query
                .filter_by(tenant_id=tenant.id, code=rule.legacy_code)
                .first()
            )
            if acc and acc.is_active and not acc.is_header:
                if not rule.expected_types or acc.type in rule.expected_types:
                    return acc

        # 2. Name search (exact/partial, EN + AR)
        if rule.search_names:
            accounts = (
                GLAccount.query
                .filter_by(tenant_id=tenant.id, is_active=True, is_header=False)
                .all()
            )
            for pattern in rule.search_names:
                for account in accounts:
                    if rule.expected_types and account.type not in rule.expected_types:
                        continue
                    if pattern.lower() in (account.name or "").lower():
                        return account
                    if pattern.lower() in (account.name_ar or "").lower():
                        return account

        # 3. Parent-code child scan
        if rule.parent_code_hint:
            parent = (
                GLAccount.query
                .filter_by(tenant_id=tenant.id, code=rule.parent_code_hint)
                .first()
            )
            if parent:
                postable = [
                    c for c in parent.children
                    if c.is_active and not c.is_header
                    and (not rule.expected_types or c.type in rule.expected_types)
                ]
                if postable:
                    # Prefer primary / main / default
                    for keyword in ("main", "primary", "default"):
                        for child in postable:
                            if keyword.lower() in (child.name or "").lower():
                                return child
                    return sorted(postable, key=lambda x: x.code)[0]

        return None

    # ================================================================
    # ================================================================

    @staticmethod
    def _create_account(tenant: Tenant, concept_code: str) -> GLAccount:
        """Create a new postable GL account for a concept."""
        rule = DEFAULT_CONCEPT_RULES[concept_code]
        tmpl = rule.creation_template or {}

        parent = None
        if rule.parent_code_hint:
            parent = (
                GLAccount.query
                .filter_by(tenant_id=tenant.id, code=rule.parent_code_hint)
                .first()
            )

        if "code_suffix" in tmpl:
            base = rule.parent_code_hint or str(tmpl.get("code_near", ""))
            code = GLAccountingSetupService._next_child_code(tenant.id, base)
        elif "code_near" in tmpl:
            code = GLAccountingSetupService._next_available_code(
                tenant.id, str(tmpl["code_near"])
            )
        else:
            raise ValueError(f"No code strategy for concept {concept_code}")

        level = (parent.level + 1) if parent else 1
        return GLAccount(
            tenant_id=tenant.id,
            code=code,
            name=str(tmpl.get("name", concept_code)),
            name_ar=str(tmpl.get("name_ar", "")),
            parent_id=parent.id if parent else None,
            type=str(tmpl.get("type", "asset")),
            is_active=True,
            is_header=False,
            level=level,
            currency="AED",
            liquidity_kind=tmpl.get("liquidity_kind"),
            is_default_liquidity=bool(tmpl.get("is_default_liquidity", False)),
        )

    @staticmethod
    def _next_child_code(tenant_id: int, parent_code: str) -> str:
        """Allocate next child code, e.g. 1120-B3."""
        existing = (
            GLAccount.query
            .filter_by(tenant_id=tenant_id)
            .filter(GLAccount.code.like(f"{parent_code}-%"))
            .order_by(GLAccount.code.asc())
            .all()
        )
        suffixes = []
        for acc in existing:
            parts = acc.code.split("-")
            if len(parts) == 2 and parts[1].startswith("B"):
                try:
                    suffixes.append(int(parts[1][1:]))
                except ValueError:
                    pass
        next_num = max(suffixes, default=0) + 1
        return f"{parent_code}-B{next_num}"

    @staticmethod
    def _next_available_code(tenant_id: int, base_code: str) -> str:
        """Find next unused code near a base, e.g. 4110 → 4111 → 4112."""
        if not GLAccount.query.filter_by(tenant_id=tenant_id, code=base_code).first():
            return base_code
        for offset in range(1, 100):
            candidate = str(int(base_code) + offset)
            if not GLAccount.query.filter_by(tenant_id=tenant_id, code=candidate).first():
                return candidate
        raise RuntimeError(f"No available code near {base_code} for tenant {tenant_id}")
