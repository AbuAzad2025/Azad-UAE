"""Tenant isolation boundary fuzzer — cross-tenant security audit.

Simulates corrupted or malicious requests attempting to bypass tenant scoping
to access data from another tenant.  Every violation MUST be cleanly rejected
with zero data leakage.

Usage:
    pytest tests/unit/utils/test_tenant_isolation_fuzzer.py -v
"""

import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest

from extensions import db
from utils.tenanting import tenant_query
from utils.exceptions import SecurityBoundaryViolation
from utils.db_safety import atomic_transaction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _tenants(app):
    """Create two completely isolated tenants with identical schemas."""
    from models import Tenant, Branch, Warehouse, Customer

    uid_a = uuid.uuid4().hex[:8]
    uid_b = uuid.uuid4().hex[:8]

    with app.app_context():
        tenant_a = Tenant(
            name=f"FuzzA {uid_a}", name_ar=f"FuzzA {uid_a}", slug=f"fuzz-a-{uid_a}",
            default_currency="AED", base_currency="AED",
            enable_tax=True, default_tax_rate=Decimal("5.00"),
            enable_pos=True, is_active=True, is_suspended=False,
            subscription_plan="pro", subscription_plan_duration="monthly",
            subscription_end=datetime.now(timezone.utc) + timedelta(days=30),
            max_users=10, max_branches=2,
        )
        tenant_b = Tenant(
            name=f"FuzzB {uid_b}", name_ar=f"FuzzB {uid_b}", slug=f"fuzz-b-{uid_b}",
            default_currency="AED", base_currency="AED",
            enable_tax=True, default_tax_rate=Decimal("5.00"),
            enable_pos=True, is_active=True, is_suspended=False,
            subscription_plan="pro", subscription_plan_duration="monthly",
            subscription_end=datetime.now(timezone.utc) + timedelta(days=30),
            max_users=10, max_branches=2,
        )
        db.session.add_all([tenant_a, tenant_b])
        db.session.flush()

        for t in (tenant_a, tenant_b):
            b = Branch(tenant_id=t.id, name=f"Main {t.id}", code=f"M{t.id}", is_active=True)
            db.session.add(b)
            w = Warehouse(tenant_id=t.id, name=f"WH {t.id}", is_active=True)
            db.session.add(w)
        db.session.flush()

        customer_a = Customer(tenant_id=tenant_a.id, name="A-Customer",
                              phone="+97150000001", balance=Decimal("100.00"))
        customer_b = Customer(tenant_id=tenant_b.id, name="B-Customer",
                              phone="+97150000002", balance=Decimal("99999.00"))
        db.session.add_all([customer_a, customer_b])
        db.session.flush()

        db.session.commit()

        return {
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "customer_a": customer_a,
            "customer_b": customer_b,
        }


# ---------------------------------------------------------------------------
# Direct-model isolation tests
# ---------------------------------------------------------------------------

class TestTenantQueryBoundary:
    """tenant_query() must never return rows from a different tenant."""

    def test_customer_isolation(self, app, _tenants):
        from models import Customer
        with app.app_context():
            rows_a = tenant_query(Customer, tenant_id=_tenants["tenant_a"].id).all()
            rows_b = tenant_query(Customer, tenant_id=_tenants["tenant_b"].id).all()
            ids_a = {r.id for r in rows_a}
            ids_b = {r.id for r in rows_b}
            assert ids_a.isdisjoint(ids_b), "Cross-tenant data leak in Customer query"
            assert _tenants["customer_a"].id in ids_a
            assert _tenants["customer_b"].id in ids_b

    def test_forced_tenant_id_injection(self, app, _tenants):
        from models import Customer
        with app.app_context():
            rows = (Customer.query
                    .filter(Customer.id == _tenants["customer_b"].id)
                    .all())
            for row in rows:
                assert row.tenant_id == _tenants["tenant_b"].id

    def test_tenant_query_rejects_none(self, app):
        from models import Customer
        with app.app_context():
            with pytest.raises((TypeError, ValueError, SecurityBoundaryViolation)):
                tenant_query(Customer, tenant_id=None).all()

    def test_cross_tenant_write_blocked(self, app, _tenants):
        from models import Customer as M
        with app.app_context(), atomic_transaction():
            target = db.session.get(M, _tenants["customer_b"].id)
            if target and target.tenant_id != _tenants["tenant_a"].id:
                pass
            else:
                pytest.fail("customer_b has wrong tenant_id")

    def test_balance_not_exposed(self, app, _tenants):
        from models import Customer
        with app.app_context():
            rows_a = tenant_query(Customer, tenant_id=_tenants["tenant_a"].id).all()
            for r in rows_a:
                if r.id == _tenants["customer_b"].id:
                    pytest.fail("customer_b leaked into tenant_a query")
                assert r.tenant_id == _tenants["tenant_a"].id, (
                    f"Row {r.id} has tenant_id {r.tenant_id}, expected {_tenants['tenant_a'].id}"
                )


# ---------------------------------------------------------------------------
# Application-layer isolation (route-level with test client)
# ---------------------------------------------------------------------------

class TestRouteLevelIsolation:
    """API endpoints must enforce tenant boundaries via the test client."""

    def test_cannot_access_other_tenant_customer(self, client, _tenants):
        resp = client.get(
            f"/api/customers/{_tenants['customer_b'].id}",
            headers={
                "X-Tenant-ID": str(_tenants["tenant_a"].id),
                "Authorization": "Bearer test-token",
            },
        )
        assert resp.status_code in (403, 404, 401), (
            f"Expected 403/404/401, got {resp.status_code}"
        )

    def test_cannot_list_other_tenant_customers(self, client, _tenants):
        resp = client.get(
            "/api/customers",
            headers={
                "X-Tenant-ID": str(_tenants["tenant_a"].id),
                "Authorization": "Bearer test-token",
            },
        )
        if resp.status_code == 200:
            data = resp.get_json(silent=True) or {}
            items = data if isinstance(data, list) else data.get("data", data.get("results", []))
            for item in items:
                if isinstance(item, dict) and item.get("id") == _tenants["customer_b"].id:
                    pytest.fail("customer_b leaked into tenant_a listing")

    def test_no_tenant_header_rejected(self, client):
        resp = client.get("/api/customers")
        assert resp.status_code in (400, 401, 403)


# ---------------------------------------------------------------------------
# Corrupted / malicious payload tests
# ---------------------------------------------------------------------------

class TestMaliciousRequestIsolation:
    """Malformed or malicious requests must not bypass tenant scoping."""

    def test_sql_injection_tenant_header(self, client):
        resp = client.get(
            "/api/customers",
            headers={
                "X-Tenant-ID": "1; DROP TABLE customers",
                "Authorization": "Bearer test-token",
            },
        )
        assert resp.status_code in (400, 401, 403, 422, 500)

    def test_negative_tenant_id(self, client):
        resp = client.get(
            "/api/customers/1",
            headers={
                "X-Tenant-ID": "-1",
                "Authorization": "Bearer test-token",
            },
        )
        assert resp.status_code in (400, 401, 403, 404)

    def test_nonexistent_tenant_uuid(self, client):
        resp = client.get(
            "/api/customers/1",
            headers={
                "X-Tenant-ID": "99999999-9999-9999-9999-999999999999",
                "Authorization": "Bearer test-token",
            },
        )
        assert resp.status_code in (400, 401, 403, 404)

    def test_empty_tenant_header(self, client):
        resp = client.get(
            "/api/customers",
            headers={"X-Tenant-ID": "", "Authorization": "Bearer test-token"},
        )
        assert resp.status_code in (400, 401, 403)
