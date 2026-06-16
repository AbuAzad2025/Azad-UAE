import traceback, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def main():
    from app import create_app
    from extensions import db
    from services.gl_service import GLService
    from services.gl_provisioning_service import GLProvisioningService
    from services.stock_service import StockService
    from models import Tenant, Branch, User, Customer, Supplier, Product, Warehouse, ProductWarehouseCost, Role, Sale, Payment, Cheque
    from decimal import Decimal

    app = create_app()
    with app.app_context():
        tid = Tenant.query.order_by(Tenant.id).first()
        if not tid:
            tid = Tenant(name='RecTest', name_ar='RecTest', slug='rectest', email='r@t.com', phone_1='0500000000', country='AE', subscription_plan='basic')
            db.session.add(tid)
            db.session.flush()
        tenant_id = tid.id
        GLService.ensure_core_accounts(tenant_id=tenant_id)
        GLProvisioningService.provision_tenant(tenant_id)

        branch = Branch.query.filter_by(tenant_id=tenant_id).first()
        if not branch:
            branch = Branch(tenant_id=tenant_id, name='Main', code='MAIN')
            db.session.add(branch)
            db.session.flush()

        role = Role.query.filter_by(slug='owner').first()
        if not role:
            role = Role(name='Owner', slug='owner')
            db.session.add(role)
            db.session.flush()

        user = User.query.filter_by(tenant_id=tenant_id).first()
        if not user:
            user = User(tenant_id=tenant_id, username='rectestuser', email='u@t.com', full_name='Test', is_active=True, is_owner=True, branch_id=branch.id, role_id=role.id)
            user.set_password('p')
            db.session.add(user)
            db.session.flush()

        customer = Customer.query.filter_by(tenant_id=tenant_id).first()
        if not customer:
            customer = Customer(tenant_id=tenant_id, name='Test Customer', phone='0500000001')
            db.session.add(customer)
            db.session.flush()

        product = Product.query.filter_by(tenant_id=tenant_id, name='Reconciliation Test Product').first()
        if not product:
            product = Product(tenant_id=tenant_id, name='Reconciliation Test Product', current_stock=0, cost_price=Decimal('600'), regular_price=Decimal('1000'), has_serial_number=False)
            db.session.add(product)
            db.session.flush()

        wh = Warehouse.query.filter_by(tenant_id=tenant_id).first()
        if not wh:
            wh = Warehouse(tenant_id=tenant_id, name='Test WH', code='TWH', branch_id=branch.id)
            db.session.add(wh)
            db.session.flush()

        pwc = ProductWarehouseCost.query.filter_by(tenant_id=tenant_id, product_id=product.id, warehouse_id=wh.id).first()
        if not pwc:
            pwc = ProductWarehouseCost(tenant_id=tenant_id, product_id=product.id, warehouse_id=wh.id, total_quantity=Decimal('0'), total_value=Decimal('0'), average_cost=Decimal('0'))
            db.session.add(pwc)
            db.session.flush()

        StockService.add_stock(product.id, Decimal('100'), reference_type='adjustment', reference_id=1, warehouse_id=wh.id)
        db.session.commit()

        from services.sale_service import SaleService
        sale = SaleService.create_sale(
            customer=customer,
            seller=user,
            lines_data=[{'product': product, 'quantity': 1, 'unit_price': Decimal('1000')}],
            warehouse_id=wh.id,
            tax_rate=Decimal('5'),
        )
        db.session.commit()
        print('Sale created OK')

        payment = SaleService.create_payment_for_sale(
            sale=sale,
            amount=Decimal('1050'),
            payment_method='cheque',
            currency='AED',
            exchange_rate=1.0,
            cheque_number='CHK001',
            cheque_date=str(__import__('datetime').date.today() + __import__('datetime').timedelta(days=30)),
            bank_name='Test Bank',
        )
        db.session.commit()
        print('Payment created OK')

        from services.cheque_service import process_cheque_clear
        cheque = Cheque.query.filter_by(cheque_number='CHK001', tenant_id=tenant_id).first()
        print(f'Cheque found: {cheque}')
        process_cheque_clear(cheque)
        db.session.commit()
        print('Cheque clear OK')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
