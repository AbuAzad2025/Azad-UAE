"""Unit tests for services/tenant_provisioning.py — industry validation & fallbacks.

Pure-function coverage for validation/resolution plus delegation coverage for
GL provisioning (mocked at the GLProvisioningService boundary).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.tenant_provisioning import (
    build_pos_profile,
    provision_tenant_gl,
    resolve_tenant_industry,
    validate_tenant_industry,
)


class TestValidateTenantIndustry:
    def test_missing_business_type_raises(self):
        with pytest.raises(ValueError):
            validate_tenant_industry(None)

    def test_blank_business_type_raises(self):
        with pytest.raises(ValueError):
            validate_tenant_industry("   ")

    def test_valid_business_type_returned_stripped(self):
        bt, ind = validate_tenant_industry("  restaurant  ", None)
        assert bt == "restaurant"
        assert ind is None

    def test_industry_blank_normalizes_to_none(self):
        bt, ind = validate_tenant_industry("retail", "   ")
        assert bt == "retail"
        assert ind is None

    def test_unknown_legacy_code_tolerated(self):
        bt, ind = validate_tenant_industry("legacy_multi_branch", "warehouses")
        assert bt == "legacy_multi_branch"
        assert ind == "warehouses"


class TestResolveTenantIndustry:
    def test_explicit_values_preserved(self):
        tenant = SimpleNamespace(business_type="restaurant", industry="cafe")
        resolved = resolve_tenant_industry(tenant)
        assert resolved == {
            "business_type": "restaurant",
            "industry": "cafe",
            "is_known": True,
        }

    def test_null_fields_fall_back_to_safe_defaults(self):
        tenant = SimpleNamespace(business_type=None, industry="")
        resolved = resolve_tenant_industry(tenant)
        assert resolved["business_type"] == "general"
        assert resolved["industry"] == "retail"
        assert resolved["is_known"] is True  # 'general' is a known type

    def test_unknown_business_type_flagged_not_known(self):
        tenant = SimpleNamespace(business_type="space_mining", industry=None)
        resolved = resolve_tenant_industry(tenant)
        assert resolved["business_type"] == "space_mining"
        assert resolved["is_known"] is False

    def test_object_without_attributes_uses_defaults(self):
        resolved = resolve_tenant_industry(object())
        assert resolved["business_type"] == "general"
        assert resolved["industry"] == "retail"


class TestBuildPosProfile:
    def test_profile_carries_resolved_industry(self):
        tenant = SimpleNamespace(business_type="restaurant", industry="cafe")
        profile = build_pos_profile(tenant)
        assert profile["business_type"] == "restaurant"
        assert profile["industry"] == "cafe"
        assert profile["is_known_business_type"] is True
        assert profile["mode"] == "restaurant"
        assert profile["enable_tables"] is True

    def test_profile_fallback_for_null_tenant_fields(self):
        tenant = SimpleNamespace(business_type=None, industry=None)
        profile = build_pos_profile(tenant)
        assert profile["industry"] == "retail"
        assert profile["mode"] == "retail"
        assert profile["enable_tables"] is False
        assert profile["is_known_business_type"] is True


class TestProvisionTenantGl:
    def test_delegates_and_maps_result(self, mocker):
        result = SimpleNamespace(
            tenant_id=5,
            created_accounts=12,
            skipped_accounts=3,
            created_mappings=4,
            skipped_mappings=1,
            errors=[],
        )
        provision = mocker.patch(
            "services.gl_provisioning_service.GLProvisioningService.provision_tenant",
            return_value=result,
        )
        out = provision_tenant_gl(5)
        provision.assert_called_once_with(5)
        assert out == {
            "tenant_id": 5,
            "created_accounts": 12,
            "skipped_accounts": 3,
            "created_mappings": 4,
            "skipped_mappings": 1,
            "errors": [],
        }
