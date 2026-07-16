"""
Integration tests: POS routes — session management, checkout, discount, credit, drawer isolation.
Tests use real HTTP JSON API endpoints, verifying DB state after each operation.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone


class TestPOSSession:
    def test_pos_session_start_creates_session(self, app, db_session, client):
        """POST /pos/api/session/open creates a POS session with opening balance."""
        from models import Tenant, Branch, Role, User, Permission, SystemSettings

        tid = uuid.uuid4().hex[:4]
        tenant = Tenant(name=f'POS {tid}', name_ar=f'POS {tid}', slug=f'pos-{tid}',
                        default_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        perm = Permission.query.filter_by(code='manage_sales').first()
        if not perm:
            perm = Permission(code='manage_sales', name='manage_sales',
                              name_ar='manage_sales', category='sales')
            db_session.add(perm); db_session.flush()
        role.permissions.append(perm)
        db_session.add(role); db_session.flush()

        user = User(username=f'pos-{tid}', email=f'pos-{tid}@t.com', full_name='Cashier',
                    role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=False)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        # Ensure SystemSettings record exists (enable_pos defaults True)
        if not SystemSettings.query.first():
            db_session.add(SystemSettings(enable_pos=True))
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.post('/pos/api/session/open',
                json={'opening_balance': 500},
                content_type='application/json')
        assert resp.status_code == 201, f'Session open failed: {resp.get_json()}'
        data = resp.get_json()
        assert data['success'] is True
        assert data['session']['opening_balance'] == 500.0
        assert data['session']['status'] == 'open'

        from models import PosSession
        session = PosSession.query.filter_by(tenant_id=tenant.id).first()
        assert session is not None
        assert session.opening_balance_cash == 500
        assert session.status == 'open'

    def test_pos_checkout_creates_sale_and_reduces_stock(self, app, db_session, client):
        """POST /pos/api/checkout creates sale, records payment, decreases stock."""
        from models import Tenant, Branch, Role, User, Permission, SystemSettings
        from models import Warehouse, Product, ProductCategory
        from services.stock_service import StockService

        tid = uuid.uuid4().hex[:4]
        tenant = Tenant(name=f'PSC {tid}', name_ar=f'PSC {tid}', slug=f'psc-{tid}',
                        default_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        perm = Permission.query.filter_by(code='manage_sales').first()
        if not perm:
            perm = Permission(code='manage_sales', name='manage_sales',
                              name_ar='manage_sales', category='sales')
            db_session.add(perm); db_session.flush()
        role.permissions.append(perm)
        db_session.add(role); db_session.flush()

        user = User(username=f'posc-{tid}', email=f'posc-{tid}@t.com', full_name='Cashier',
                    role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=False)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        wh = Warehouse(name=f'WH {tid}', tenant_id=tenant.id, branch_id=branch.id,
                       is_active=True, allow_negative_inventory=False)
        db_session.add(wh); db_session.flush()

        cat = ProductCategory(name=f'Cat {tid}', tenant_id=tenant.id, is_active=True)
        db_session.add(cat); db_session.flush()

        product = Product(name=f'Item {tid}', sku=f'ITM-{tid}', tenant_id=tenant.id,
                          category_id=cat.id, regular_price=Decimal('25'),
                          cost_price=Decimal('10'), is_active=True)
        db_session.add(product); db_session.flush()

        StockService.add_stock(product.id, Decimal('50'), warehouse_id=wh.id)
        db_session.flush()

        if not SystemSettings.query.first():
            db_session.add(SystemSettings(enable_pos=True))
        db_session.commit()

        with client:
            client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)

            # Open POS session
            resp = client.post('/pos/api/session/open',
                json={'opening_balance': 500},
                content_type='application/json')
            assert resp.status_code == 201

            # Open POS shift (required by checkout)
            resp = client.post('/pos/api/shift/open',
                json={'starting_cash': 500},
                content_type='application/json')
            assert resp.status_code == 201

            # Checkout
            resp = client.post('/pos/api/checkout',
                json={
                    'lines': [
                        {'product_id': product.id, 'quantity': 3,
                         'unit_price': 25.0, 'discount_percent': 0},
                    ],
                    'payment_method': 'cash',
                    'paid_amount': 75.0,
                    'currency': 'AED',
                    'warehouse_id': wh.id,
                },
                content_type='application/json')
        assert resp.status_code == 200, f'Checkout failed: {resp.get_json()}'
        data = resp.get_json()
        assert data['success'] is True
        sale_id = data['sale_id']
        assert data['sale_number'] is not None

        from models import Sale, Payment
        sale = Sale.query.get(sale_id)
        assert sale is not None
        assert sale.total_amount == 75
        assert sale.warehouse_id == wh.id

        from models import Payment
        payment = Payment.query.filter_by(sale_id=sale.id).first()
        assert payment is not None
        assert float(payment.amount) == 75.0

        stock = StockService.get_product_stock(product.id, warehouse_id=wh.id)
        assert stock == 47, f'Expected stock 47, got {stock}'

        from models import GLJournalEntry
        gl = GLJournalEntry.query.filter_by(tenant_id=tenant.id).order_by(GLJournalEntry.id.desc()).first()
        if gl:
            total_dr = sum(Decimal(str(l.debit or 0)) for l in gl.lines)
            total_cr = sum(Decimal(str(l.credit or 0)) for l in gl.lines)
            assert total_dr == total_cr

    def test_pos_session_close_reconciles_cash(self, app, db_session, client):
        """POST /pos/api/session/close reconciles actual vs expected cash."""
        from models import Tenant, Branch, Role, User, Permission, SystemSettings
        from models import Warehouse, Product, ProductCategory
        from services.stock_service import StockService

        tid = uuid.uuid4().hex[:4]
        tenant = Tenant(name=f'PCL {tid}', name_ar=f'PCL {tid}', slug=f'pcl-{tid}',
                        default_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        perm = Permission.query.filter_by(code='manage_sales').first()
        if not perm:
            perm = Permission(code='manage_sales', name='manage_sales',
                              name_ar='manage_sales', category='sales')
            db_session.add(perm); db_session.flush()
        role.permissions.append(perm)
        db_session.add(role); db_session.flush()

        user = User(username=f'pcl-{tid}', email=f'pcl-{tid}@t.com', full_name='Cashier',
                    role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=False)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        wh = Warehouse(name=f'WH {tid}', tenant_id=tenant.id, branch_id=branch.id,
                       is_active=True, allow_negative_inventory=False)
        db_session.add(wh); db_session.flush()

        cat = ProductCategory(name=f'Cat {tid}', tenant_id=tenant.id, is_active=True)
        db_session.add(cat); db_session.flush()

        product = Product(name=f'Item {tid}', sku=f'ITM-{tid}', tenant_id=tenant.id,
                          category_id=cat.id, regular_price=Decimal('25'),
                          cost_price=Decimal('10'), is_active=True)
        db_session.add(product); db_session.flush()

        StockService.add_stock(product.id, Decimal('100'), warehouse_id=wh.id)
        db_session.flush()

        if not SystemSettings.query.first():
            db_session.add(SystemSettings(enable_pos=True))
        db_session.commit()

        with client:
            client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)

            client.post('/pos/api/session/open',
                json={'opening_balance': 500},
                content_type='application/json')

            client.post('/pos/api/shift/open',
                json={'starting_cash': 500},
                content_type='application/json')

            client.post('/pos/api/checkout',
                json={
                    'lines': [
                        {'product_id': product.id, 'quantity': 3,
                         'unit_price': 25.0, 'discount_percent': 0},
                    ],
                    'payment_method': 'cash',
                    'paid_amount': 75.0,
                    'currency': 'AED',
                    'warehouse_id': wh.id,
                },
                content_type='application/json')

            resp = client.post('/pos/api/session/close',
                json={'closing_balance': 575},
                content_type='application/json')
        assert resp.status_code == 200, f'Close failed: {resp.get_json()}'
        data = resp.get_json()
        assert data['success'] is True
        assert data['session']['status'] == 'closed'
        assert data['session']['closing_balance'] == 575.0
        assert data['session']['difference'] == 0.0

        from models import PosSession
        session = PosSession.query.filter_by(tenant_id=tenant.id).first()
        assert session.status == 'closed'
        assert session.expected_balance == 575
        assert session.difference == 0

    def test_pos_session_close_overage_posts_gl(self, app, db_session, client):
        """Cash overage (actual > expected) posts a balanced GL entry."""
        from models import Tenant, Branch, Role, User, Permission, SystemSettings
        from models import Warehouse, Product, ProductCategory
        from services.stock_service import StockService
        from utils.gl_reference_types import GLRef

        tid = uuid.uuid4().hex[:4]
        tenant = Tenant(name=f'POV {tid}', name_ar=f'POV {tid}', slug=f'pov-{tid}',
                        default_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        perm = Permission.query.filter_by(code='manage_sales').first()
        if not perm:
            perm = Permission(code='manage_sales', name='manage_sales',
                              name_ar='manage_sales', category='sales')
            db_session.add(perm); db_session.flush()
        role.permissions.append(perm)
        db_session.add(role); db_session.flush()

        user = User(username=f'pov-{tid}', email=f'pov-{tid}@t.com', full_name='Cashier',
                    role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=False)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        wh = Warehouse(name=f'WH {tid}', tenant_id=tenant.id, branch_id=branch.id,
                       is_active=True, allow_negative_inventory=False)
        db_session.add(wh); db_session.flush()

        cat = ProductCategory(name=f'Cat {tid}', tenant_id=tenant.id, is_active=True)
        db_session.add(cat); db_session.flush()

        product = Product(name=f'Item {tid}', sku=f'ITM-{tid}', tenant_id=tenant.id,
                          category_id=cat.id, regular_price=Decimal('25'),
                          cost_price=Decimal('10'), is_active=True)
        db_session.add(product); db_session.flush()

        StockService.add_stock(product.id, Decimal('100'), warehouse_id=wh.id)
        db_session.flush()

        if not SystemSettings.query.first():
            db_session.add(SystemSettings(enable_pos=True))
        db_session.commit()

        with client:
            client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)

            client.post('/pos/api/session/open',
                json={'opening_balance': 500},
                content_type='application/json')

            client.post('/pos/api/shift/open',
                json={'starting_cash': 500},
                content_type='application/json')

            client.post('/pos/api/checkout',
                json={
                    'lines': [
                        {'product_id': product.id, 'quantity': 3,
                         'unit_price': 25.0, 'discount_percent': 0},
                    ],
                    'payment_method': 'cash',
                    'paid_amount': 75.0,
                    'currency': 'AED',
                    'warehouse_id': wh.id,
                },
                content_type='application/json')

            resp = client.post('/pos/api/session/close',
                json={'closing_balance': 580},
                content_type='application/json')
        assert resp.status_code == 200, f'Close failed: {resp.get_json()}'
        data = resp.get_json()
        assert data['session']['difference'] == 5.0

        from models import PosSession
        session = PosSession.query.filter_by(tenant_id=tenant.id).first()
        assert float(session.difference) == 5.0

        from models import GLJournalEntry
        gl = GLJournalEntry.query.filter_by(
            reference_type=GLRef.POS_CASH_DIFFERENCE,
            reference_id=session.id,
            tenant_id=tenant.id,
        ).first()
        assert gl is not None, 'GL entry should exist for overage'
        total_dr = sum(Decimal(str(l.debit or 0)) for l in gl.lines)
        total_cr = sum(Decimal(str(l.credit or 0)) for l in gl.lines)
        assert total_dr == total_cr
        assert total_dr == 5

    def test_pos_checkout_with_price_override_permission(self, app, db_session, client):
        """Price override without permission must be blocked."""
        from models import Tenant, Branch, Role, User, Permission, SystemSettings
        from models import Warehouse, Product, ProductCategory
        from services.stock_service import StockService

        tid = uuid.uuid4().hex[:4]
        tenant = Tenant(name=f'PPR {tid}', name_ar=f'PPR {tid}', slug=f'ppr-{tid}',
                        default_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        perm = Permission.query.filter_by(code='manage_sales').first()
        if not perm:
            perm = Permission(code='manage_sales', name='manage_sales',
                              name_ar='manage_sales', category='sales')
            db_session.add(perm); db_session.flush()
        role.permissions.append(perm)
        db_session.add(role); db_session.flush()

        user = User(username=f'ppr-{tid}', email=f'ppr-{tid}@t.com', full_name='Cashier',
                    role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=False)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        wh = Warehouse(name=f'WH {tid}', tenant_id=tenant.id, branch_id=branch.id,
                       is_active=True, allow_negative_inventory=False)
        db_session.add(wh); db_session.flush()

        cat = ProductCategory(name=f'Cat {tid}', tenant_id=tenant.id, is_active=True)
        db_session.add(cat); db_session.flush()

        product = Product(name=f'Item {tid}', sku=f'ITM-{tid}', tenant_id=tenant.id,
                          category_id=cat.id, regular_price=Decimal('25'),
                          cost_price=Decimal('10'), is_active=True)
        db_session.add(product); db_session.flush()

        StockService.add_stock(product.id, Decimal('50'), warehouse_id=wh.id)
        db_session.flush()

        if not SystemSettings.query.first():
            db_session.add(SystemSettings(enable_pos=True))
        db_session.commit()

        with client:
            client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)

            client.post('/pos/api/session/open',
                json={'opening_balance': 500},
                content_type='application/json')

            client.post('/pos/api/shift/open',
                json={'starting_cash': 500},
                content_type='application/json')

            # Override price from 25 to 15 — cashier without override_sale_price should be blocked
            resp = client.post('/pos/api/checkout',
                json={
                    'lines': [
                        {'product_id': product.id, 'quantity': 1,
                         'unit_price': 15.0, 'discount_percent': 0},
                    ],
                    'payment_method': 'cash',
                    'paid_amount': 15.0,
                    'currency': 'AED',
                    'warehouse_id': wh.id,
                },
                content_type='application/json')
        assert resp.status_code == 403, f'Expected 403, got {resp.status_code}: {resp.get_json()}'

    def test_pos_sale_on_customer_credit(self, app, db_session, client):
        """POS sale on credit defers payment — sale has balance_due > 0."""
        from models import Tenant, Branch, Role, User, Permission, SystemSettings
        from models import Warehouse, Product, ProductCategory, Customer
        from services.stock_service import StockService

        tid = uuid.uuid4().hex[:4]
        tenant = Tenant(name=f'PCR {tid}', name_ar=f'PCR {tid}', slug=f'pcr-{tid}',
                        default_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        perm = Permission.query.filter_by(code='manage_sales').first()
        if not perm:
            perm = Permission(code='manage_sales', name='manage_sales',
                              name_ar='manage_sales', category='sales')
            db_session.add(perm); db_session.flush()
        role.permissions.append(perm)
        db_session.add(role); db_session.flush()

        user = User(username=f'pcr-{tid}', email=f'pcr-{tid}@t.com', full_name='Cashier',
                    role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=False)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        wh = Warehouse(name=f'WH {tid}', tenant_id=tenant.id, branch_id=branch.id,
                       is_active=True, allow_negative_inventory=False)
        db_session.add(wh); db_session.flush()

        cat = ProductCategory(name=f'Cat {tid}', tenant_id=tenant.id, is_active=True)
        db_session.add(cat); db_session.flush()

        product = Product(name=f'Item {tid}', sku=f'ITM-{tid}', tenant_id=tenant.id,
                          category_id=cat.id, regular_price=Decimal('50'),
                          cost_price=Decimal('20'), is_active=True)
        db_session.add(product); db_session.flush()

        StockService.add_stock(product.id, Decimal('100'), warehouse_id=wh.id)
        db_session.flush()

        customer = Customer(name=f'CreditCust {tid}', phone=f'050{tid[:4]}1111',
                            tenant_id=tenant.id, customer_type='regular', is_active=True)
        db_session.add(customer); db_session.flush()

        if not SystemSettings.query.first():
            db_session.add(SystemSettings(enable_pos=True))
        db_session.commit()

        with client:
            client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)

            client.post('/pos/api/session/open',
                json={'opening_balance': 500},
                content_type='application/json')

            client.post('/pos/api/shift/open',
                json={'starting_cash': 500},
                content_type='application/json')

            resp = client.post('/pos/api/checkout',
                json={
                    'lines': [
                        {'product_id': product.id, 'quantity': 2,
                         'unit_price': 50.0, 'discount_percent': 0},
                    ],
                    'customer_id': customer.id,
                    'currency': 'AED',
                    'warehouse_id': wh.id,
                },
                content_type='application/json')
        assert resp.status_code == 200, f'Credit checkout failed: {resp.get_json()}'
        data = resp.get_json()
        assert data['success'] is True

        from models import Sale
        sale = Sale.query.get(data['sale_id'])
        assert sale is not None
        assert sale.total_amount == 100
        assert sale.customer_id == customer.id
        assert sale.balance_due == 100

        db_session.refresh(customer)
        assert float(customer.balance or 0) <= -100

    def test_pos_drawer_isolation_per_session(self, app, db_session):
        """Two cashiers have separate drawers/sessions in the same branch."""
        from models import Tenant, Branch, Role, User, Permission, SystemSettings

        tid = uuid.uuid4().hex[:4]
        tenant = Tenant(name=f'PIS {tid}', name_ar=f'PIS {tid}', slug=f'pis-{tid}',
                        default_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        perm = Permission.query.filter_by(code='manage_sales').first()
        if not perm:
            perm = Permission(code='manage_sales', name='manage_sales',
                              name_ar='manage_sales', category='sales')
            db_session.add(perm); db_session.flush()
        role.permissions.append(perm)
        db_session.add(role); db_session.flush()

        user1 = User(username=f'pos1-{tid}', email=f'pos1-{tid}@t.com', full_name='Cashier1',
                     role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                     is_active=True, is_owner=False)
        user1.set_password('x')
        db_session.add(user1); db_session.flush()

        user2 = User(username=f'pos2-{tid}', email=f'pos2-{tid}@t.com', full_name='Cashier2',
                     role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                     is_active=True, is_owner=False)
        user2.set_password('x')
        db_session.add(user2); db_session.flush()

        if not SystemSettings.query.first():
            db_session.add(SystemSettings(enable_pos=True))
        db_session.commit()

        from utils.pos_helpers import create_pos_session

        s1 = create_pos_session(user=user1, branch_id=branch.id, opening_balance=Decimal('300'))
        db_session.flush()
        assert s1.status == 'open'
        assert float(s1.opening_balance_cash) == 300.0

        s2 = create_pos_session(user=user2, branch_id=branch.id, opening_balance=Decimal('500'))
        db_session.flush()
        assert s2.status == 'open'
        assert float(s2.opening_balance_cash) == 500.0

        assert s1.id != s2.id
        assert s1.user_id == user1.id
        assert s2.user_id == user2.id

    def test_pos_walkin_customer_auto_created(self, app, db_session, client):
        """GET /pos/api/walkin-customer returns/creates a tenant-scoped walk-in customer."""
        from models import Tenant, Branch, Role, User, Permission, SystemSettings

        tid = uuid.uuid4().hex[:4]
        tenant = Tenant(name=f'PWC {tid}', name_ar=f'PWC {tid}', slug=f'pwc-{tid}',
                        default_currency='AED')
        db_session.add(tenant); db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'{tid[:4]}')
        db_session.add(branch); db_session.flush()

        role = Role(name=f'R {tid}', slug=f'r-{tid}', is_active=True)
        perm = Permission.query.filter_by(code='manage_sales').first()
        if not perm:
            perm = Permission(code='manage_sales', name='manage_sales',
                              name_ar='manage_sales', category='sales')
            db_session.add(perm); db_session.flush()
        role.permissions.append(perm)
        db_session.add(role); db_session.flush()

        user = User(username=f'pwc-{tid}', email=f'pwc-{tid}@t.com', full_name='Cashier',
                    role_id=role.id, tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=False)
        user.set_password('x')
        db_session.add(user); db_session.flush()

        if not SystemSettings.query.first():
            db_session.add(SystemSettings(enable_pos=True))
        db_session.commit()

        with client:
            client.post('/auth/login', data={
                'username': user.username, 'password': 'x',
            }, follow_redirects=True)

            resp = client.get('/pos/api/walkin-customer')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['id'] is not None
        assert data['is_walkin'] is True

        from models import Customer
        customer = Customer.query.get(data['id'])
        assert customer is not None
        assert customer.tenant_id == tenant.id
