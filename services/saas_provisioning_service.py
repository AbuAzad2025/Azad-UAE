"""
SaaS Provisioning Service — activates a purchased package onto a tenant.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from flask_babel import gettext

from extensions import db
from utils.db_safety import atomic_transaction

logger = logging.getLogger(__name__)

# ── Standard commercial package tiers (single source of truth) ──
# -1 means "unlimited". Ids/slugs are stable; seed_packages() is idempotent.
DEFAULT_PACKAGES: tuple[dict, ...] = (
    {
        "slug": "basic",
        "name_ar": gettext("الباقة الأساسية"),
        "name_en": "Basic",
        "icon": "📦",
        "price": "29.000",
        "description_ar": gettext("بداية مثالية للمنشآت الصغيرة — نقاط بيع وفواتير وتقارير أساسية."),
        "description_en": "Starter tier for small businesses — core POS, invoicing and basic reports.",
        "features": [gettext("نقاط بيع أساسية"), gettext("فواتير"), gettext("تقارير أساسية")],
        "tier_level": 10,
        "max_users": 2,
        "max_branches": 1,
        "max_warehouses": 1,
        "max_products": 500,
        "max_customers": 300,
        "max_suppliers": 100,
        "max_storage_mb": 512,
        "max_invoices_per_month": 100,
        "max_sales_per_month": 300,
        "has_pos": True,
        "has_ai": False,
        "has_advanced_reports": False,
        "has_customization": False,
        "enable_payroll": False,
        "enable_expenses": True,
        "enable_cheques": True,
        "enable_reports": True,
        "enable_ai": False,
        "enable_store": False,
        "enable_gl": True,
        "enable_api": False,
        "sort_order": 10,
    },
    {
        "slug": "pro",
        "name_ar": gettext("الباقة الاحترافية"),
        "name_en": "Pro",
        "icon": "🚀",
        "price": "79.000",
        "description_ar": gettext("للمنشآت المتوسطة — رواتب وتقارير متقدمة وسعة أوسع."),
        "description_en": "For growing SMEs — payroll, advanced reports and wider capacity.",
        "features": [gettext("كل ميزات الأساسية"), gettext("رواتب"), gettext("تقارير متقدمة"), "POS متقدم"],
        "is_featured": True,
        "badge_text": gettext("الأكثر شعبية"),
        "tier_level": 20,
        "max_users": 10,
        "max_branches": 3,
        "max_warehouses": 3,
        "max_products": 5000,
        "max_customers": 3000,
        "max_suppliers": 1000,
        "max_storage_mb": 5120,
        "max_invoices_per_month": 1000,
        "max_sales_per_month": 3000,
        "has_pos": True,
        "has_ai": False,
        "has_advanced_reports": True,
        "has_customization": False,
        "enable_payroll": True,
        "enable_expenses": True,
        "enable_cheques": True,
        "enable_reports": True,
        "enable_ai": False,
        "enable_store": False,
        "enable_gl": True,
        "enable_api": False,
        "sort_order": 20,
    },
    {
        "slug": "enterprise",
        "name_ar": gettext("باقة المؤسسات"),
        "name_en": "Enterprise",
        "icon": "👑",
        "price": "199.000",
        "description_ar": gettext("بلا حدود — كل الميزات والذكاء الاصطناعي والمتجر والتكاملات."),
        "description_en": "Unlimited — every feature including AI, store and integrations.",
        "features": [
            gettext("كل الميزات"),
            gettext("ذكاء اصطناعي"),
            gettext("متجر إلكتروني"),
            "API",
            gettext("دعم أولوية"),
        ],
        "tier_level": 30,
        "max_users": -1,
        "max_branches": -1,
        "max_warehouses": -1,
        "max_products": -1,
        "max_customers": -1,
        "max_suppliers": -1,
        "max_storage_mb": -1,
        "max_invoices_per_month": -1,
        "max_sales_per_month": -1,
        "has_pos": True,
        "has_ai": True,
        "has_whatsapp": True,
        "has_advanced_reports": True,
        "has_customization": True,
        "has_training": True,
        "has_priority_support": True,
        "enable_payroll": True,
        "enable_expenses": True,
        "enable_cheques": True,
        "enable_reports": True,
        "enable_ai": True,
        "enable_store": True,
        "enable_gl": True,
        "enable_api": True,
        "sort_order": 30,
    },
)


def seed_packages() -> dict:
    """Idempotently upsert the standard commercial package tiers by slug.

    Returns {"created": [...], "updated": [...]} slug lists.
    """
    from models.package import Package

    created, updated = [], []
    with atomic_transaction("seed_packages"):
        for spec in DEFAULT_PACKAGES:
            pkg = Package.query.filter_by(slug=spec["slug"]).first()
            if pkg is None:
                pkg = Package(slug=spec["slug"])
                db.session.add(pkg)
                created.append(spec["slug"])
            else:
                updated.append(spec["slug"])
            for key, value in spec.items():
                if key == "slug":
                    continue
                if key == "price":
                    from decimal import Decimal

                    value = Decimal(str(value))
                setattr(pkg, key, value)
            pkg.is_active = True
        db.session.flush()
    logger.info("seed_packages: created=%s updated=%s", created, updated)
    return {"created": created, "updated": updated}


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

        now = datetime.now(UTC)

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

        package.apply_to_tenant(tenant)

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
            "package_snapshot": {
                "tier_level": package.tier_level,
                "has_whatsapp": bool(package.has_whatsapp),
                "has_training": bool(package.has_training),
                "has_priority_support": bool(package.has_priority_support),
            },
        }

    @staticmethod
    def apply_plan_with_template(
        tenant,
        plan: str | None,
        duration: str | None = None,
        is_trial: bool | None = None,
    ) -> bool:
        """Update plan labels; when the plan slug changes to a known active
        Package, apply that package's limits/flags template onto the tenant.

        Manual overrides survive a re-select of the *same* plan (no slug
        change → no template re-application). Caller wraps in an atomic
        transaction. Returns True when a package template was applied.
        """
        from models.package import Package

        plan_changed = plan is not None and plan != tenant.subscription_plan
        tenant.apply_subscription_plan(plan, duration, is_trial)
        if not plan_changed:
            return False
        package = Package.query.filter_by(slug=plan, is_active=True).first()
        if package is None:
            return False
        package.apply_to_tenant(tenant)
        logger.info("Tenant %s plan changed to %s — package template applied", tenant.id, plan)
        return True

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
