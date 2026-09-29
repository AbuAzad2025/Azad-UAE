from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from models.gl_account_registry import BASE_ACCOUNTS
from services.gl_provisioning_service import GLProvisioningService, ProvisionResult


class TestProvisionResult:
    def test_post_init_sets_errors_list(self):
        result = ProvisionResult(tenant_id=1)
        assert result.errors == []


class TestProvisionTenant:
    def test_tenant_not_found(self, mocker):
        mocker.patch("services.gl_provisioning_service.db.session.get", return_value=None)
        result = GLProvisioningService.provision_tenant(999)
        assert "not found" in result.errors[0]

    def test_provision_success_commits(self, db_session, sample_tenant, mocker):
        """The tenant's chart is built, and via the one owner of the tree.

        Was a mock test asserting that two private helpers were called. It now
        runs the real path and checks the outcome, which is the thing the caller
        depends on: after provision_tenant the core accounts exist.
        """
        mappings = mocker.patch.object(GLProvisioningService, "_provision_module_mappings")
        GLProvisioningService.provision_tenant(sample_tenant.id)
        from models.gl import GLAccount

        codes = {row[0] for row in db_session.query(GLAccount.code).filter_by(tenant_id=sample_tenant.id).all()}
        core = {t.code for t in BASE_ACCOUNTS}
        assert core <= codes, f"missing after provision: {sorted(core - codes)[:10]}"
        mappings.assert_called()

    def test_provision_exception_rolls_back(self, mocker):
        tenant = SimpleNamespace(id=1, default_currency="AED", business_type="general")
        mocker.patch("services.gl_provisioning_service.db.session.get", return_value=tenant)
        mocker.patch(
            "services.gl_provisioning_service.GLService.ensure_core_accounts",
            side_effect=RuntimeError("db fail"),
        )
        mocker.patch("services.gl_provisioning_service.db.session")
        result = GLProvisioningService.provision_tenant(1)
        assert "db fail" in result.errors[0]

    def test_provision_is_idempotent(self, db_session, sample_tenant):
        """Second run adds nothing, because the tree is built by the self-healing
        path that matches on code rather than by an insert-only second writer."""
        from models.gl import GLAccount

        GLProvisioningService.provision_tenant(sample_tenant.id)
        first = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id).count()
        GLProvisioningService.provision_tenant(sample_tenant.id)
        second = db_session.query(GLAccount).filter_by(tenant_id=sample_tenant.id).count()
        assert first == second


class TestChartHasSingleBuilder:
    """The chart of accounts must have exactly one implementation.

    There were two: GLTreeBuilder.build (used by the boot) and
    _provision_base_accounts / _provision_industry_accounts (used at tenant
    creation). The second only inserted and never repaired, so a renamed or
    re-parented account was reported as present by both and fixed by neither.
    """

    def test_dead_builders_are_gone(self):
        for name in ("_provision_base_accounts", "_provision_industry_accounts"):
            assert not hasattr(GLProvisioningService, name), f"{name} still exists"

    def test_provision_delegates_to_the_tree_builder(self, db_session, sample_tenant, mocker):
        spy = mocker.spy(
            __import__("services.gl_service", fromlist=["GLService"]).GLService,
            "ensure_core_accounts",
        )
        GLProvisioningService.provision_tenant(sample_tenant.id)
        assert spy.call_count == 1

    def test_readiness_diagnostics_survive_consolidation(self, db_session, app, sample_tenant):
        """The before/after-build distinction the dry-run report depends on.

        This replaces test_cash_bank_readiness_before_build, which called
        provision_tenant and then asserted the chart was *not* built yet. That
        was only ever true because provision_tenant used to be a partial writer;
        now that it delegates to the tree builder there is no "after provision,
        before build" state, and the test was asserting the duplication rather
        than the behaviour. The distinction itself is still real and still
        tested - the only way to reach it is a tenant that has never been
        provisioned, which is why this makes one instead of using sample_tenant
        (that fixture arrives with a chart already built).
        """
        import uuid

        from models import Branch, Tenant
        from services.gl_mapping_validation import GLMappingValidationService

        tenant = Tenant(
            name=f"Ready-{uuid.uuid4().hex[:6]}",
            name_ar="ready",
            name_en="Ready",
            slug=f"ready-{uuid.uuid4().hex[:6]}",
            default_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        # The readiness check is per active branch, so a tenant with no branch
        # reports nothing about its cash accounts at all.
        db_session.add(Branch(tenant_id=tenant.id, name="Main", code="RDM", is_main=True))
        db_session.flush()

        result = GLMappingValidationService.dry_run(tenant_id=tenant.id, include_ready=True)
        codes = {r["concept_code"] for r in result["rows"]}
        assert "CASH_READINESS" in codes, "an unprovisioned tenant must report the gap"
        assert "BANK_READINESS" in codes

        GLProvisioningService.provision_tenant(tenant.id)

        after = GLMappingValidationService.dry_run(tenant_id=tenant.id, include_ready=True)
        after_codes = {r["concept_code"] for r in after["rows"]}
        assert "CASH_READINESS" not in after_codes
        assert "BANK_READINESS" not in after_codes

    def test_provision_repairs_a_drifted_account(self, db_session, sample_tenant):
        """The self-healing path repairs; the old insert-only writer could not."""
        from extensions import db as flask_db
        from models.gl import GLAccount

        GLProvisioningService.provision_tenant(sample_tenant.id)
        acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="1140").first()
        assert acc is not None
        original = acc.name
        acc.name = "WRONG NAME"
        db_session.flush()

        GLProvisioningService.provision_tenant(sample_tenant.id)
        flask_db.session.expire_all()
        assert GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="1140").first().name == original


class TestProvisionModuleMappings:
    def test_skips_non_mapping_resolution_mode(self, mocker):
        tenant = SimpleNamespace(id=1)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mod = SimpleNamespace(
            required=True,
            feature_flag=None,
            mappings=[SimpleNamespace(concept_code="CASH", account_code="1111")],
        )
        mocker.patch(
            "services.gl_provisioning_service.GL_MODULE_DEFINITIONS",
            {"core": mod},
        )
        mocker.patch(
            "services.gl_provisioning_service.GL_CONCEPT_REGISTRY",
            {"CASH": {"resolution_mode": "liquidity"}},
        )
        mocker.patch(
            "services.gl_provisioning_service.RESOLUTION_MODE_MAPPING",
            "mapping",
        )
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert result.skipped_mappings >= 1

    def test_skips_missing_account(self, mocker):
        tenant = SimpleNamespace(id=1)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        account_q = MagicMock()
        account_q.filter_by.return_value.first.return_value = None
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mocker.patch("services.gl_provisioning_service.GLAccount").query = account_q
        mapping = SimpleNamespace(concept_code="AR", account_code="1130")
        mod = SimpleNamespace(required=True, feature_flag=None, mappings=[mapping])
        mocker.patch("services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod})
        mocker.patch(
            "services.gl_provisioning_service.GL_CONCEPT_REGISTRY",
            {"AR": {"resolution_mode": "mapping"}},
        )
        mocker.patch("services.gl_provisioning_service.RESOLUTION_MODE_MAPPING", "mapping")
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert any("not found" in e for e in result.errors)

    def test_skips_foreign_tenant_account(self, mocker):
        tenant = SimpleNamespace(id=1)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        account = SimpleNamespace(id=1, tenant_id=2, is_active=True, is_header=False, code="1130")
        account_q = MagicMock()
        account_q.filter_by.return_value.first.return_value = account
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mocker.patch("services.gl_provisioning_service.GLAccount").query = account_q
        mapping = SimpleNamespace(concept_code="AR", account_code="1130")
        mod = SimpleNamespace(required=True, feature_flag=None, mappings=[mapping])
        mocker.patch("services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod})
        mocker.patch(
            "services.gl_provisioning_service.GL_CONCEPT_REGISTRY",
            {"AR": {"resolution_mode": "mapping"}},
        )
        mocker.patch("services.gl_provisioning_service.RESOLUTION_MODE_MAPPING", "mapping")
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert any("different tenant" in e for e in result.errors)

    def test_skips_inactive_account(self, mocker):
        tenant = SimpleNamespace(id=1)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        account = SimpleNamespace(id=2, tenant_id=1, is_active=False, is_header=False, code="1130")
        account_q = MagicMock()
        account_q.filter_by.return_value.first.return_value = account
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mocker.patch("services.gl_provisioning_service.GLAccount").query = account_q
        mapping = SimpleNamespace(concept_code="AR", account_code="1130")
        mod = SimpleNamespace(required=True, feature_flag=None, mappings=[mapping])
        mocker.patch("services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod})
        mocker.patch(
            "services.gl_provisioning_service.GL_CONCEPT_REGISTRY",
            {"AR": {"resolution_mode": "mapping"}},
        )
        mocker.patch("services.gl_provisioning_service.RESOLUTION_MODE_MAPPING", "mapping")
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert any("inactive" in e for e in result.errors)

    def test_skips_header_account(self, mocker):
        tenant = SimpleNamespace(id=1)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        account = SimpleNamespace(id=3, tenant_id=1, is_active=True, is_header=True, code="1130")
        account_q = MagicMock()
        account_q.filter_by.return_value.first.return_value = account
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mocker.patch("services.gl_provisioning_service.GLAccount").query = account_q
        mapping = SimpleNamespace(concept_code="AR", account_code="1130")
        mod = SimpleNamespace(required=True, feature_flag=None, mappings=[mapping])
        mocker.patch("services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod})
        mocker.patch(
            "services.gl_provisioning_service.GL_CONCEPT_REGISTRY",
            {"AR": {"resolution_mode": "mapping"}},
        )
        mocker.patch("services.gl_provisioning_service.RESOLUTION_MODE_MAPPING", "mapping")
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert any("header" in e for e in result.errors)

    def test_creates_mapping_for_valid_account(self, mocker):
        tenant = SimpleNamespace(id=1)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        account = SimpleNamespace(id=5, tenant_id=1, is_active=True, is_header=False, code="1130")
        account_q = MagicMock()
        account_q.filter_by.return_value.first.return_value = account
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mocker.patch("services.gl_provisioning_service.GLAccount").query = account_q
        mapping = SimpleNamespace(concept_code="AR", account_code="1130")
        mod = SimpleNamespace(required=True, feature_flag=None, mappings=[mapping])
        mocker.patch("services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod})
        mocker.patch(
            "services.gl_provisioning_service.GL_CONCEPT_REGISTRY",
            {"AR": {"resolution_mode": "mapping"}},
        )
        mocker.patch("services.gl_provisioning_service.RESOLUTION_MODE_MAPPING", "mapping")
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert result.created_mappings == 1

    def test_skips_existing_mapping(self, mocker):
        tenant = SimpleNamespace(id=1)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = [("AR",)]
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mapping = SimpleNamespace(concept_code="AR", account_code="1130")
        mod = SimpleNamespace(required=True, feature_flag=None, mappings=[mapping])
        mocker.patch("services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod})
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert result.skipped_mappings >= 1

    def test_get_missing_mappings_skips_disabled_module(self, mocker):
        tenant = SimpleNamespace(id=1, enable_treasury=False)
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.get.return_value = tenant
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        session.query.return_value = existing_q
        missing = GLProvisioningService.get_missing_mappings(1)
        assert isinstance(missing, list)

    def test_optional_module_skipped_by_feature_flag(self, mocker):
        tenant = SimpleNamespace(id=1, enable_treasury=False)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mod = SimpleNamespace(
            required=False,
            feature_flag="enable_treasury",
            mappings=[SimpleNamespace(concept_code="X", account_code="Y")],
        )
        mocker.patch("services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"treasury": mod})
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert result.created_mappings == 0


class TestMissingAndValidate:
    def test_get_missing_accounts_no_tenant(self, mocker):
        mocker.patch("services.gl_provisioning_service.db.session.get", return_value=None)
        assert GLProvisioningService.get_missing_accounts(1) == []

    def test_get_missing_accounts_lists_gaps(self, db_session, sample_tenant):
        """Real gap detection, and it shrinks to empty once the tree is built.

        Replaces a mock test that fed a fake empty account list in. The point of
        the function is what a real tenant is missing, so it is asserted against
        a real tenant - and against the repair, which is the half that was
        untested.
        """

        before = GLProvisioningService.get_missing_accounts(sample_tenant.id)
        assert len(before) > 0, "a fresh tenant should be missing its chart"

        GLProvisioningService.provision_tenant(sample_tenant.id)
        assert GLProvisioningService.get_missing_accounts(sample_tenant.id) == []

    def test_get_missing_accounts_includes_industry_templates(self, db_session, sample_tenant):
        """A tenant in a sector that has extension accounts must be reported
        missing them before provisioning, and not after."""
        from models.gl_account_registry import INDUSTRY_EXTENSIONS

        industry = next(k for k, v in INDUSTRY_EXTENSIONS.items() if v and sample_tenant is not None)
        sample_tenant.business_type = industry
        db_session.flush()

        codes_before = {t.code for t in GLProvisioningService.get_missing_accounts(sample_tenant.id)}
        extension_codes = {t.code for t in INDUSTRY_EXTENSIONS[industry]}
        assert extension_codes & codes_before, "industry templates should appear as gaps"

        GLProvisioningService.provision_tenant(sample_tenant.id)
        assert GLProvisioningService.get_missing_accounts(sample_tenant.id) == []

    def test_get_missing_mappings_no_tenant(self, mocker):
        mocker.patch("services.gl_provisioning_service.db.session.get", return_value=None)
        assert GLProvisioningService.get_missing_mappings(1) == []

    def test_validate_tenant_chart_not_found(self, mocker):
        mocker.patch("services.gl_provisioning_service.db.session.get", return_value=None)
        result = GLProvisioningService.validate_tenant_chart(1)
        assert "not found" in result["errors"][0]

    def test_validate_tenant_chart_ok_flags(self, mocker):
        tenant = SimpleNamespace(id=1, business_type="general")
        mocker.patch("services.gl_provisioning_service.db.session.get", return_value=tenant)
        mocker.patch.object(GLProvisioningService, "get_missing_accounts", return_value=[])
        mocker.patch.object(GLProvisioningService, "get_missing_mappings", return_value=[])
        result = GLProvisioningService.validate_tenant_chart(1)
        assert result["accounts_ok"] is True
        assert result["mappings_ok"] is True

    def test_validate_tenant_chart_with_gaps(self, mocker):
        tenant = SimpleNamespace(id=1, business_type="general")
        mocker.patch("services.gl_provisioning_service.db.session.get", return_value=tenant)
        gap = BASE_ACCOUNTS[0]
        mocker.patch.object(GLProvisioningService, "get_missing_accounts", return_value=[gap])
        mocker.patch.object(
            GLProvisioningService,
            "get_missing_mappings",
            return_value=[SimpleNamespace(concept_code="AR", account_code="1130")],
        )
        result = GLProvisioningService.validate_tenant_chart(1)
        assert result["accounts_ok"] is False
        assert result["mappings_ok"] is False
        assert result["missing_accounts"][0]["code"] == gap.code
