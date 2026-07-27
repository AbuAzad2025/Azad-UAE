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
        max_products=321,
        max_sales_per_month=654,
        has_ai=True,
        has_pos=True,
        has_customization=True,
        has_advanced_reports=True,
        has_whatsapp=True,
        enable_ai=True,
        enable_store=True,
        enable_payroll=True,
    )
    db_session.add(package)
    db_session.commit()
    return package


class TestActivatePurchasedPackageValidation:
    def test_missing_tenant_raises(self, db_session, sample_package):
        with pytest.raises(SaaSProvisioningError, match="Tenant .* not found"):
            SaaSProvisioningService.activate_purchased_package(tenant_id=999999999, package_id=sample_package.id)

    def test_missing_package_raises(self, db_session, sample_tenant):
        with pytest.raises(SaaSProvisioningError, match="not found or inactive"):
            SaaSProvisioningService.activate_purchased_package(tenant_id=sample_tenant.id, package_id=999999999)

    def test_inactive_package_raises(self, db_session, sample_tenant, sample_package):
        sample_package.is_active = False
        db_session.commit()
        with pytest.raises(SaaSProvisioningError, match="not found or inactive"):
            SaaSProvisioningService.activate_purchased_package(tenant_id=sample_tenant.id, package_id=sample_package.id)


class TestActivatePurchasedPackageDurations:
    def test_monthly_sets_30_day_window(self, db_session, sample_tenant, sample_package):
        result = SaaSProvisioningService.activate_purchased_package(
            tenant_id=sample_tenant.id, package_id=sample_package.id
        )
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert result["subscription_plan"] == sample_package.slug
        assert result["subscription_plan_duration"] == "monthly"
        assert result["is_trial"] is False
        delta = tenant.subscription_end - tenant.subscription_start
        assert delta == timedelta(days=30)

    def test_annual_sets_365_day_window(self, db_session, sample_tenant, sample_package):
        SaaSProvisioningService.activate_purchased_package(
            tenant_id=sample_tenant.id,
            package_id=sample_package.id,
            duration_type="annual",
        )
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert tenant.subscription_plan_duration == "annual"
        assert tenant.is_trial is False
        assert tenant.subscription_end - tenant.subscription_start == timedelta(days=365)

    def test_trial_sets_7_day_window_and_flag(self, db_session, sample_tenant, sample_package):
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
    def test_package_limits_and_flags_applied(self, db_session, sample_tenant, sample_package):
        SaaSProvisioningService.activate_purchased_package(tenant_id=sample_tenant.id, package_id=sample_package.id)
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert tenant.max_users == 7
        assert tenant.max_branches == 4
        assert tenant.max_products == 321
        assert tenant.max_sales_per_month == 654
        assert tenant.enable_ai is True
        assert tenant.enable_pos is True
        assert tenant.enable_store is True
        assert tenant.enable_payroll is True
        assert tenant.allow_custom_integrations is True
        assert tenant.enable_reports is True

    def test_none_limits_leave_tenant_defaults(self, db_session, sample_tenant, sample_package):
        sample_package.max_users = None
        sample_package.max_branches = None
        db_session.commit()
        original_users = sample_tenant.max_users
        original_branches = sample_tenant.max_branches
        SaaSProvisioningService.activate_purchased_package(tenant_id=sample_tenant.id, package_id=sample_package.id)
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
        snapshot = result["package_snapshot"]
        assert snapshot["has_whatsapp"] is True
        assert snapshot["has_training"] is False
        assert snapshot["has_priority_support"] is False


class TestApplyPlanWithTemplate:
    def test_plan_change_applies_package_template(self, db_session, sample_tenant, sample_package):
        applied = SaaSProvisioningService.apply_plan_with_template(sample_tenant, sample_package.slug, "annual", False)
        assert applied is True
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert tenant.subscription_plan == sample_package.slug
        assert tenant.subscription_plan_duration == "annual"
        assert tenant.max_users == 7
        assert tenant.max_sales_per_month == 654
        assert tenant.enable_payroll is True

    def test_same_plan_reselect_preserves_manual_overrides(self, db_session, sample_tenant, sample_package):
        sample_tenant.subscription_plan = sample_package.slug
        sample_tenant.max_users = 99
        db_session.commit()
        applied = SaaSProvisioningService.apply_plan_with_template(sample_tenant, sample_package.slug, "monthly", None)
        assert applied is False
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert tenant.max_users == 99
        assert tenant.subscription_plan_duration == "monthly"

    def test_unknown_plan_slug_updates_labels_only(self, db_session, sample_tenant):
        applied = SaaSProvisioningService.apply_plan_with_template(sample_tenant, "no-such-plan", None, None)
        assert applied is False
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert tenant.subscription_plan == "no-such-plan"

    def test_none_plan_leaves_everything(self, db_session, sample_tenant):
        before = sample_tenant.subscription_plan
        applied = SaaSProvisioningService.apply_plan_with_template(sample_tenant, None, "annual", True)
        assert applied is False
        tenant = db_session.get(type(sample_tenant), sample_tenant.id)
        assert tenant.subscription_plan == before
        assert tenant.subscription_plan_duration == "annual"
        assert tenant.is_trial is True


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


class TestSeedPackages:
    def test_creates_three_standard_tiers(self, db_session):
        from models.package import Package
        from services.saas_provisioning_service import DEFAULT_PACKAGES, seed_packages

        result = seed_packages()
        assert sorted(result["created"] + result["updated"]) == ["basic", "enterprise", "pro"]
        assert len(DEFAULT_PACKAGES) == 3
        for slug, expected_tier in (("basic", 10), ("pro", 20), ("enterprise", 30)):
            pkg = Package.query.filter_by(slug=slug).first()
            assert pkg is not None and pkg.is_active is True
            assert pkg.tier_level == expected_tier

    def test_idempotent_second_run_updates(self, db_session):
        from services.saas_provisioning_service import seed_packages

        seed_packages()
        result = seed_packages()
        assert result["created"] == []
        assert sorted(result["updated"]) == ["basic", "enterprise", "pro"]

    def test_enterprise_unlimited_minus_one(self, db_session):
        from models.package import Package
        from services.saas_provisioning_service import seed_packages

        seed_packages()
        pkg = Package.query.filter_by(slug="enterprise").first()
        for col in (
            "max_users",
            "max_branches",
            "max_products",
            "max_customers",
            "max_suppliers",
            "max_warehouses",
            "max_storage_mb",
            "max_invoices_per_month",
            "max_sales_per_month",
        ):
            assert getattr(pkg, col) == -1, col
        for flag in (
            "enable_payroll",
            "enable_expenses",
            "enable_cheques",
            "enable_reports",
            "enable_ai",
            "enable_store",
            "enable_gl",
            "enable_api",
        ):
            assert getattr(pkg, flag) is True, flag

    def test_plan_meets_uses_db_tier_levels(self, db_session):
        from services.saas_provisioning_service import seed_packages
        from utils.pos_features import plan_meets

        seed_packages()
        assert plan_meets("basic", "pro") is False
        assert plan_meets("pro", "pro") is True
        assert plan_meets("enterprise", "pro") is True
        assert plan_meets(None, "basic") is True
        assert plan_meets(None, "enterprise") is False
