"""Unit tests for ProductService lookup/scoping helpers."""

from __future__ import annotations

import uuid

import pytest

from extensions import db
from models import Customer
from services.product_service import ProductService


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    yield
    db_session.rollback()


def _customer(tenant_id, name, customer_type="regular", is_active=True):
    customer = Customer(
        tenant_id=tenant_id,
        name=name,
        customer_type=customer_type,
        email=f"{uuid.uuid4().hex[:8]}@products.test",
        phone="0500000000",
        is_active=is_active,
    )
    db.session.add(customer)
    db.session.flush()
    return customer


class TestTenantBusinessType:
    def test_returns_normalized_business_type(self, db_session, sample_tenant):
        sample_tenant.business_type = "  Retail "
        db.session.flush()
        assert ProductService.tenant_business_type(sample_tenant.id) == "retail"

    def test_returns_none_when_unset(self, db_session, sample_tenant):
        sample_tenant.business_type = ""
        db.session.flush()
        assert ProductService.tenant_business_type(sample_tenant.id) is None

    def test_returns_none_for_missing_tenant(self):
        assert ProductService.tenant_business_type(987654321) is None


class TestScopedCustomers:
    def test_scoped_customers_filter_type_and_order_by_name(self, db_session, sample_tenant):
        alpha = _customer(sample_tenant.id, "Alpha Merchant", customer_type="merchant")
        beta = _customer(sample_tenant.id, "Beta Merchant", customer_type="merchant")
        _customer(sample_tenant.id, "Partner One", customer_type="partner")

        merchants = [c for c in ProductService.scoped_customers("merchant") if c.tenant_id == sample_tenant.id]

        assert {alpha.id, beta.id} <= {c.id for c in merchants}
        assert all(c.customer_type == "merchant" for c in merchants)
        relevant_names = [c.name for c in merchants if c.id in (alpha.id, beta.id)]
        assert relevant_names == sorted(relevant_names)

    def test_scoped_customers_excludes_inactive(self, db_session, sample_tenant):
        active = _customer(sample_tenant.id, "Active Partner", customer_type="partner")
        _customer(sample_tenant.id, "Inactive Partner", customer_type="partner", is_active=False)

        partners = [c for c in ProductService.scoped_customers("partner") if c.tenant_id == sample_tenant.id]

        assert active.id in {c.id for c in partners}
        assert all(c.is_active for c in partners)

    def test_find_scoped_customer_returns_match(self, db_session, sample_tenant):
        customer = _customer(sample_tenant.id, "Find Me", customer_type="partner")

        found = ProductService.find_scoped_customer(customer.id, "partner")

        assert found is not None
        assert found.id == customer.id

    def test_find_scoped_customer_respects_customer_type(self, db_session, sample_tenant):
        customer = _customer(sample_tenant.id, "Wrong Type", customer_type="merchant")

        assert ProductService.find_scoped_customer(customer.id, "partner") is None

    def test_find_scoped_customer_missing_returns_none(self):
        assert ProductService.find_scoped_customer(987654321, "merchant") is None

    def test_scoped_customers_query_with_branch_scope_executes(self, db_session, sample_tenant):
        _customer(sample_tenant.id, "Branch Buyer", customer_type="merchant")

        result = ProductService.scoped_customers_query(
            "merchant",
            branch_scope_id=sample_tenant.id,
        ).all()

        assert isinstance(result, list)
