"""Platform/tenant boundary guards for the owner panel.

Architectural invariant: tenant financial operations, sales analytics,
bookkeeping, and customer records must NEVER be reachable from the global
owner workspace. These tests pin the removal and the explicit-tenant rule.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def owner_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp

    app = app_factory(owner_bp)
    return app.test_client()


class TestRemovedTenantSurfaces404:
    """Purged owner routes must not resolve (no silent re-registration)."""

    @pytest.mark.parametrize(
        "url",
        [
            "/owner/financial-overview",
            "/owner/financial-overview?_platform=1",
            "/owner/financial-dashboard-advanced",
            "/owner/sales-insights",
            "/owner/customer-insights",
            "/owner/product-performance",
            "/owner/forecasting",
            "/owner/cards-vault",
            "/owner/cards-vault?customer=5",
            "/owner/cards-vault/1/view",
        ],
    )
    def test_purged_route_is_gone(self, owner_client, url):
        assert owner_client.get(url).status_code == 404


class TestArchivedRequiresExplicitTenant:
    """Archived business snapshots: one tenant at a time, never global."""

    def test_no_tenant_404(self, owner_client):
        assert owner_client.get("/owner/archived").status_code == 404

    def test_unknown_tenant_404(self, owner_client):
        assert owner_client.get("/owner/archived?tenant_id=999999999").status_code == 404

    def test_valid_tenant_renders(self, owner_client, db_session, sample_tenant):
        from unittest.mock import patch

        from services.owner_ops_service import OwnerOpsService

        with (
            patch.object(OwnerOpsService, "get_tenant", return_value=sample_tenant),
            patch.object(OwnerOpsService, "active_ai_tenants", return_value=[sample_tenant]),
            patch("routes.owner.core.render_template", return_value="ok"),
        ):
            resp = owner_client.get(f"/owner/archived?tenant_id={sample_tenant.id}")
        assert resp.status_code == 200


class TestLeakEnginesDeleted:
    """The cross-tenant aggregation helpers must not exist anymore."""

    def test_financial_overview_removed(self):
        from services.financial_service import FinancialService

        assert not hasattr(FinancialService, "financial_overview")

    def test_card_vault_helpers_removed(self):
        from services.owner_ops_service import OwnerOpsService

        assert not hasattr(OwnerOpsService, "card_vault_context")
        assert not hasattr(OwnerOpsService, "get_card_or_404")
