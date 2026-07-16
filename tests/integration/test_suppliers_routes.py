"""
Integration tests: Supplier routes — purchases, payables, cheques, ageing.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta


class TestSupplierCreate:
    def test_supplier_create_auto_linked_to_tenant(self, app, db_session, client):
        """New supplier must be auto-linked to the active tenant."""
        from models import Tenant, Branch, Role, User, Supplier

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(name=f'SuppT {tid}', name_ar=f'SuppT {tid}', slug=f'supp-{tid}',
                        default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        # No branch_id → "all" scope → supplier viewable after creation
        user = User(username=f'pur-{tid}', email=f'pur-{tid}@t.com', full_name='Purchaser',
                    role_id=role.id, tenant_id=tenant.id, branch_id=None,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user); db_session.flush()
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.post('/suppliers/create', data={
                'name': f'SupplierCo {tid}',
                'phone': f'0501111{str(tenant.id)[-4:]}',
                'email': f'supplier{tid}@example.com',
                'supplier_type': 'parts',
            }, follow_redirects=True)
        assert resp.status_code == 200

        supplier = Supplier.query.filter_by(phone=f'0501111{str(tenant.id)[-4:]}').first()
        assert supplier is not None, 'Supplier not created'
        assert supplier.tenant_id == tenant.id, 'Supplier not linked to tenant'


class TestSupplierBranchIsolation:
    def test_supplier_branch_isolation(self, app, db_session, client):
        """Supplier visible only in the branch where it has a Purchase."""
        from models import Tenant, Branch, Role, User, Supplier, Purchase
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(name=f'BrS {tid}', name_ar=f'BrS {tid}', slug=f'brs-{tid}',
                        default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()

        b1 = Branch(tenant_id=tenant.id, name=f'North {tid}', code=f'B1{tid[:4]}')
        b2 = Branch(tenant_id=tenant.id, name=f'South {tid}', code=f'B2{tid[:4]}')
        db_session.add(b1); db_session.flush()
        db_session.add(b2); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        u1 = User(username=f'u1-{tid}', email=f'u1-{tid}@t.com', full_name='User1',
                  role_id=role.id, tenant_id=tenant.id, branch_id=b1.id,
                  is_active=True, is_owner=True)
        u1.set_password('x')
        db_session.add(u1); db_session.flush()

        u2 = User(username=f'u2-{tid}', email=f'u2-{tid}@t.com', full_name='User2',
                  role_id=role.id, tenant_id=tenant.id, branch_id=b2.id,
                  is_active=True, is_owner=True)
        u2.set_password('x')
        db_session.add(u2); db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f'SuppB1 {tid}', phone='0502222222')
        db_session.add(supplier); db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        purchase = Purchase(tenant_id=tenant.id, branch_id=b1.id, supplier_id=supplier.id,
                            supplier_name=f'SuppB1 {tid}', user_id=u1.id,
                            purchase_number=f'P-B1-{tid}',
                            total_amount=Decimal('1000'), amount=Decimal('1000'),
                            amount_aed=Decimal('1000'), currency='AED')
        db_session.add(purchase)
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': u2.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.get('/suppliers/')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert f'SuppB1 {tid}' not in html, \
            'Supplier from Branch 1 visible in Branch 2 list'

    def test_supplier_branch_isolation_reverse(self, app, db_session, client):
        """Supplier in Branch 2 must NOT appear in Branch 1's list."""
        from models import Tenant, Branch, Role, User, Supplier, Purchase
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(name=f'BrR {tid}', name_ar=f'BrR {tid}', slug=f'brr-{tid}',
                        default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()

        b1 = Branch(tenant_id=tenant.id, name=f'Left {tid}', code=f'L{tid[:4]}')
        b2 = Branch(tenant_id=tenant.id, name=f'Right {tid}', code=f'R{tid[:4]}')
        db_session.add(b1); db_session.flush()
        db_session.add(b2); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        u1 = User(username=f'w1-{tid}', email=f'w1-{tid}@t.com', full_name='U1',
                  role_id=role.id, tenant_id=tenant.id, branch_id=b1.id,
                  is_active=True, is_owner=True)
        u1.set_password('x')
        db_session.add(u1); db_session.flush()

        u2 = User(username=f'w2-{tid}', email=f'w2-{tid}@t.com', full_name='U2',
                  role_id=role.id, tenant_id=tenant.id, branch_id=b2.id,
                  is_active=True, is_owner=True)
        u2.set_password('x')
        db_session.add(u2); db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f'SuppB2 {tid}', phone='0503333333')
        db_session.add(supplier); db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        purchase = Purchase(tenant_id=tenant.id, branch_id=b2.id, supplier_id=supplier.id,
                            supplier_name=f'SuppB2 {tid}', user_id=u2.id,
                            purchase_number=f'P-B2-{tid}',
                            total_amount=Decimal('500'), amount=Decimal('500'),
                            amount_aed=Decimal('500'), currency='AED')
        db_session.add(purchase)
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': u1.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.get('/suppliers/')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert f'SuppB2 {tid}' not in html, \
            'Supplier from Branch 2 visible in Branch 1 list'


class TestSupplierStatement:
    def test_statement_shows_purchases_and_payments(self, app, db_session, client):
        """Supplier statement must show purchases (debit) and payments (credit)."""
        from models import Tenant, Branch, Role, User, Supplier, Purchase, Payment

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(name=f'StS {tid}', name_ar=f'StS {tid}', slug=f'sts-{tid}',
                        default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        user = User(username=f'acc-{tid}', email=f'acc-{tid}@t.com', full_name='Accountant',
                    role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f'StmtSupp {tid}', phone='0504444444')
        db_session.add(supplier); db_session.flush()
        db_session.commit()

        purchase = Purchase(tenant_id=tenant.id, branch_id=branch.id, supplier_id=supplier.id,
                            supplier_name=f'StmtSupp {tid}', user_id=user.id,
                            purchase_number=f'P-STMT-{tid}',
                            total_amount=Decimal('2000'), amount=Decimal('2000'),
                            amount_aed=Decimal('2000'), currency='AED')
        db_session.add(purchase)
        db_session.commit()

        payment = Payment(tenant_id=tenant.id, branch_id=branch.id, supplier_id=supplier.id,
                          user_id=user.id,
                          payment_number=f'PM-STMT-{tid}',
                          amount=Decimal('500'), amount_aed=Decimal('500'),
                          currency='AED', payment_method='cash', payment_type='purchase_payment',
                          direction='outgoing', payment_confirmed=True)
        db_session.add(payment)
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.get(f'/suppliers/{supplier.id}/statement')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert f'P-STMT-{tid}' in html, 'Purchase ref missing from statement'
        assert f'PM-STMT-{tid}' in html, 'Payment ref missing from statement'


class TestPayablesReport:
    def test_purchases_report_shows_supplier_balances(self, app, db_session, client):
        """Purchases report must list suppliers with their payable balances."""
        from models import Tenant, Branch, Role, User, Supplier, Purchase
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(name=f'Pay {tid}', name_ar=f'Pay {tid}', slug=f'pay-{tid}',
                        default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        user = User(username=f'rep-{tid}', email=f'rep-{tid}@t.com', full_name='ReportUser',
                    role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f'PaySupp {tid}', phone='0505555555')
        db_session.add(supplier); db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        purchase = Purchase(tenant_id=tenant.id, branch_id=branch.id, supplier_id=supplier.id,
                            supplier_name=f'PaySupp {tid}', user_id=user.id,
                            purchase_number=f'P-REP-{tid}',
                            total_amount=Decimal('3000'), amount=Decimal('3000'),
                            amount_aed=Decimal('3000'), currency='AED')
        db_session.add(purchase)
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.get('/reports/purchases')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert f'PaySupp {tid}' in html, 'Supplier missing from purchases report'


class TestSupplierChequeReport:
    def test_statement_shows_cheque_payments(self, app, db_session, client):
        """Supplier statement must show payments linked to outgoing cheques."""
        from models import Tenant, Branch, Role, User, Supplier, Purchase, Payment, Cheque

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(name=f'ChS {tid}', name_ar=f'ChS {tid}', slug=f'chs-{tid}',
                        default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        user = User(username=f'chq-{tid}', email=f'chq-{tid}@t.com', full_name='ChqUser',
                    role_id=role.id, tenant_id=tenant.id, branch_id=None,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f'ChqSupp {tid}', phone='0506666666')
        db_session.add(supplier); db_session.flush()
        db_session.commit()

        purchase = Purchase(tenant_id=tenant.id, branch_id=branch.id, supplier_id=supplier.id,
                            supplier_name=f'ChqSupp {tid}', user_id=user.id,
                            purchase_number=f'P-CHQ-{tid}',
                            total_amount=Decimal('2500'), amount=Decimal('2500'),
                            amount_aed=Decimal('2500'), currency='AED')
        db_session.add(purchase)
        db_session.commit()

        cheque = Cheque(tenant_id=tenant.id, branch_id=branch.id, supplier_id=supplier.id,
                        cheque_number=f'CH-SUP-{tid}', cheque_bank_number=f'BNK-SUP-{tid}',
                        cheque_type='outgoing', bank_name='TestBank',
                        amount=Decimal('2500'), amount_aed=Decimal('2500'),
                        currency='AED', status='pending',
                        issue_date=datetime.now(timezone.utc).date(),
                        due_date=datetime.now(timezone.utc).date() + timedelta(days=30))
        db_session.add(cheque)
        db_session.commit()

        payment = Payment(tenant_id=tenant.id, branch_id=branch.id, supplier_id=supplier.id,
                          user_id=user.id, purchase_id=purchase.id, cheque_id=cheque.id,
                          payment_number=f'PM-CHQ-{tid}',
                          amount=Decimal('2500'), amount_aed=Decimal('2500'),
                          currency='AED', payment_method='cheque', payment_type='purchase_payment',
                          direction='outgoing', payment_confirmed=True)
        db_session.add(payment)
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.get(f'/suppliers/{supplier.id}/statement')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert f'PM-CHQ-{tid}' in html, 'Cheque payment ref missing from statement'


class TestSupplierAgeing:
    def test_purchases_report_shows_ageing_data(self, app, db_session, client):
        """Purchases report must show older purchases with their payable balances."""
        from models import Tenant, Branch, Role, User, Supplier, Purchase
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(name=f'Age {tid}', name_ar=f'Age {tid}', slug=f'age-{tid}',
                        default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        user = User(username=f'age-{tid}', email=f'age-{tid}@t.com', full_name='AgeUser',
                    role_id=role.id, tenant_id=tenant.id, branch_id=None,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f'AgeSupp {tid}', phone='0507777777')
        db_session.add(supplier); db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        old_purchase = Purchase(tenant_id=tenant.id, branch_id=branch.id, supplier_id=supplier.id,
                                supplier_name=f'AgeSupp {tid}', user_id=user.id,
                                purchase_number=f'P-OLD-{tid}',
                                total_amount=Decimal('5000'), amount=Decimal('5000'),
                                amount_aed=Decimal('5000'), currency='AED',
                                purchase_date=datetime.now(timezone.utc) - timedelta(days=100))
        db_session.add(old_purchase)
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.get('/reports/purchases')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert f'AgeSupp {tid}' in html, 'Supplier missing from purchases report'
        assert f'P-OLD-{tid}' in html, 'Old purchase missing from report'


class TestSupplierDelete:
    def test_delete_supplier_with_purchases_soft_deletes(self, app, db_session, client):
        """Supplier with purchases must be soft-deleted (is_active=False)."""
        from models import Tenant, Branch, Role, User, Supplier, Purchase
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(name=f'Del {tid}', name_ar=f'Del {tid}', slug=f'del-{tid}',
                        default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        user = User(username=f'del-{tid}', email=f'del-{tid}@t.com', full_name='Del',
                    role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f'DelSupp {tid}', phone='0508888888')
        db_session.add(supplier); db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        purchase = Purchase(tenant_id=tenant.id, branch_id=branch.id, supplier_id=supplier.id,
                            supplier_name=f'DelSupp {tid}', user_id=user.id,
                            purchase_number=f'P-DEL-{tid}',
                            total_amount=Decimal('1000'), amount=Decimal('1000'),
                            amount_aed=Decimal('1000'), currency='AED')
        db_session.add(purchase)
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.post(f'/suppliers/{supplier.id}/delete', follow_redirects=True)
        assert resp.status_code == 200

        db_session.expire_all()
        deleted = Supplier.query.get(supplier.id)
        assert deleted is not None, 'Supplier hard-deleted despite having purchases'
        assert deleted.is_active is False, 'Supplier should be inactive after soft-delete'

    def test_delete_supplier_without_links_hard_deletes(self, app, db_session, client):
        """Supplier with NO linked records must be hard-deleted."""
        from models import Tenant, Branch, Role, User, Supplier

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(name=f'Del2 {tid}', name_ar=f'Del2 {tid}', slug=f'del2-{tid}',
                        default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        user = User(username=f'del2-{tid}', email=f'del2-{tid}@t.com', full_name='Del2',
                    role_id=role.id, tenant_id=tenant.id, branch_id=None,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f'Del2Supp {tid}', phone='0509999999')
        db_session.add(supplier); db_session.flush()
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.post(f'/suppliers/{supplier.id}/delete', follow_redirects=True)
        assert resp.status_code == 200

        db_session.expire_all()
        deleted = Supplier.query.get(supplier.id)
        assert deleted is None, 'Supplier should have been hard-deleted (no links)'


class TestSupplierSearch:
    def test_supplier_search_by_name(self, app, db_session, client):
        """Searching suppliers by name must return matching results."""
        from models import Tenant, Branch, Role, User, Supplier, Purchase
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(name=f'Sch {tid}', name_ar=f'Sch {tid}', slug=f'sch-{tid}',
                        default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        user = User(username=f'sch-{tid}', email=f'sch-{tid}@t.com', full_name='Search',
                    role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f'FindMeSupp {tid}', phone='0500001111')
        db_session.add(supplier); db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        purchase = Purchase(tenant_id=tenant.id, branch_id=branch.id, supplier_id=supplier.id,
                            supplier_name=f'FindMeSupp {tid}', user_id=user.id,
                            purchase_number=f'P-SCH-{tid}',
                            total_amount=Decimal('100'), amount=Decimal('100'),
                            amount_aed=Decimal('100'), currency='AED')
        db_session.add(purchase)
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.get('/suppliers/', query_string={'search': 'FindMe'})
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert f'FindMeSupp {tid}' in html, 'Search should find FindMeSupp'


class TestSupplierCrossTenant:
    def test_supplier_cross_tenant_isolation(self, app, db_session, client):
        """Suppliers from different tenants must be completely isolated."""
        from models import Tenant, Branch, Role, User, Supplier, Purchase
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        t1 = Tenant(name=f'T1S {tid}', name_ar=f'T1S {tid}', slug=f't1s-{tid}',
                    default_currency='AED', base_currency='AED')
        t2 = Tenant(name=f'T2S {tid}', name_ar=f'T2S {tid}', slug=f't2s-{tid}',
                    default_currency='AED', base_currency='AED')
        db_session.add(t1); db_session.flush()
        db_session.add(t2); db_session.flush()

        b1 = Branch(tenant_id=t1.id, name=f'B1 {tid}', code=f'B1{tid[:4]}')
        b2 = Branch(tenant_id=t2.id, name=f'B2 {tid}', code=f'B2{tid[:4]}')
        db_session.add(b1); db_session.flush()
        db_session.add(b2); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        u1 = User(username=f'pur1-{tid}', email=f'pur1-{tid}@t.com', full_name='Pur1',
                  role_id=role.id, tenant_id=t1.id, branch_id=None,
                  is_active=True, is_owner=True)
        u1.set_password('x')
        db_session.add(u1); db_session.flush()

        s1 = Supplier(tenant_id=t1.id, name=f'T1Supp {tid}', phone='0500000011')
        s2 = Supplier(tenant_id=t2.id, name=f'T2Supp {tid}', phone='0500000022')
        db_session.add(s1); db_session.flush()
        db_session.add(s2); db_session.flush()

        GLService.ensure_core_accounts(tenant_id=t1.id)
        db_session.commit()

        p1 = Purchase(tenant_id=t1.id, branch_id=b1.id, supplier_id=s1.id,
                      supplier_name=f'T1Supp {tid}', user_id=u1.id,
                      purchase_number=f'P-T1-{tid}',
                      total_amount=Decimal('100'), amount=Decimal('100'),
                      amount_aed=Decimal('100'), currency='AED')
        db_session.add(p1)
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': u1.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.get('/suppliers/')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert f'T1Supp {tid}' in html, 'Own tenant supplier missing'
        assert f'T2Supp {tid}' not in html, 'Cross-tenant supplier leaked'


class TestSupplierCreditLimit:
    def test_supplier_credit_limit_tracks_purchases(self, app, db_session, client):
        """Supplier credit_limit must not prevent showing total_purchases_aed."""
        from models import Tenant, Branch, Role, User, Supplier, Purchase
        from services.gl_service import GLService

        tid = uuid.uuid4().hex[:12]
        tenant = Tenant(name=f'Lim {tid}', name_ar=f'Lim {tid}', slug=f'lim-{tid}',
                        default_currency='AED', base_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        db_session.add(role); db_session.flush()

        user = User(username=f'lim-{tid}', email=f'lim-{tid}@t.com', full_name='LimitUser',
                    role_id=role.id, tenant_id=tenant.id, branch_id=None,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f'LimitSupp {tid}', phone='0501231234',
                            credit_limit=Decimal('1000'), total_purchases_aed=Decimal('800'),
                            total_paid_aed=Decimal('0'))
        db_session.add(supplier); db_session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        purchase = Purchase(tenant_id=tenant.id, branch_id=branch.id, supplier_id=supplier.id,
                            supplier_name=f'LimitSupp {tid}', user_id=user.id,
                            purchase_number=f'P-LIM-{tid}',
                            total_amount=Decimal('500'), amount=Decimal('500'),
                            amount_aed=Decimal('500'), currency='AED')
        db_session.add(purchase)
        db_session.commit()

        db_session.refresh(supplier)
        assert float(supplier.total_purchases_aed or 0) >= 800, \
            'Supplier total_purchases_aed should reflect existing balance'
