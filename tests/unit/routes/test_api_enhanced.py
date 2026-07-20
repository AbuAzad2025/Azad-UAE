"""Unit tests for routes/api_enhanced.py — /api/v2 endpoints.

Complements tests/integration/test_api_enhanced_assurance.py (which covers the
basic happy paths); this file focuses on what that suite does not: the real
permission contract, cross-tenant isolation (IDOR), search-by-SKU, result
ordering, and service-call argument passthrough.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def no_perm_client(client, db_session, sample_tenant):
    """Authenticated tenant user whose role has zero permissions."""
    from models import Role, User

    unique = str(uuid.uuid4())[:8]
    role = Role(name=f"No Perms {unique}", slug=f"no_perms_{unique}", is_active=True)
    db_session.add(role)
    db_session.flush()
    user = User(
        username=f"noperm-{unique}",
        email=f"noperm-{unique}@example.com",
        full_name="No Perms",
        tenant_id=sample_tenant.id,
        role_id=role.id,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=False,
    )
    return client


@pytest.fixture
def foreign_sale(db_session):
    """A sale belonging to a different tenant (IDOR probe)."""
    from datetime import datetime, timezone
    from decimal import Decimal

    from flask import g

    from models import Customer, Role, Sale, Tenant, User

    unique = str(uuid.uuid4())[:8]
    g.skip_tenant_scope = True  # established pattern for cross-tenant fixtures
    try:
        tenant = Tenant(
            name=f"Foreign Co {unique}",
            name_ar="أجنبية",
            slug=f"foreign-{unique}",
            email=f"foreign-{unique}@example.com",
            country="AE",
            subscription_plan="basic",
        )
        role = Role(name=f"Foreign Role {unique}", slug=f"foreign_{unique}", is_active=True)
        db_session.add_all([tenant, role])
        db_session.flush()
        customer = Customer(tenant_id=tenant.id, name="Foreign Customer")
        user = User(
            username=f"foreign-{unique}",
            email=f"foreign-user-{unique}@example.com",
            full_name="Foreign User",
            tenant_id=tenant.id,
            role_id=role.id,
        )
        user.set_password("password123")
        db_session.add_all([customer, user])
        db_session.flush()
        sale = Sale(
            tenant_id=tenant.id,
            sale_number=f"FOREIGN-{unique}",
            customer_id=customer.id,
            seller_id=user.id,
            sale_date=datetime.now(timezone.utc),
            subtotal=Decimal("50"),
            total_amount=Decimal("50"),
            amount=Decimal("50"),
            amount_aed=Decimal("50"),
            currency="AED",
        )
        db_session.add(sale)
        db_session.commit()
    finally:
        g.skip_tenant_scope = False
    return sale


class TestAccessContract:
    def test_anonymous_redirected_to_login(self, client):
        assert client.get("/api/v2/sales").status_code == 302

    def test_sales_requires_manage_sales(self, no_perm_client):
        assert no_perm_client.get("/api/v2/sales").status_code == 403

    def test_customers_requires_manage_customers(self, no_perm_client):
        assert no_perm_client.get("/api/v2/customers").status_code == 403

    def test_search_requires_manage_products(self, no_perm_client):
        assert no_perm_client.get("/api/v2/products/search?q=x").status_code == 403

    def test_analytics_requires_view_reports(self, no_perm_client):
        assert no_perm_client.get("/api/v2/analytics/sales-forecast").status_code == 403


class TestSalesList:
    def test_envelope_and_own_sale_visible(self, auth_client, sample_sale):
        resp = auth_client.get("/api/v2/sales?per_page=50")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert {"sales", "total", "page", "pages"} <= set(data)
        assert data["page"] == 1
        assert data["total"] >= 1
        assert sample_sale.id in [s["id"] for s in data["sales"]]


class TestSaleDetailTenantIsolation:
    def test_cross_tenant_sale_not_found(self, auth_client, foreign_sale):
        from werkzeug.exceptions import NotFound

        try:
            resp = auth_client.get(f"/api/v2/sales/{foreign_sale.id}")
        except NotFound:
            return
        assert resp.status_code == 404


class TestProductSearch:
    def test_search_by_sku(self, auth_client, sample_product):
        resp = auth_client.get("/api/v2/products/search?q=SKU-TEST-001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["count"] >= 1
        assert sample_product.id in [p["id"] for p in data["products"]]

    def test_cross_tenant_product_not_returned(self, auth_client, db_session):
        from decimal import Decimal

        from flask import g

        from models import Product, Tenant

        unique = str(uuid.uuid4())[:8]
        g.skip_tenant_scope = True
        try:
            tenant = Tenant(
                name=f"Foreign Co {unique}",
                name_ar="أجنبية",
                slug=f"foreign-{unique}",
                email=f"foreign-{unique}@example.com",
                country="AE",
                subscription_plan="basic",
            )
            db_session.add(tenant)
            db_session.flush()
            product = Product(
                tenant_id=tenant.id,
                name="Foreign Product",
                sku=f"FOREIGN-SKU-{unique}",
                cost_price=Decimal("1"),
                regular_price=Decimal("2"),
            )
            db_session.add(product)
            db_session.commit()
        finally:
            g.skip_tenant_scope = False

        resp = auth_client.get(f"/api/v2/products/search?q=FOREIGN-SKU-{unique}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 0
        assert data["products"] == []


class TestCustomersList:
    def test_customers_ordered_by_name(self, auth_client, db_session, sample_tenant):
        from models import Customer

        zeta = Customer(tenant_id=sample_tenant.id, name="Zeta Customer")
        alpha = Customer(tenant_id=sample_tenant.id, name="Alpha Customer")
        db_session.add_all([zeta, alpha])
        db_session.commit()

        resp = auth_client.get("/api/v2/customers?per_page=50")
        assert resp.status_code == 200
        names = [c["name"] for c in resp.get_json()["customers"]]
        assert names.index("Alpha Customer") < names.index("Zeta Customer")


class TestAnalyticsPassthrough:
    def test_forecast_passes_days_ahead(self, auth_client, mocker):
        predict = mocker.patch(
            "services.ai_service.AIService.predict_sales_trend",
            return_value={"success": True, "forecast": []},
        )
        resp = auth_client.get("/api/v2/analytics/sales-forecast?days=21")
        assert resp.status_code == 200
        predict.assert_called_once_with(days_ahead=21)
