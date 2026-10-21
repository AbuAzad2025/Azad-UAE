"""Every GL concept a posting can name must have a way to resolve.

Under the production default (``ENABLE_DYNAMIC_GL_MAPPING=True``) a posting
resolves its account through the tenant's ``gl_account_mappings`` rows, and
those rows are provisioned per module from ``GL_MODULE_DEFINITIONS``
(``models/gl_account_registry.py``). Two gaps made ordinary postings get
refused outright with ``GLMappingError``:

* a concept the registry declares ``mapping``-owned that no module carried -
  the resolver found no row for it and raised;
* a module whose ``feature_flag`` was not a column on ``tenants`` - the
  provisioning engine reads the flag with ``getattr(tenant, flag, False)``, so
  a flag with no column was always False, the module was never provisioned,
  and the concepts it owned had no row either.

These tests pin the fix:

* every ``mapping``-owned concept has a mapping row;
* every mapping row points at an account that exists in the seeded chart, is
  postable (a header cannot be posted to) and hangs off a parent that exists;
* every module's feature flag is a real ``Tenant`` column;
* a freshly provisioned tenant really carries the rows, and the resolver
  really resolves the concepts through them;
* every concept the services post is a concept the registry knows, so no
  posting names a concept the resolver refuses as unknown;
* every ``legacy_code`` hint names an account the seed really creates and the
  account the registry maps the concept to, so the Owner panel's mapping
  preview does not report noise for every tenant;
* no source file carries a run of question marks, which is what an Arabic
  string turns into when the file is written in the wrong encoding.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlalchemy as sa

from models._constants import (
    GL_CONCEPT_CODES,
    GL_CONCEPT_REGISTRY,
    RESOLUTION_MODE_LIQUIDITY,
    RESOLUTION_MODE_MAPPING,
    RESOLUTION_MODE_NON_POSTING,
    RESOLUTION_MODE_RECORD,
)
from models.gl_account_registry import (
    BASE_ACCOUNTS,
    GL_MODULE_DEFINITIONS,
    INDUSTRY_EXTENSIONS,
    GLAccountTemplate,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# The feature flag each non-core module is gated on. The names are asserted
# exactly, so a flag that does not exist on ``tenants`` cannot come back.
#
# Eight of these columns (enable_shipments, enable_campaigns, enable_partners,
# enable_fixed_assets, enable_donations, enable_warranty_tracking,
# enable_bank_reconciliation, enable_azad_platform) were added to the Tenant
# model in parallel with this work, by the revision
# ``5e2b8f4a6c13_add_tenant_module_feature_flags``. ``enable_store`` and
# ``enable_payroll`` were already on the model. The two flags that this work
# repaired are ``shop_online`` (it named ``enable_online_store``, which is not
# a column anywhere - the store gate is ``enable_store``) and
# ``azad_platform`` (it named ``enable_ecommerce``, which is a *platform*
# setting on ``SystemSettings``, not a tenant column).
EXPECTED_MODULE_FEATURE_FLAGS = {
    "shop_online": "enable_store",
    "shipments": "enable_shipments",
    "campaigns": "enable_campaigns",
    "partners": "enable_partners",
    "payroll": "enable_payroll",
    "fixed_assets": "enable_fixed_assets",
    "donations": "enable_donations",
    "warranty": "enable_warranty_tracking",
    "bank_reconciliation": "enable_bank_reconciliation",
    "azad_platform": "enable_azad_platform",
}

# Concepts whose resolution is not the mapping table: liquidity concepts are
# resolved from an explicit account code plus its ``liquidity_kind``, record
# concepts from an explicit account code plus ``explicit_account_allowed``,
# and a non-posting concept is refused outright.
NON_MAPPING_CONCEPTS = frozenset(
    code for code, meta in GL_CONCEPT_REGISTRY.items() if meta["resolution_mode"] != RESOLUTION_MODE_MAPPING
)

# Concepts the services post with a concept code, found by reading the
# source. The literal is the only way a posting line names a concept, so the
# scan is exact rather than a heuristic.
_POSTED_CONCEPT_PATTERN = re.compile(r"""["']concept_code["']\s*:\s*["']([A-Z_0-9]+)["']""")
_POSTING_SOURCE_DIRS = ("services", "models", "routes", "utils")

# One concept is posted by a service and is not in the registry:
# ``CAMPAIGN_DISCOUNT_REVERSAL`` (services/return_service.py). The resolver
# rejects a concept it does not know with "Unknown GL concept code" before it
# looks at the flag, so a promotional sale return is refused in both flag
# states. Fixing it needs a new concept, a registry entry and a migration
# that widens ``ck_gl_account_mappings_concept_code`` - the check constraint
# that lists the allowed concept codes - so it is listed here rather than
# silently ignored.
KNOWN_POSTED_CONCEPTS_WITHOUT_A_REGISTRY_ENTRY = frozenset({"CAMPAIGN_DISCOUNT_REVERSAL"})

# The database constrains gl_account_mappings.concept_code to a fixed list
# (ck_gl_account_mappings_concept_code, created by
# migrations/versions/squash_001_baseline.py). One concept is in the registry
# but not in that list: PAYROLL_EXPENSE_2 was added to the registry without
# widening the constraint, so PostgreSQL refuses any mapping row for it - and
# it refuses it by aborting the whole provisioning transaction, not by
# skipping the row. The concept is never posted by a service, so nothing is
# refused today, but it cannot be given a mapping row until the schema is
# brought back into step with the registry.
KNOWN_CONCEPTS_MISSING_FROM_THE_SCHEMA_CONSTRAINT = frozenset({"PAYROLL_EXPENSE_2"})

# The mapping-owned concepts that carry no legacy_code hint at all. The Owner
# panel's preview reports a concept without a hint as "manual_required" and
# leaves the mapping to the Owner; that is a different thing from a concept
# whose hint names an account the chart does not have, which is a defect. The
# set is pinned so that a hint appearing or disappearing is a deliberate
# change rather than a drift nobody notices.
CONCEPTS_WITHOUT_A_LEGACY_CODE_HINT = frozenset(
    {
        "COGS_REVERSAL",
        "CUSTOMS_DUTY",
        "FX_GAIN",
        "FX_LOSS",
        "FREIGHT_IN",
        "INVENTORY_ADJUSTMENT_GAIN",
        "INVENTORY_ADJUSTMENT_LOSS",
        "PURCHASE_RETURNS",
        "PURCHASES",
        "SALES_DISCOUNT",
        "SALES_RETURNS",
        "TIER_DISCOUNT",
    }
)


def _chart_templates() -> dict[str, GLAccountTemplate]:
    """Every account the seed can create: the base chart plus every industry."""
    templates: dict[str, GLAccountTemplate] = {t.code: t for t in BASE_ACCOUNTS}
    for extension in INDUSTRY_EXTENSIONS.values():
        for template in extension:
            templates.setdefault(template.code, template)
    return templates


def _mapping_rows() -> dict[str, list[tuple[str, str]]]:
    """concept code -> [(module code, account code), ...]."""
    rows: dict[str, list[tuple[str, str]]] = {}
    for module_code, module in GL_MODULE_DEFINITIONS.items():
        for mapping in module.mappings:
            rows.setdefault(mapping.concept_code, []).append((module_code, mapping.account_code))
    return rows


def _posted_concepts() -> dict[str, set[str]]:
    """concept code -> the source files that post it."""
    found: dict[str, set[str]] = {}
    for folder in _POSTING_SOURCE_DIRS:
        for path in sorted((PROJECT_ROOT / folder).rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in _POSTED_CONCEPT_PATTERN.finditer(text):
                found.setdefault(match.group(1), set()).add(str(path.relative_to(PROJECT_ROOT)))
    return found


def _concept_codes_allowed_by_the_schema() -> set[str]:
    """The concept codes the database accepts in gl_account_mappings."""
    from extensions import db

    constraints = sa.inspect(db.engine).get_check_constraints("gl_account_mappings")
    allowed: set[str] = set()
    for constraint in constraints:
        sqltext = constraint.get("sqltext") or ""
        if "concept_code" not in sqltext:
            continue
        allowed.update(re.findall(r"'([A-Z_0-9]+)'", sqltext))
    return allowed


class TestConceptCoverage:
    """Every mapping-owned concept has a mapping row."""

    def test_every_mapping_concept_has_a_mapping_row(self):
        rows = _mapping_rows()
        missing = sorted(
            code
            for code, meta in GL_CONCEPT_REGISTRY.items()
            if meta["resolution_mode"] == RESOLUTION_MODE_MAPPING
            and code not in rows
            and code not in KNOWN_CONCEPTS_MISSING_FROM_THE_SCHEMA_CONSTRAINT
        )
        assert not missing, (
            "these concepts are mapping-owned but no module carries a row for them, so a posting "
            f"that names one is refused with GLMappingError: {missing}"
        )

    def test_the_one_concept_the_schema_refuses_is_the_only_one(self):
        """PAYROLL_EXPENSE_2 is the single registry entry the schema rejects.

        The database constrains gl_account_mappings.concept_code to a fixed
        list, and PAYROLL_EXPENSE_2 is in the registry but not in that list.
        It therefore cannot carry a mapping row at all, and it is the only
        concept in that state.
        """
        rows = _mapping_rows()
        unmappable = sorted(
            code
            for code, meta in GL_CONCEPT_REGISTRY.items()
            if meta["resolution_mode"] == RESOLUTION_MODE_MAPPING and code not in rows
        )
        assert unmappable == sorted(KNOWN_CONCEPTS_MISSING_FROM_THE_SCHEMA_CONSTRAINT), (
            "the set of registry concepts that carry no mapping row changed: "
            f"{unmappable}. A new one is a posting that will be refused; a missing one means the "
            "schema has been widened and the exemption can be dropped."
        )

    def test_the_industry_revenue_concepts_are_mapped(self):
        """FOOD/BEVERAGE_SALES_REVENUE are the two industry-scoped concepts.

        Their own accounts (4114 Food Sales, 4115 Beverage Sales) are
        industry-extension accounts: they exist only in the chart of a tenant
        whose business_type is "restaurant". The provisioning engine can gate
        a module on a tenant boolean column and on nothing else, so a module
        carrying 4114/4115 would either be skipped for every tenant or report
        "account 4114 not found" for every non-restaurant tenant. Both
        concepts therefore resolve to the Sales Revenue account every chart
        carries. This test records the decision so it cannot be forgotten
        silently.
        """
        rows = _mapping_rows()
        for concept in ("FOOD_SALES_REVENUE", "BEVERAGE_SALES_REVENUE"):
            assert concept in rows, f"{concept} must have a mapping row"
            accounts = {account for _module, account in rows[concept]}
            assert accounts == {"4100"}, (
                f"{concept} points at {accounts}; the industry accounts 4114/4115 only exist for "
                "restaurant tenants, so they cannot be a tenant-wide mapping"
            )

    def test_non_mapping_concepts_have_no_mapping_row(self):
        rows = _mapping_rows()
        for code in sorted(NON_MAPPING_CONCEPTS):
            assert code not in rows, (
                f"{code} is {GL_CONCEPT_REGISTRY[code]['resolution_mode']}-owned, so a mapping row for "
                "it would be stale and ignored during posting"
            )

    def test_landed_cost_is_never_posted(self):
        """LANDED_COST is non-posting: nothing may post it."""
        posted = _posted_concepts()
        assert "LANDED_COST" not in posted, (
            f"LANDED_COST is non-posting and the resolver refuses it outright: {sorted(posted.get('LANDED_COST', ()))}"
        )

    def test_a_required_concept_has_a_mapping_row(self):
        """A concept the registry marks required must resolve for every tenant."""
        rows = _mapping_rows()
        required = sorted(
            code
            for code, meta in GL_CONCEPT_REGISTRY.items()
            if meta.get("required") and meta["resolution_mode"] == RESOLUTION_MODE_MAPPING
        )
        missing = [code for code in required if code not in rows]
        assert not missing, f"required concepts without a mapping row: {missing}"


class TestMappingTargets:
    """Every mapping row points at an account that really exists."""

    def test_every_mapped_account_exists_in_the_chart(self):
        templates = _chart_templates()
        missing = sorted(
            {
                (concept, account)
                for concept, entries in _mapping_rows().items()
                for _module, account in entries
                if account not in templates
            }
        )
        assert not missing, (
            "these mapping rows point at accounts the seed never creates, so provisioning skips them "
            f"with 'Mapping skipped: account ... not found': {missing}"
        )

    def test_every_mapped_account_is_postable(self):
        templates = _chart_templates()
        headers = sorted(
            {
                (concept, account)
                for concept, entries in _mapping_rows().items()
                for _module, account in entries
                if account in templates and templates[account].is_header
            }
        )
        assert not headers, f"a header account cannot be posted to: {headers}"

    def test_every_mapped_account_has_a_parent_in_the_chart(self):
        templates = _chart_templates()
        orphans = sorted(
            {
                (concept, account)
                for concept, entries in _mapping_rows().items()
                for _module, account in entries
                if account in templates
                and templates[account].parent_code is not None
                and templates[account].parent_code not in templates
            }
        )
        assert not orphans, f"these accounts hang off a parent the seed never creates: {orphans}"

    def test_the_concepts_the_services_post_all_resolve(self):
        """A posting must never name a concept the resolver will refuse."""
        posted = _posted_concepts()
        rows = _mapping_rows()
        unknown = sorted(
            code
            for code in posted
            if code not in GL_CONCEPT_REGISTRY and code not in KNOWN_POSTED_CONCEPTS_WITHOUT_A_REGISTRY_ENTRY
        )
        assert not unknown, (
            f"these concepts are posted but are not in the registry, so the resolver refuses them as unknown: {unknown}"
        )
        unresolvable = sorted(
            code
            for code in posted
            if code in GL_CONCEPT_REGISTRY
            and GL_CONCEPT_REGISTRY[code]["resolution_mode"] == RESOLUTION_MODE_MAPPING
            and code not in rows
        )
        assert not unresolvable, f"posted concepts with no mapping row: {unresolvable}"

    def test_the_non_posting_concept_is_not_posted_by_any_source(self):
        posted = _posted_concepts()
        offenders = sorted(
            code
            for code in posted
            if code in GL_CONCEPT_REGISTRY
            and GL_CONCEPT_REGISTRY[code]["resolution_mode"] == RESOLUTION_MODE_NON_POSTING
        )
        assert not offenders, f"non-posting concepts are posted by: {offenders}"

    def test_the_liquidity_and_record_concepts_are_not_mapping_owned(self):
        """CASH/BANK and the record concepts resolve from an explicit account."""
        for code in ("CASH", "BANK", "FIXED_ASSET_ASSET", "DEPRECIATION_EXPENSE", "ACCUMULATED_DEPRECIATION"):
            mode = GL_CONCEPT_REGISTRY[code]["resolution_mode"]
            assert mode in (RESOLUTION_MODE_LIQUIDITY, RESOLUTION_MODE_RECORD), f"{code} is {mode}"


class TestLegacyCodeHints:
    """A concept's ``legacy_code`` hint must name an account that exists.

    ``GL_CONCEPT_REGISTRY[concept]["legacy_code"]`` is the hint the Owner
    panel's mapping-validation preview reads
    (``services/gl_mapping_validation.py``): it matches the hint against the
    tenant's own accounts to propose a mapping.

    A hint that names an account the chart does not have is reported as
    "manual_required" for *every* tenant, which buries the real findings
    under noise. A hint that names the wrong account is worse: the preview
    proposes a mapping the registry would never provision, so the Owner
    approves one account and the ledger posts to another.

    The chart is the set of accounts the seed creates - the base chart
    (``BASE_ACCOUNTS``) plus the industry extensions
    (``INDUSTRY_EXTENSIONS``) - the same two sources
    ``services/gl_tree_builder.py`` builds a tenant's chart from, so the
    assertions cannot be fooled by a partial list.
    """

    def test_every_hint_names_an_account_the_seed_creates(self):
        templates = _chart_templates()
        offenders = sorted(
            (code, meta["legacy_code"])
            for code, meta in GL_CONCEPT_REGISTRY.items()
            if meta["legacy_code"] is not None and meta["legacy_code"] not in templates
        )
        assert not offenders, (
            "these concepts carry a legacy_code hint that names an account the seed never creates, so "
            "the Owner panel's preview reports them as 'manual_required' for every tenant: "
            f"{offenders}"
        )

    def test_a_mapping_concept_hint_names_a_postable_account(self):
        """A mapping-owned concept is posted to, so its hint must be a leaf.

        The preview rejects a header account as unpostable and reports the
        concept as an invalid candidate for every tenant. The hints that do
        name a header are the concepts the preview never resolves by hint:
        BANK (1120) is the header the tenant's bank accounts hang off, and
        LANDED_COST (5300) is the header the landed-cost accounts hang off.
        """
        templates = _chart_templates()
        headers = sorted(
            (code, meta["legacy_code"])
            for code, meta in GL_CONCEPT_REGISTRY.items()
            if meta["resolution_mode"] == RESOLUTION_MODE_MAPPING
            and meta["legacy_code"] is not None
            and meta["legacy_code"] in templates
            and templates[meta["legacy_code"]].is_header
        )
        assert not headers, (
            f"these hints name a header account, which the preview rejects as unpostable for every tenant: {headers}"
        )

    def test_a_mapping_concept_hint_names_the_account_the_registry_maps_it_to(self):
        rows = _mapping_rows()
        offenders = sorted(
            (code, meta["legacy_code"], sorted({account for _module, account in rows[code]}))
            for code, meta in GL_CONCEPT_REGISTRY.items()
            if meta["resolution_mode"] == RESOLUTION_MODE_MAPPING
            and meta["legacy_code"] is not None
            and code in rows
            and meta["legacy_code"] not in {account for _module, account in rows[code]}
        )
        assert not offenders, (
            "these hints name an account the registry does not map the concept to, so the preview "
            f"proposes a mapping the provisioning engine would never create: {offenders}"
        )

    def test_the_concepts_that_carry_no_hint_are_the_pinned_ones(self):
        hintless = sorted(
            code
            for code, meta in GL_CONCEPT_REGISTRY.items()
            if meta["resolution_mode"] == RESOLUTION_MODE_MAPPING and meta["legacy_code"] is None
        )
        assert hintless == sorted(CONCEPTS_WITHOUT_A_LEGACY_CODE_HINT), (
            "the set of mapping-owned concepts without a legacy_code hint changed. A concept that "
            "loses its hint is reported as 'manual_required' for every tenant, and one that gains "
            f"one names an account the chart may not have. Changed: {hintless}"
        )

    def test_the_misc_expense_hint_names_the_account_it_maps_to(self):
        """The precedent: MISC_EXPENSE maps to 6500, so 6990 would be wrong.

        The hint is what the Owner panel's preview reads, and a hint that
        names an account the chart does not have turns the concept into
        "manual_required" noise for every tenant.
        """
        assert GL_CONCEPT_REGISTRY["MISC_EXPENSE"]["legacy_code"] == "6500"
        assert _mapping_rows()["MISC_EXPENSE"] == [("core_payments", "6500")]


class TestSchemaConstraint:
    """The database constrains the concept codes a mapping row may carry."""

    def test_the_database_constrains_the_concept_code(self):
        allowed = _concept_codes_allowed_by_the_schema()
        assert allowed, "gl_account_mappings has no concept_code check constraint"

    def test_every_mapped_concept_is_accepted_by_the_database(self):
        """A row the database refuses aborts the whole provisioning transaction."""
        allowed = _concept_codes_allowed_by_the_schema()
        offenders = sorted(code for code in _mapping_rows() if code not in allowed)
        assert not offenders, (
            f"these mapping rows name a concept the database refuses: {offenders}. PostgreSQL raises "
            "CheckViolation and rolls the whole provisioning transaction back."
        )

    def test_the_registry_does_not_drift_further_from_the_schema(self):
        allowed = _concept_codes_allowed_by_the_schema()
        drift = set(GL_CONCEPT_CODES) - allowed
        assert drift <= KNOWN_CONCEPTS_MISSING_FROM_THE_SCHEMA_CONSTRAINT, (
            f"these registry concepts are not in the database constraint: {sorted(drift - allowed)}"
        )


class TestModuleFeatureFlags:
    """A module's feature flag must be a real column on the tenant."""

    def test_every_flag_is_a_tenant_column(self):
        from models.tenant import Tenant

        columns = Tenant.__table__.columns
        for module_code, module in GL_MODULE_DEFINITIONS.items():
            flag = module.feature_flag
            if not flag:
                continue
            assert flag in columns, (
                f"module {module_code} is gated on {flag!r}, which is not a column on tenants, so "
                "getattr(tenant, flag, False) is always False and the module is never provisioned"
            )

    def test_the_flag_names_are_the_expected_ones(self):
        gated = {
            module_code: module.feature_flag
            for module_code, module in GL_MODULE_DEFINITIONS.items()
            if module.feature_flag
        }
        assert gated == EXPECTED_MODULE_FEATURE_FLAGS, (
            "the feature flag of a module changed; a flag with no column on tenants silently "
            f"disables the module. Got {gated}, expected {EXPECTED_MODULE_FEATURE_FLAGS}"
        )

    def test_a_required_module_has_no_flag(self):
        """A required module is provisioned for every tenant, so it needs no flag."""
        for module_code, module in GL_MODULE_DEFINITIONS.items():
            if module.required:
                assert module.feature_flag is None, f"required module {module_code} carries a flag"

    def test_no_module_names_a_platform_setting(self):
        """``enable_ecommerce`` is a SystemSettings column, not a tenant column."""
        from models.system_settings import SystemSettings

        system_columns = set(SystemSettings.__table__.columns)
        for module_code, module in GL_MODULE_DEFINITIONS.items():
            flag = module.feature_flag
            if flag:
                assert flag not in system_columns, (
                    f"module {module_code} names the platform setting {flag!r}; the provisioning engine "
                    "reads it off the tenant"
                )


class TestProvisionedTenant:
    """A freshly provisioned tenant really carries the mapping rows."""

    @pytest.fixture
    def provisioned(self, db_session, sample_tenant):
        from services.gl_provisioning_service import GLProvisioningService

        result = GLProvisioningService.provision_tenant(sample_tenant.id)
        assert result.errors == [], f"provisioning reported: {result.errors}"
        return sample_tenant

    @staticmethod
    def _concepts_of(tenant, db_session) -> set[str]:
        from models.gl import GLAccountMapping

        return {
            row[0]
            for row in db_session.query(GLAccountMapping.concept_code)
            .filter_by(tenant_id=tenant.id, branch_id=None)
            .all()
        }

    def test_a_required_modules_concepts_all_have_a_row(self, provisioned, db_session):
        concepts = self._concepts_of(provisioned, db_session)
        expected = {
            mapping.concept_code
            for module in GL_MODULE_DEFINITIONS.values()
            if module.required
            for mapping in module.mappings
        }
        assert expected <= concepts, f"missing mapping rows: {sorted(expected - concepts)}"

    def test_the_concepts_the_services_post_all_have_a_row(self, provisioned, db_session):
        """The rows that make the postings work, one by one."""
        concepts = self._concepts_of(provisioned, db_session)
        expected = {
            "ACCOUNTS_PAYABLE",
            "AP",
            "AR",
            "BANK_FEES",
            "CHEQUES_UNDER_COLLECTION",
            "COGS",
            "INVENTORY_ASSET",
            "MISC_EXPENSE",
            "OPENING_BALANCE_EQUITY",
            "PURCHASES",
            "SALES_REVENUE",
            "SUSPENSE",
            "VAT_INPUT",
            "VAT_OUTPUT",
        }
        assert expected <= concepts, f"missing mapping rows: {sorted(expected - concepts)}"

    def test_the_store_concepts_wait_for_the_store_switch(self, provisioned, db_session):
        """The shop module is gated on the tenant's own store switch."""
        concepts = self._concepts_of(provisioned, db_session)
        shop = {m.concept_code for m in GL_MODULE_DEFINITIONS["shop_online"].mappings}
        assert shop and not (shop & concepts), f"shop concepts provisioned while the store is off: {shop}"

    def test_switching_the_store_on_provisions_its_concepts(self, db_session, sample_tenant):
        from services.gl_provisioning_service import GLProvisioningService

        sample_tenant.enable_store = True
        db_session.flush()
        GLProvisioningService.provision_tenant(sample_tenant.id)
        concepts = self._concepts_of(sample_tenant, db_session)
        shop = {m.concept_code for m in GL_MODULE_DEFINITIONS["shop_online"].mappings}
        assert shop <= concepts, f"shop concepts missing with the store on: {sorted(shop - concepts)}"

    def test_the_resolver_resolves_through_the_new_rows(self, provisioned, db_session, app):
        """End to end: the concept resolves to the account the registry names."""
        from services.gl_account_resolver import resolve_gl_account

        original = app.config.get("ENABLE_DYNAMIC_GL_MAPPING")
        app.config["ENABLE_DYNAMIC_GL_MAPPING"] = True
        try:
            expected = {
                "MISC_EXPENSE": "6500",
                "SUSPENSE": "2999",
                "ACCOUNTS_PAYABLE": "2110",
                "PURCHASES": "1140",
                "FOOD_SALES_REVENUE": "4100",
                "BEVERAGE_SALES_REVENUE": "4100",
            }
            for concept, code in expected.items():
                account = resolve_gl_account(tenant_id=provisioned.id, concept_code=concept)
                assert account is not None, f"{concept} did not resolve"
                assert account.code == code, f"{concept} resolved to {account.code}, expected {code}"
        finally:
            app.config["ENABLE_DYNAMIC_GL_MAPPING"] = original


class TestSourceTextIntegrity:
    """No source file may carry a run of question marks.

    A file that is rewritten in the wrong encoding writes every Arabic
    character as "?", and the corruption is invisible in a diff of a file
    that is mostly ASCII. It also reaches the ledger: a fixed-asset disposal
    was posted with the description "??? بيع ??? - ASSET-001" instead of the
    Arabic text it is supposed to carry.
    """

    SCANNED_DIRECTORIES = ("models", "services", "routes", "utils", "migrations")

    def test_no_source_file_has_a_run_of_question_marks(self):
        offenders: list[str] = []
        for directory in self.SCANNED_DIRECTORIES:
            for path in sorted((PROJECT_ROOT / directory).rglob("*.py")):
                text = path.read_text(encoding="utf-8", errors="replace")
                for number, line in enumerate(text.splitlines(), start=1):
                    if "???" in line:
                        offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{number}")
        assert not offenders, (
            "these source lines carry a run of question marks, which is what an Arabic string turns "
            f"into when the file is written in the wrong encoding: {offenders}"
        )
