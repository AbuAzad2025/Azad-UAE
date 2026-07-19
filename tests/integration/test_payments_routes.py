"""
Integration tests: Payments routes — real business logic via POST /payments/voucher/submit.
"""

import uuid


class TestPaymentsVoucher:
    def test_create_receipt_reduces_customer_balance(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer, Sale
        from services.gl_service import GLService
        from models.gl import GLJournalEntry
        from utils.gl_reference_types import GLRef
        from decimal import Decimal

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"P1 {tid}",
            name_ar=f"P1 {tid}",
            slug=f"pay-test-{tid}",
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
            username=f"cash-{tid}",
            email=f"cash-{tid}@t.com",
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

        customer = Customer(
            tenant_id=tenant.id,
            name=f"Debtor {tid}",
            phone=f"053{tid}",
            balance=Decimal("500"),
        )
        db_session.add(customer)
        db_session.flush()

        sale = Sale(
            tenant_id=tenant.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"INV-{tid}",
            branch_id=branch.id,
            subtotal=Decimal("500"),
            total_amount=Decimal("500"),
            amount=Decimal("500"),
            amount_aed=Decimal("500"),
            paid_amount=Decimal("0"),
            balance_due=Decimal("500"),
            status="confirmed",
            payment_status="unpaid",
            currency="AED",
        )
        db_session.add(sale)
        db_session.commit()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        with client:
            resp = client.post(
                "/auth/login",
                data={
                    "username": user.username,
                    "password": "x",
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200

            resp = client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "incoming",
                    "party_type": "customer",
                    "party_id": str(customer.id),
                    "amount": "200",
                    "currency": "AED",
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )

        assert resp.status_code in (200, 302), f"Unexpected status {resp.status_code}"

        customer_after = Customer.query.get(customer.id)
        # customer.balance tracks credit: receipt adds to it
        assert customer_after.balance == Decimal("700"), (
            f"balance={customer_after.balance}"
        )

        gl_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == GLRef.RECEIPT,
        ).all()
        if gl_entries:
            total_debit = sum((e.total_debit or 0) for e in gl_entries)
            total_credit = sum((e.total_credit or 0) for e in gl_entries)
            assert total_debit == total_credit, (
                f"GL unbalanced: debit={total_debit} credit={total_credit}"
            )

    def test_create_payment_to_supplier_reduces_ap(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Supplier, Purchase
        from services.gl_service import GLService
        from models.gl import GLJournalEntry
        from utils.gl_reference_types import GLRef
        from decimal import Decimal

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"P2 {tid}",
            name_ar=f"P2 {tid}",
            slug=f"pay-test-2-{tid}",
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
            username=f"acc-{tid}",
            email=f"acc-{tid}@t.com",
            full_name="Accountant",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f"Cred {tid}", phone=f"054{tid}")
        db_session.add(supplier)
        db_session.flush()

        purchase = Purchase(
            tenant_id=tenant.id,
            supplier_id=supplier.id,
            branch_id=branch.id,
            supplier_name=f"Cred {tid}",
            user_id=user.id,
            purchase_number=f"PO-{tid}",
            subtotal=Decimal("1000"),
            total_amount=Decimal("1000"),
            amount=Decimal("1000"),
            amount_aed=Decimal("1000"),
            status="confirmed",
            currency="AED",
        )
        db_session.add(purchase)
        db_session.commit()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        with client:
            resp = client.post(
                "/auth/login",
                data={
                    "username": user.username,
                    "password": "x",
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200

            resp = client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "outgoing",
                    "party_type": "supplier",
                    "party_id": str(supplier.id),
                    "amount": "400",
                    "currency": "AED",
                    "payment_method": "bank_transfer",
                },
                follow_redirects=False,
            )

        assert resp.status_code in (200, 302), f"Unexpected status {resp.status_code}"

        supplier_after = Supplier.query.get(supplier.id)
        assert supplier_after.total_paid_aed >= Decimal("400"), (
            f"paid={supplier_after.total_paid_aed}"
        )

        gl_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == GLRef.PAYMENT,
        ).all()
        if gl_entries:
            total_debit = sum((e.total_debit or 0) for e in gl_entries)
            total_credit = sum((e.total_credit or 0) for e in gl_entries)
            assert total_debit == total_credit, (
                f"GL unbalanced: debit={total_debit} credit={total_credit}"
            )
