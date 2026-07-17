"""
Real route tests: Sales routes — HTTP client.get() / client.post() only.
"""

import uuid
from decimal import Decimal


class TestSalesListPage:
    def test_sales_list_page_renders(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer, Sale

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"SL {tid}",
            name_ar=f"SL {tid}",
            slug=f"sl-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"Admin {tid}", slug=f"admin-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"sluser-{tid}",
            email=f"sl-{tid}@t.com",
            full_name="Seller",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()
        customer = Customer(tenant_id=tenant.id, name=f"SL C {tid}")
        db_session.add(customer)
        db_session.flush()
        sale = Sale(
            tenant_id=tenant.id,
            sale_number=f"S-{tid}",
            customer_id=customer.id,
            seller_id=user.id,
            warehouse_id=None,
            branch_id=branch.id,
            currency="AED",
            exchange_rate=Decimal("1"),
            subtotal=Decimal("100"),
            discount_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            tax_rate=Decimal("0"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("100"),
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            paid_amount=Decimal("0"),
            paid_amount_aed=Decimal("0"),
            balance_due=Decimal("100"),
            payment_status="unpaid",
            status="confirmed",
        )
        db_session.add(sale)
        db_session.commit()

        with client:
            resp = client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            assert resp.status_code == 200
            resp = client.get("/sales/")
        assert resp.status_code == 200
        assert sale.sale_number.encode() in resp.data

    def test_sales_create_page_renders(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer, Product

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"SC {tid}",
            name_ar=f"SC {tid}",
            slug=f"sc-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"Admin {tid}", slug=f"admin-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"scuser-{tid}",
            email=f"sc-{tid}@t.com",
            full_name="Seller",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()
        customer = Customer(tenant_id=tenant.id, name=f"SC C {tid}")
        db_session.add(customer)
        db_session.flush()
        product = Product(
            name=f"SC P {tid}",
            sku=f"SC-{tid}",
            tenant_id=tenant.id,
            regular_price=Decimal("50"),
            is_active=True,
        )
        db_session.add(product)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.get("/sales/create")
        assert resp.status_code == 200
        assert b"customer" in resp.data.lower()
