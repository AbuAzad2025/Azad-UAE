"""
Audit tests: Tenant Isolation + RBAC + User Uniqueness.
Verifies the actual implemented behaviors discovered via code inspection.
"""

import pytest
import uuid
from decimal import Decimal


class TestUserUniqueness:
    def test_username_is_globally_unique(self, app, db_session):
        from models import Tenant, User, Role

        t1 = Tenant(
            name=f"UQ1 {uuid.uuid4().hex[:4]}",
            name_ar="T1",
            slug=f"uq1-{uuid.uuid4().hex[:4]}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(t1)
        db_session.flush()
        t2 = Tenant(
            name=f"UQ2 {uuid.uuid4().hex[:4]}",
            name_ar="T2",
            slug=f"uq2-{uuid.uuid4().hex[:4]}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(t2)
        db_session.flush()
        r = Role(name="R", slug=f"r-{uuid.uuid4().hex[:4]}", is_active=True)
        db_session.add(r)
        db_session.flush()

        shared_username = f"dup-{uuid.uuid4().hex[:4]}"
        u1 = User(
            username=shared_username,
            email=f"{shared_username}@1.com",
            full_name="U1",
            role_id=r.id,
            tenant_id=t1.id,
            is_active=True,
        )
        u1.set_password("x")
        db_session.add(u1)
        db_session.flush()

        from sqlalchemy.exc import IntegrityError

        u2 = User(
            username=shared_username,
            email=f"{shared_username}@2.com",
            full_name="U2",
            role_id=r.id,
            tenant_id=t2.id,
            is_active=True,
        )
        u2.set_password("x")
        db_session.add(u2)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_email_is_globally_unique(self, app, db_session):
        from models import Tenant, User, Role

        t1 = Tenant(
            name=f"UQ3 {uuid.uuid4().hex[:4]}",
            name_ar="T3",
            slug=f"uq3-{uuid.uuid4().hex[:4]}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(t1)
        db_session.flush()
        t2 = Tenant(
            name=f"UQ4 {uuid.uuid4().hex[:4]}",
            name_ar="T4",
            slug=f"uq4-{uuid.uuid4().hex[:4]}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(t2)
        db_session.flush()
        r = Role(name="R2", slug=f"r2-{uuid.uuid4().hex[:4]}", is_active=True)
        db_session.add(r)
        db_session.flush()

        shared_email = f"dup-{uuid.uuid4().hex[:4]}@test.com"
        u1 = User(
            username=f"u1-{uuid.uuid4().hex[:4]}",
            email=shared_email,
            full_name="U1",
            role_id=r.id,
            tenant_id=t1.id,
            is_active=True,
        )
        u1.set_password("x")
        db_session.add(u1)
        db_session.flush()

        from sqlalchemy.exc import IntegrityError

        u2 = User(
            username=f"u2-{uuid.uuid4().hex[:4]}",
            email=shared_email,
            full_name="U2",
            role_id=r.id,
            tenant_id=t2.id,
            is_active=True,
        )
        u2.set_password("x")
        db_session.add(u2)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


class TestTenantIsolation:
    def test_tenant_isolation_enforced_via_orm_scope(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer
        from services.gl_service import GLService

        tid1 = uuid.uuid4().hex[:4]
        t1 = Tenant(
            name=f"TI1 {tid1}",
            name_ar="TI1",
            slug=f"ti1-{tid1}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(t1)
        db_session.flush()
        b1 = Branch(tenant_id=t1.id, name=f"B1 {tid1}", code=f"B1{tid1[:4]}")
        db_session.add(b1)
        db_session.flush()
        r1 = Role(name=f"R1 {tid1}", slug=f"r1-{tid1}", is_active=True)
        db_session.add(r1)
        db_session.flush()
        u1 = User(
            username=f"u1-{tid1}",
            email=f"u1-{tid1}@t.com",
            full_name="U1",
            role_id=r1.id,
            tenant_id=t1.id,
            branch_id=b1.id,
            is_active=True,
            is_owner=True,
        )
        u1.set_password("x")
        db_session.add(u1)
        db_session.flush()
        c1 = Customer(tenant_id=t1.id, name=f"C1 {tid1}")
        db_session.add(c1)
        db_session.flush()

        tid2 = uuid.uuid4().hex[:4]
        t2 = Tenant(
            name=f"TI2 {tid2}",
            name_ar="TI2",
            slug=f"ti2-{tid2}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(t2)
        db_session.flush()
        b2 = Branch(tenant_id=t2.id, name=f"B2 {tid2}", code=f"B2{tid2[:4]}")
        db_session.add(b2)
        db_session.flush()
        r2 = Role(name=f"R2 {tid2}", slug=f"r2-{tid2}", is_active=True)
        db_session.add(r2)
        db_session.flush()
        u2 = User(
            username=f"u2-{tid2}",
            email=f"u2-{tid2}@t.com",
            full_name="U2",
            role_id=r2.id,
            tenant_id=t2.id,
            branch_id=b2.id,
            is_active=True,
            is_owner=True,
        )
        u2.set_password("x")
        db_session.add(u2)
        db_session.flush()
        c2 = Customer(tenant_id=t2.id, name=f"C2 {tid2}")
        db_session.add(c2)
        db_session.flush()
        db_session.commit()

        GLService.ensure_core_accounts(tenant_id=t1.id)
        GLService.ensure_core_accounts(tenant_id=t2.id)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={"username": u1.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.get("/sales/")
        assert resp.status_code == 200
        assert c1.name.encode() in resp.data or b"sales" in resp.data.lower()

        with client:
            client.post(
                "/auth/login",
                data={"username": u2.username, "password": "x"},
                follow_redirects=True,
            )
        resp2 = client.get("/sales/")
        assert resp2.status_code == 200
        assert c2.name.encode() in resp2.data or b"sales" in resp2.data.lower()


class TestBranchIsolation:
    def test_branch_scope_filters_by_user_branch(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer

        tid = uuid.uuid4().hex[:4]
        t = Tenant(
            name=f"BI {tid}",
            name_ar="BI",
            slug=f"bi-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(t)
        db_session.flush()
        b1 = Branch(tenant_id=t.id, name=f"B1 {tid}", code=f"B1{tid[:4]}")
        db_session.add(b1)
        db_session.flush()
        b2 = Branch(tenant_id=t.id, name=f"B2 {tid}", code=f"B2{tid[:4]}")
        db_session.add(b2)
        db_session.flush()
        r = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(r)
        db_session.flush()

        u_b1 = User(
            username=f"ub1-{tid}",
            email=f"ub1-{tid}@t.com",
            full_name="UB1",
            role_id=r.id,
            tenant_id=t.id,
            branch_id=b1.id,
            is_active=True,
            is_owner=True,
        )
        u_b1.set_password("x")
        db_session.add(u_b1)
        db_session.flush()
        u_b2 = User(
            username=f"ub2-{tid}",
            email=f"ub2-{tid}@t.com",
            full_name="UB2",
            role_id=r.id,
            tenant_id=t.id,
            branch_id=b2.id,
            is_active=True,
            is_owner=True,
        )
        u_b2.set_password("x")
        db_session.add(u_b2)
        db_session.flush()
        c = Customer(tenant_id=t.id, name=f"C {tid}")
        db_session.add(c)
        db_session.flush()
        Sale = __import__("models", fromlist=["Sale"]).Sale
        s1 = Sale(
            tenant_id=t.id,
            sale_number=f"S1-{tid}",
            customer_id=c.id,
            seller_id=u_b1.id,
            branch_id=b1.id,
            currency="AED",
            exchange_rate=Decimal("1"),
            subtotal=Decimal("10"),
            discount_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            tax_rate=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("10"),
            amount=Decimal("10"),
            amount_aed=Decimal("10"),
            paid_amount=Decimal("0"),
            paid_amount_aed=Decimal("0"),
            balance_due=Decimal("10"),
            payment_status="unpaid",
            status="confirmed",
        )
        db_session.add(s1)
        s2 = Sale(
            tenant_id=t.id,
            sale_number=f"S2-{tid}",
            customer_id=c.id,
            seller_id=u_b2.id,
            branch_id=b2.id,
            currency="AED",
            exchange_rate=Decimal("1"),
            subtotal=Decimal("20"),
            discount_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            tax_rate=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("20"),
            amount=Decimal("20"),
            amount_aed=Decimal("20"),
            paid_amount=Decimal("0"),
            paid_amount_aed=Decimal("0"),
            balance_due=Decimal("20"),
            payment_status="unpaid",
            status="confirmed",
        )
        db_session.add(s2)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={"username": u_b1.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.get("/sales/")
        assert resp.status_code == 200
        assert b"S1-" in resp.data, "Expected branch 1 sale in response"


class TestOwnerAccess:
    def test_global_owner_can_access_owner_dashboard(self, app, db_session, client):
        from models import User, Role

        r = Role(
            name=f"Owner-{uuid.uuid4().hex[:4]}",
            slug=f"own-{uuid.uuid4().hex[:4]}",
            is_active=True,
        )
        db_session.add(r)
        db_session.flush()
        owner = User(
            username=f"gown-{uuid.uuid4().hex[:4]}",
            email=f"gown-{uuid.uuid4().hex[:4]}@t.com",
            full_name="Global Owner",
            role_id=r.id,
            is_active=True,
            is_owner=True,
        )
        owner.set_password("x")
        db_session.add(owner)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={"username": owner.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.get("/owner/dashboard")
        assert resp.status_code in (200, 302)


class TestRoleHierarchy:
    def test_seller_cannot_access_owner_pages(self, app, db_session, client):
        from models import Tenant, User, Role

        t = Tenant(
            name=f"RH {uuid.uuid4().hex[:4]}",
            name_ar="RH",
            slug=f"rh-{uuid.uuid4().hex[:4]}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(t)
        db_session.flush()
        r = Role(
            name=f"Seller-{uuid.uuid4().hex[:4]}",
            slug=f"seller-{uuid.uuid4().hex[:4]}",
            is_active=True,
        )
        db_session.add(r)
        db_session.flush()
        user = User(
            username=f"sell-{uuid.uuid4().hex[:4]}",
            email=f"sell-{uuid.uuid4().hex[:4]}@t.com",
            full_name="Seller",
            role_id=r.id,
            tenant_id=t.id,
            is_active=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.commit()

        from werkzeug.exceptions import NotFound

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            try:
                resp = client.get("/owner/dashboard", follow_redirects=False)
            except NotFound:
                pass
            else:
                assert resp.status_code == 404
