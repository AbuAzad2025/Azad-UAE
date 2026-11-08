"""Integration: statutory e-invoice routes + artifact wiring on posted sales."""

import uuid
from decimal import Decimal

from models import Branch, Customer, Product, Role, Sale, SaleLine, Tenant, User


def _make_admin(db_session, tid, slug):
    role = Role(name=f"Admin {slug}", slug=f"admin-{slug}", is_active=True)
    db_session.add(role)
    db_session.flush()
    branch = Branch(tenant_id=tid, name=f"Main {slug}", code=f"BR{slug[:4]}")
    db_session.add(branch)
    db_session.flush()
    user = User(
        username=f"admin-{slug}",
        email=f"admin-{slug}@example.test",
        full_name="Admin",
        role_id=role.id,
        tenant_id=tid,
        branch_id=branch.id,
        is_active=True,
        is_owner=True,
    )
    user.set_password("x")
    db_session.add(user)
    db_session.flush()
    return user, branch


def _make_sale(db_session, tenant, branch, user, sale_number="EINV-1"):
    product = Product(tenant_id=tenant.id, name="Widget", regular_price=Decimal("1000"))
    db_session.add(product)
    customer = Customer(tenant_id=tenant.id, name="Buyer", phone="0500000000")
    db_session.add(customer)
    db_session.flush()
    sale = Sale(
        tenant_id=tenant.id,
        customer_id=customer.id,
        seller_id=user.id,
        sale_number=sale_number,
        branch_id=branch.id,
        currency="AED",
        base_currency="AED",
        amount=Decimal("1050"),
        amount_aed=Decimal("1050"),
        subtotal=Decimal("1000"),
        tax_rate=Decimal("5"),
        tax_amount=Decimal("50"),
        taxable_amount=Decimal("1000"),
        total_amount=Decimal("1050"),
    )
    db_session.add(sale)
    db_session.flush()
    line = SaleLine(
        tenant_id=tenant.id,
        sale_id=sale.id,
        product_id=product.id,
        quantity=Decimal("1"),
        unit_price=Decimal("1000"),
        line_total=Decimal("1000"),
    )
    db_session.add(line)
    db_session.flush()
    return sale


class TestEInvoiceRoutes:
    def test_posted_sale_produces_and_serves_statutory_xml(self, app, db_session, client):
        tid = uuid.uuid4().hex[:6]
        tenant = Tenant(
            name=f"EINV {tid}",
            name_ar=f"EINV {tid}",
            slug=f"einv-{tid}",
            default_currency="AED",
            base_currency="AED",
            vat_country="AE",
        )
        db_session.add(tenant)
        db_session.flush()
        user, branch = _make_admin(db_session, tenant.id, tid)
        sale = _make_sale(db_session, tenant, branch, user)

        from services.einvoice_service import EInvoiceService

        row = EInvoiceService.generate_for_sale(sale)
        assert row is not None
        assert row.format == "fta_ubl_xml"

        db_session.commit()
        with client:
            resp = client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            assert resp.status_code == 200

            resp = client.get(f"/sales/{sale.id}/einvoice.xml")
            assert resp.status_code == 200
            assert resp.headers["Content-Type"].startswith("application/xml")
            body = resp.get_data(as_text=True)
            assert "<cbc:ID>EINV-1</cbc:ID>" in body

            # No QR for AE — the FTA has not mandated one; expect 404.
            resp = client.get(f"/sales/{sale.id}/einvoice-qr.png")
            assert resp.status_code == 404

    def test_einvoice_routes_are_tenant_scoped(self, app, db_session, client):
        tid_a = uuid.uuid4().hex[:6]
        tid_b = uuid.uuid4().hex[:6]
        tenant_a = Tenant(
            name=f"AINV {tid_a}",
            name_ar=f"AINV {tid_a}",
            slug=f"ainv-{tid_a}",
            default_currency="AED",
            base_currency="AED",
            vat_country="AE",
        )
        tenant_b = Tenant(
            name=f"BINV {tid_b}",
            name_ar=f"BINV {tid_b}",
            slug=f"binv-{tid_b}",
            default_currency="AED",
            base_currency="AED",
            vat_country="AE",
        )
        db_session.add_all([tenant_a, tenant_b])
        db_session.flush()
        user_a, branch_a = _make_admin(db_session, tenant_a.id, f"a{tid_a}")
        user_b, branch_b = _make_admin(db_session, tenant_b.id, f"b{tid_b}")
        sale = _make_sale(db_session, tenant_a, branch_a, user_a, sale_number="EINV-A1")

        from services.einvoice_service import EInvoiceService

        EInvoiceService.generate_for_sale(sale)
        db_session.commit()
        with client:
            resp = client.post(
                "/auth/login",
                data={"username": user_b.username, "password": "x"},
                follow_redirects=True,
            )
            assert resp.status_code == 200
            resp = client.get(f"/sales/{sale.id}/einvoice.xml")
            assert resp.status_code in (302, 403, 404), f"foreign tenant reached the document: {resp.status_code}"

    def test_missing_artifact_is_a_404(self, app, db_session, client):
        tid = uuid.uuid4().hex[:6]
        tenant = Tenant(
            name=f"MINV {tid}",
            name_ar=f"MINV {tid}",
            slug=f"minv-{tid}",
            default_currency="AED",
            base_currency="AED",
            vat_country="AE",
        )
        db_session.add(tenant)
        db_session.flush()
        user, branch = _make_admin(db_session, tenant.id, tid)
        sale = _make_sale(db_session, tenant, branch, user, sale_number="EINV-M1")
        db_session.commit()
        with client:
            resp = client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            assert resp.status_code == 200
            resp = client.get(f"/sales/{sale.id}/einvoice.xml")
            assert resp.status_code == 404
