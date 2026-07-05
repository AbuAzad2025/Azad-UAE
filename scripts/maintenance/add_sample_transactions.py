"""Add sample sales and purchases to existing professional seeds."""
import sys
sys.path.insert(0, r'D:\Data\karaj\UAE\Azad-UAE')

from app import create_app
from extensions import db
from decimal import Decimal
from datetime import timezone

app = create_app()
with app.app_context():
    from models import Tenant, Customer, Supplier, Product, User, Warehouse
    from services.sale_service import SaleService
    from services.purchase_service import PurchaseService
    from models.sale import Sale

    tenant = Tenant.query.first()
    if not tenant:
        print('No tenant found!')
        sys.exit(1)
    tenant_id = tenant.id

    # Fix walk-in customer to be active
    walkin = Customer.query.filter_by(tenant_id=tenant_id, customer_type='walkin').first()
    if walkin and not walkin.is_active:
        walkin.is_active = True
        db.session.commit()
        print(f'Fixed walk-in customer active status: {walkin.id}')

    customers = Customer.query.filter_by(tenant_id=tenant_id, is_active=True).all()
    suppliers = Supplier.query.filter_by(tenant_id=tenant_id).all()
    products = Product.query.filter_by(tenant_id=tenant_id, is_active=True).all()
    users = User.query.filter_by(tenant_id=tenant_id, is_active=True).all()
    warehouses = Warehouse.query.filter_by(tenant_id=tenant_id, is_active=True).all()

    if not customers:
        print('No active customers found!')
        sys.exit(1)
    if not suppliers:
        print('No suppliers found!')
        sys.exit(1)
    if not products:
        print('No products found!')
        sys.exit(1)

    owner_user = next((u for u in users if u.username == 'owner'), users[0])
    sales_user = next((u for u in users if u.username == 'sales'), users[0])
    wh = next((w for w in warehouses if w.warehouse_type == 'physical'), warehouses[0])

    # Create sales
    existing_sales = Sale.query.filter_by(tenant_id=tenant_id).count()
    if existing_sales == 0:
        for i in range(3):
            customer = customers[i % len(customers)]
            try:
                sale = SaleService.create_sale(
                    customer=customer,
                    seller=sales_user,
                    lines_data=[
                        {'product': products[i], 'quantity': 2, 'discount_percent': 0, 'unit_price': None},
                        {'product': products[(i+1) % len(products)], 'quantity': 1, 'discount_percent': 5, 'unit_price': None},
                    ],
                    warehouse_id=wh.id,
                    currency='AED',
                    user_exchange_rate=1,
                    payment_data={'amount': 0, 'payment_method': '', 'currency': 'AED', 'exchange_rate': 1} if i == 2 else None,
                )
                db.session.commit()
                print(f'Sale {i+1} created: {sale.sale_number}')
            except Exception as e:
                db.session.rollback()
                print(f'  Sale {i+1} error: {e}')
    else:
        print(f'Sales already exist: {existing_sales}')

    # Create purchases
    from models.purchase import Purchase
    existing_purchases = Purchase.query.filter_by(tenant_id=tenant_id).count()
    if existing_purchases == 0:
        supplier = suppliers[0]
        for i in range(2):
            try:
                purchase = PurchaseService.create_purchase(
                    user=owner_user,
                    supplier_data={'id': supplier.id},
                    lines_data=[
                        {'product_id': products[i].id, 'quantity': 10, 'unit_price': products[i].cost_price * Decimal('0.9') if products[i].cost_price else Decimal('100')},
                        {'product_id': products[(i+2) % len(products)].id, 'quantity': 5, 'unit_price': products[(i+2) % len(products)].cost_price * Decimal('0.9') if products[(i+2) % len(products)].cost_price else Decimal('100')},
                    ],
                    warehouse_id=wh.id,
                    currency='AED',
                )
                db.session.commit()
                print(f'Purchase {i+1} created: {purchase.purchase_number}')
            except Exception as e:
                db.session.rollback()
                print(f'  Purchase {i+1} error: {e}')
    else:
        print(f'Purchases already exist: {existing_purchases}')

    print('\nDone!')
