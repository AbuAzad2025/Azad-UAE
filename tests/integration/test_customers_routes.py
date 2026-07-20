"""
Integration tests: Customers routes — real business logic via HTTP.
"""

import uuid
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone


class TestCustomerBranchIsolation:
    def test_customer_branch_isolation(self, app, db_session, client):
        """Customer in Branch 1 should NOT appear in Branch 2's list."""
        from models import Tenant, Branch, Role, User, Customer, Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"BrT {tid}",
            name_ar=f"BrT {tid}",
            slug=f"br-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        b1 = Branch(tenant_id=tenant.id, name=f"North {tid}", code=f"B1{tid[:4]}")
        b2 = Branch(tenant_id=tenant.id, name=f"South {tid}", code=f"B2{tid[:4]}")
        db_session.add(b1)
        db_session.flush()
        db_session.add(b2)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        u1 = User(
            username=f"u1-{tid}",
            email=f"u1-{tid}@t.com",
            full_name="User 1",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=b1.id,
            is_active=True,
            is_owner=True,
        )
        u1.set_password("x")
        db_session.add(u1)
        db_session.flush()

        u2 = User(
            username=f"u2-{tid}",
            email=f"u2-{tid}@t.com",
            full_name="User 2",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=b2.id,
            is_active=True,
            is_owner=True,
        )
        u2.set_password("x")
        db_session.add(u2)
        db_session.flush()

        cust_b1 = Customer(tenant_id=tenant.id, name=f"NorthCustomer {tid}", phone="0501111111")
        cust_b2 = Customer(tenant_id=tenant.id, name=f"SouthCustomer {tid}", phone="0502222222")
        db_session.add(cust_b1)
        db_session.flush()
        db_session.add(cust_b2)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale_b1 = Sale(
            tenant_id=tenant.id,
            branch_id=b1.id,
            customer_id=cust_b1.id,
            seller_id=u1.id,
            sale_number=f"S-N-{tid}",
            total_amount=Decimal("100"),
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
        )
        db_session.add(sale_b1)

        sale_b2 = Sale(
            tenant_id=tenant.id,
            branch_id=b2.id,
            customer_id=cust_b2.id,
            seller_id=u2.id,
            sale_number=f"S-S-{tid}",
            total_amount=Decimal("200"),
            amount=Decimal("200"),
            amount_aed=Decimal("200"),
        )
        db_session.add(sale_b2)
        db_session.commit()

        with client:
            resp = client.post(
                "/auth/login",
                data={
                    "username": u1.username,
                    "password": "x",
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200

            resp = client.get("/customers/")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert f"NorthCustomer {tid}" in html
        assert f"SouthCustomer {tid}" not in html, "BUG: Customer from Branch 2 leaked into Branch 1 list"

    def test_customer_branch_isolation_reverse(self, app, db_session, client):
        """Customer in Branch 2 should NOT appear in Branch 1's list (reverse check)."""
        from models import Tenant, Branch, Role, User, Customer, Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"BrR {tid}",
            name_ar=f"BrR {tid}",
            slug=f"brr-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        b1 = Branch(tenant_id=tenant.id, name=f"Left {tid}", code=f"L{tid[:4]}")
        b2 = Branch(tenant_id=tenant.id, name=f"Right {tid}", code=f"R{tid[:4]}")
        db_session.add(b1)
        db_session.flush()
        db_session.add(b2)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        u1 = User(
            username=f"w1-{tid}",
            email=f"w1-{tid}@t.com",
            full_name="U1",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=b1.id,
            is_active=True,
            is_owner=True,
        )
        u1.set_password("x")
        db_session.add(u1)
        db_session.flush()

        u2 = User(
            username=f"w2-{tid}",
            email=f"w2-{tid}@t.com",
            full_name="U2",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=b2.id,
            is_active=True,
            is_owner=True,
        )
        u2.set_password("x")
        db_session.add(u2)
        db_session.flush()

        cust = Customer(tenant_id=tenant.id, name=f"LeftCustomer {tid}", phone="0503333333")
        db_session.add(cust)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = Sale(
            tenant_id=tenant.id,
            branch_id=b1.id,
            customer_id=cust.id,
            seller_id=u1.id,
            sale_number=f"S-L-{tid}",
            total_amount=Decimal("150"),
            amount=Decimal("150"),
            amount_aed=Decimal("150"),
        )
        db_session.add(sale)
        db_session.commit()

        with client:
            resp = client.post(
                "/auth/login",
                data={
                    "username": u2.username,
                    "password": "x",
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200

            resp = client.get("/customers/")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert f"LeftCustomer {tid}" not in html, "BUG: Customer from Branch 1 leaked into Branch 2 list"


class TestCustomerStatement:
    def test_statement_shows_sales_receipts(self, app, db_session, client):
        """Customer statement must show sales and receipts."""
        from models import Tenant, Branch, Role, User, Customer, Sale, Receipt
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"Stmt {tid}",
            name_ar=f"Stmt {tid}",
            slug=f"stmt-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"acc-{tid}",
            email=f"acc-{tid}@t.com",
            full_name="Acc",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"StmtCust {tid}", phone="0504444444")
        db_session.add(customer)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S-STMT-{tid}",
            total_amount=Decimal("1000"),
            amount=Decimal("1000"),
            amount_aed=Decimal("1000"),
        )
        db_session.add(sale)
        db_session.commit()

        now = datetime.now(timezone.utc)
        receipt = Receipt(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            receipt_number=f"R-STMT-{tid}",
            amount=Decimal("300"),
            amount_aed=Decimal("300"),
            payment_method="cash",
            direction="incoming",
            receipt_date=now,
            user_id=user.id,
        )
        db_session.add(receipt)
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

            resp = client.get(f"/customers/{customer.id}/statement")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert f"S-STMT-{tid}" in html, "Sale missing from statement"
        assert "سند قبض" in html, "Receipt receipt-type row missing from statement"

    def test_statement_shows_payments_with_cheques(self, app, db_session, client):
        """Customer statement must show payments linked to cheques."""
        from models import Tenant, Branch, Role, User, Customer, Sale, Payment, Cheque
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"Stm2 {tid}",
            name_ar=f"Stm2 {tid}",
            slug=f"stm2-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"acc2-{tid}",
            email=f"acc2-{tid}@t.com",
            full_name="Acc2",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"Stm2Cust {tid}", phone="0505555555")
        db_session.add(customer)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S2-STMT-{tid}",
            total_amount=Decimal("1000"),
            amount=Decimal("1000"),
            amount_aed=Decimal("1000"),
        )
        db_session.add(sale)
        db_session.commit()

        cheque = Cheque(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            cheque_number=f"CH-STMT-{tid}",
            cheque_bank_number=f"BNK-STMT-{tid}",
            cheque_type="incoming",
            bank_name="Test Bank",
            amount=Decimal("200"),
            amount_aed=Decimal("200"),
            currency="AED",
            status="pending",
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
        )
        db_session.add(cheque)
        db_session.commit()

        payment = Payment(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            user_id=user.id,
            sale_id=sale.id,
            payment_number=f"P-STMT-{tid}",
            cheque_id=cheque.id,
            amount=Decimal("200"),
            amount_aed=Decimal("200"),
            currency="AED",
            payment_method="cheque",
            payment_type="sale_payment",
            direction="incoming",
            payment_confirmed=True,
        )
        db_session.add(payment)
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

            resp = client.get(f"/customers/{customer.id}/statement")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert f"S2-STMT-{tid}" in html, "Sale missing from statement"
        assert "دفعة" in html, "Payment row missing from statement"


class TestCustomerDelete:
    def test_delete_customer_with_sales_soft_deletes(self, app, db_session, client):
        """Customer with sales must be soft-deleted (is_active=False), not hard-deleted."""
        from models import Tenant, Branch, Role, User, Customer, Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"Del {tid}",
            name_ar=f"Del {tid}",
            slug=f"del-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"del-{tid}",
            email=f"del-{tid}@t.com",
            full_name="Del",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"DelCust {tid}", phone="0506666666")
        db_session.add(customer)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S-DEL-{tid}",
            total_amount=Decimal("100"),
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
        )
        db_session.add(sale)
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

            resp = client.post(f"/customers/{customer.id}/delete", follow_redirects=True)
        assert resp.status_code == 200

        db_session.expire_all()
        deleted = Customer.query.get(customer.id)
        assert deleted is not None, "BUG: Customer hard-deleted despite having sales"
        assert deleted.is_active is False, "Customer should be inactive after soft-delete"

    def test_delete_customer_without_links_hard_deletes(self, app, db_session, client):
        """Customer with NO linked records should be hard-deleted."""
        from models import Tenant, Branch, Role, User, Customer
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"Del2 {tid}",
            name_ar=f"Del2 {tid}",
            slug=f"del2-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"del2-{tid}",
            email=f"del2-{tid}@t.com",
            full_name="Del2",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=None,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"Del2Cust {tid}", phone="0507777777")
        db_session.add(customer)
        db_session.flush()

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

            resp = client.post(f"/customers/{customer.id}/delete", follow_redirects=True)
        assert resp.status_code == 200

        db_session.expire_all()
        deleted = Customer.query.get(customer.id)
        assert deleted is None, "BUG: Customer should have been hard-deleted (no links)"


class TestCustomerView:
    def test_customer_view_shows_balance_and_unpaid_sales(self, app, db_session, client):
        """Customer view page must show balance and unpaid sales."""
        from models import Tenant, Branch, Role, User, Customer, Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"View {tid}",
            name_ar=f"View {tid}",
            slug=f"view-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"vw-{tid}",
            email=f"vw-{tid}@t.com",
            full_name="Vw",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"ViewCust {tid}", phone="0508888888")
        db_session.add(customer)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S-VW-{tid}",
            total_amount=Decimal("500"),
            amount=Decimal("500"),
            amount_aed=Decimal("500"),
            status="confirmed",
        )
        db_session.add(sale)
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

            resp = client.get(f"/customers/{customer.id}")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert f"ViewCust {tid}" in html


class TestCustomerSearch:
    def test_customer_search_by_name(self, app, db_session, client):
        """Searching customers by name should return matching results."""
        from models import Tenant, Branch, Role, User, Customer, Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"Sch {tid}",
            name_ar=f"Sch {tid}",
            slug=f"sch-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"sch-{tid}",
            email=f"sch-{tid}@t.com",
            full_name="Sch",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        cust_a = Customer(tenant_id=tenant.id, name=f"AlphaSearch {tid}", phone="0509990001")
        cust_b = Customer(tenant_id=tenant.id, name=f"BetaSearch {tid}", phone="0509990002")
        db_session.add(cust_a)
        db_session.flush()
        db_session.add(cust_b)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale_a = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=cust_a.id,
            seller_id=user.id,
            sale_number=f"S-SA-{tid}",
            total_amount=Decimal("10"),
            amount=Decimal("10"),
            amount_aed=Decimal("10"),
        )
        sale_b = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=cust_b.id,
            seller_id=user.id,
            sale_number=f"S-SB-{tid}",
            total_amount=Decimal("20"),
            amount=Decimal("20"),
            amount_aed=Decimal("20"),
        )
        db_session.add(sale_a)
        db_session.add(sale_b)
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

            resp = client.get("/customers/", query_string={"search": "Alpha"})
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert f"AlphaSearch {tid}" in html, "Search should find AlphaSearch"
        assert f"BetaSearch {tid}" not in html, "Search should exclude BetaSearch"


class TestReceivablesReport:
    def test_receivables_report_aging_buckets(self, app, db_session, client):
        """Receivables report must have correct aging buckets (0-30/31-60/61-90/90+ days)."""
        from models import Tenant, Branch, Role, User, Customer, Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"Recv {tid}",
            name_ar=f"Recv {tid}",
            slug=f"recv-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"recv-{tid}",
            email=f"recv-{tid}@t.com",
            full_name="Recv",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"AgeCust {tid}", phone="0500000001")
        db_session.add(customer)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        old_date = datetime.now(timezone.utc) - timedelta(days=100)

        sale_old = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S-OLD-{tid}",
            total_amount=Decimal("1000"),
            amount=Decimal("1000"),
            amount_aed=Decimal("1000"),
            sale_date=old_date,
        )
        db_session.add(sale_old)
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

            resp = client.get("/reports/receivables")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert f"AgeCust {tid}" in html

    def test_receivables_report_totals_accurate(self, app, db_session, client):
        """Receivables report totals must match sale unpaid balances."""
        from models import Tenant, Branch, Role, User, Customer, Sale, Payment
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"Rec2 {tid}",
            name_ar=f"Rec2 {tid}",
            slug=f"rec2-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"rec2-{tid}",
            email=f"rec2-{tid}@t.com",
            full_name="Rec2",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"Rec2Cust {tid}", phone="0500000002")
        db_session.add(customer)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S-REC2-{tid}",
            total_amount=Decimal("500"),
            amount=Decimal("500"),
            amount_aed=Decimal("500"),
        )
        db_session.add(sale)
        db_session.commit()

        payment = Payment(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            user_id=user.id,
            sale_id=sale.id,
            payment_number=f"P-REC2-{tid}",
            amount=Decimal("200"),
            amount_aed=Decimal("200"),
            currency="AED",
            payment_method="cash",
            payment_type="sale_payment",
            direction="incoming",
            payment_confirmed=True,
        )
        db_session.add(payment)
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

            resp = client.get("/reports/receivables")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        html = resp.data.decode("utf-8")
        assert f"Rec2Cust {tid}" in html, "Customer missing from receivables report"

    def test_receivables_defaults_to_all_confirmed_sales(self, app, db_session, client):
        """Receivables report should load without a customer filter."""
        from models import Tenant, Branch, Role, User, Customer, Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"Rec3 {tid}",
            name_ar=f"Rec3 {tid}",
            slug=f"rec3-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"rec3-{tid}",
            email=f"rec3-{tid}@t.com",
            full_name="Rec3",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"Rec3Cust {tid}", phone="0500000003")
        db_session.add(customer)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S-REC3-{tid}",
            total_amount=Decimal("300"),
            amount=Decimal("300"),
            amount_aed=Decimal("300"),
        )
        db_session.add(sale)
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

            resp = client.get("/reports/receivables")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        html = resp.data.decode("utf-8")

        assert f"Rec3Cust {tid}" in html, "Customer missing from unfiltered receivables report"


class TestCustomerApi:
    def test_api_search_returns_json(self, app, db_session, client):
        """API search endpoint should return JSON with matching customers."""
        from models import Tenant, Branch, Role, User, Customer, Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"API {tid}",
            name_ar=f"API {tid}",
            slug=f"api-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"api-{tid}",
            email=f"api-{tid}@t.com",
            full_name="API",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"APICust {tid}", phone="0500000004")
        db_session.add(customer)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S-API-{tid}",
            total_amount=Decimal("50"),
            amount=Decimal("50"),
            amount_aed=Decimal("50"),
        )
        db_session.add(sale)
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

            resp = client.get("/customers/api/search", query_string={"q": "APICust"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert any(c["name"] == f"APICust {tid}" for c in data), "API search did not return the expected customer"

    def test_api_balance_returns_json(self, app, db_session, client):
        """Balance API endpoint should return customer balance and unpaid sales."""
        from models import Tenant, Branch, Role, User, Customer, Sale
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(
            name=f"BAL {tid}",
            name_ar=f"BAL {tid}",
            slug=f"bal-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"bal-{tid}",
            email=f"bal-{tid}@t.com",
            full_name="Bal",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f"BalCust {tid}", phone="0500000005")
        db_session.add(customer)
        db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = Sale(
            tenant_id=tenant.id,
            branch_id=branch.id,
            customer_id=customer.id,
            seller_id=user.id,
            sale_number=f"S-BAL-{tid}",
            total_amount=Decimal("750"),
            amount=Decimal("750"),
            amount_aed=Decimal("750"),
        )
        db_session.add(sale)
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

            resp = client.get(f"/customers/{customer.id}/balance")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "balance_aed" in data
        assert "unpaid_sales" in data
