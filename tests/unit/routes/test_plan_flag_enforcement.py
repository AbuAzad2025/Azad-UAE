"""Plan flag enforcement: a locked module must not be reachable by URL.

Guards the alignment between a tenant's package flags and the routes that
serve each module, including ledger-backed reports and partner data.
"""

from __future__ import annotations


class TestPlanFlagEnforcement:
    def test_locked_modules_are_denied(self, auth_client, db_session, sample_tenant):
        for flag in (
            "enable_gl",
            "enable_cheques",
            "enable_partners",
            "enable_payroll",
            "enable_reports",
        ):
            setattr(sample_tenant, flag, False)
        db_session.flush()

        expected_403 = [
            "/ledger/",
            "/admin/ledger/",
            "/ledger/advanced/journal-management",
            "/reports/ar-reconciliation",
            "/reports/inventory-reconciliation",
            "/reports/treasury",
            "/reports/vat-return",
            "/reports/wps-export",
            "/reports/partners",
            "/partners/",
            "/cheques/",
        ]
        for path in expected_403:
            response = auth_client.get(path)
            assert response.status_code == 403, (path, response.status_code)

    def test_reports_still_open_when_reports_enabled(self, auth_client, db_session, sample_tenant):
        sample_tenant.enable_reports = True
        sample_tenant.enable_gl = False
        db_session.flush()
        response = auth_client.get("/reports/sales")
        assert response.status_code == 200

    def test_plan_change_rewrites_tenant_flags_limits_and_route_access(self, auth_client, db_session, sample_tenant):
        """Choosing a plan must change behaviour, not just the plan label."""
        import uuid
        from decimal import Decimal

        from models.package import Package
        from services.saas_provisioning_service import SaaSProvisioningService

        slug = "audit-" + uuid.uuid4().hex[:8]
        package = Package(
            slug=slug,
            name_ar="باقة تدقيق",
            name_en="Audit plan",
            price=Decimal("1"),
            is_active=True,
            tier_level=10,
            max_users=2,
            max_branches=1,
            enable_gl=False,
            enable_ai=False,
            enable_store=False,
            enable_api=False,
            has_pos=True,
        )
        db_session.add(package)
        db_session.flush()

        SaaSProvisioningService.activate_purchased_package(sample_tenant.id, package.id)
        db_session.flush()

        assert sample_tenant.subscription_plan == slug
        assert sample_tenant.enable_gl is False
        assert sample_tenant.max_users == 2
        assert auth_client.get("/ledger/").status_code == 403

    def test_platform_module_switch_is_enforced(self, auth_client, db_session):
        from models.system_settings import SystemSettings

        settings = SystemSettings.query.filter_by(is_active=True).first()
        if settings is None:
            return  # defaults are all enabled; nothing to switch off
        original = settings.enable_sales
        try:
            settings.enable_sales = False
            db_session.flush()
            assert auth_client.get("/sales/").status_code == 403
            assert auth_client.get("/reports/sales").status_code == 200
        finally:
            settings.enable_sales = original
            db_session.flush()
