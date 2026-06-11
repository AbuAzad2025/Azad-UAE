import random
import sys
import os
from decimal import Decimal
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def seed():
    from app import create_app
    from extensions import db
    from models import (
        Tenant, User, Role, Warehouse, ProductCategory, Product,
        Customer, Supplier, Sale, SaleLine, Purchase, PurchaseLine,
        Payment, ExpenseCategory, Expense, Cheque, GLAccount,
    )
    from services.gl_accounting_setup import GLAccountingSetupService
    from utils.helpers import generate_number

    app = create_app()
    with app.app_context():
        tenant = Tenant.query.filter_by(slug='demo-seed-v3').first()
        if tenant and Product.query.filter_by(tenant_id=tenant.id).first():
            print('Seed already exists (demo-seed-v3) with products.')
            return

        tenant = Tenant(
            name='شركة التجارة الذكية التجريبية v3',
            name_ar='شركة التجارة الذكية التجريبية v3',
            slug='demo-seed-v3',
            country='UAE',
            default_currency='AED',
            tax_number='1234567890',
            phone_1='0500000000',
            email='demo@example.com',
            address_ar='دبي، الإمارات العربية المتحدة',
            is_active=True,
        )
        db.session.add(tenant)
        db.session.flush()

        role_owner = Role.query.filter_by(slug='owner').first()
        if not role_owner:
            role_owner = Role(name='Seed Owner', slug='seed_owner', is_active=True)
            db.session.add(role_owner)
            db.session.flush()
        role_seller = Role.query.filter_by(slug='seller').first()
        if not role_seller:
            role_seller = Role(name='Seed Seller', slug='seed_seller', is_active=True)
            db.session.add(role_seller)
            db.session.flush()
        role_accountant = Role.query.filter_by(slug='accountant').first()
        if not role_accountant:
            role_accountant = Role(name='Seed Accountant', slug='seed_accountant', is_active=True)
            db.session.add(role_accountant)
            db.session.flush()

        owner = User(
            username=f'seed_owner_{tenant.id}',
            email=f'owner{tenant.id}@example.com',
            full_name='أحمد المالك',
            tenant_id=tenant.id,
            role_id=role_owner.id,
            is_active=True,
            is_owner=True,
        )
        owner.set_password('password123')
        seller = User(
            username=f'seed_seller_{tenant.id}',
            email=f'seller{tenant.id}@example.com',
            full_name='محمد البائع',
            tenant_id=tenant.id,
            role_id=role_seller.id,
            is_active=True,
        )
        seller.set_password('password123')
        accountant = User(
            username=f'seed_accountant_{tenant.id}',
            email=f'accountant{tenant.id}@example.com',
            full_name='فاطمة المحاسبة',
            tenant_id=tenant.id,
            role_id=role_accountant.id,
            is_active=True,
        )
        accountant.set_password('password123')
        db.session.add_all([owner, seller, accountant])
        db.session.flush()

        warehouse = Warehouse(
            tenant_id=tenant.id,
            name='المستودع الرئيسي',
            name_ar='المستودع الرئيسي',
            location='دبي',
            is_main=True,
            is_active=True,
        )
        db.session.add(warehouse)
        db.session.flush()

        categories = [
            'إلكترونيات',
            'مواد بناء',
            'أدوات منزلية',
            'ملابس',
            'مواد غذائية',
        ]
        cats = []
        for name in categories:
            c = ProductCategory(tenant_id=tenant.id, name=name, name_ar=name, is_active=True)
            db.session.add(c)
            cats.append(c)
        db.session.flush()

        products = []
        product_data = [
            ('هاتف ذكي', 0, 1200, 800, 50),
            ('لابتوب', 0, 3500, 2500, 30),
            ('سماعات بلوتوث', 0, 150, 80, 100),
            ('أسمنت', 1, 25, 15, 500),
            ('حديد تسليح', 1, 180, 120, 200),
            ('دهان جدران', 1, 45, 25, 150),
            ('ثلاجة', 2, 2200, 1500, 20),
            ('مكيف', 2, 1800, 1200, 25),
            ('غسالة', 2, 1400, 900, 15),
            ('قميص', 3, 80, 35, 200),
            ('بنطلون', 3, 120, 50, 150),
            ('فستان', 3, 200, 80, 100),
            ('أرز', 4, 30, 18, 300),
            ('سكر', 4, 25, 12, 400),
            ('زيت طعام', 4, 40, 22, 250),
        ]
        for name, cat_idx, price, cost, qty in product_data:
            cat = cats[cat_idx] if cat_idx < len(cats) else cats[0]
            p = Product(
                tenant_id=tenant.id,
                name=name,
                name_ar=name,
                sku=f'SKU-{random.randint(1000,9999)}',
                barcode=f'{random.randint(100000000,999999999)}',
                regular_price=Decimal(str(price)),
                cost_price=Decimal(str(cost)),
                category_id=cat.id,
                unit='قطعة',
                is_active=True,
                has_serial_number=cat_idx == 0,
                warranty_days=365 if cat_idx == 0 else 0,
            )
            db.session.add(p)
            products.append(p)
        db.session.flush()

        customers = []
        customer_names = [
            'شركة النور', 'مؤسسة الصقر', 'محل البركة', 'مؤسسة السلام',
            'شركة الرؤية', 'محل الزهور', 'مؤسسة الاتحاد', 'شركة الأمل',
        ]
        for name in customer_names:
            c = Customer(
                tenant_id=tenant.id,
                name=name,
                phone=f'05{random.randint(10000000,99999999)}',
                email=f'contact{random.randint(1,999)}@example.com',
                address='دبي، الإمارات العربية المتحدة',
                customer_type=random.choice(['regular', 'wholesale', 'retail']),
                is_active=True,
            )
            db.session.add(c)
            customers.append(c)
        db.session.flush()

        suppliers = []
        supplier_names = [
            'مصنع الإمارات', 'شركة الاستيراد الكبرى', 'مؤسسة التوريد', 'شركة التوزيع',
            'مصنع الخليج', 'مؤسسة الاستيراد', 'شركة البضائع', 'مورد العالم',
        ]
        for name in supplier_names:
            s = Supplier(
                tenant_id=tenant.id,
                name=name,
                name_ar=name,
                phone=f'05{random.randint(10000000,99999999)}',
                email=f'contact{random.randint(1,999)}@example.com',
                address='دبي، الإمارات العربية المتحدة',
                is_active=True,
            )
            db.session.add(s)
            suppliers.append(s)
        db.session.flush()

        GLAccountingSetupService.execute(tenant_id=tenant.id, dry_run=False)

        for i in range(5):
            sale = Sale(
                tenant_id=tenant.id,
                sale_number=generate_number('S', Sale, 'sale_number', tenant_id=tenant.id),
                customer_id=random.choice(customers).id,
                seller_id=random.choice([seller.id, owner.id]),
                warehouse_id=warehouse.id,
                branch_id=warehouse.branch_id,
                currency='AED',
                exchange_rate=Decimal('1'),
                discount_amount=Decimal('0'),
                shipping_cost=Decimal('0'),
                tax_rate=Decimal('5'),
                total_amount=Decimal('0'),
                amount=Decimal('0'),
                amount_aed=Decimal('0'),
                status='confirmed',
                payment_status=random.choice(['paid', 'partial', 'unpaid']),
                source='internal',
                is_active=True,
                sale_date=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 30)),
            )
            db.session.add(sale)
            db.session.flush()
            for j in range(random.randint(1, 3)):
                prod = random.choice(products)
                qty = random.randint(1, 5)
                line = SaleLine(
                    tenant_id=tenant.id,
                    sale_id=sale.id,
                    product_id=prod.id,
                    quantity=qty,
                    unit_price=prod.regular_price,
                    discount_percent=Decimal('0'),
                    cost_price=prod.cost_price,
                    line_total=Decimal(str(qty)) * prod.regular_price,
                )
                db.session.add(line)
            subtotal = sum(line.line_total for line in sale.lines)
            sale.subtotal = subtotal
            sale.tax_amount = (subtotal * Decimal('0.05')).quantize(Decimal('0.01'))
            sale.total_amount = (subtotal + sale.tax_amount).quantize(Decimal('0.001'))
            sale.amount = sale.total_amount
            sale.amount_aed = sale.total_amount
            sale.balance_due = sale.total_amount
            db.session.add(sale)

        for i in range(3):
            purchase = Purchase(
                tenant_id=tenant.id,
                purchase_number=generate_number('P', Purchase, 'purchase_number', tenant_id=tenant.id),
                supplier_id=random.choice(suppliers).id,
                warehouse_id=warehouse.id,
                branch_id=warehouse.branch_id,
                supplier_name=random.choice(suppliers).name,
                currency='AED',
                exchange_rate=Decimal('1'),
                discount_amount=Decimal('0'),
                tax_rate=Decimal('5'),
                total_amount=Decimal('0'),
                amount=Decimal('0'),
                amount_aed=Decimal('0'),
                status='confirmed',
                user_id=owner.id,
                is_active=True,
            )
            db.session.add(purchase)
            db.session.flush()
            for j in range(random.randint(1, 3)):
                prod = random.choice(products)
                qty = random.randint(10, 50)
                unit_cost = prod.cost_price * Decimal('0.9')
                line = PurchaseLine(
                    tenant_id=tenant.id,
                    purchase_id=purchase.id,
                    product_id=prod.id,
                    quantity=qty,
                    unit_cost=unit_cost,
                    discount_percent=Decimal('0'),
                    line_total=Decimal(str(qty)) * unit_cost,
                )
                db.session.add(line)
            subtotal = sum(line.line_total for line in purchase.lines)
            purchase.subtotal = subtotal
            purchase.tax_amount = (subtotal * Decimal('0.05')).quantize(Decimal('0.01'))
            purchase.total_amount = (subtotal + purchase.tax_amount).quantize(Decimal('0.001'))
            purchase.amount = purchase.total_amount
            purchase.amount_aed = purchase.total_amount
            db.session.add(purchase)

        payment_methods = ['cash', 'bank_transfer', 'cheque', 'credit_card']
        for i in range(8):
            payment = Payment(
                tenant_id=tenant.id,
                payment_number=generate_number('PMT', Payment, 'payment_number', tenant_id=tenant.id),
                customer_id=random.choice(customers).id if random.random() > 0.3 else None,
                supplier_id=random.choice(suppliers).id if random.random() > 0.7 else None,
                amount=Decimal(str(random.randint(100, 5000))),
                amount_aed=Decimal(str(random.randint(100, 5000))),
                currency='AED',
                payment_method=random.choice(payment_methods),
                payment_date=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 30)),
                status='confirmed',
                payment_confirmed=True,
                is_active=True,
            )
            db.session.add(payment)
        db.session.flush()

        expense_cats = [
            ('إيجار', 'rent'),
            ('رواتب', 'salaries'),
            ('كهرباء', 'electricity'),
            ('ماء', 'water'),
            ('صيانة', 'maintenance'),
            ('وقود', 'fuel'),
            ('إنترنت', 'internet'),
            ('إعلانات', 'advertising'),
        ]
        ecats = []
        for name, slug in expense_cats:
            ec = ExpenseCategory(tenant_id=tenant.id, name=name, name_ar=name, slug=slug, is_active=True)
            db.session.add(ec)
            ecats.append(ec)
        db.session.flush()

        for i in range(10):
            exp = Expense(
                tenant_id=tenant.id,
                expense_number=generate_number('EXP', Expense, 'expense_number', tenant_id=tenant.id),
                category_id=random.choice(ecats).id,
                amount=Decimal(str(random.randint(50, 2000))),
                amount_aed=Decimal(str(random.randint(50, 2000))),
                currency='AED',
                expense_date=datetime.now(timezone.utc) - timedelta(days=random.randint(0, 60)),
                status='approved',
                payment_method=random.choice(payment_methods),
                is_active=True,
                notes='ملاحظات إدارية',
            )
            db.session.add(exp)
        db.session.flush()

        cheque_banks = ['بنك الإمارات دبي الوطني', 'بنك أبوظبي الأول', 'بنك دبي الإسلامي', 'مصرف الراجحي']
        cheque_statuses = ['received', 'issued', 'cleared', 'bounced', 'cancelled']
        for i in range(10):
            status = random.choice(cheque_statuses)
            ch = Cheque(
                tenant_id=tenant.id,
                cheque_number=f'CHQ{random.randint(100000,999999)}',
                bank_name=random.choice(cheque_banks),
                amount=Decimal(str(random.randint(500, 10000))),
                amount_aed=Decimal(str(random.randint(500, 10000))),
                currency='AED',
                cheque_date=datetime.now(timezone.utc) + timedelta(days=random.randint(-10, 30)),
                status=status,
                cheque_type='incoming' if status in ['received', 'cleared', 'bounced'] else 'outgoing',
                customer_id=random.choice(customers).id if random.random() > 0.5 else None,
                supplier_id=random.choice(suppliers).id if random.random() > 0.5 else None,
                notes='ملاحظات إدارية',
                is_active=True,
            )
            if status == 'cleared':
                ch.clearance_date = datetime.now(timezone.utc)
            elif status == 'bounced':
                ch.bounce_date = datetime.now(timezone.utc)
                ch.bounce_reason = 'لا يوجد رصيد كافي'
            db.session.add(ch)
        db.session.flush()

        db.session.commit()
        print(f'Seeded: tenant={tenant.id}, products={len(products)}, customers={len(customers)}, suppliers={len(suppliers)}, sales=5, purchases=3, payments=8, expenses=10, cheques=10')


if __name__ == '__main__':
    seed()
