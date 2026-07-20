"""
SaaS Provisioning Service — activates a purchased package onto a tenant.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from extensions import db
from utils.db_safety import atomic_transaction

logger = logging.getLogger(__name__)


class SaaSProvisioningError(Exception):
    """Raised when provisioning a purchased package fails."""


class SaaSProvisioningService:
    @staticmethod
    def activate_purchased_package(
        tenant_id: int,
        package_id: int,
        duration_type: str = "monthly",
    ) -> dict:
        from models.package import Package
        from models.tenant import Tenant

        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            raise SaaSProvisioningError(f"Tenant {tenant_id} not found")

        package = db.session.get(Package, package_id)
        if not package or not package.is_active:
            raise SaaSProvisioningError(f"Package {package_id} not found or inactive")

        now = datetime.now(timezone.utc)

        if duration_type == "lifetime":
            subscription_end = None
            is_trial = False
        elif duration_type == "annual":
            subscription_end = now + timedelta(days=365)
            is_trial = False
        elif duration_type == "trial":
            subscription_end = now + timedelta(days=7)
            is_trial = True
            duration_type = "trial"
        else:
            subscription_end = now + timedelta(days=30)
            is_trial = False

        tenant.subscription_plan = package.slug
        tenant.subscription_plan_duration = duration_type
        tenant.subscription_start = now
        tenant.subscription_end = subscription_end
        tenant.is_trial = is_trial

        if package.max_users is not None:
            tenant.max_users = package.max_users
        if package.max_branches is not None:
            tenant.max_branches = package.max_branches

        tenant.enable_ai = package.has_ai
        tenant.enable_pos = package.has_pos
        tenant.enable_store = bool(package.has_pos)
        tenant.allow_custom_integrations = package.has_customization

        if package.has_advanced_reports:
            tenant.enable_reports = True
        if package.has_priority_support:
            pass

        with atomic_transaction("saas_provisioning_activate"):
            db.session.flush()

        logger.info(
            "Tenant %s activated with package %s (duration=%s, end=%s, trial=%s)",
            tenant_id,
            package.slug,
            duration_type,
            subscription_end,
            is_trial,
        )

        return {
            "tenant_id": tenant.id,
            "package_id": package.id,
            "package_slug": package.slug,
            "subscription_plan": tenant.subscription_plan,
            "subscription_plan_duration": tenant.subscription_plan_duration,
            "is_trial": tenant.is_trial,
            "subscription_start": (tenant.subscription_start.isoformat() if tenant.subscription_start else None),
            "subscription_end": (tenant.subscription_end.isoformat() if tenant.subscription_end else None),
        }

    @staticmethod
    def activate_demo_tenant(tenant_id: int) -> dict:
        from models.package import Package

        demo = Package.query.filter_by(slug="demo", is_active=True).first()
        if not demo:
            raise SaaSProvisioningError(
                "Demo package not found. Create a Package with slug='demo', "
                "max_users=1, max_branches=1 before activating demo tenants."
            )
        return SaaSProvisioningService.activate_purchased_package(
            tenant_id=tenant_id,
            package_id=demo.id,
            duration_type="trial",
        )

    @staticmethod
    def is_demo_tenant(tenant) -> bool:
        return getattr(tenant, "is_trial", False) and getattr(tenant, "subscription_plan", "") == "demo"
