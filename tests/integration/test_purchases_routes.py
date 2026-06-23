"""
Integration tests: Purchases routes — real business logic via POST /purchases/create.
"""
import pytest
import uuid
from decimal import Decimal


class TestPurchasesCreate:
    def test_create_purchase_increases_stock_and_creates_payable(self, app, db_session, client):
        from models import Tenant, Branch, User, Role, Supplier, Product, Warehouse, ProductWarehouseStock
        from services.gl_service import GLService
        from models.gl import GLJournalEntry
        from utils.gl_reference_types import GLRef

        tid = str(uuid.uuid4())[:8]
        tenant = Tenant(name=f'PT {tid}', name_ar=f'PT {tid}',
                        slug=f'pur-test-{tid}', default_currency='AED', base_currency='AED')
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

        user = User(username=f'buyer-{tid}', email=f'buyer-{tid}@t.com',
                    full_name='Buyer', role_id=role.id,
                    tenant_id=tenant.id, branch_id=branch.id,
                    is_active=True, is_owner=True)
        user.set_password('x')
        db_session.add(user)
        db_session.flush()

        supplier = Supplier(tenant_id=tenant.id, name=f'Supp {tid}', phone=f'052{tid}')
        db_session.add(supplier)
        db_session.flush()

        product = Product(name=f'Mat {tid}', sku=f'MAT-{tid}', tenant_id=tenant.id,
                          cost_price=Decimal('30'), regular_price=Decimal('60'),
                          current_stock=Decimal('10'), is_active=True)
        db_session.add(product)
        db_session.flush()

        stock = ProductWarehouseStock(tenant_id=tenant.id, product_id=product.id,
                                      warehouse_id=warehouse.id, quantity=Decimal('10'))
        db_session.add(stock)
        db_session.commit()

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        with client:
            resp = client.post('/auth/login', data={
                'username': user.username,
                'password': 'x',
            }, follow_redirects=True)
            assert resp.status_code == 200

            resp = client.post('/purchases/create', data={
                'warehouse_id': str(warehouse.id),
                'supplier_id': str(supplier.id),
                'line_count': '1',
                'lines[0][product_id]': str(product.id),
                'lines[0][quantity]': '20',
                'lines[0][unit_cost]': '30',
                'lines[0][discount_percent]': '0',
                'currency': 'AED',
            }, follow_redirects=False)

        assert resp.status_code == 302, f'Expected redirect, got {resp.status_code}'

        from models import Purchase
        purchase = Purchase.query.filter_by(tenant_id=tenant.id).first()
        assert purchase is not None, 'Purchase was not created'
        assert purchase.total_amount == Decimal('600'), f'total={purchase.total_amount}'

        stock_after = ProductWarehouseStock.query.filter_by(
            product_id=product.id, warehouse_id=warehouse.id).first()
        assert stock_after.quantity == Decimal('30'), f'Expected 30, got {stock_after.quantity}'

        gl_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == GLRef.PURCHASE,
            GLJournalEntry.reference_id == purchase.id,
        ).all()
        assert len(gl_entries) >= 1, f'Expected >=1 GL entry, got {len(gl_entries)}'
        total_debit = sum((e.total_debit or 0) for e in gl_entries)
        total_credit = sum((e.total_credit or 0) for e in gl_entries)
        assert total_debit == total_credit == Decimal('600'), \
            f'GL unbalanced: debit={total_debit} credit={total_credit}'
