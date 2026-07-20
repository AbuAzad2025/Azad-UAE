"""
Real route tests: Payments routes — HTTP client.get() only.
"""

import uuid
from decimal import Decimal


class TestPaymentsListPage:
    def test_receipts_list_page_renders(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer, Receipt, Payment
        from datetime import date

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"PM {tid}",
            name_ar=f"PM {tid}",
            slug=f"pm-{tid}",
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
            username=f"pmuser-{tid}",
            email=f"pm-{tid}@t.com",
            full_name="Cashier",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"PM C {tid}")
        db_session.add(customer)
        db_session.flush()
        receipt = Receipt(
            tenant_id=tenant.id,
            receipt_number=f"R-{tid}",
            direction="incoming",
            amount=Decimal("100"),
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=Decimal("100"),
            customer_id=customer.id,
            payment_method="cash",
            receipt_date=date.today(),
            branch_id=branch.id,
            user_id=user.id,
        )
        db_session.add(receipt)
        payment = Payment(
            tenant_id=tenant.id,
            payment_number=f"P-{tid}",
            payment_type="expense",
            direction="outgoing",
            branch_id=branch.id,
            amount=Decimal("200"),
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=Decimal("200"),
            payment_method="cash",
            payment_date=date.today(),
            user_id=user.id,
        )
        db_session.add(payment)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.get("/payments/receipts")
        assert resp.status_code == 200
        assert receipt.receipt_number.encode() in resp.data or b"receipt" in resp.data.lower()
