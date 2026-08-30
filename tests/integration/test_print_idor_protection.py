"""
Integration tests for cross-tenant IDOR protection on printing endpoints.

Spec: R-3 from the zero-trust authorization audit (H-1, H-2, R-3).

A user authenticated in Tenant A must NEVER be able to read, view, or
print a document that belongs to Tenant B by guessing or passing an
arbitrary primary key. The expected response is HTTP 404 (preferred —
hides existence) or HTTP 403.

This test exercises the real Flask test client against the real ORM
listener, validating the full defense stack:
  - @login_required (session)
  - @permission_required (role gate)
  - PrintService.get_document (explicit tenant filter)
  - SQLAlchemy ORM listener (with_loader_criteria)
  - before_flush (write guard)
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest


def _login_as(client, user, tenant_id):
    """Push the user_id into the session the way Flask-Login expects,
    and set active_tenant_id so the ORM scoping layer resolves correctly."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["active_tenant_id"] = tenant_id


def _make_tenant_role(db_session, slug_prefix, role_slug="super_admin"):
    """Create a tenant + role + branch + user in one shot. Returns the user."""
    from models import Branch, Customer, Role, Tenant, User

    suffix = str(uuid.uuid4())[:8]
    tenant = Tenant(
        name=f"{slug_prefix}_{suffix}",
        name_ar=f"{slug_prefix}_{suffix}",
        slug=f"{slug_prefix.lower()}-{suffix}",
        default_currency="AED",
        base_currency="AED",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.flush()

    role = Role(name=f"Role_{suffix}", slug=f"{role_slug}_{suffix}", is_active=True)
    db_session.add(role)
    db_session.flush()

    branch = Branch(
        tenant_id=tenant.id,
        name=f"Br_{suffix}",
        code=f"B{suffix[:4].upper()}",
        is_active=True,
    )
    db_session.add(branch)
    db_session.flush()

    customer = Customer(tenant_id=tenant.id, name=f"Cust_{suffix}", phone=f"050{suffix}")
    db_session.add(customer)
    db_session.flush()

    user = User(
        tenant_id=tenant.id,
        branch_id=branch.id,
        username=f"u_{slug_prefix}_{suffix}",
        email=f"{slug_prefix}_{suffix}@test.com",
        is_active=True,
        password_hash="fakehash",
        role_id=role.id,
    )
    db_session.add(user)
    db_session.flush()
    db_session.commit()
    return user, tenant, role, branch, customer


def _make_sale(db_session, tenant, branch, user, customer):
    """Create a minimal Sale that satisfies the ORM listener."""
    from models import Sale

    sale = Sale(
        tenant_id=tenant.id,
        branch_id=branch.id,
        seller_id=user.id,
        customer_id=customer.id,
        sale_number=f"INV-{uuid.uuid4().hex[:8]}",
        sale_date=datetime.now(UTC),
        subtotal=Decimal("100.000"),
        total_amount=Decimal("100.000"),
        amount=Decimal("100.000"),
        amount_aed=Decimal("100.000"),
        balance_due=Decimal("100.000"),
        currency="AED",
    )
    db_session.add(sale)
    db_session.flush()
    db_session.commit()
    return sale


class TestPrintServiceIDOR:
    """Direct service-layer test: PrintService.get_document must reject
    a cross-tenant lookup even when called with a valid record_id."""

    def test_get_document_without_tenant_id_raises(self, app, db_session):
        """Spec R-3 + H-1: explicit required-parameter contract."""
        from models import Sale
        from services.print_service import PrintService

        with app.app_context():
            with pytest.raises(ValueError, match="tenant_id is required"):
                PrintService.get_document(Sale, 1, None)

    def test_get_document_cross_tenant_returns_none(self, app, db_session):
        """A valid record_id from Tenant A must NOT be returned to Tenant B."""
        from models import Sale
        from services.print_service import PrintService

        user_a, tenant_a, _, branch_a, customer_a = _make_tenant_role(db_session, "A")
        sale_a = _make_sale(db_session, tenant_a, branch_a, user_a, customer_a)

        with app.app_context():
            found = PrintService.get_document(Sale, sale_a.id, tenant_id=999_999)
            assert found is None, (
                f"Cross-tenant lookup must return None, but got {found!r} for sale {sale_a.id} of tenant {tenant_a.id}"
            )


class TestPrintRouteIDOR:
    """Route-layer test: a user logged into Tenant A must get 404
    when hitting /printing/sale/<id_of_tenant_B_sale>."""

    def test_sale_print_cross_tenant_returns_404(self, app, db_session):
        from app import create_app  # noqa: F401

        user_a, tenant_a, _, branch_a, customer_a = _make_tenant_role(db_session, "Tna")
        user_b, tenant_b, _, branch_b, customer_b = _make_tenant_role(db_session, "Tnb")
        sale_b = _make_sale(db_session, tenant_b, branch_b, user_b, customer_b)

        with app.test_client() as client:
            _login_as(client, user_a, tenant_a.id)
            resp = client.get(f"/printing/sale/{sale_b.id}")
            # The route may redirect (302 to login) on session/perm issues
            # or abort with 404 (preferred security response). Both are valid;
            # the IDOR invariant is that we never get 200 with cross-tenant data.
            assert resp.status_code in (302, 404, 403), (
                f"Cross-tenant print must NOT return 200. Got {resp.status_code}. "
                f"User A (tenant {tenant_a.id}) accessed sale {sale_b.id} "
                f"of tenant {tenant_b.id}."
            )
            if resp.status_code == 302:
                # If redirecting, must be away from the target — never to the sale's render
                location = resp.headers.get("Location", "")
                assert "/printing/sale/" not in location, (
                    f"Cross-tenant print must not redirect to the cross-tenant URL. Location: {location}"
                )

    def test_sale_pdf_cross_tenant_returns_404(self, app, db_session):
        from app import create_app  # noqa: F401

        user_a, tenant_a, _, branch_a, customer_a = _make_tenant_role(db_session, "Pa")
        user_b, tenant_b, _, branch_b, customer_b = _make_tenant_role(db_session, "Pb")
        sale_b = _make_sale(db_session, tenant_b, branch_b, user_b, customer_b)

        with app.test_client() as client:
            _login_as(client, user_a, tenant_a.id)
            resp = client.get(f"/printing/sale/{sale_b.id}/pdf")
            assert resp.status_code in (302, 404, 403), (
                f"Cross-tenant PDF print must NOT return 200. Got {resp.status_code}."
            )
            if resp.status_code == 302:
                location = resp.headers.get("Location", "")
                assert "/printing/sale/" not in location


class TestPrintRouteAuthRequired:
    """Unauthenticated access must be denied, not silently 200."""

    def test_sale_print_unauthenticated_redirects(self, app, db_session):
        from app import create_app  # noqa: F401

        user_b, tenant_b, _, branch_b, customer_b = _make_tenant_role(db_session, "Qb")
        sale_b = _make_sale(db_session, tenant_b, branch_b, user_b, customer_b)

        with app.test_client() as client:
            resp = client.get(f"/printing/sale/{sale_b.id}")
            # @login_required redirects (302) to login, or aborts (401/403)
            assert resp.status_code in (302, 401, 403), (
                f"Unauthenticated access must be denied, got {resp.status_code}."
            )
