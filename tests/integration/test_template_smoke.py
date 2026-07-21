"""Template rendering smoke tests — GET requests to trigger Jinja2 template coverage.

These tests do NOT mock render_template. They make real authenticated GET
requests to top-priority routes so Flask's template_rendered signal fires
and the coverage tracker in conftest.py records the templates.

Uses existing owner_client (platform owner) and auth_client (tenant user)
fixtures from tests/conftest.py.
"""

from __future__ import annotations

import pytest


class TestOwnerPanelTemplateSmoke:
    """Owner panel routes — uses owner_client fixture (platform owner login)."""

    @pytest.mark.parametrize(
        "route",
        [
            "/owner/dashboard",
            "/owner/config",
            "/owner/audit-logs",
            "/owner/company-info",
            "/owner/developer-settings",
            "/owner/system-config",
            "/owner/reports",
            "/owner/integrations",
            "/owner/invoice-settings",
            "/owner/currency-settings",
            "/owner/exchange-rates",
            "/owner/payment-gateways",
            "/owner/email-settings",
            "/owner/sms-settings",
            "/owner/whatsapp-settings",
            "/owner/notification-templates",
            "/owner/store-payment-methods",
            "/owner/tenants",
            "/owner/tenant-stores",
            "/owner/tenant-ai",
            "/owner/users-list",
            "/owner/roles-permissions",
            "/owner/database-tools",
            "/owner/sql-console",
            "/owner/import-export-tools",
            "/owner/data-cleanup",
            "/owner/verify-backups",
            "/owner/system-health",
            "/owner/activity-monitor",
            "/owner/login-history",
            "/owner/performance-metrics",
            "/owner/security-alerts",
            "/owner/ip-whitelist",
            "/owner/api-keys",
            "/owner/financial-dashboard-advanced",
            "/owner/sales-insights",
            "/owner/customer-insights",
            "/owner/product-performance",
            "/owner/forecasting",
            "/owner/backups/list",
            "/owner/scheduled-backups",
        ],
    )
    def test_owner_route_renders(self, owner_client, route):
        resp = owner_client.get(route, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{route} returned {resp.status_code}"


class TestTenantRouteTemplateSmoke:
    """Tenant-scoped routes — uses auth_client fixture (tenant user login)."""

    @pytest.mark.parametrize(
        "route",
        [
            "/",
            "/dashboard",
            "/my-profile",
            "/cheques/",
            "/cheques/archived",
            "/cheques/create",
            "/admin/ledger/",
            "/admin/ledger/accounts",
            "/admin/ledger/vaults",
            "/admin/ledger/journals",
            "/admin/ledger/reports",
            "/admin/ledger/settings",
            "/branches/",
            "/branches/create",
            "/customers/",
            "/customers/create",
            "/expenses/",
            "/expenses/categories",
            "/expenses/archived",
            "/sales/",
            "/sales/archived",
            "/reports/",
            "/reports/top-selling",
            "/hr/",
            "/hr/attendance",
            "/hr/leave-request",
            "/crm/leads",
            "/crm/pipeline",
            "/suppliers/",
            "/purchases/",
            "/warehouse/",
            "/pos/",
            "/pos/sessions",
            "/tickets/",
            "/partners/",
            "/projects/",
            "/monitoring/",
            "/email-marketing/",
            "/treasury/",
            "/payroll/",
        ],
    )
    def test_tenant_route_renders(self, auth_client, route):
        resp = auth_client.get(route, follow_redirects=True)
        assert resp.status_code in (200, 404, 403), f"{route} returned {resp.status_code}"


class TestPublicRouteTemplateSmoke:
    """Public routes — no auth needed, uses bare client fixture."""

    @pytest.mark.parametrize(
        "route",
        [
            "/auth/login",
            "/auth/register",
        ],
    )
    def test_public_route_renders(self, client, route):
        resp = client.get(route, follow_redirects=True)
        assert resp.status_code in (200, 404, 302), f"{route} returned {resp.status_code}"
