"""Unit tests for services/saas_provisioning_service.py — package activation.

DB-backed: verifies tenant/package validation, duration math, feature-flag
mapping, result payload shape, and demo-tenant helpers.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from services.saas_provisioning_service import (
    SaaSProvisioningError,
    SaaSProvisioningService,
)


@pytest.fixture
def sample_package(db_session):
    from models.package import Package

    unique = str(uuid.uuid4())[:8]
    package = Package(
        name_ar="باقة تجريبية",
        name_en=f"Test Package {unique}",
        slug=f"test-pkg-{unique}",
        price=99.0,
        is_active=True,
        max_users=7,
        max_branches=4,
        has_ai=True,
        has_pos=True,
        has_customization=True,
        has_advanced_reports=True,
    )
    db_session.add(package)
    db_session.commit()
    return package


class TestActivatePurchasedPackageValidation:
    def test_missing_tenant_raises(self, db_session, sample_package):
        with pytest.raises(SaaSProvisioningError, match="Tenant .* not found"):
            SaaSProvisioningService.activate_purchased_package(
                tenant_id=999999999, package_id=sample_package.id
            )

    def test_missing_package_raises(self, db_session, sample_tenant):
        with pytest.raises(SaaSProvisioningError, match="not found or inactive"):
            SaaSProvisioningService.activate_purchased_package(
                tenant_id=sample_tenant.id, package_id=999999999
            )

    def test_inactive_package_raises(self, db_session, sample_tenant, sample_package):
        sample_package.is_active = False
        db_session.commit()
        with pytest.raises(SaaSProvisioningError, match="not found or inactive"):
            SaaSProvisioningService.activate_purchased_package(
                tenant_id=sample_tenant.id, package_id=sample_package.id
            )


class TestActivatePurchasedPackageDurations:
    def test_monthly_sets_30_day_window(
        self, db_session, sample_tenant, sample_package
    ):
        result = SaaSProvisioningService.activate_purchased_package(
            tenant_id=sample_tenant.id, package_id=sample_package.id
        )
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert result["subscription_plan"] == sample_package.slug
        assert result["subscription_plan_duration"] == "monthly"
        assert result["is_trial"] is False
        delta = tenant.subscription_end - tenant.subscription_start
        assert delta == timedelta(days=30)

    def test_annual_sets_365_day_window(
        self, db_session, sample_tenant, sample_package
    ):
        SaaSProvisioningService.activate_purchased_package(
            tenant_id=sample_tenant.id,
            package_id=sample_package.id,
            duration_type="annual",
        )
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert tenant.subscription_plan_duration == "annual"
        assert tenant.is_trial is False
        assert tenant.subscription_end - tenant.subscription_start == timedelta(
            days=365
        )

    def test_trial_sets_7_day_window_and_flag(
        self, db_session, sample_tenant, sample_package
    ):
        result = SaaSProvisioningService.activate_purchased_package(
            tenant_id=sample_tenant.id,
            package_id=sample_package.id,
            duration_type="trial",
        )
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert result["is_trial"] is True
        assert tenant.subscription_plan_duration == "trial"
        assert tenant.subscription_end - tenant.subscription_start == timedelta(days=7)

    def test_lifetime_has_no_end(self, db_session, sample_tenant, sample_package):
        result = SaaSProvisioningService.activate_purchased_package(
            tenant_id=sample_tenant.id,
            package_id=sample_package.id,
            duration_type="lifetime",
        )
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert result["subscription_end"] is None
        assert tenant.subscription_end is None
        assert tenant.is_trial is False


class TestActivatePurchasedPackageFeatures:
    def test_package_limits_and_flags_applied(
        self, db_session, sample_tenant, sample_package
    ):
        SaaSProvisioningService.activate_purchased_package(
            tenant_id=sample_tenant.id, package_id=sample_package.id
        )
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert tenant.max_users == 7
        assert tenant.max_branches == 4
        assert tenant.enable_ai is True
        assert tenant.enable_pos is True
        assert tenant.enable_store is True
        assert tenant.allow_custom_integrations is True
        assert tenant.enable_reports is True

    def test_none_limits_leave_tenant_defaults(
        self, db_session, sample_tenant, sample_package
    ):
        sample_package.max_users = None
        sample_package.max_branches = None
        db_session.commit()
        original_users = sample_tenant.max_users
        original_branches = sample_tenant.max_branches
        SaaSProvisioningService.activate_purchased_package(
            tenant_id=sample_tenant.id, package_id=sample_package.id
        )
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert tenant.max_users == original_users
        assert tenant.max_branches == original_branches

    def test_result_payload_shape(self, db_session, sample_tenant, sample_package):
        result = SaaSProvisioningService.activate_purchased_package(
            tenant_id=sample_tenant.id, package_id=sample_package.id
        )
        assert result["tenant_id"] == sample_tenant.id
        assert result["package_id"] == sample_package.id
        assert result["package_slug"] == sample_package.slug
        assert result["subscription_start"] is not None
        assert result["subscription_end"] is not None


class TestDemoTenant:
    def test_activate_demo_without_demo_package_raises(self, db_session, sample_tenant):
        from models.package import Package

        assert Package.query.filter_by(slug="demo", is_active=True).first() is None
        with pytest.raises(SaaSProvisioningError, match="Demo package not found"):
            SaaSProvisioningService.activate_demo_tenant(sample_tenant.id)

    def test_activate_demo_uses_trial_duration(self, db_session, sample_tenant):
        from models.package import Package

        demo = Package(
            name_ar="تجريبي",
            name_en="Demo",
            slug="demo",
            price=0.0,
            is_active=True,
            max_users=1,
            max_branches=1,
        )
        db_session.add(demo)
        db_session.commit()
        result = SaaSProvisioningService.activate_demo_tenant(sample_tenant.id)
        assert result["is_trial"] is True
        assert result["subscription_plan"] == "demo"

    def test_is_demo_tenant(self, db_session, sample_tenant):
        assert SaaSProvisioningService.is_demo_tenant(sample_tenant) is False
        demo_like = type("T", (), {"is_trial": True, "subscription_plan": "demo"})()
        assert SaaSProvisioningService.is_demo_tenant(demo_like) is True
