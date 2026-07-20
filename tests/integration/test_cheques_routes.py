"""
Integration tests: Cheques routes — full lifecycle (create, deposit, clear, bounce, cancel, delete).
"""

import uuid
from decimal import Decimal
from datetime import date, timedelta


class TestChequesCreate:
    def test_create_incoming_cheque_gl_balanced(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer
        from models.cheque import Cheque
        from models.gl import GLJournalEntry, GLJournalLine
        from models.sale import Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"CHQ1 {tid}",
            name_ar=f"CHQ1 {tid}",
            slug=f"chq1-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"B {tid}", code=f"B{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"chqu-{tid}",
            email=f"chqu-{tid}@t.com",
            full_name="CHQ User",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"C {tid}")
        db_session.add(customer)
        db_session.flush()

        # a Sale in this branch so the branch scope check in _scoped_customers_query passes
        sale = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S-{tid}",
            total_amount=Decimal("5000"),
            amount=Decimal("5000"),
            amount_aed=Decimal("5000"),
        )
        db_session.add(sale)

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        today_str = date.today().isoformat()
        due_str = (date.today() + timedelta(days=30)).isoformat()

        with client:
            resp = client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            assert resp.status_code == 200

            resp = client.post(
                "/cheques/create",
                data={
                    "cheque_type": "incoming",
                    "cheque_bank_number": f"BNK-{tid}",
                    "bank_name": "Test Bank",
                    "amount": "5000.00",
                    "currency": "AED",
                    "issue_date": today_str,
                    "due_date": due_str,
                    "customer_id": str(customer.id),
                    "drawer_name": "John Doe",
                },
                follow_redirects=False,
            )

        assert resp.status_code in (200, 302), f"Unexpected: {resp.status_code}"
        cheque = Cheque.query.filter_by(cheque_bank_number=f"BNK-{tid}").first()
        assert cheque is not None, "Cheque not created"
        assert cheque.cheque_type == "incoming"
        assert cheque.status == "pending"
        assert cheque.amount == Decimal("5000.00")
        assert cheque.amount_aed == Decimal("5000.00")
        assert cheque.customer_id == customer.id

        gl_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == "ChequeReceive",
            GLJournalEntry.reference_id == cheque.id,
        ).all()
        assert len(gl_entries) >= 1
        total_debit = sum((e.total_debit or 0) for e in gl_entries)
        total_credit = sum((e.total_credit or 0) for e in gl_entries)
        assert total_debit == total_credit, f"GL unbalanced: {total_debit} vs {total_credit}"
        assert total_debit == Decimal("5000.00")

        lines = (
            GLJournalLine.query.join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(
                GLJournalEntry.reference_type == "ChequeReceive",
                GLJournalEntry.reference_id == cheque.id,
            )
            .all()
        )
        assert len(lines) >= 2
        accounts = [(line.account.code, line.debit or 0, line.credit or 0) for line in lines]
        has_cuc = any("1150" in str(acc) and d > 0 for acc, d, c in accounts)
        has_ar = any(c > 0 for acc, d, c in accounts if c > 0)
        assert has_cuc, f"Expected Dr ChequesUnderCollection, got {accounts}"
        assert has_ar, f"Expected Cr AR, got {accounts}"

    def test_create_outgoing_cheque_gl_balanced(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Supplier
        from models.cheque import Cheque
        from models.gl import GLJournalEntry, GLJournalLine
        from models.purchase import Purchase
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"CHQ2 {tid}",
            name_ar=f"CHQ2 {tid}",
            slug=f"chq2-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"B {tid}", code=f"B{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"chqu2-{tid}",
            email=f"chqu2-{tid}@t.com",
            full_name="CHQ User 2",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        supplier = Supplier(
            tenant_id=tenant.id,
            name=f"S {tid}",
            total_purchases_aed=Decimal("0"),
            total_paid_aed=Decimal("0"),
        )
        db_session.add(supplier)
        db_session.flush()

        purchase = Purchase(
            tenant_id=tenant.id,
            branch_id=branch.id,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            user_id=user.id,
            purchase_number=f"P-{tid}",
            total_amount=Decimal("3000"),
            amount=Decimal("3000"),
            amount_aed=Decimal("3000"),
        )
        db_session.add(purchase)

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        today_str = date.today().isoformat()
        due_str = (date.today() + timedelta(days=30)).isoformat()

        with client:
            resp = client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            assert resp.status_code == 200

            resp = client.post(
                "/cheques/create",
                data={
                    "cheque_type": "outgoing",
                    "cheque_bank_number": f"BNK2-{tid}",
                    "bank_name": "Test Bank",
                    "amount": "3000.00",
                    "currency": "AED",
                    "issue_date": today_str,
                    "due_date": due_str,
                    "supplier_id": str(supplier.id),
                    "payee_name": "Supplier Corp",
                },
                follow_redirects=False,
            )

        assert resp.status_code in (200, 302)
        cheque = Cheque.query.filter_by(cheque_bank_number=f"BNK2-{tid}").first()
        assert cheque is not None
        assert cheque.cheque_type == "outgoing"
        assert cheque.status == "pending"
        assert cheque.amount == Decimal("3000.00")

        gl_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == "ChequeIssue",
            GLJournalEntry.reference_id == cheque.id,
        ).all()
        assert len(gl_entries) >= 1
        total_debit = sum((e.total_debit or 0) for e in gl_entries)
        total_credit = sum((e.total_credit or 0) for e in gl_entries)
        assert total_debit == total_credit
        assert total_debit == Decimal("3000.00")

        lines = (
            GLJournalLine.query.join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(
                GLJournalEntry.reference_type == "ChequeIssue",
                GLJournalEntry.reference_id == cheque.id,
            )
            .all()
        )
        accounts = [(line.account.code, line.debit or 0, line.credit or 0) for line in lines]
        has_deferred = any("2130" in str(acc) and c > 0 for acc, d, c in accounts)
        assert has_deferred, f"Expected Cr DeferredCheques, got {accounts}"


class TestChequesLifecycle:
    def test_incoming_cheque_full_lifecycle_gl_balanced(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer
        from models.cheque import Cheque
        from models.gl import GLJournalEntry
        from models.sale import Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"CHQ3 {tid}",
            name_ar=f"CHQ3 {tid}",
            slug=f"chq3-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"B {tid}", code=f"B{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"chqu3-{tid}",
            email=f"chqu3-{tid}@t.com",
            full_name="CHQ User 3",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"C3 {tid}")
        db_session.add(customer)
        db_session.flush()

        sale = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S3-{tid}",
            total_amount=Decimal("8000"),
            amount=Decimal("8000"),
            amount_aed=Decimal("8000"),
        )
        db_session.add(sale)

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        today_str = date.today().isoformat()
        due_str = (date.today() + timedelta(days=30)).isoformat()

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )

            resp = client.post(
                "/cheques/create",
                data={
                    "cheque_type": "incoming",
                    "cheque_bank_number": f"BNK3-{tid}",
                    "bank_name": "Test Bank",
                    "amount": "8000.00",
                    "currency": "AED",
                    "issue_date": today_str,
                    "due_date": due_str,
                    "customer_id": str(customer.id),
                    "drawer_name": "John Doe",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)
        cheque = Cheque.query.filter_by(cheque_bank_number=f"BNK3-{tid}").first()
        assert cheque is not None
        cheque_id = cheque.id

        with client:
            resp = client.post(
                f"/cheques/{cheque_id}/deposit",
                data={
                    "deposit_date": today_str,
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)
        cheque = Cheque.query.get(cheque_id)
        assert cheque.status == "deposited"

        with client:
            resp = client.post(
                f"/cheques/{cheque_id}/clear",
                data={
                    "clearance_date": today_str,
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)
        cheque = Cheque.query.get(cheque_id)
        assert cheque.status == "cleared"

        gl_entries = (
            GLJournalEntry.query.filter(
                GLJournalEntry.reference_id == cheque.id,
            )
            .order_by(GLJournalEntry.id)
            .all()
        )
        assert len(gl_entries) >= 2

        total_debit_all = sum((e.total_debit or 0) for e in gl_entries)
        total_credit_all = sum((e.total_credit or 0) for e in gl_entries)
        assert total_debit_all == total_credit_all, f"Total GL unbalanced: {total_debit_all} vs {total_credit_all}"

        receive_entry = next((e for e in gl_entries if e.reference_type == "ChequeReceive"), None)
        assert receive_entry is not None
        assert receive_entry.total_debit == Decimal("8000.00")

        clearing_entry = next((e for e in gl_entries if e.reference_type == "ChequeClear"), None)
        assert clearing_entry is not None
        assert clearing_entry.total_debit == Decimal("8000.00")

    def test_incoming_cheque_bounce_reverses_gl(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer
        from models.cheque import Cheque
        from models.gl import GLJournalEntry, GLJournalLine
        from models.sale import Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"CHQ4 {tid}",
            name_ar=f"CHQ4 {tid}",
            slug=f"chq4-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"B {tid}", code=f"B{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"chqu4-{tid}",
            email=f"chqu4-{tid}@t.com",
            full_name="CHQ User 4",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"C4 {tid}")
        db_session.add(customer)
        db_session.flush()

        sale = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S4-{tid}",
            total_amount=Decimal("2000"),
            amount=Decimal("2000"),
            amount_aed=Decimal("2000"),
        )
        db_session.add(sale)

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        today_str = date.today().isoformat()
        due_str = (date.today() + timedelta(days=30)).isoformat()

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.post(
                "/cheques/create",
                data={
                    "cheque_type": "incoming",
                    "cheque_bank_number": f"BNK4-{tid}",
                    "bank_name": "Test Bank",
                    "amount": "2000.00",
                    "currency": "AED",
                    "issue_date": today_str,
                    "due_date": due_str,
                    "customer_id": str(customer.id),
                    "drawer_name": "John Doe",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)
        cheque = Cheque.query.filter_by(cheque_bank_number=f"BNK4-{tid}").first()
        assert cheque is not None

        with client:
            resp = client.post(
                f"/cheques/{cheque.id}/deposit",
                data={
                    "deposit_date": today_str,
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

        with client:
            resp = client.post(
                f"/cheques/{cheque.id}/bounce",
                data={
                    "bounce_reason": "Insufficient funds",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)
        cheque = Cheque.query.get(cheque.id)
        assert cheque.status == "bounced"
        assert "Insufficient funds" in (cheque.bounce_reason or "")

        bounce_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == "ChequeBounce",
            GLJournalEntry.reference_id == cheque.id,
        ).all()
        assert len(bounce_entries) >= 1
        total_debit = sum((e.total_debit or 0) for e in bounce_entries)
        total_credit = sum((e.total_credit or 0) for e in bounce_entries)
        assert total_debit == total_credit
        assert total_debit == Decimal("2000.00")

        lines = (
            GLJournalLine.query.join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(
                GLJournalEntry.reference_type == "ChequeBounce",
                GLJournalEntry.reference_id == cheque.id,
            )
            .all()
        )
        accounts = [(line.account.code, line.debit or 0, line.credit or 0) for line in lines]
        has_ar_debit = any("1130" in str(acc) and d > 0 for acc, d, c in accounts)
        has_cuc_credit = any("1150" in str(acc) and c > 0 for acc, d, c in accounts)
        assert has_ar_debit, f"Expected Dr AR on bounce, got {accounts}"
        assert has_cuc_credit, f"Expected Cr CUC on bounce, got {accounts}"


class TestChequesViewEdit:
    def test_cheque_list_page_renders(self, app, db_session, client):
        from models import Tenant, Branch, User, Role

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"CHQ5 {tid}",
            name_ar=f"CHQ5 {tid}",
            slug=f"chq5-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"B {tid}", code=f"B{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"chqv-{tid}",
            email=f"chqv-{tid}@t.com",
            full_name="CHQ View",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.get("/cheques/")
        assert resp.status_code == 200
        assert b"cheque" in resp.data.lower() or b"chq" in resp.data.lower() or "شيك".encode("utf-8") in resp.data

    def test_cheque_create_page_renders(self, app, db_session, client):
        from models import Tenant, Branch, User, Role

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"CHQ6 {tid}",
            name_ar=f"CHQ6 {tid}",
            slug=f"chq6-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"B {tid}", code=f"B{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"chqc-{tid}",
            email=f"chqc-{tid}@t.com",
            full_name="CHQ Create",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.get("/cheques/create")
        assert resp.status_code == 200

    def test_cheque_view_page_renders(self, app, db_session, client):
        from models import Tenant, Branch, User, Role
        from models.cheque import Cheque

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"CHQ7 {tid}",
            name_ar=f"CHQ7 {tid}",
            slug=f"chq7-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"B {tid}", code=f"B{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"chqvw-{tid}",
            email=f"chqvw-{tid}@t.com",
            full_name="CHQ View2",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        cheque = Cheque(
            tenant_id=tenant.id,
            branch_id=branch.id,
            user_id=user.id,
            cheque_number=f"CHQ-{tid}",
            cheque_bank_number=f"BNK-V-{tid}",
            cheque_type="incoming",
            bank_name="Test Bank",
            amount=Decimal("1000.00"),
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=Decimal("1000.00"),
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            drawer_name="John",
            status="pending",
        )
        db_session.add(cheque)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.get(f"/cheques/{cheque.id}")
        assert resp.status_code == 200
        assert b"BNK-V-" in resp.data or b"1000" in resp.data or b"John" in resp.data

    def test_edit_cheque_updates_cheque(self, app, db_session, client):
        from models import Tenant, Branch, User, Role
        from models.cheque import Cheque

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"CHQ8 {tid}",
            name_ar=f"CHQ8 {tid}",
            slug=f"chq8-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"B {tid}", code=f"B{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"chqe-{tid}",
            email=f"chqe-{tid}@t.com",
            full_name="CHQ Edit",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        cheque = Cheque(
            tenant_id=tenant.id,
            branch_id=branch.id,
            user_id=user.id,
            cheque_number=f"CHQ-E-{tid}",
            cheque_bank_number=f"BNK-E-{tid}",
            cheque_type="incoming",
            bank_name="Old Bank",
            amount=Decimal("1000.00"),
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=Decimal("1000.00"),
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            drawer_name="Old",
            status="pending",
        )
        db_session.add(cheque)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.post(
                f"/cheques/{cheque.id}/edit",
                data={
                    "cheque_bank_number": f"BNK-E-{tid}",
                    "bank_name": "New Bank",
                    "amount": "2000.00",
                    "currency": "AED",
                    "issue_date": date.today().isoformat(),
                    "due_date": (date.today() + timedelta(days=60)).isoformat(),
                    "drawer_name": "New Drawer",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)
        cheque = Cheque.query.get(cheque.id)
        assert cheque.bank_name == "New Bank"
        assert cheque.amount == Decimal("2000.00")
        assert cheque.drawer_name == "New Drawer"


class TestChequesDelete:
    def test_archive_cheque_with_links_soft_deletes(self, app, db_session, client):
        from models import Tenant, Branch, User, Role
        from models.cheque import Cheque
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"CHQ9 {tid}",
            name_ar=f"CHQ9 {tid}",
            slug=f"chq9-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"B {tid}", code=f"B{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"chqdel-{tid}",
            email=f"chqdel-{tid}@t.com",
            full_name="CHQ Del",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        today_str = date.today().isoformat()
        due_str = (date.today() + timedelta(days=30)).isoformat()

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.post(
                "/cheques/create",
                data={
                    "cheque_type": "incoming",
                    "cheque_bank_number": f"BNK-DEL-{tid}",
                    "bank_name": "Test Bank",
                    "amount": "1500.00",
                    "currency": "AED",
                    "issue_date": today_str,
                    "due_date": due_str,
                    "drawer_name": "John",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

        cheque = Cheque.query.filter_by(cheque_bank_number=f"BNK-DEL-{tid}").first()
        assert cheque is not None
        assert cheque.status == "pending"
        cheque.status = "deposited"
        db_session.commit()

        with client:
            resp = client.post(
                f"/cheques/{cheque.id}/delete",
                data={
                    "delete_reason": "Deleted for testing",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

        cheque = Cheque.query.get(cheque.id)
        assert cheque is not None, "Cheque should still exist (soft-deleted)"
        assert cheque.is_active is False, "Cheque should be soft-deleted"
        assert "testing" in (cheque.archive_reason or "")


class TestChequesApi:
    def test_api_stats_returns_json(self, app, db_session, client):
        from models import Tenant, Branch, User, Role

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"CHQA {tid}",
            name_ar=f"CHQA {tid}",
            slug=f"chqa-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()
        branch = Branch(tenant_id=tenant.id, name=f"B {tid}", code=f"B{tid[:4]}")
        db_session.add(branch)
        db_session.flush()
        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()
        user = User(
            username=f"chqapi-{tid}",
            email=f"chqapi-{tid}@t.com",
            full_name="CHQ API",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.commit()

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            resp = client.get("/cheques/api/stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None
        assert "total_incoming" in data
        assert "total_outgoing" in data
        assert isinstance(data["total_incoming"], int)
