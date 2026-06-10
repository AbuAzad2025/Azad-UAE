import pytest
from decimal import Decimal
from extensions import db
from models import Tenant
from models.gl import GLAccount, GLAccountMapping
from models.gl_account_registry import (
    BASE_ACCOUNTS,
    INDUSTRY_EXTENSIONS,
    GL_MODULE_DEFINITIONS,
    VALID_INDUSTRY_CODES,
)
from services.gl_provisioning_service import GLProvisioningService


class TestGLProvisioningService:
    def test_provision_tenant_creates_base_accounts(self, app, sample_tenant):
        with app.app_context():
            result = GLProvisioningService.provision_tenant(sample_tenant.id)
            assert result.errors == []
            assert result.created_accounts > 0
            existing = GLAccount.query.filter_by(tenant_id=sample_tenant.id).count()
            assert existing >= len({t.code for t in BASE_ACCOUNTS})

    def test_provision_tenant_idempotent(self, app, sample_tenant):
        with app.app_context():
            r1 = GLProvisioningService.provision_tenant(sample_tenant.id)
            db.session.commit()
            r2 = GLProvisioningService.provision_tenant(sample_tenant.id)
            assert r2.created_accounts == 0
            assert r2.created_mappings == 0

    def test_provision_tenant_creates_mappings(self, app, sample_tenant):
        with app.app_context():
            result = GLProvisioningService.provision_tenant(sample_tenant.id)
            assert result.created_mappings > 0
            mappings = GLAccountMapping.query.filter_by(
                tenant_id=sample_tenant.id, branch_id=None
            ).all()
            assert len(mappings) > 0

    def test_validate_tenant_chart_complete(self, app, sample_tenant):
        with app.app_context():
            GLProvisioningService.provision_tenant(sample_tenant.id)
            report = GLProvisioningService.validate_tenant_chart(sample_tenant.id)
            assert report['accounts_ok'] is True
            assert report['mappings_ok'] is True
            assert report['missing_accounts'] == []
            assert report['missing_mappings'] == []

    def test_missing_accounts_empty_after_provision(self, app, sample_tenant):
        with app.app_context():
            GLProvisioningService.provision_tenant(sample_tenant.id)
            missing = GLProvisioningService.get_missing_accounts(sample_tenant.id)
            assert len(missing) == 0

    def test_missing_mappings_empty_after_provision(self, app, sample_tenant):
        with app.app_context():
            GLProvisioningService.provision_tenant(sample_tenant.id)
            missing = GLProvisioningService.get_missing_mappings(sample_tenant.id)
            assert len(missing) == 0

    def test_industry_accounts_for_automotive(self, app):
        with app.app_context():
            tenant = Tenant(
                name='Automotive Test',
                name_ar='اختبار سيارات',
                slug='automotive-test',
                business_type='automotive',
            )
            db.session.add(tenant)
            db.session.flush()
            result = GLProvisioningService.provision_tenant(tenant.id)
            db.session.commit()
            acc_4105 = GLAccount.query.filter_by(
                tenant_id=tenant.id, code='4105'
            ).first()
            assert acc_4105 is not None
            assert acc_4105.name == 'Service Revenue'
            assert acc_4105.industry_code == 'automotive'

    def test_industry_accounts_for_supermarket(self, app):
        with app.app_context():
            tenant = Tenant(
                name='Supermarket Test',
                name_ar='اختبار سوبرماركت',
                slug='supermarket-test',
                business_type='supermarket',
            )
            db.session.add(tenant)
            db.session.flush()
            GLProvisioningService.provision_tenant(tenant.id)
            db.session.commit()
            acc_1144 = GLAccount.query.filter_by(
                tenant_id=tenant.id, code='1144'
            ).first()
            assert acc_1144 is not None
            assert acc_1144.name == 'Inventory - Perishable Goods'

    def test_no_industry_accounts_for_general(self, app):
        with app.app_context():
            tenant = Tenant(
                name='General Test',
                name_ar='اختبار عام',
                slug='general-test',
                business_type='general',
            )
            db.session.add(tenant)
            db.session.flush()
            GLProvisioningService.provision_tenant(tenant.id)
            db.session.commit()
            acc_1144 = GLAccount.query.filter_by(
                tenant_id=tenant.id, code='1144'
            ).first()
            assert acc_1144 is None

    def test_base_accounts_registry_no_duplicates(self):
        codes = [t.code for t in BASE_ACCOUNTS]
        assert len(codes) == len(set(codes)), f"Duplicate codes: {codes}"

    def test_industry_extensions_valid_parent_codes(self):
        base_codes = {t.code for t in BASE_ACCOUNTS}
        for industry, accounts in INDUSTRY_EXTENSIONS.items():
            for tmpl in accounts:
                if tmpl.parent_code:
                    assert tmpl.parent_code in base_codes, (
                        f"Industry {industry}: {tmpl.code} parent {tmpl.parent_code} not in base"
                    )

    def test_module_definitions_use_valid_concepts(self):
        from models._constants import VALID_GL_CONCEPT_CODES
        for mod in GL_MODULE_DEFINITIONS.values():
            for mapping in mod.mappings:
                assert mapping.concept_code in VALID_GL_CONCEPT_CODES, (
                    f"Module {mod.module_code}: invalid concept {mapping.concept_code}"
                )

    def test_module_definitions_map_to_valid_accounts(self):
        base_codes = {t.code for t in BASE_ACCOUNTS}
        industry_codes = set()
        for industry_accounts in INDUSTRY_EXTENSIONS.values():
            for tmpl in industry_accounts:
                industry_codes.add(tmpl.code)
        all_codes = base_codes | industry_codes
        for mod in GL_MODULE_DEFINITIONS.values():
            for mapping in mod.mappings:
                assert mapping.account_code in all_codes, (
                    f"Module {mod.module_code}: {mapping.concept_code} maps to unknown account {mapping.account_code}"
                )


class TestGLAccountRegistry:
    def test_all_base_accounts_have_name_ar(self):
        for tmpl in BASE_ACCOUNTS:
            assert tmpl.name_ar, f"Account {tmpl.code} missing Arabic name"

    def test_all_base_accounts_have_valid_types(self):
        valid_types = {'asset', 'liability', 'equity', 'revenue', 'expense'}
        for tmpl in BASE_ACCOUNTS:
            assert tmpl.type in valid_types, f"Account {tmpl.code} has invalid type {tmpl.type}"

    def test_header_accounts_no_parent_or_valid_parent(self):
        base_codes = {t.code for t in BASE_ACCOUNTS}
        for tmpl in BASE_ACCOUNTS:
            if tmpl.is_header and tmpl.parent_code:
                assert tmpl.parent_code in base_codes, (
                    f"Header {tmpl.code} parent {tmpl.parent_code} not found"
                )


    def test_industry_codes_valid(self):
        assert 'general' in VALID_INDUSTRY_CODES
        assert 'automotive' in VALID_INDUSTRY_CODES
        assert 'supermarket' in VALID_INDUSTRY_CODES
        assert 'mobile_new' in VALID_INDUSTRY_CODES
        assert 'batteries' in VALID_INDUSTRY_CODES
        assert 'clothing' in VALID_INDUSTRY_CODES

    def test_no_duplicate_codes_between_base_and_industry(self):
        base_codes = {t.code for t in BASE_ACCOUNTS}
        for industry, accounts in INDUSTRY_EXTENSIONS.items():
            for tmpl in accounts:
                assert tmpl.code not in base_codes, (
                    f"Industry {industry}: {tmpl.code} duplicates base account"
                )
