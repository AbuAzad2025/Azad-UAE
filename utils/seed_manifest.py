"""Single manifest of every seedable data set in the system.

Why this exists
---------------
Seeding was spread across eight modules with no index: ``utils/system_init.py``,
``utils/seed_industry_fields.py``, ``models/gl_account_registry.py``,
``models/_constants.py``, ``models/pos_order_type.py``,
``services/store_payment_method_service.py``,
``services/saas_provisioning_service.py`` and
``services/document_sequence_service.py``. Nothing recorded which of those
actually run on a given boot. That is how AGENTS.md came to claim "37 perms /
8 roles / 76 industry fields" when the real counts are 36 / 9 / 74, and how
``app/runtime/accounting_repair.py`` came to carry a docstring claiming it runs
at startup when it has no production caller.

This module is the index. It is **pure data plus dotted callables** - importing it
touches no database and inserts nothing. ``app/bootstrap.py`` reads it at boot to
*verify* what is present; it never seeds from here, because every entry already
has an owner that knows how to seed itself idempotently.

Scope vocabulary
----------------
``platform``
    One copy for the whole install. Seeded once, at boot.
``tenant``
    One copy per tenant. Seeded at tenant creation, then repaired on each boot
    for tenants that already exist.
``lazy``
    Created on first read rather than up front. Correct for anything that belongs
    to a single business object.
``deliberate``
    Intentionally not seeded. The operator or tenant creates it. Listed here so a
    later reader does not "fix" it - ``packages`` is the important one: the owner
    panel owns SaaS pricing, and auto-seeding it would silently override a
    product decision (``scripts/ops/first_run_dev.py:160``).

The counts in ``expected`` are asserted against the source, not estimated.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeedSet:
    """One seedable data set.

    Attributes:
        key: Stable identifier, safe to use in logs and tests.
        label: Human description.
        scope: ``platform`` | ``tenant`` | ``lazy`` | ``deliberate``.
        seeder: Dotted path to the callable that seeds it, or ``None`` when the
            data set is not seeded at all.
        expected: Row count when the data set is fully seeded. ``None`` when the
            count depends on the deployment (per-tenant GL trees, for example).
        source: Where the data set is defined, for a reader who wants the rows.
        note: Why it is wired the way it is.
        verify: Dotted path to a zero-argument callable returning the current row
            count. Optional; a set without one is reported as unverified.
    """

    key: str
    label: str
    scope: str
    seeder: str | None
    expected: int | None
    source: str
    note: str = ""
    verify: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


# ── Platform-wide, seeded at every boot ──────────────────────────────────────

PLATFORM_SEEDS: tuple[SeedSet, ...] = (
    SeedSet(
        key="permissions",
        label="Role permissions",
        scope="platform",
        seeder="utils.system_init._ensure_permissions",
        expected=36,
        source="utils/constants.py:PERMISSION_CODES",
        note="Re-applied on every boot; the owner role is granted all of them.",
        verify="utils.seed_manifest_probe.count_permissions",
        tags=("rbac",),
    ),
    SeedSet(
        key="roles",
        label="System roles (owner, super_admin, developer + 6 functional)",
        scope="platform",
        seeder="utils.system_init._ensure_owner_role/_ensure_super_admin_role/"
        "_ensure_developer_role/_ensure_functional_roles",
        expected=9,
        source="utils/system_init.py",
        note="owner, super_admin, developer, manager, seller, branch_manager, accountant, kitchen, cashier",
        verify="utils.seed_manifest_probe.count_roles",
        tags=("rbac",),
    ),
    SeedSet(
        key="currencies",
        label="Base currencies",
        scope="platform",
        seeder="utils.system_init._ensure_platform_reference_data",
        expected=3,
        source="utils/system_init.py:318",
        note="ILS (base), AED, USD. Exchange rates are deliberately NOT seeded - the legacy rows were dead data.",
        verify="utils.seed_manifest_probe.count_currencies",
        tags=("finance", "i18n"),
    ),
    SeedSet(
        key="industry_field_definitions",
        label="Product field definitions per industry",
        scope="platform",
        seeder="utils.seed_industry_fields.seed_industry_fields",
        expected=74,
        source="utils/seed_industry_fields.py",
        note="13 core fields + 61 industry-specific across 12 industries.",
        verify="utils.seed_manifest_probe.count_industry_fields",
        tags=("catalog",),
    ),
    SeedSet(
        key="system_settings",
        label="System settings singleton",
        scope="platform",
        seeder="models.system_settings.SystemSettings.get_current",
        expected=1,
        source="models/system_settings.py",
        note="Created on first read; every other value is a column default.",
        verify="utils.seed_manifest_probe.count_system_settings",
        tags=("platform",),
    ),
    SeedSet(
        key="security_alerts",
        label="Server activation record",
        scope="platform",
        seeder="utils.system_init._record_server_activation",
        expected=1,
        source="utils/system_init.py",
        note="Written once, on the first boot that creates the owner.",
        verify="utils.seed_manifest_probe.count_activation_alerts",
        tags=("platform", "audit"),
    ),
)


# ── Per tenant, repaired on every boot for tenants that exist ────────────────

TENANT_SEEDS: tuple[SeedSet, ...] = (
    SeedSet(
        key="gl_accounts",
        label="Chart of accounts",
        scope="tenant",
        seeder="services.gl_service.GLService.ensure_core_accounts",
        expected=None,
        source="models/gl_account_registry.py:BASE_ACCOUNTS",
        note="98 base accounts + the tenant's industry extension (49 across 13 "
        "industries) + 2 liquidity accounts per active branch. Self-healing: "
        "matches on code and repairs name/type/parent/header/level/contra.",
        verify="utils.seed_manifest_probe.min_gl_accounts_for_active_tenant",
        tags=("finance", "gl"),
    ),
    SeedSet(
        key="gl_account_mappings",
        label="GL concept to account mappings",
        scope="tenant",
        seeder="services.gl_service.GLService.ensure_gl_mappings",
        expected=None,
        source="services/gl_provisioning_service.py",
        note="Gated on ENABLE_DYNAMIC_GL_MAPPING. Accounts are created without "
        "mappings, so a tenant created outside the Owner panel gets accounts "
        "but no mappings.",
        verify="utils.seed_manifest_probe.count_gl_mappings",
        tags=("finance", "gl"),
    ),
    SeedSet(
        key="pos_order_types",
        label="POS order types",
        scope="tenant",
        seeder="models.pos_order_type.ensure_default_pos_order_types",
        expected=6,
        source="models/pos_order_type.py:DEFAULT_POS_ORDER_TYPES",
        note="Seeded at tenant creation in the Owner panel, not on every boot.",
        tags=("pos", "tenant-creation"),
    ),
    SeedSet(
        key="store_payment_methods",
        label="Storefront payment methods",
        scope="tenant",
        seeder="services.store_payment_method_service.StorePaymentMethodService.ensure_defaults",
        expected=5,
        source="services/store_payment_method_service.py",
        note="cod/bank_transfer/card/e_wallet/online_pay. Only cod is enabled by "
        "default. Seeded for tenant 1 at boot; other tenants get them lazily.",
        tags=("store",),
    ),
    SeedSet(
        key="branches",
        label="Branches",
        scope="tenant",
        seeder=None,
        expected=None,
        source="routes/branches.py",
        note="Operator-created. Creating one also seeds its 1110-B/1120-B "
        "liquidity accounts via the Branch after_insert listener.",
        tags=("deliberate-empty",),
    ),
)


# ── Created on first use ─────────────────────────────────────────────────────

LAZY_SEEDS: tuple[SeedSet, ...] = (
    SeedSet(
        key="document_sequences",
        label="Numbering sequences",
        scope="lazy",
        seeder="services.document_sequence_service.DocumentSequenceService.get_or_create",
        expected=9,
        source="services/document_sequence_service.py",
        note="sale, purchase, payment, receipt, gl_entry, cheque, invoice, "
        "return, expense. Locked with SELECT ... FOR UPDATE on first use.",
        tags=("numbering",),
    ),
    SeedSet(
        key="tenant_stores",
        label="Tenant storefronts",
        scope="lazy",
        seeder="services.store_service.StoreService.ensure_tenant_store",
        expected=None,
        source="services/store_service.py",
        note="Created on first store access.",
        tags=("store",),
    ),
    SeedSet(
        key="invoice_settings",
        label="Invoice settings",
        scope="lazy",
        seeder="models.invoice_settings.InvoiceSettings.get_active",
        expected=None,
        source="models/invoice_settings.py",
        note="Created on first read.",
        tags=("invoicing",),
    ),
    SeedSet(
        key="integration_settings",
        label="Integration settings",
        scope="lazy",
        seeder="models.integration_settings.IntegrationSettings.get_service_config",
        expected=None,
        source="models/integration_settings.py",
        note="Created on first read of a service config.",
        tags=("integrations",),
    ),
)


# ── Intentionally NOT seeded ─────────────────────────────────────────────────
#
# These are listed so their absence is a recorded decision rather than an
# apparent oversight. None of them is a platform "basic": each belongs to a
# tenant's own business, and inventing rows would put data in the system that no
# operator asked for. The tenant-dropdown template already hardcodes eleven
# currency codes against three seeded rows, which is the shape of problem this
# comment exists to prevent.

DELIBERATELY_UNSEEDED: tuple[SeedSet, ...] = (
    SeedSet(
        key="packages",
        label="SaaS packages",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="services/saas_provisioning_service.py:seed_packages",
        note="DELIBERATE. The platform owner creates SaaS packages from the "
        "Owner panel (payment_vault/packages-management). An idempotent "
        "seeder exists but is deliberately not called at boot - see "
        "scripts/ops/first_run_dev.py:160 and first_run_prod.py:18.",
        tags=("deliberate-empty", "saas"),
    ),
    SeedSet(
        key="expense_categories",
        label="Expense categories",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="routes/expenses.py",
        note="Tenant business data. Created by the operator.",
        tags=("deliberate-empty",),
    ),
    SeedSet(
        key="product_categories",
        label="Product categories",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="services/product_service.py",
        note="Tenant business data. Created by the operator.",
        tags=("deliberate-empty",),
    ),
    SeedSet(
        key="departments_job_positions_leave_types",
        label="HR structures (departments, job positions, leave types)",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="services/hr_service.py",
        note="Tenant business data.",
        tags=("deliberate-empty", "hr"),
    ),
    SeedSet(
        key="crm_stages_and_teams",
        label="CRM stages and teams",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="models/crm.py",
        note="Tenant business data.",
        tags=("deliberate-empty", "crm"),
    ),
    SeedSet(
        key="helpdesk_categories",
        label="Ticket categories and priorities",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="models/helpdesk.py",
        note="Tenant business data.",
        tags=("deliberate-empty", "helpdesk"),
    ),
    SeedSet(
        key="cost_profit_fiscal_positions",
        label="Cost centres, profit centres, fiscal positions",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="models/cost_center.py, models/profit_center.py, models/fiscal_position.py",
        note="Tenant business data.",
        tags=("deliberate-empty", "finance"),
    ),
    SeedSet(
        key="customs_taxes_and_rules",
        label="Customs taxes and tax calculation rules",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="models/advanced_accounting.py",
        note="Tenant business data.",
        tags=("deliberate-empty", "finance"),
    ),
    SeedSet(
        key="gl_periods",
        label="Accounting periods",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="routes/ledger.py",
        note="Created by the explicit close-month action, never in bulk: an "
        "auto-created period would silently lock a month.",
        tags=("deliberate-empty", "finance"),
    ),
    SeedSet(
        key="exchange_rates",
        label="Exchange rates",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="models/currency.py, models/exchange_rate_record.py",
        note="DELIBERATE. Rates are entered by the operator or fetched from the "
        "configured provider. utils/system_init.py:303 records that the legacy "
        "seeded rows were dead data - written but read by nothing.",
        tags=("deliberate-empty", "finance"),
    ),
    SeedSet(
        key="units_of_measure",
        label="Units of measure",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="models/product.py:unit (free text)",
        note="No table exists. utils/constants.py:PRODUCT_UNITS looks like a "
        "master list but has exactly one reference in the repo - its own "
        "definition. products.unit is free text defaulting to 'piece'.",
        tags=("deliberate-empty", "catalog"),
    ),
    SeedSet(
        key="vat_rates",
        label="VAT rates",
        scope="deliberate",
        seeder=None,
        expected=None,
        source="utils/tax_settings.py, models/tenant.py",
        note="No table. Rates live in tenant/system-settings columns; "
        "VAT_RATES_BY_COUNTRY in utils/tax_settings.py is a display fallback.",
        tags=("deliberate-empty", "finance"),
    ),
)


ALL_SEED_SETS: tuple[SeedSet, ...] = PLATFORM_SEEDS + TENANT_SEEDS + LAZY_SEEDS + DELIBERATELY_UNSEEDED


def seed_sets_by_scope(scope: str) -> tuple[SeedSet, ...]:
    return tuple(s for s in ALL_SEED_SETS if s.scope == scope)


def expected_total_for_scope(scope: str) -> int | None:
    """Sum of fixed expected counts, or None if any member is deployment-shaped."""
    total = 0
    for s in seed_sets_by_scope(scope):
        if s.expected is None:
            return None
        total += s.expected
    return total
