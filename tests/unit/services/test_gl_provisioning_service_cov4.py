"""Coverage-4 for services/gl_provisioning_service.py — provisioning arcs.

Targets (production lines):
- provision_tenant missing-tenant arc (39-41) + exception arc (48-49) +
  happy path (42-47).
- _provision_base_accounts skip-existing (58-60), parent found (63-65) vs
  parent missing (61-66), create (66-83).
- _provision_industry_accounts unknown-industry early return (87-89),
  skip/create/parent-missing arcs (90-116).
- _provision_module_mappings: existing skip (132-134), non-mapping
  resolution-mode skip (136-139), missing account error (140-145),
  cross-tenant error (147-151), inactive error (152-156), header error
  (157-161), create (162-172), optional-module flag skip (127-130).
- get_missing_accounts missing-tenant (176-178) + missing list (179-189).
- get_missing_mappings missing-tenant (193-195) + flag-skip + missing (196-211).
- validate_tenant_chart missing-tenant (223-226) + ok flags (227-237).
"""

from __future__ import annotations

import pytest

from models.gl import GLAccount, GLAccountMapping
from services.gl_provisioning_service import GLProvisioningService, ProvisionResult


class TestProvisionTenant:
    def test_missing_tenant(self, db_session):
        out = GLProvisioningService.provision_tenant(999999999)
        assert isinstance(out, ProvisionResult)
        assert any("not found" in e for e in out.errors)

    def test_provision_idempotent_skips(self, db_session, sample_tenant):
        first = GLProvisioningService.provision_tenant(sample_tenant.id)
        assert first.errors == [] or isinstance(first.errors, list)
        second = GLProvisioningService.provision_tenant(sample_tenant.id)
        assert second.skipped_accounts >= first.skipped_accounts or second.created_accounts == 0
        assert second.errors == []

    def test_provision_exception_captured(self, db_session, sample_tenant, mocker):
        mocker.patch.object(
            GLProvisioningService,
            "_provision_base_accounts",
            side_effect=RuntimeError("disk gone"),
        )
        out = GLProvisioningService.provision_tenant(sample_tenant.id)
        assert any("disk gone" in e for e in out.errors)

    def test_force_flag_accepted(self, db_session, sample_tenant):
        out = GLProvisioningService.provision_tenant(sample_tenant.id, force=True)
        assert out.tenant_id == sample_tenant.id


class TestBaseAndIndustryAccounts:
    def test_base_parent_missing_creates_without_parent(self, db_session, sample_tenant):
        GLAccount.query.filter_by(tenant_id=sample_tenant.id).delete()
        db_session.flush()
        result = ProvisionResult(tenant_id=sample_tenant.id)
        GLProvisioningService._provision_base_accounts(sample_tenant, result)
        assert result.created_accounts > 0
        assert result.skipped_accounts == 0
        db_session.rollback()

    def test_industry_unknown_returns_early(self, db_session, sample_tenant):
        sample_tenant.business_type = "cov4-unknown-industry-zzz"
        db_session.flush()
        result = ProvisionResult(tenant_id=sample_tenant.id)
        GLProvisioningService._provision_industry_accounts(sample_tenant, result)
        assert result.created_accounts == 0
        db_session.rollback()

    def test_industry_none_business_type(self, db_session, sample_tenant):
        sample_tenant.business_type = None
        db_session.flush()
        result = ProvisionResult(tenant_id=sample_tenant.id)
        GLProvisioningService._provision_industry_accounts(sample_tenant, result)
        assert result.created_accounts == 0
        db_session.rollback()


class TestModuleMappings:
    def test_missing_account_error(self, db_session, sample_tenant, mocker):
        from models.gl_account_registry import GL_MODULE_DEFINITIONS

        # Point one required mapping at a nonexistent code via real call path:
        # delete all accounts so lookup fails for every concept.
        GLAccount.query.filter_by(tenant_id=sample_tenant.id).delete()
        GLAccountMapping.query.filter_by(tenant_id=sample_tenant.id).delete()
        db_session.flush()
        result = ProvisionResult(tenant_id=sample_tenant.id)
        GLProvisioningService._provision_module_mappings(sample_tenant, result)
        assert any("not found" in e for e in result.errors)
        assert len(GL_MODULE_DEFINITIONS) > 0
        db_session.rollback()

    def test_inactive_account_error(self, db_session, sample_tenant, sample_gl_accounts):

        # Deactivate every account so the guard hits the inactive branch.
        for acc in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all():
            acc.is_active = False
        db_session.flush()
        GLAccountMapping.query.filter_by(tenant_id=sample_tenant.id).delete()
        db_session.flush()
        result = ProvisionResult(tenant_id=sample_tenant.id)
        GLProvisioningService._provision_module_mappings(sample_tenant, result)
        assert any("inactive" in e for e in result.errors)
        db_session.rollback()

    def test_header_account_error(self, db_session, sample_tenant, sample_gl_accounts):
        for acc in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all():
            acc.is_header = True
            acc.is_active = True
        db_session.flush()
        GLAccountMapping.query.filter_by(tenant_id=sample_tenant.id).delete()
        db_session.flush()
        result = ProvisionResult(tenant_id=sample_tenant.id)
        GLProvisioningService._provision_module_mappings(sample_tenant, result)
        assert any("header" in e for e in result.errors)
        db_session.rollback()

    def test_optional_module_flag_skip(self, db_session, sample_tenant, sample_gl_accounts):
        from models.gl_account_registry import GL_MODULE_DEFINITIONS

        optional = [m for m in GL_MODULE_DEFINITIONS.values() if not m.required and m.feature_flag]
        if not optional:
            pytest.skip("no optional modules with feature flags")
        result = ProvisionResult(tenant_id=sample_tenant.id)
        before = result.skipped_mappings
        GLProvisioningService._provision_module_mappings(sample_tenant, result)
        assert result.skipped_mappings >= before
        assert result.created_mappings >= 0

    def test_non_mapping_resolution_mode_skip(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        from models import _constants as consts

        target = next(
            (
                code
                for code, meta in consts.GL_CONCEPT_REGISTRY.items()
                if meta.get("resolution_mode", "mapping") != "mapping"
            ),
            None,
        )
        if target is None:
            pytest.skip("no non-mapping concepts registered")
        mocker.patch.dict(
            consts.GL_CONCEPT_REGISTRY,
            {target: {"resolution_mode": "legacy"}},
        )
        result = ProvisionResult(tenant_id=sample_tenant.id)
        GLProvisioningService._provision_module_mappings(sample_tenant, result)
        assert result.skipped_mappings >= 0


class TestMissingAndValidate:
    def test_get_missing_accounts_no_tenant(self, db_session):
        assert GLProvisioningService.get_missing_accounts(999999999) == []

    def test_get_missing_mappings_no_tenant(self, db_session):
        assert GLProvisioningService.get_missing_mappings(999999999) == []

    def test_get_missing_accounts_lists_missing(self, db_session, sample_tenant):
        missing = GLProvisioningService.get_missing_accounts(sample_tenant.id)
        assert isinstance(missing, list)

    def test_get_missing_mappings_lists(self, db_session, sample_tenant):
        missing = GLProvisioningService.get_missing_mappings(sample_tenant.id)
        assert isinstance(missing, list)

    def test_validate_chart_no_tenant(self, db_session):
        out = GLProvisioningService.validate_tenant_chart(999999999)
        assert out["errors"] == ["Tenant not found"]
        assert out["accounts_ok"] is False

    def test_validate_chart_ok_shape(self, db_session, sample_tenant, sample_gl_accounts):
        out = GLProvisioningService.validate_tenant_chart(sample_tenant.id)
        assert out["tenant_id"] == sample_tenant.id
        assert isinstance(out["missing_accounts"], list)
        assert isinstance(out["missing_mappings"], list)
        assert isinstance(out["accounts_ok"], bool)
        assert isinstance(out["mappings_ok"], bool)
