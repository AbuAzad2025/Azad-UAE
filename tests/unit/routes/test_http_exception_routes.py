"""HTTPException must survive broad handlers in tenant-scoped routes.

A bare ``except Exception`` around ``abort(403)`` / ``tenant_get_or_404`` used
to turn a missing or cross-tenant id into a flashed 200 or a masked 500. These
tests pin the real HTTP status on the repaired handlers and keep valid flows
working.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def foreign_customer(db_session):
    from models import Customer, Tenant
    from utils.tenanting import without_tenant_scope

    unique = uuid.uuid4().hex[:8]
    with without_tenant_scope():
        tenant = Tenant(
            name=f"Foreign {unique}",
            name_ar="شركة أجنبية",
            slug=f"foreign-{unique}",
            country="AE",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        customer = Customer(tenant_id=tenant.id, name="Foreign Customer", is_active=True)
        db_session.add(customer)
        db_session.flush()
    return customer


@pytest.fixture
def foreign_product(db_session):
    from decimal import Decimal

    from models import Product, Tenant
    from utils.tenanting import without_tenant_scope

    unique = uuid.uuid4().hex[:8]
    with without_tenant_scope():
        tenant = Tenant(
            name=f"Foreign {unique}",
            name_ar="شركة أجنبية",
            slug=f"foreign-product-{unique}",
            country="AE",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        product = Product(
            tenant_id=tenant.id,
            name="Foreign Product",
            sku=f"FOREIGN-{unique}",
            regular_price=Decimal("10.000"),
            cost_price=Decimal("5.000"),
        )
        db_session.add(product)
        db_session.flush()
    return product


class TestHttpExceptionNotSwallowed:
    def test_sales_create_cross_tenant_customer_is_404(self, auth_client, foreign_customer):
        resp = auth_client.post(
            "/sales/create",
            data={"customer_id": str(foreign_customer.id), "line_count": "0"},
        )
        assert resp.status_code == 404

    def test_sales_create_with_own_customer_is_not_404(self, auth_client, db_session, sample_tenant):
        from models import Customer

        customer = Customer(tenant_id=sample_tenant.id, name="Own Customer", is_active=True)
        db_session.add(customer)
        db_session.flush()
        resp = auth_client.post(
            "/sales/create",
            data={"customer_id": str(customer.id), "line_count": "0"},
        )
        assert resp.status_code != 404

    def test_add_stock_missing_product_is_404(self, auth_client):
        resp = auth_client.post("/warehouse/add-stock/98765432", data={"quantity": "5"})
        assert resp.status_code == 404

    def test_add_stock_cross_tenant_product_is_404(self, auth_client, foreign_product):
        resp = auth_client.post(f"/warehouse/add-stock/{foreign_product.id}", data={"quantity": "5"})
        assert resp.status_code == 404

    def test_invoice_settings_without_tenant_is_404(self, owner_client):
        # The owner login restores an active tenant in the session; clear it so
        # the POST runs in platform-only context, where the tenant is missing.
        with owner_client.session_transaction() as sess:
            sess.pop("active_tenant_id", None)
        resp = owner_client.post("/owner/invoice-settings", data={"company_name_ar": "شركتنا"})
        assert resp.status_code == 404, resp.headers.get("Location")

    def test_invoice_settings_with_tenant_still_saves(self, auth_client, sample_tenant):
        resp = auth_client.post(
            "/owner/invoice-settings",
            data={"company_name_ar": "شركتنا"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
