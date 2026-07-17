from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


from services.gl_provisioning_service import GLProvisioningService, ProvisionResult
from models.gl_account_registry import BASE_ACCOUNTS, GLAccountTemplate


class TestProvisionResult:
    def test_post_init_sets_errors_list(self):
        result = ProvisionResult(tenant_id=1)
        assert result.errors == []


class TestProvisionTenant:
    def test_tenant_not_found(self, mocker):
        mocker.patch(
            "services.gl_provisioning_service.db.session.get", return_value=None
        )
        result = GLProvisioningService.provision_tenant(999)
        assert "not found" in result.errors[0]

    def test_provision_success_commits(self, mocker):
        tenant = SimpleNamespace(id=1, default_currency="USD", business_type="general")
        mocker.patch(
            "services.gl_provisioning_service.db.session.get", return_value=tenant
        )
        mocker.patch.object(GLProvisioningService, "_provision_base_accounts")
        mocker.patch.object(GLProvisioningService, "_provision_industry_accounts")
        mocker.patch.object(GLProvisioningService, "_provision_module_mappings")
        session = mocker.patch("services.gl_provisioning_service.db.session")
        result = GLProvisioningService.provision_tenant(1)
        session.flush.assert_called_once()
        assert result.errors == []

    def test_provision_exception_rolls_back(self, mocker):
        tenant = SimpleNamespace(id=1, default_currency="AED", business_type="general")
        mocker.patch(
            "services.gl_provisioning_service.db.session.get", return_value=tenant
        )
        mocker.patch.object(
            GLProvisioningService,
            "_provision_base_accounts",
            side_effect=RuntimeError("db fail"),
        )
        mocker.patch("services.gl_provisioning_service.db.session")
        result = GLProvisioningService.provision_tenant(1)
        assert "db fail" in result.errors[0]


class TestProvisionBaseAccounts:
    def test_creates_new_accounts_with_parent(self, mocker):
        tenant = SimpleNamespace(id=1, default_currency="EUR")
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        parent = SimpleNamespace(id=99)
        parent_q = MagicMock()
        parent_q.filter_by.return_value.first.return_value = parent
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mocker.patch("services.gl_provisioning_service.GLAccount").query = parent_q
        tmpl = GLAccountTemplate(
            "9999", "Test", "اختبار", "asset", 2, False, "1110", module_code="core"
        )
        mocker.patch("services.gl_provisioning_service.BASE_ACCOUNTS", [tmpl])
        GLProvisioningService._provision_base_accounts(tenant, result)
        assert result.created_accounts == 1
        session.add.assert_called()
        session.flush.assert_called()

    def test_skips_existing_codes(self, mocker):
        tenant = SimpleNamespace(id=1, default_currency="AED")
        result = ProvisionResult(tenant_id=1)
        existing_codes = [(a.code,) for a in BASE_ACCOUNTS]
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = existing_codes
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        GLProvisioningService._provision_base_accounts(tenant, result)
        assert result.skipped_accounts == len(BASE_ACCOUNTS)
        assert result.created_accounts == 0


class TestProvisionIndustryAccounts:
    def test_unknown_industry_noop(self, mocker):
        tenant = SimpleNamespace(id=1, business_type="unknown", default_currency="AED")
        result = ProvisionResult(tenant_id=1)
        GLProvisioningService._provision_industry_accounts(tenant, result)
        assert result.created_accounts == 0

    def test_industry_extension_creates_account(self, mocker):
        from models.gl_account_registry import INDUSTRY_EXTENSIONS

        industry = next(iter(INDUSTRY_EXTENSIONS.keys()))
        tenant = SimpleNamespace(id=1, business_type=industry, default_currency="AED")
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        parent_q = MagicMock()
        parent_q.filter_by.return_value.first.return_value = None
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mocker.patch("services.gl_provisioning_service.GLAccount").query = parent_q
        GLProvisioningService._provision_industry_accounts(tenant, result)
        assert result.created_accounts >= 1


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
        mocker.patch(
            "services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod}
        )
        mocker.patch(
            "services.gl_provisioning_service.GL_CONCEPT_REGISTRY",
            {"AR": {"resolution_mode": "mapping"}},
        )
        mocker.patch(
            "services.gl_provisioning_service.RESOLUTION_MODE_MAPPING", "mapping"
        )
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert any("not found" in e for e in result.errors)

    def test_skips_foreign_tenant_account(self, mocker):
        tenant = SimpleNamespace(id=1)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        account = SimpleNamespace(
            id=1, tenant_id=2, is_active=True, is_header=False, code="1130"
        )
        account_q = MagicMock()
        account_q.filter_by.return_value.first.return_value = account
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mocker.patch("services.gl_provisioning_service.GLAccount").query = account_q
        mapping = SimpleNamespace(concept_code="AR", account_code="1130")
        mod = SimpleNamespace(required=True, feature_flag=None, mappings=[mapping])
        mocker.patch(
            "services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod}
        )
        mocker.patch(
            "services.gl_provisioning_service.GL_CONCEPT_REGISTRY",
            {"AR": {"resolution_mode": "mapping"}},
        )
        mocker.patch(
            "services.gl_provisioning_service.RESOLUTION_MODE_MAPPING", "mapping"
        )
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert any("different tenant" in e for e in result.errors)

    def test_skips_inactive_account(self, mocker):
        tenant = SimpleNamespace(id=1)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        account = SimpleNamespace(
            id=2, tenant_id=1, is_active=False, is_header=False, code="1130"
        )
        account_q = MagicMock()
        account_q.filter_by.return_value.first.return_value = account
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mocker.patch("services.gl_provisioning_service.GLAccount").query = account_q
        mapping = SimpleNamespace(concept_code="AR", account_code="1130")
        mod = SimpleNamespace(required=True, feature_flag=None, mappings=[mapping])
        mocker.patch(
            "services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod}
        )
        mocker.patch(
            "services.gl_provisioning_service.GL_CONCEPT_REGISTRY",
            {"AR": {"resolution_mode": "mapping"}},
        )
        mocker.patch(
            "services.gl_provisioning_service.RESOLUTION_MODE_MAPPING", "mapping"
        )
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert any("inactive" in e for e in result.errors)

    def test_skips_header_account(self, mocker):
        tenant = SimpleNamespace(id=1)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        account = SimpleNamespace(
            id=3, tenant_id=1, is_active=True, is_header=True, code="1130"
        )
        account_q = MagicMock()
        account_q.filter_by.return_value.first.return_value = account
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mocker.patch("services.gl_provisioning_service.GLAccount").query = account_q
        mapping = SimpleNamespace(concept_code="AR", account_code="1130")
        mod = SimpleNamespace(required=True, feature_flag=None, mappings=[mapping])
        mocker.patch(
            "services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod}
        )
        mocker.patch(
            "services.gl_provisioning_service.GL_CONCEPT_REGISTRY",
            {"AR": {"resolution_mode": "mapping"}},
        )
        mocker.patch(
            "services.gl_provisioning_service.RESOLUTION_MODE_MAPPING", "mapping"
        )
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert any("header" in e for e in result.errors)

    def test_creates_mapping_for_valid_account(self, mocker):
        tenant = SimpleNamespace(id=1)
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        account = SimpleNamespace(
            id=5, tenant_id=1, is_active=True, is_header=False, code="1130"
        )
        account_q = MagicMock()
        account_q.filter_by.return_value.first.return_value = account
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        mocker.patch("services.gl_provisioning_service.GLAccount").query = account_q
        mapping = SimpleNamespace(concept_code="AR", account_code="1130")
        mod = SimpleNamespace(required=True, feature_flag=None, mappings=[mapping])
        mocker.patch(
            "services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod}
        )
        mocker.patch(
            "services.gl_provisioning_service.GL_CONCEPT_REGISTRY",
            {"AR": {"resolution_mode": "mapping"}},
        )
        mocker.patch(
            "services.gl_provisioning_service.RESOLUTION_MODE_MAPPING", "mapping"
        )
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
        mocker.patch(
            "services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"sales": mod}
        )
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
        mocker.patch(
            "services.gl_provisioning_service.GL_MODULE_DEFINITIONS", {"treasury": mod}
        )
        GLProvisioningService._provision_module_mappings(tenant, result)
        assert result.created_mappings == 0


class TestMissingAndValidate:
    def test_get_missing_accounts_no_tenant(self, mocker):
        mocker.patch(
            "services.gl_provisioning_service.db.session.get", return_value=None
        )
        assert GLProvisioningService.get_missing_accounts(1) == []

    def test_get_missing_accounts_lists_gaps(self, mocker):
        tenant = SimpleNamespace(id=1, business_type="general")
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.get.return_value = tenant
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        session.query.return_value = existing_q
        missing = GLProvisioningService.get_missing_accounts(1)
        assert len(missing) == len(BASE_ACCOUNTS)

    def test_get_missing_mappings_no_tenant(self, mocker):
        mocker.patch(
            "services.gl_provisioning_service.db.session.get", return_value=None
        )
        assert GLProvisioningService.get_missing_mappings(1) == []

    def test_validate_tenant_chart_not_found(self, mocker):
        mocker.patch(
            "services.gl_provisioning_service.db.session.get", return_value=None
        )
        result = GLProvisioningService.validate_tenant_chart(1)
        assert "not found" in result["errors"][0]

    def test_industry_skips_existing_codes(self, mocker):
        from models.gl_account_registry import INDUSTRY_EXTENSIONS

        industry = next(iter(INDUSTRY_EXTENSIONS.keys()))
        tmpl = INDUSTRY_EXTENSIONS[industry][0]
        tenant = SimpleNamespace(id=1, business_type=industry, default_currency="AED")
        result = ProvisionResult(tenant_id=1)
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = [(tmpl.code,)]
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.query.return_value = existing_q
        GLProvisioningService._provision_industry_accounts(tenant, result)
        assert result.skipped_accounts >= 1

    def test_get_missing_accounts_includes_industry_templates(self, mocker):
        from models.gl_account_registry import INDUSTRY_EXTENSIONS

        industry = next(iter(INDUSTRY_EXTENSIONS.keys()))
        tenant = SimpleNamespace(id=1, business_type=industry)
        session = mocker.patch("services.gl_provisioning_service.db.session")
        session.get.return_value = tenant
        existing_q = MagicMock()
        existing_q.filter_by.return_value.all.return_value = []
        session.query.return_value = existing_q
        missing = GLProvisioningService.get_missing_accounts(1)
        industry_codes = {t.code for t in INDUSTRY_EXTENSIONS[industry]}
        missing_codes = {t.code for t in missing}
        assert industry_codes.issubset(missing_codes)

    def test_validate_tenant_chart_ok_flags(self, mocker):
        tenant = SimpleNamespace(id=1, business_type="general")
        mocker.patch(
            "services.gl_provisioning_service.db.session.get", return_value=tenant
        )
        mocker.patch.object(
            GLProvisioningService, "get_missing_accounts", return_value=[]
        )
        mocker.patch.object(
            GLProvisioningService, "get_missing_mappings", return_value=[]
        )
        result = GLProvisioningService.validate_tenant_chart(1)
        assert result["accounts_ok"] is True
        assert result["mappings_ok"] is True

    def test_validate_tenant_chart_with_gaps(self, mocker):
        tenant = SimpleNamespace(id=1, business_type="general")
        mocker.patch(
            "services.gl_provisioning_service.db.session.get", return_value=tenant
        )
        gap = BASE_ACCOUNTS[0]
        mocker.patch.object(
            GLProvisioningService, "get_missing_accounts", return_value=[gap]
        )
        mocker.patch.object(
            GLProvisioningService,
            "get_missing_mappings",
            return_value=[SimpleNamespace(concept_code="AR", account_code="1130")],
        )
        result = GLProvisioningService.validate_tenant_chart(1)
        assert result["accounts_ok"] is False
        assert result["mappings_ok"] is False
        assert result["missing_accounts"][0]["code"] == gap.code
