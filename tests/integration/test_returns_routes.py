"""
Integration tests: Returns routes — real business logic via POST /returns/api/create.
"""
import pytest
import uuid
from decimal import Decimal

from models import StockMovement


def _add_initial_stock(db_session, product_id, warehouse_id, tenant_id, quantity):
    sm = StockMovement(
        product_id=product_id,
        warehouse_id=warehouse_id,
        tenant_id=tenant_id,
        movement_type='adjustment',
        quantity=quantity,
        notes='Initial test stock',
    )
    db_session.add(sm)


class TestReturnsApiCreate:
    def _create_sale(self, db_session, client, tenant, branch, warehouse, user, customer, product, quantity=5, unit_price=100, tax_rate=0):
        """Helper: create a sale via the sales route and return the sale object."""
        from models import Sale
        with client:
            resp = client.post('/auth/login', data={
                'username': user.username,
                'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            data = {
                'customer_id': str(customer.id),
                'line_count': '1',
                'lines[0][product_id]': str(product.id),
                'lines[0][quantity]': str(quantity),
                'lines[0][unit_price]': str(unit_price),
                'lines[0][discount_percent]': '0',
                'currency': 'AED',
                'warehouse_id': str(warehouse.id),
            }
            if tax_rate:
                data['tax_rate'] = str(tax_rate)

            resp = client.post('/sales/create', data=data, follow_redirects=False)

        assert resp.status_code == 302, f'Expected redirect, got {resp.status_code}'
        sale = Sale.query.filter_by(tenant_id=tenant.id).first()
        assert sale is not None
        return sale

    def test_return_reverses_stock_and_creates_gl(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer, Product, Warehouse, ProductWarehouseStock, SaleLine
        from services.gl_service import GLService
        from models.gl import GLJournalEntry
        from models import ProductReturn, ProductReturnLine

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(name=f'RT {tid}', name_ar=f'RT {tid}',
                        slug=f'ret-test-{tid}', default_currency='AED', base_currency='AED')
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch)
        db_session.flush()

        warehouse = Warehouse(tenant_id=tenant.id, name=f'WH {tid}', code=f'WH{tid[:4]}',
                              branch_id=branch.id, is_active=True, allow_negative_inventory=False)
        db_session.add(warehouse)
        db_session.flush()

        role = Role(name=f'Admin {tid}', slug=f'admin-{tid}', is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(username=f'retuser-{tid}', email=f'retuser-{tid}@t.com',
                    full_name='Ret User', role_id=role.id,
                    tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f'RetCust {tid}', phone=f'052{tid}')
        db_session.add(customer)
        db_session.flush()

        product = Product(name=f'RetItem {tid}', sku=f'RET-{tid}', tenant_id=tenant.id,
                          cost_price=Decimal('30'), regular_price=Decimal('100'),
                          current_stock=Decimal('50'), is_active=True)
        db_session.add(product)
        db_session.flush()

        stock = ProductWarehouseStock(tenant_id=tenant.id, product_id=product.id,
                                      warehouse_id=warehouse.id, quantity=Decimal('50'))
        db_session.add(stock)
        _add_initial_stock(db_session, product.id, warehouse.id, tenant.id, Decimal('50'))
        db_session.commit()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = self._create_sale(db_session, client, tenant, branch, warehouse, user, customer, product, quantity=3, unit_price=100)
        stock_after_sale = ProductWarehouseStock.query.filter_by(
            product_id=product.id, warehouse_id=warehouse.id).first()
        assert stock_after_sale.quantity == Decimal('47'), f'Expected 47 after sale, got {stock_after_sale.quantity}'

        sale_line = SaleLine.query.filter_by(sale_id=sale.id).first()
        assert sale_line is not None

        with client:
            import json
            resp = client.post('/returns/api/create', data=json.dumps({
                'sale_id': sale.id,
                'lines': [{'sale_line_id': sale_line.id, 'quantity': 2}],
            }), content_type='application/json', follow_redirects=False)

        assert resp.status_code == 200, f'Expected 200, got {resp.status_code}: {resp.data}'
        data = resp.get_json()
        assert data['success'] is True
        assert 'return_id' in data
        assert 'return_number' in data
        assert float(data['refund_amount']) == 200.0

        product_return = ProductReturn.query.get(data['return_id'])
        assert product_return is not None

        return_lines = ProductReturnLine.query.filter_by(return_id=product_return.id).all()
        assert len(return_lines) == 1
        assert return_lines[0].quantity == Decimal('2')
        assert return_lines[0].line_total == Decimal('200')

        stock_after_return = ProductWarehouseStock.query.filter_by(
            product_id=product.id, warehouse_id=warehouse.id).first()
        assert stock_after_return.quantity == Decimal('49'), f'Expected 49, got {stock_after_return.quantity}'

        gl_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == 'ProductReturn',
            GLJournalEntry.reference_id == product_return.id,
        ).all()
        assert len(gl_entries) >= 1
        total_debit = sum((e.total_debit or 0) for e in gl_entries)
        total_credit = sum((e.total_credit or 0) for e in gl_entries)
        assert total_debit == total_credit, f'GL unbalanced: debit={total_debit} credit={total_credit}'

        revenue_entries = [e for e in gl_entries if 'Sales Return' in (e.description or '')]
        cost_entries = [e for e in gl_entries if 'COGS' in (e.description or '')]
        assert len(revenue_entries) >= 1
        assert len(cost_entries) >= 1

        customer_after = Customer.query.get(customer.id)
        assert customer_after is not None
        assert customer_after.balance is not None

    def test_return_with_vat_reverses_tax_and_gl(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer, Product, Warehouse, ProductWarehouseStock, SaleLine
        from services.gl_service import GLService
        from models.gl import GLJournalEntry, GLJournalLine
        from models import ProductReturn, ProductReturnLine

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(name=f'RTX {tid}', name_ar=f'RTX {tid}',
                        slug=f'ret-tax-{tid}', default_currency='AED', base_currency='AED')
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch)
        db_session.flush()

        warehouse = Warehouse(tenant_id=tenant.id, name=f'WH {tid}', code=f'WH{tid[:4]}',
                              branch_id=branch.id, is_active=True)
        db_session.add(warehouse)
        db_session.flush()

        role = Role(name=f'Admin {tid}', slug=f'admin-{tid}', is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(username=f'retuser2-{tid}', email=f'retuser2-{tid}@t.com',
                    full_name='Ret User', role_id=role.id,
                    tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f'RetCst2 {tid}', phone=f'053{tid}')
        db_session.add(customer)
        db_session.flush()

        product = Product(name=f'RetItem2 {tid}', sku=f'RET2-{tid}', tenant_id=tenant.id,
                          cost_price=Decimal('40'), regular_price=Decimal('100'),
                          current_stock=Decimal('30'), is_active=True)
        db_session.add(product)
        db_session.flush()

        stock = ProductWarehouseStock(tenant_id=tenant.id, product_id=product.id,
                                      warehouse_id=warehouse.id, quantity=Decimal('30'))
        db_session.add(stock)
        _add_initial_stock(db_session, product.id, warehouse.id, tenant.id, Decimal('30'))
        db_session.commit()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = self._create_sale(db_session, client, tenant, branch, warehouse, user, customer, product, quantity=2, unit_price=100, tax_rate=5)

        sale_line = SaleLine.query.filter_by(sale_id=sale.id).first()
        assert sale_line is not None

        with client:
            import json
            resp = client.post('/returns/api/create', data=json.dumps({
                'sale_id': sale.id,
                'lines': [{'sale_line_id': sale_line.id, 'quantity': 1}],
            }), content_type='application/json', follow_redirects=False)

        assert resp.status_code == 200, f'Expected 200, got {resp.status_code}: {resp.data}'
        data = resp.get_json()
        assert data['success'] is True

        product_return = ProductReturn.query.get(data['return_id'])
        assert product_return is not None

        return_lines = ProductReturnLine.query.filter_by(return_id=product_return.id).all()
        assert len(return_lines) == 1
        assert return_lines[0].quantity == Decimal('1')

        gl_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == 'ProductReturn',
            GLJournalEntry.reference_id == product_return.id,
        ).all()
        assert len(gl_entries) >= 1

        total_debit = sum((e.total_debit or 0) for e in gl_entries)
        total_credit = sum((e.total_credit or 0) for e in gl_entries)
        assert total_debit == total_credit, f'GL unbalanced: debit={total_debit} credit={total_credit}'

        revenue_entry = None
        cost_entry = None
        for e in gl_entries:
            desc = (e.description or '')
            if 'Sales Return' in desc and 'COGS' not in desc:
                revenue_entry = e
            if 'COGS' in desc:
                cost_entry = e
        assert revenue_entry is not None, 'No revenue GL entry found'
        assert cost_entry is not None, 'No COGS GL entry found'

        rev_lines = GLJournalLine.query.filter_by(entry_id=revenue_entry.id).all()
        assert len(rev_lines) >= 2
        debits = [l.debit for l in rev_lines if (l.debit or 0) > 0]
        credits = [l.credit for l in rev_lines if (l.credit or 0) > 0]
        assert len(debits) >= 2
        assert len(credits) >= 1
        assert Decimal('5') in debits, f'Expected VAT debit 5 in {debits}'

    def test_return_full_quantity_reverses_entire_sale(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Customer, Product, Warehouse, ProductWarehouseStock, SaleLine
        from services.gl_service import GLService
        from models.gl import GLJournalEntry
        from models import ProductReturn, ProductReturnLine

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(name=f'RTF {tid}', name_ar=f'RTF {tid}',
                        slug=f'ret-full-{tid}', default_currency='AED', base_currency='AED')
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f'Main {tid}', code=f'BR{tid[:4]}')
        db_session.add(branch)
        db_session.flush()

        warehouse = Warehouse(tenant_id=tenant.id, name=f'WH {tid}', code=f'WH{tid[:4]}',
                              branch_id=branch.id, is_active=True)
        db_session.add(warehouse)
        db_session.flush()

        role = Role(name=f'Admin {tid}', slug=f'admin-{tid}', is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(username=f'retuser3-{tid}', email=f'retuser3-{tid}@t.com',
                    full_name='Ret User', role_id=role.id,
                    tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user)
        db_session.flush()

        customer = Customer(tenant_id=tenant.id, name=f'RetCst3 {tid}', phone=f'054{tid}')
        db_session.add(customer)
        db_session.flush()

        product = Product(name=f'RetItem3 {tid}', sku=f'RET3-{tid}', tenant_id=tenant.id,
                          cost_price=Decimal('25'), regular_price=Decimal('100'),
                          current_stock=Decimal('20'), is_active=True)
        db_session.add(product)
        db_session.flush()

        stock = ProductWarehouseStock(tenant_id=tenant.id, product_id=product.id,
                                      warehouse_id=warehouse.id, quantity=Decimal('20'))
        db_session.add(stock)
        _add_initial_stock(db_session, product.id, warehouse.id, tenant.id, Decimal('20'))
        db_session.commit()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        sale = self._create_sale(db_session, client, tenant, branch, warehouse, user, customer, product, quantity=4, unit_price=50)

        sale_line = SaleLine.query.filter_by(sale_id=sale.id).first()
        assert sale_line is not None
        stock_before_return = ProductWarehouseStock.query.filter_by(
            product_id=product.id, warehouse_id=warehouse.id).first()
        assert stock_before_return.quantity == Decimal('16'), f'Expected 16 after sale, got {stock_before_return.quantity}'

        with client:
            import json
            resp = client.post('/returns/api/create', data=json.dumps({
                'sale_id': sale.id,
                'lines': [{'sale_line_id': sale_line.id, 'quantity': 4}],
            }), content_type='application/json', follow_redirects=False)

        assert resp.status_code == 200, f'Expected 200, got {resp.status_code}: {resp.data}'
        data = resp.get_json()
        assert data['success'] is True
        assert float(data['refund_amount']) == 200.0

        stock_after_return = ProductWarehouseStock.query.filter_by(
            product_id=product.id, warehouse_id=warehouse.id).first()
        assert stock_after_return.quantity == Decimal('20'), f'Expected 20 (full revert), got {stock_after_return.quantity}'

        gl_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == 'ProductReturn',
            GLJournalEntry.reference_id == data['return_id'],
        ).all()
        assert len(gl_entries) >= 1
        total_debit = sum((e.total_debit or 0) for e in gl_entries)
        total_credit = sum((e.total_credit or 0) for e in gl_entries)
        assert total_debit == total_credit
