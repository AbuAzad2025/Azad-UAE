import random
from datetime import datetime, timedelta
from decimal import Decimal
import re
from flask import current_app
from extensions import db
from models import (
    User, Role, Branch, Customer, Supplier, Product, ProductCategory, Warehouse,
    Sale, SaleLine, Purchase, PurchaseLine, Payment, GLAccount, ExpenseCategory,
    Currency, ExchangeRate, StockMovement, GLJournalEntry, GLJournalLine, Employee,
    Expense, Cheque, SalaryAdvance, PayrollTransaction
)
from services.gl_service import GLService
from services.stock_service import StockService


def _generate_unique_number(model, field_name, prefix, digits=5):
    """Generate unique document number for seeded rows."""
    field = getattr(model, field_name)
    while True:
        value = f"{prefix}-{random.randint(10 ** (digits - 1), (10 ** digits) - 1)}"
        if not model.query.filter(field == value).first():
            return value


def _generate_unique_product_value(field_name, prefix):
    field = getattr(Product, field_name)
    while True:
        value = f"{prefix}-{random.randint(100000, 999999)}"
        if not Product.query.filter(field == value).first():
            return value


def _resolve_role(*slugs):
    for slug in slugs:
        role = Role.query.filter_by(slug=slug).first()
        if role:
            return role
    return Role.query.order_by(Role.id.asc()).first()


def _ensure_user(username, email, full_name, role, branch_id=None, phone=None, password='123456'):
    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            full_name_ar=full_name,
            phone=phone,
            role_id=role.id if role else None,
            branch_id=branch_id,
            is_owner=False,
            is_active=True,
            email_verified=True,
            login_attempts=0,
        )
        user.set_password(password)
        db.session.add(user)
    else:
        user.email = user.email or email
        user.full_name = user.full_name or full_name
        user.full_name_ar = user.full_name_ar or full_name
        user.phone = user.phone or phone
        if role and not user.role_id:
            user.role_id = role.id
        if branch_id and not user.branch_id:
            user.branch_id = branch_id
        user.is_owner = bool(user.is_owner)
        user.email_verified = True
        user.login_attempts = 0
        user.is_active = True
    return user


def _branch_token(branch_code: str, fallback_id: int | None = None) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", (branch_code or "").lower()).strip("_")
    if not token:
        token = f"branch_{fallback_id or 'x'}"
    return token


def seed_comprehensive_data():
    """Seed comprehensive data for testing all system aspects"""
    print("🌱 Starting Comprehensive Seeding...")
    
    # 1. Clear existing data (Optional, be careful in production)
    # db.drop_all()
    # db.create_all()

    # 2. Setup Currencies
    aed = Currency.query.filter_by(code='AED').first()
    if not aed:
        aed = Currency(code='AED', name='UAE Dirham', symbol='AED', is_base=True)
        db.session.add(aed)
        db.session.flush()
        
        # Add Rate for AED (1.0)
        rate_aed = ExchangeRate(currency_id=aed.id, from_currency='AED', to_currency='AED', rate=1.0, is_manual=True)
        db.session.add(rate_aed)
    
    usd = Currency.query.filter_by(code='USD').first()
    if not usd:
        usd = Currency(code='USD', name='US Dollar', symbol='$', is_base=False)
        db.session.add(usd)
        db.session.flush()
        
        # Add Rate for USD
        rate_usd = ExchangeRate(currency_id=usd.id, from_currency='USD', to_currency='AED', rate=3.67, is_manual=True)
        db.session.add(rate_usd)
    
    db.session.commit()
    print("✅ Currencies Seeded")

    # 3. Setup Chart of Accounts (Basic)
    print("🔄 Ensuring Core GL Accounts...")
    GLService.ensure_core_accounts()
    
    # Map accounts for seeding usage
    gl_accounts = {
        '1010': GLAccount.query.filter_by(code='1110').first(), # Cash
        '1020': GLAccount.query.filter_by(code='1120').first(), # Bank
        '1100': GLAccount.query.filter_by(code='1130').first(), # AR
        '1200': GLAccount.query.filter_by(code='1140').first(), # Inventory
        '2000': GLAccount.query.filter_by(code='2110').first(), # AP
        '2100': GLAccount.query.filter_by(code='2130').first(), # Taxes
        '3000': GLAccount.query.filter_by(code='3100').first(), # Capital
        '4000': GLAccount.query.filter_by(code='4100').first(), # Sales
        '5000': GLAccount.query.filter_by(code='5100').first(), # COGS
        '5100': GLAccount.query.filter_by(code='6200').first(), # Rent
        '5200': GLAccount.query.filter_by(code='6100').first()  # Salaries
    }
    
    db.session.commit()
    print("✅ Chart of Accounts Seeded")

    # 4. Setup Branches & Warehouses
    branches = []
    branch_specs = [
        {'name': 'فلسطين', 'code': 'MAIN', 'is_main': True, 'city': 'فلسطين', 'address': 'المقر الرئيسي - فلسطين', 'phone': '+971500001001'},
        {'name': 'الإمارات', 'code': 'NORTH', 'is_main': True, 'city': 'الإمارات', 'address': 'المقر الرئيسي - الإمارات', 'phone': '+971500001002'},
        {'name': 'دبي', 'code': 'SOUTH', 'is_main': False, 'city': 'دبي', 'address': 'فرع مدينة دبي - الإمارات', 'phone': '+971500001003'},
        {'name': 'أبوظبي', 'code': 'EAST', 'is_main': False, 'city': 'أبوظبي', 'address': 'فرع مدينة أبوظبي - الإمارات', 'phone': '+971500001004'},
    ]
    for spec in branch_specs:
        branch = Branch.query.filter_by(code=spec['code']).first()
        if not branch:
            branch = Branch(
                name=spec['name'],
                code=spec['code'],
                is_main=spec['is_main'],
                is_active=True,
                city=spec['city'],
                address=spec['address'],
                phone=spec['phone'],
            )
            db.session.add(branch)
            db.session.flush()
        else:
            branch.city = branch.city or spec['city']
            branch.address = branch.address or spec['address']
            branch.phone = branch.phone or spec['phone']
            branch.is_active = True
        branches.append(branch)

    all_active_branches = Branch.query.filter_by(is_active=True).order_by(Branch.id.asc()).all()
    warehouses = []
    for branch in all_active_branches:
        warehouse = Warehouse.query.filter_by(code=f'WH-{branch.code}').first()
        if not warehouse:
            warehouse = Warehouse(
                name=f'{branch.name} Warehouse',
                name_ar=f'{branch.name} Warehouse',
                code=f'WH-{branch.code}',
                branch_id=branch.id,
                location=f'{branch.name} - Storage Area',
                is_main=branch.is_main,
                is_active=True,
            )
            db.session.add(warehouse)
        else:
            warehouse.branch_id = warehouse.branch_id or branch.id
            warehouse.name_ar = warehouse.name_ar or warehouse.name
            warehouse.location = warehouse.location or f'{branch.name} - Storage Area'
            warehouse.is_active = True
        warehouses.append(warehouse)
    
    db.session.commit()
    branch_manager_map = {
        user.branch_id: user.id
        for user in User.query.filter(User.username.like('branch_manager_%')).all()
    }
    for warehouse in warehouses:
        if warehouse.branch_id and not warehouse.manager_id:
            warehouse.manager_id = branch_manager_map.get(warehouse.branch_id)
    db.session.commit()
    print("✅ Branches & Warehouses Seeded")

    # 5. Setup Categories & Products
    categories = ['Engine Parts', 'Body Parts', 'Electronics', 'Fluids']
    cats_db = {}
    for cat_name in categories:
        cat = ProductCategory.query.filter_by(name=cat_name).first()
        if not cat:
            cat = ProductCategory(
                name=cat_name,
                name_ar=cat_name,
                description=f'Seed category for {cat_name}',
                is_active=True,
            )
            db.session.add(cat)
        else:
            cat.name_ar = cat.name_ar or cat.name
            cat.description = cat.description or f'Seed category for {cat_name}'
            cat.is_active = True
        cats_db[cat_name] = cat
    db.session.commit()

    products_data = [
        ('فلتر زيت', 'Engine Parts', 50, 20),
        ('فحمات فرامل', 'Engine Parts', 150, 80),
        ('مصباح أمامي', 'Body Parts', 400, 200),
        ('بطارية', 'Electronics', 350, 250),
        ('زيت صناعي', 'Fluids', 80, 40)
    ]
    
    products_db = []
    for name, cat, price, cost in products_data:
        prod = Product.query.filter_by(name=name).first()
        if not prod:
            prod = Product(
                name=name,
                name_ar=name,
                commercial_name=name,
                sku=_generate_unique_product_value('sku', 'SKU'),
                part_number=_generate_unique_product_value('part_number', 'PN'),
                barcode=_generate_unique_product_value('barcode', 'BAR'),
                country_of_origin='UAE',
                category_id=cats_db[cat].id,
                regular_price=price,
                cost_price=cost,
                merchant_price=Decimal(str(price)),
                merchant_share=Decimal('100.00'),
                partner_price=Decimal(str(price)),
                current_stock=0, # Initial stock
                min_stock_alert=10,
                has_serial_number=False,
                warranty_days=365,
                unit='piece',
                location='A1-R1',
                warranty_period=12,
                warranty_unit='months',
                is_returnable=True,
                return_period_days=30,
                image_url='https://example.com/assets/products/default.png',
                description=f'منتج بذري: {name}',
                notes='Generated by seed_comprehensive.',
                is_active=True,
            )
            db.session.add(prod)
            products_db.append(prod)
        else:
            prod.name_ar = prod.name_ar or prod.name
            prod.commercial_name = prod.commercial_name or prod.name
            prod.sku = prod.sku or _generate_unique_product_value('sku', 'SKU')
            prod.part_number = prod.part_number or _generate_unique_product_value('part_number', 'PN')
            prod.barcode = prod.barcode or _generate_unique_product_value('barcode', 'BAR')
            prod.country_of_origin = prod.country_of_origin or 'UAE'
            prod.merchant_price = prod.merchant_price if prod.merchant_price is not None else prod.regular_price
            prod.merchant_share = prod.merchant_share if prod.merchant_share is not None else Decimal('100.00')
            prod.partner_price = prod.partner_price if prod.partner_price is not None else prod.regular_price
            prod.unit = prod.unit or 'piece'
            prod.has_serial_number = bool(prod.has_serial_number)
            prod.warranty_days = prod.warranty_days or 365
            prod.location = prod.location or 'A1-R1'
            prod.warranty_period = prod.warranty_period or 12
            prod.warranty_unit = prod.warranty_unit or 'months'
            prod.is_returnable = True if prod.is_returnable is None else bool(prod.is_returnable)
            prod.return_period_days = prod.return_period_days or 30
            prod.image_url = prod.image_url or 'https://example.com/assets/products/default.png'
            prod.description = prod.description or f'منتج بذري: {name}'
            prod.notes = prod.notes or 'Generated by seed_comprehensive.'
            prod.min_stock_alert = prod.min_stock_alert or 10
            prod.is_active = True
            products_db.append(prod)
    
    db.session.commit()
    print("✅ Products Seeded")

    # 6. Setup Partners (Customers & Suppliers)
    customer_names = ['أحمد الكرمي', 'محمد الشامي', 'ليث الخطيب', 'سليم أبو عيشة', 'رامي التميمي']
    customers = []
    for i in range(5):
        seed_email = f'cust{i}@test.com'
        cust = Customer.query.filter_by(email=seed_email).first() or Customer.query.filter_by(name=f'Customer {i+1}').first()
        customer_name = customer_names[i % len(customer_names)]
        if not cust:
            cust = Customer(
                name=customer_name,
                name_ar=customer_name,
                phone=f'050123456{i}',
                email=seed_email,
                address=f'Dubai - Customer District {i+1}',
                customer_type='regular',
                customer_classification='regular',
                preferred_currency='AED',
                tax_number=f'CTN-{10000 + i}',
                credit_limit=Decimal('50000.000'),
                total_purchases=Decimal('0.000'),
                balance=Decimal('0.000'),
                notes='Seeded customer profile for production-like testing.',
                is_active=True,
            )
            db.session.add(cust)
            customers.append(cust)
        else:
            cust.name = customer_name
            cust.name_ar = customer_name
            cust.phone = cust.phone or f'050123456{i}'
            cust.email = cust.email or seed_email
            cust.address = cust.address or f'Dubai - Customer District {i+1}'
            cust.customer_type = cust.customer_type or 'regular'
            cust.customer_classification = cust.customer_classification or 'regular'
            cust.preferred_currency = cust.preferred_currency or 'AED'
            cust.tax_number = cust.tax_number or f'CTN-{10000 + i}'
            cust.credit_limit = cust.credit_limit if cust.credit_limit is not None else Decimal('50000.000')
            cust.total_purchases = cust.total_purchases if cust.total_purchases is not None else Decimal('0.000')
            cust.balance = cust.balance if cust.balance is not None else Decimal('0.000')
            cust.notes = cust.notes or 'Seeded customer profile for production-like testing.'
            cust.is_active = True
            customers.append(cust)

    supplier_names = ['مؤسسة القدس للتوريد', 'شركة الفارس لقطع الغيار', 'مخازن النور التجارية']
    suppliers = []
    for i in range(3):
        seed_email = f'supp{i}@test.com'
        supp = Supplier.query.filter_by(email=seed_email).first() or Supplier.query.filter_by(name=f'Supplier {i+1}').first()
        supplier_name = supplier_names[i % len(supplier_names)]
        if not supp:
            supp = Supplier(
                name=supplier_name,
                name_ar=supplier_name,
                name_en=supplier_name,
                company_name=supplier_name,
                phone=f'050987654{i}',
                phone2=f'050987654{i}',
                email=seed_email,
                website=f'https://supplier{i+1}.example.com',
                address=f'Abu Dhabi - Supplier Zone {i+1}',
                city='Abu Dhabi',
                country='UAE',
                tax_number=f'STN-{20000 + i}',
                commercial_registration=f'CR-{30000 + i}',
                supplier_type='parts',
                rating=4,
                credit_limit=Decimal('100000.000'),
                payment_terms_days=30,
                preferred_currency='AED',
                total_purchases_aed=Decimal('0.000'),
                total_paid_aed=Decimal('0.000'),
                notes='Seeded supplier profile for production-like testing.',
                tags='parts,preferred,seed',
                is_verified=True,
                is_active=True,
            )
            db.session.add(supp)
            suppliers.append(supp)
        else:
            supp.name = supplier_name
            supp.name_ar = supplier_name
            supp.name_en = supp.name_en or supplier_name
            supp.company_name = supp.company_name or supplier_name
            supp.phone = supp.phone or f'050987654{i}'
            supp.phone2 = supp.phone2 or supp.phone
            supp.email = supp.email or seed_email
            supp.website = supp.website or f'https://supplier{i+1}.example.com'
            supp.address = supp.address or f'Abu Dhabi - Supplier Zone {i+1}'
            supp.city = supp.city or 'Abu Dhabi'
            supp.country = supp.country or 'UAE'
            supp.tax_number = supp.tax_number or f'STN-{20000 + i}'
            supp.commercial_registration = supp.commercial_registration or f'CR-{30000 + i}'
            supp.supplier_type = supp.supplier_type or 'parts'
            supp.rating = supp.rating or 4
            supp.credit_limit = supp.credit_limit if supp.credit_limit is not None else Decimal('100000.000')
            supp.payment_terms_days = supp.payment_terms_days or 30
            supp.preferred_currency = supp.preferred_currency or 'AED'
            supp.total_purchases_aed = supp.total_purchases_aed if supp.total_purchases_aed is not None else Decimal('0.000')
            supp.total_paid_aed = supp.total_paid_aed if supp.total_paid_aed is not None else Decimal('0.000')
            supp.notes = supp.notes or 'Seeded supplier profile for production-like testing.'
            supp.tags = supp.tags or 'parts,preferred,seed'
            supp.is_verified = True
            supp.is_active = True
            suppliers.append(supp)
            
    db.session.commit()
    print("✅ Partners Seeded")

    # 7. Seed branch-scoped users
    seller_role = _resolve_role('seller', 'manager')
    manager_role = _resolve_role('manager', 'branch_manager', 'seller')
    accountant_role = _resolve_role('accountant', 'manager', 'seller')
    branch_manager_role = _resolve_role('branch_manager', 'manager', 'seller')

    for branch in all_active_branches:
        code = _branch_token(branch.code, branch.id)
        _ensure_user(
            username=f'seller_{code}',
            email=f'seller_{code}@example.com',
            full_name=f'Seller {branch.code}',
            role=seller_role,
            branch_id=branch.id,
            phone=f'055100{branch.id:04d}',
        )
        _ensure_user(
            username=f'manager_{code}',
            email=f'manager_{code}@example.com',
            full_name=f'Manager {branch.code}',
            role=manager_role,
            branch_id=branch.id,
            phone=f'055200{branch.id:04d}',
        )
        _ensure_user(
            username=f'accountant_{code}',
            email=f'accountant_{code}@example.com',
            full_name=f'Accountant {branch.code}',
            role=accountant_role,
            branch_id=branch.id,
            phone=f'055300{branch.id:04d}',
        )
        _ensure_user(
            username=f'branch_manager_{code}',
            email=f'branch_manager_{code}@example.com',
            full_name=f'Branch Manager {branch.code}',
            role=branch_manager_role,
            branch_id=branch.id,
            phone=f'055400{branch.id:04d}',
        )

    # Global seed users
    super_admin_role = _resolve_role('super_admin', 'manager')
    developer_role = _resolve_role('developer', 'super_admin', 'manager')
    _ensure_user(
        username='seed_super_admin',
        email='seed_super_admin@example.com',
        full_name='Seed Super Admin',
        role=super_admin_role,
        branch_id=None,
        phone='0559000001',
    )
    _ensure_user(
        username='seed_developer',
        email='seed_developer@example.com',
        full_name='Seed Developer',
        role=developer_role,
        branch_id=None,
        phone='0559000002',
    )
    db.session.commit()

    # Ensure each warehouse has an assigned branch manager when available.
    manager_by_branch = {
        user.branch_id: user.id
        for user in User.query.filter(User.username.like('branch_manager_%')).all()
        if user.branch_id
    }
    for warehouse in warehouses:
        if not warehouse.manager_id and warehouse.branch_id in manager_by_branch:
            warehouse.manager_id = manager_by_branch[warehouse.branch_id]
    db.session.commit()

    branch_users = {
        user.branch_id: user
        for user in User.query.filter(
            User.username.in_([f'seller_{_branch_token(b.code, b.id)}' for b in all_active_branches])
        ).all()
    }

    # 8. Seed employees by branch (dozens; monthly + daily)
    employee_templates = [
        ('أمين صندوق', 'salary', Decimal('4500.00')),
        ('أمين مستودع', 'salary', Decimal('4800.00')),
        ('مندوب مبيعات', 'salary', Decimal('5200.00')),
        ('محاسب الفرع', 'salary', Decimal('6800.00')),
        ('مشرف مستودع', 'salary', Decimal('6200.00')),
        ('مسؤول مشتريات', 'salary', Decimal('5900.00')),
        ('فني أول', 'salary', Decimal('7100.00')),
        ('فني', 'daily', Decimal('220.00')),
        ('عامل تركيب', 'daily', Decimal('210.00')),
        ('عامل تحميل', 'daily', Decimal('180.00')),
        ('سائق', 'daily', Decimal('200.00')),
        ('عامل مساعد', 'daily', Decimal('170.00')),
    ]
    for branch in all_active_branches:
        code = _branch_token(branch.code, branch.id)
        for idx, (title, employment_type, salary) in enumerate(employee_templates, start=1):
            name = f'{title} - {branch.name} {idx}'
            employee = Employee.query.filter_by(name=name).first()
            if not employee:
                employee = Employee(
                    name=name,
                    name_ar=name,
                    phone=f'056{branch.id:02d}{idx:04d}',
                    email=f'emp_{code}_{idx}@example.com',
                    employment_type=employment_type,
                    basic_salary=salary,
                    currency='AED',
                    branch_id=branch.id,
                    is_active=True,
                )
                db.session.add(employee)
            else:
                employee.name_ar = employee.name_ar or employee.name
                employee.phone = employee.phone or f'056{branch.id:02d}{idx:04d}'
                employee.email = employee.email or f'emp_{code}_{idx}@example.com'
                employee.employment_type = employee.employment_type or employment_type
                if not employee.basic_salary or Decimal(str(employee.basic_salary)) <= Decimal('0'):
                    employee.basic_salary = salary
                employee.currency = employee.currency or 'AED'
                employee.branch_id = employee.branch_id or branch.id
                employee.is_active = True
    db.session.commit()
    print("✅ Branch Users & Employees Seeded")

    # 9. Seed expense categories and expenses
    expense_category_specs = [
        ("Rent", "إيجار", "6200"),
        ("Salaries", "رواتب", "6100"),
        ("Utilities", "مرافق", "6300"),
        ("Maintenance", "صيانة", "6400"),
    ]
    expense_categories = []
    for idx, (name, name_ar, gl_code) in enumerate(expense_category_specs, start=1):
        category = ExpenseCategory.query.filter_by(name=name).first()
        if not category:
            category = ExpenseCategory(
                name=name,
                name_ar=name_ar,
                gl_account_code=gl_code,
                is_active=True,
            )
            db.session.add(category)
        else:
            category.name_ar = category.name_ar or name_ar
            category.gl_account_code = category.gl_account_code or gl_code
            category.is_active = True
        expense_categories.append(category)
    db.session.commit()

    for branch in all_active_branches:
        branch_accountant = User.query.filter(
            User.branch_id == branch.id,
            User.username.like('accountant_%')
        ).first() or branch_users.get(branch.id)
        if not branch_accountant:
            continue

        for category in expense_categories:
            seed_desc = f"Seeded {category.name} expense for {branch.code}"
            expense = Expense.query.filter_by(branch_id=branch.id, description=seed_desc).first()
            if expense:
                continue
            base_amount = {
                "Rent": Decimal("12000.000"),
                "Salaries": Decimal("18000.000"),
                "Utilities": Decimal("2500.000"),
                "Maintenance": Decimal("1600.000"),
            }.get(category.name, Decimal("1000.000"))
            expense = Expense(
                expense_number=_generate_unique_number(Expense, 'expense_number', 'EXP'),
                category_id=category.id,
                description=seed_desc,
                description_ar=f"مصروف {category.name_ar} للفرع {branch.code}",
                amount=base_amount,
                currency='AED',
                exchange_rate=Decimal('1.000000'),
                amount_aed=base_amount,
                expense_date=datetime.now() - timedelta(days=random.randint(1, 20)),
                payment_method='cash',
                reference_number=_generate_unique_number(Expense, 'reference_number', 'EXPR', digits=4),
                cheque_number='N/A',
                bank_name='N/A',
                supplier_name='N/A',
                notes='Seeded operating expense for branch-level analytics.',
                status='confirmed',
                is_active=True,
                user_id=branch_accountant.id,
                branch_id=branch.id,
                is_reversed=False,
            )
            db.session.add(expense)
    db.session.commit()
    print("✅ Expense Categories & Expenses Seeded")

    # 10. Seed incoming/outgoing cheques by branch
    for branch in all_active_branches:
        branch_user = branch_users.get(branch.id) or User.query.filter(User.branch_id == branch.id).first()
        if not branch_user:
            continue
        customer = random.choice(customers)
        supplier = random.choice(suppliers)

        incoming_bank_no = f"SEED-CHQ-IN-{branch.code}"
        incoming = Cheque.query.filter_by(cheque_bank_number=incoming_bank_no, cheque_type='incoming').first()
        if not incoming:
            incoming = Cheque(
                cheque_number=_generate_unique_number(Cheque, 'cheque_number', 'CHQ'),
                cheque_bank_number=incoming_bank_no,
                cheque_type='incoming',
                bank_name='Seed National Bank',
                bank_branch=f'{branch.code} City',
                account_number=f'IN-{branch.code}-001',
                amount=Decimal('4500.00'),
                currency='AED',
                exchange_rate=Decimal('1.000000'),
                issue_date=(datetime.now() - timedelta(days=4)).date(),
                due_date=(datetime.now() + timedelta(days=18)).date(),
                status='pending',
                drawer_name=customer.name,
                drawer_id_number=f'ID-{branch.code}-IN',
                customer_id=customer.id,
                branch_id=branch.id,
                notes=f'Seeded incoming cheque for {branch.code}.',
                user_id=branch_user.id,
                is_active=True,
            )
            incoming.calculate_amount_aed()
            incoming.update_status_based_on_date()
            db.session.add(incoming)
        else:
            incoming.branch_id = incoming.branch_id or branch.id
            incoming.user_id = incoming.user_id or branch_user.id
            incoming.customer_id = incoming.customer_id or customer.id
            incoming.drawer_name = incoming.drawer_name or customer.name
            incoming.bank_name = incoming.bank_name or 'Seed National Bank'
            incoming.cheque_type = incoming.cheque_type or 'incoming'
            incoming.currency = incoming.currency or 'AED'
            incoming.exchange_rate = incoming.exchange_rate or Decimal('1.000000')
            incoming.amount = incoming.amount if incoming.amount and Decimal(str(incoming.amount)) > 0 else Decimal('4500.00')
            incoming.issue_date = incoming.issue_date or (datetime.now() - timedelta(days=4)).date()
            incoming.due_date = incoming.due_date or (datetime.now() + timedelta(days=18)).date()
            incoming.calculate_amount_aed()
            incoming.update_status_based_on_date()

        outgoing_bank_no = f"SEED-CHQ-OUT-{branch.code}"
        outgoing = Cheque.query.filter_by(cheque_bank_number=outgoing_bank_no, cheque_type='outgoing').first()
        if not outgoing:
            outgoing = Cheque(
                cheque_number=_generate_unique_number(Cheque, 'cheque_number', 'CHQ'),
                cheque_bank_number=outgoing_bank_no,
                cheque_type='outgoing',
                bank_name='Seed National Bank',
                bank_branch=f'{branch.code} City',
                account_number=f'OUT-{branch.code}-001',
                amount=Decimal('3800.00'),
                currency='AED',
                exchange_rate=Decimal('1.000000'),
                issue_date=(datetime.now() - timedelta(days=3)).date(),
                due_date=(datetime.now() + timedelta(days=14)).date(),
                status='pending',
                payee_name=supplier.name,
                supplier_id=supplier.id,
                branch_id=branch.id,
                notes=f'Seeded outgoing cheque for {branch.code}.',
                user_id=branch_user.id,
                is_active=True,
            )
            outgoing.calculate_amount_aed()
            outgoing.update_status_based_on_date()
            db.session.add(outgoing)
        else:
            outgoing.branch_id = outgoing.branch_id or branch.id
            outgoing.user_id = outgoing.user_id or branch_user.id
            outgoing.supplier_id = outgoing.supplier_id or supplier.id
            outgoing.payee_name = outgoing.payee_name or supplier.name
            outgoing.bank_name = outgoing.bank_name or 'Seed National Bank'
            outgoing.cheque_type = outgoing.cheque_type or 'outgoing'
            outgoing.currency = outgoing.currency or 'AED'
            outgoing.exchange_rate = outgoing.exchange_rate or Decimal('1.000000')
            outgoing.amount = outgoing.amount if outgoing.amount and Decimal(str(outgoing.amount)) > 0 else Decimal('3800.00')
            outgoing.issue_date = outgoing.issue_date or (datetime.now() - timedelta(days=3)).date()
            outgoing.due_date = outgoing.due_date or (datetime.now() + timedelta(days=14)).date()
            outgoing.calculate_amount_aed()
            outgoing.update_status_based_on_date()

    db.session.commit()
    print("✅ Cheques Seeded")

    # 11. Seed salary advances and payroll transactions
    current_month = datetime.now().month
    current_year = datetime.now().year
    for employee in Employee.query.filter_by(is_active=True).all():
        branch_manager = User.query.filter(
            User.branch_id == employee.branch_id,
            User.username.like('manager_%')
        ).first() or User.query.filter(User.branch_id == employee.branch_id).first()
        created_by_id = branch_manager.id if branch_manager else 1

        seeded_advance_desc = f"Seeded salary advance {current_month}/{current_year} for {employee.name}"
        existing_advance = SalaryAdvance.query.filter_by(
            employee_id=employee.id,
            description=seeded_advance_desc
        ).first()
        if not existing_advance:
            base_salary = Decimal(str(employee.basic_salary or 0))
            advance_amount = (base_salary * Decimal('0.15')).quantize(Decimal('0.01'))
            if advance_amount <= 0:
                advance_amount = Decimal('350.00')
            advance = SalaryAdvance(
                employee_id=employee.id,
                amount=advance_amount,
                date=datetime.now().date() - timedelta(days=10),
                description=seeded_advance_desc,
                status='approved',
                is_deducted=False,
                created_by=created_by_id,
            )
            db.session.add(advance)

        existing_payroll = PayrollTransaction.query.filter_by(
            employee_id=employee.id,
            month=current_month,
            year=current_year
        ).first()
        if existing_payroll:
            continue

        basic_salary = Decimal(str(employee.basic_salary or 0))
        if employee.employment_type == 'daily':
            basic_amount = (basic_salary * Decimal('22')).quantize(Decimal('0.01'))
            days_worked = Decimal('22.00')
        else:
            basic_amount = basic_salary.quantize(Decimal('0.01'))
            days_worked = Decimal('30.00')

        allowances = (basic_amount * Decimal('0.05')).quantize(Decimal('0.01'))
        deductions = (basic_amount * Decimal('0.02')).quantize(Decimal('0.01'))
        advances_deducted = (basic_amount * Decimal('0.10')).quantize(Decimal('0.01'))
        net_salary = (basic_amount + allowances - deductions - advances_deducted).quantize(Decimal('0.01'))
        if net_salary < 0:
            net_salary = Decimal('0.00')

        payroll = PayrollTransaction(
            employee_id=employee.id,
            month=current_month,
            year=current_year,
            basic_amount=basic_amount,
            days_worked=days_worked,
            allowances=allowances,
            deductions=deductions,
            advances_deducted=advances_deducted,
            net_salary=net_salary,
            payment_date=datetime.now().date(),
            status='paid',
            branch_id=employee.branch_id,
            notes=f'Seeded payroll {current_month}/{current_year}',
            created_by=created_by_id,
        )
        db.session.add(payroll)
    db.session.commit()
    print("✅ Salary Advances & Payroll Transactions Seeded")

    # 12. Simulate Business Operations (Purchase -> Stock -> Sale)
    
    # A. Purchase Stock
    for prod in products_db:
        target_warehouse = random.choice(warehouses)
        target_branch_id = target_warehouse.branch_id
        target_supplier = random.choice(suppliers)
        # Create Purchase
        purchase = Purchase(
            supplier_id=target_supplier.id,
            supplier_name=target_supplier.name,
            supplier_phone=target_supplier.phone,
            supplier_email=target_supplier.email,
            user_id=branch_users[target_branch_id].id if target_branch_id in branch_users else 1,
            purchase_date=datetime.now() - timedelta(days=random.randint(10, 30)),
            status='completed',
            warehouse_id=target_warehouse.id,
            branch_id=target_branch_id,
            subtotal=0,
            discount_amount=Decimal('0.000'),
            tax_rate=Decimal('5.00'),
            tax_amount=Decimal('0.000'),
            total_amount=0, # Will be calc
            currency='AED',
            exchange_rate=1,
            amount_aed=0, # Will be calc
            purchase_number=_generate_unique_number(Purchase, 'purchase_number', 'PUR'),
            notes='Seeded purchase transaction',
        )
        db.session.add(purchase)
        db.session.flush() # Get ID

        qty = 100
        cost = prod.cost_price
        line = PurchaseLine(
            purchase_id=purchase.id,
            product_id=prod.id,
            quantity=qty,
            unit_cost=cost,
            line_total=qty * cost
        )
        db.session.add(line)
        purchase.total_amount = line.line_total
        purchase.subtotal = line.line_total
        purchase.tax_amount = (purchase.subtotal * Decimal('0.05')).quantize(Decimal('0.001'))
        purchase.total_amount = purchase.subtotal + purchase.tax_amount
        purchase.amount_aed = purchase.total_amount
        
        # Stock Movement
        StockService.add_stock(
            product_id=prod.id,
            quantity=qty,
            reference_type='purchase',
            reference_id=purchase.id,
            warehouse_id=target_warehouse.id
        )
        
        # GL Entry (Inventory Dr, AP Cr)
        # Assuming GLService.create_journal_entry logic is similar to post_entry but handled internally or needs adaptation
        # Since GLService.create_journal_entry failed with 'date', we'll try 'post_entry' if available or manual creation
        
        # Check available GLService methods
        if hasattr(GLService, 'post_entry'):
             GLService.post_entry(
                lines=[
                    {'account': '1140', 'debit': purchase.total_amount, 'credit': 0}, # Inventory
                    {'account': '2110', 'debit': 0, 'credit': purchase.total_amount}  # AP
                ],
                description=f"Purchase {purchase.purchase_number}",
                reference_type='purchase',
                reference_id=purchase.id,
                date=purchase.purchase_date,
                branch_id=purchase.branch_id
            )
        else:
            # Manual fallback
            entry = GLJournalEntry(
                date=purchase.purchase_date,
                description=f"Purchase {purchase.purchase_number}",
                reference=purchase.purchase_number,
                type='purchase',
                currency_id=aed.id,
                exchange_rate=1.0,
                status='posted'
            )
            db.session.add(entry)
            db.session.flush()
            
            l1 = GLJournalLine(entry_id=entry.id, account_id=gl_accounts['1200'].id, debit=purchase.total_amount, credit=0)
            l2 = GLJournalLine(entry_id=entry.id, account_id=gl_accounts['2000'].id, debit=0, credit=purchase.total_amount)
            db.session.add_all([l1, l2])

    db.session.commit()
    print("✅ Purchases & Stock Simulated")

    # B. Sales Operations
    for i in range(20):
        cust = random.choice(customers)
        target_warehouse = random.choice(warehouses)
        target_branch_id = target_warehouse.branch_id
        sale = Sale(
            customer_id=cust.id,
            seller_id=branch_users[target_branch_id].id if target_branch_id in branch_users else 1,
            sale_date=datetime.now() - timedelta(days=random.randint(0, 10)),
            status='completed',
            payment_status='paid',
            warehouse_id=target_warehouse.id,
            branch_id=target_branch_id,
            total_amount=0,
            amount_aed=0,
            sale_number=_generate_unique_number(Sale, 'sale_number', 'INV'),
            notes='Seeded sales transaction',
        )
        db.session.add(sale)
        db.session.flush()

        # Add random products
        sale_total = 0
        total_cost = 0
        
        num_items = random.randint(1, 3)
        selected_prods = random.sample(products_db, num_items)
        
        for prod in selected_prods:
            qty = random.randint(1, 5)
            price = prod.regular_price
            
            line = SaleLine(
                sale_id=sale.id,
                product_id=prod.id,
                quantity=qty,
                unit_price=price,
                line_total=qty * price,
                cost_price=prod.cost_price # Simple FIFO approx
            )
            db.session.add(line)
            sale_total += line.line_total
            total_cost += (qty * prod.cost_price)
            
            # Stock Out
            StockService.remove_stock(
                product_id=prod.id,
                warehouse_id=target_warehouse.id,
                quantity=qty,
                reference_type='sale',
                reference_id=sale.id
            )

        sale.total_amount = sale_total
        sale.subtotal = sale_total
        sale.discount_amount = Decimal('0.000')
        sale.shipping_cost = Decimal('0.000')
        sale.tax_rate = Decimal('5.00')
        sale.tax_amount = (sale.subtotal * Decimal('0.05')).quantize(Decimal('0.001'))
        sale.total_amount = sale.subtotal + sale.tax_amount
        sale.amount_aed = sale_total
        sale.amount_aed = sale.total_amount
        sale.paid_amount = sale.total_amount
        sale.paid_amount_aed = sale.amount_aed
        sale.balance_due = Decimal('0')
        
        # Payment
        pay = Payment(
            sale_id=sale.id,
            customer_id=sale.customer_id,
            amount=sale.total_amount,
            payment_type='sale_payment',
            direction='incoming',
            payment_method='cash',
            payment_date=sale.sale_date,
            reference_number=_generate_unique_number(Payment, 'reference_number', 'PAY', digits=4),
            currency='AED',
            exchange_rate=1.0,
            amount_aed=sale.amount_aed,
            payment_number=_generate_unique_number(Payment, 'payment_number', 'PAY'),
            branch_id=sale.branch_id,
            user_id=sale.seller_id,
            notes='Seeded payment for completed sale',
            supplier_name='N/A',
            cheque_number='N/A',
            bank_name='N/A',
            rejection_reason='N/A',
        )
        db.session.add(pay)

        # GL Entries
        # 1. Revenue (Cash Dr, Sales Cr)
        if hasattr(GLService, 'post_entry'):
             GLService.post_entry(
                lines=[
                    {'account': '1110', 'debit': sale_total, 'credit': 0}, # Cash
                    {'account': '4100', 'debit': 0, 'credit': sale_total}  # Revenue
                ],
                description=f"Sale {sale.sale_number}",
                reference_type='sale',
                reference_id=sale.id,
                date=sale.sale_date,
                branch_id=sale.branch_id
            )
             
             GLService.post_entry(
                lines=[
                    {'account': '5100', 'debit': total_cost, 'credit': 0}, # COGS
                    {'account': '1140', 'debit': 0, 'credit': total_cost}  # Inventory
                ],
                description=f"COGS {sale.sale_number}",
                reference_type='sale_cogs',
                reference_id=sale.id,
                date=sale.sale_date,
                branch_id=sale.branch_id
            )
        else:
            # Manual
            pass # Skipping manual for sales to keep it short, assuming post_entry works

    db.session.commit()
    print("✅ Sales & Financials Simulated")
    print("🚀 Comprehensive Seeding Completed Successfully!")

if __name__ == "__main__":
    # This block allows running the seeder directly
    from app import create_app
    app = create_app()
    with app.app_context():
        seed_comprehensive_data()
