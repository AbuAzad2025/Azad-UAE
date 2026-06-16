"""
Purge ALL demo data and create minimal professional seeds.
One tenant, complete data set, matching Azadexa structure.
"""
import sys
sys.path.insert(0, r'D:\Data\karaj\UAE\Azad-UAE')

from app import create_app
from extensions import db
from sqlalchemy import text

# System tables to NEVER touch
SYSTEM_TABLES = {
    'alembic_version', 'system_settings', 'roles', 'permissions', 'role_permissions',
    'currencies', 'exchange_rates', 'packages', 'error_audit_logs', 'login_history',
    'invoice_settings', 'integration_settings', 'industry_field_definitions',
}

# Order matters for FK constraints — child first, parent last
# We'll use CASCADE truncate where possible
TABLES_TO_TRUNCATE = [
    # POS / Sales / Purchases (transaction lines first)
    'pos_kds_orders', 'pos_table_orders', 'pos_tables', 'pos_floors',
    'sale_lines', 'sales', 'purchase_lines', 'purchases',
    'product_return_lines', 'product_returns',
    'purchase_return_lines', 'purchase_returns',
    'receipts', 'payments', 'payment_logs', 'payment_transactions',
    'card_payments', 'card_vault', 'payment_vault',
    'expenses', 'advanced_expenses',
    'stock_movements', 'product_warehouse_costs', 'product_warehouse_stock',
    'product_cost_history', 'product_serials', 'product_images',
    'product_partners', 'product_price_tiers', 'shop_product_variants',
    'shop_stock_alerts', 'shop_reviews', 'shop_saved_payments',
    'shop_wishlist', 'shop_loyalty_transactions', 'shop_loyalty',
    'shop_abandoned_carts', 'shop_newsletters', 'shop_customer_accounts',
    # GL / Accounting
    'gl_journal_lines', 'gl_journal_entries', 'journal_entry_audits',
    'gl_account_mappings', 'gl_periods',
    'bank_reconciliation_items', 'bank_reconciliations', 'bank_statement_lines',
    'cash_boxes', 'budget_lines', 'budgets', 'cost_centers', 'profit_centers',
    'fixed_assets', 'depreciation_schedules', 'customs_taxes',
    'fiscal_position_tax_rules', 'fiscal_positions', 'tax_calculation_rules',
    # Payroll / HR
    'payroll_transactions', 'salary_advances', 'hr_contracts',
    'attendances', 'timesheets', 'leave_requests', 'leave_types',
    'departments', 'job_positions', 'employees', 'payroll_settings',
    # CRM / Tickets / Projects
    'crm_activities', 'crm_leads', 'crm_team_members', 'crm_teams', 'crm_stages',
    'ticket_comments', 'tickets', 'ticket_categories', 'ticket_priorities',
    'task_stages', 'tasks', 'project_members', 'projects',
    # Store / E-commerce
    'store_coupons', 'store_payment_methods', 'tenant_stores',
    'campaign_logs', 'campaigns', 'email_campaigns', 'email_lists',
    'email_subscribers', 'email_templates',
    'donations', 'package_purchases', 'partners', 'partner_commission_entries',
    'partner_profit_distributions', 'partner_transactions',
    # Print / Security / Audit
    'print_history', 'security_alerts', 'archived_records',
    'warranty_claims', 'shipments', 'cheques',
    # Products / Inventory / Partners
    'products', 'product_categories',
    # Customers / Suppliers
    'customers', 'suppliers',
    # Branches / Warehouses
    'warehouses', 'branches',
    # Users / Tenants
    'users', 'tenants',
    # GL Accounts (must be after tenants if tenant_id FK exists)
    'gl_accounts', 'exchange_rate_records',
    # Misc
    'api_keys', 'document_sequences',
]

def truncate_tables(app):
    with app.app_context():
        conn = db.engine.raw_connection()
        cursor = conn.cursor()
        for tbl in TABLES_TO_TRUNCATE:
            if tbl in SYSTEM_TABLES:
                continue
            try:
                cursor.execute(f'TRUNCATE TABLE {tbl} CASCADE')
                print(f'  TRUNCATED {tbl}')
            except Exception as e:
                print(f'  SKIP {tbl}: {e}')
        conn.commit()
        cursor.close()
        conn.close()
        print('\nAll demo data purged.')


def reset_sequences(app):
    with app.app_context():
        conn = db.engine.raw_connection()
        cursor = conn.cursor()
        # Reset all sequences
        cursor.execute("""
            SELECT c.relname
            FROM pg_class c
            WHERE c.relkind = 'S'
        """)
        for (seq_name,) in cursor.fetchall():
            try:
                cursor.execute(f"ALTER SEQUENCE {seq_name} RESTART WITH 1")
            except Exception:
                pass
        conn.commit()
        cursor.close()
        conn.close()
        print('Sequences reset.')


from decimal import Decimal
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash

def create_seeds(app):
    with app.app_context():
        from models import (
            Tenant, Branch, Warehouse, User, Role,
            ProductCategory, Product,
            Customer, Supplier,
            GLAccount,
            ExpenseCategory,
            Employee, Department, JobPosition,
            Currency,
        )
        from models.system_settings import SystemSettings
        from services.sale_service import SaleService
        from services.purchase_service import PurchaseService
        from utils.helpers import generate_number
        from utils.tenanting import get_active_tenant_id

        # Ensure currencies exist
        curr_aed = Currency.query.filter_by(code='AED').first()
        if not curr_aed:
            curr_aed = Currency(code='AED', name='UAE Dirham', name_ar='درهم إماراتي', symbol='د.إ', rate_to_usd=Decimal('0.2723'))
            db.session.add(curr_aed)
            curr_usd = Currency(code='USD', name='US Dollar', name_ar='دولار أمريكي', symbol='$', rate_to_usd=Decimal('1'))
            db.session.add(curr_usd)
            curr_sar = Currency(code='SAR', name='Saudi Riyal', name_ar='ريال سعودي', symbol='ر.س', rate_to_usd=Decimal('0.2667'))
            db.session.add(curr_sar)
            db.session.flush()

        # Create Tenant
        tenant = Tenant(
            name='Azad Electronics LLC',
            name_ar='أزاد للإلكترونيات ذ.م.م',
            name_en='Azad Electronics LLC',
            slug='azad-electronics',
            business_type='retail',
            industry='electronics',
            address_ar='دبي، الإمارات العربية المتحدة',
            address_en='Dubai, UAE',
            city='Dubai',
            country='AE',
            phone_1='+971-4-123-4567',
            email='info@azadelectronics.ae',
            tax_number='1234567890123',
            commercial_register='987654321',
            license_number='TRN-2024-001',
            default_currency='AED',
            default_language='ar',
            timezone='Asia/Dubai',
            enable_pos=True,
            enable_multi_currency=True,
            enable_multi_warehouse=True,
            enable_gl=True,
            enable_reports=True,
            enable_expenses=True,
            is_active=True,
        )
        db.session.add(tenant)
        db.session.flush()
        tenant_id = tenant.id
        print(f'Tenant created: ID={tenant_id}')

        # Create Branches
        branch_main = Branch(
            tenant_id=tenant_id, name='الفرع الرئيسي - دبي', code='DB-Main',
            address='ديرة، دبي', city='Dubai', is_main=True, is_active=True,
        )
        branch_ajman = Branch(
            tenant_id=tenant_id, name='فرع عجمان', code='AJ-01',
            address='عجمان الصناعية', city='Ajman', is_main=False, is_active=True,
        )
        db.session.add_all([branch_main, branch_ajman])
        db.session.flush()
        print(f'Branches created: main={branch_main.id}, ajman={branch_ajman.id}')

        # Create Warehouses
        wh_main = Warehouse(
            tenant_id=tenant_id, branch_id=branch_main.id,
            name='المستودع الرئيسي - دبي', name_ar='المستودع الرئيسي - دبي', code='WH-DB-01',
            location='ديرة، دبي', warehouse_type='physical', is_main=True, is_active=True,
        )
        wh_ajman = Warehouse(
            tenant_id=tenant_id, branch_id=branch_ajman.id,
            name='مستودع عجمان', name_ar='مستودع عجمان', code='WH-AJ-01',
            location='عجمان الصناعية', warehouse_type='physical', is_main=False, is_active=True,
        )
        wh_online = Warehouse(
            tenant_id=tenant_id, branch_id=branch_main.id,
            name='مستودع التوصيل', name_ar='مستودع التوصيل', code='WH-ONL',
            location='ديرة، دبي', warehouse_type='online', is_main=False, is_active=True,
        )
        db.session.add_all([wh_main, wh_ajman, wh_online])
        db.session.flush()
        print(f'Warehouses created')

        # Get Roles
        role_owner = Role.query.filter_by(slug='owner').first()
        role_super = Role.query.filter_by(slug='super_admin').first()
        role_manager = Role.query.filter_by(slug='manager').first()
        role_cashier = Role.query.filter_by(slug='cashier').first()
        role_sales = Role.query.filter_by(slug='sales').first()
        role_accountant = Role.query.filter_by(slug='accountant').first()
        role_inventory = Role.query.filter_by(slug='inventory').first()
        if not role_owner:
            role_owner = Role(name='Owner', slug='owner', description='مالك النظام')
            db.session.add(role_owner)
            db.session.flush()

        users_data = [
            ('owner@azad.ae', 'Owner', 'مالك النظام', 'owner', role_owner),
            ('admin@azad.ae', 'Admin', 'مدير النظام', 'super_admin', role_super),
            ('manager@azad.ae', 'Branch Manager', 'مدير الفرع', 'manager', role_manager),
            ('cashier@azad.ae', 'Ahmed Cashier', 'أحمد - كاشير', 'cashier', role_cashier),
            ('sales@azad.ae', 'Mohamed Sales', 'محمد - مبيعات', 'sales', role_sales),
            ('accountant@azad.ae', 'Fatima Accountant', 'فاطمة - محاسبة', 'accountant', role_accountant),
            ('inventory@azad.ae', 'Ali Warehouse', 'علي - مخزن', 'inventory', role_inventory),
        ]
        created_users = []
        for email, full_name, full_name_ar, username, role in users_data:
            if not role:
                continue
            u = User(
                tenant_id=tenant_id,
                email=email,
                username=username,
                full_name=full_name,
                full_name_ar=full_name_ar,
                password_hash=generate_password_hash('Azad2024!'),
                role_id=role.id,
                is_active=True,
                email_verified=True,
                branch_id=branch_main.id,
            )
            db.session.add(u)
            created_users.append(u)
        db.session.flush()
        print(f'Users created: {len(created_users)}')
        owner_user = created_users[0]

        # Create GL Accounts (minimal professional chart)
        gl_accounts_data = [
            # Assets
            (tenant_id, '1000', 'Assets', 'أصول', 'asset', None, True, 1),
            (tenant_id, '1100', 'Current Assets', 'أصول متداولة', 'asset', None, True, 2),
            (tenant_id, '1110', 'Cash', 'الصندوق', 'asset', 'cash', False, 3),
            (tenant_id, '1120', 'Bank', 'البنك', 'asset', 'bank', False, 3),
            (tenant_id, '1130', 'Accounts Receivable', 'ذمم مدينة', 'asset', 'receivable', False, 3),
            (tenant_id, '1140', 'Inventory', 'المخزون', 'asset', 'inventory', False, 3),
            (tenant_id, '1200', 'Fixed Assets', 'أصول ثابتة', 'asset', 'fixed_asset', False, 2),
            # Liabilities
            (tenant_id, '2000', 'Liabilities', 'خصوم', 'liability', None, True, 1),
            (tenant_id, '2100', 'Current Liabilities', 'خصوم متداولة', 'liability', None, True, 2),
            (tenant_id, '2110', 'Accounts Payable', 'ذمم دائنة', 'liability', 'payable', False, 3),
            (tenant_id, '2120', 'VAT Payable', 'ضريبة القيمة المضافة', 'liability', 'vat', False, 3),
            # Equity
            (tenant_id, '3000', 'Equity', 'حقوق الملكية', 'equity', None, True, 1),
            (tenant_id, '3100', 'Capital', 'رأس المال', 'equity', 'equity_share', False, 2),
            (tenant_id, '3200', 'Retained Earnings', 'أرباح مرحلة', 'equity', 'retained_earnings', False, 2),
            # Revenue
            (tenant_id, '4000', 'Revenue', 'الإيرادات', 'revenue', None, True, 1),
            (tenant_id, '4100', 'Sales Revenue', 'إيرادات المبيعات', 'revenue', 'revenue_operating', False, 2),
            (tenant_id, '4200', 'Other Revenue', 'إيرادات أخرى', 'revenue', 'revenue_non_operating', False, 2),
            # Expenses
            (tenant_id, '5000', 'Cost of Sales', 'تكلفة البضاعة المباعة', 'expense', None, True, 1),
            (tenant_id, '5100', 'COGS', 'تكلفة البضاعة', 'expense', 'cogs', False, 2),
            (tenant_id, '6000', 'Operating Expenses', 'مصاريف التشغيل', 'expense', None, True, 1),
            (tenant_id, '6100', 'Salaries', 'رواتب', 'expense', 'expense_operating', False, 2),
            (tenant_id, '6200', 'Rent', 'إيجار', 'expense', 'expense_operating', False, 2),
            (tenant_id, '6300', 'Utilities', 'مرافق', 'expense', 'expense_operating', False, 2),
            (tenant_id, '6400', 'Marketing', 'تسويق', 'expense', 'expense_operating', False, 2),
            (tenant_id, '6500', 'Depreciation', 'إهلاك', 'expense', 'depreciation', False, 2),
            (tenant_id, '6600', 'Tax', 'ضرائب', 'expense', 'tax', False, 2),
        ]

        gl_map = {}
        parent_map = {}
        for data in gl_accounts_data:
            acc = GLAccount(
                tenant_id=data[0], code=data[1], name=data[2], name_ar=data[3],
                type=data[4], sub_type=data[5], is_header=data[6], level=data[7],
                is_active=True, currency='AED',
            )
            db.session.add(acc)
            gl_map[data[1]] = acc
        db.session.flush()

        # Link parents
        parent_codes = {'1100': '1000', '1200': '1000', '2100': '2000', '3100': '3000', '3200': '3000',
                        '4100': '4000', '4200': '4000', '5100': '5000', '6100': '6000', '6200': '6000',
                        '6300': '6000', '6400': '6000', '6500': '6000', '6600': '6000',
                        '1110': '1100', '1120': '1100', '1130': '1100', '1140': '1100',
                        '2110': '2100', '2120': '2100'}
        for child_code, parent_code in parent_codes.items():
            if child_code in gl_map and parent_code in gl_map:
                gl_map[child_code].parent_id = gl_map[parent_code].id

        db.session.flush()
        print(f'GL Accounts created: {len(gl_accounts_data)}')

        # Create Product Categories
        cat_elec = ProductCategory(tenant_id=tenant_id, name='Electronics', name_ar='إلكترونيات', is_active=True)
        cat_mob = ProductCategory(tenant_id=tenant_id, name='Mobile Phones', name_ar='هواتف محمولة', parent=cat_elec, is_active=True)
        cat_acc = ProductCategory(tenant_id=tenant_id, name='Accessories', name_ar='اكسسوارات', parent=cat_elec, is_active=True)
        cat_comp = ProductCategory(tenant_id=tenant_id, name='Computers', name_ar='حواسيب', parent=cat_elec, is_active=True)
        db.session.add_all([cat_elec, cat_mob, cat_acc, cat_comp])
        db.session.flush()

        # Create Products
        products_data = [
            ('iPhone 15 Pro', 'IPH15P', 3999, cat_mob.id, True),
            ('Samsung S24 Ultra', 'SAM-S24', 3799, cat_mob.id, True),
            ('AirPods Pro 2', 'APP-PRO2', 899, cat_acc.id, True),
            ('MacBook Air M3', 'MBA-M3', 5499, cat_comp.id, True),
            ('Dell XPS 15', 'DELL-XPS', 4999, cat_comp.id, True),
            ('Wireless Mouse', 'MOUSE-WL', 129, cat_acc.id, True),
            ('USB-C Cable', 'USB-C-1M', 49, cat_acc.id, True),
            ('iPad Pro 12.9', 'IPAD-129', 4299, cat_comp.id, True),
            ('Power Bank 20000mAh', 'PB-20K', 199, cat_acc.id, True),
            ('Monitor 27\" 4K', 'MON-27K', 1499, cat_acc.id, True),
        ]
        created_products = []
        for name, sku, price, cat_id, track in products_data:
            p = Product(
                tenant_id=tenant_id,
                name=name,
                name_ar=name,
                sku=sku,
                barcode=sku,
                regular_price=Decimal(str(price)),
                cost_price=Decimal(str(price * 0.6)),
                category_id=cat_id,
                is_active=True,
                current_stock=Decimal('100'),
                min_stock_alert=Decimal('10'),
                unit='piece',
                is_returnable=True,
                return_period_days=7,
            )
            db.session.add(p)
            created_products.append(p)
        db.session.flush()
        print(f'Products created: {len(created_products)}')

        # Create Customers
        customers_data = [
            ('Walk-in Customer', 'عميل نقدي', 'walkin@local', '000', 'walkin', True),
            ('Abu Dhabi Electronics', 'إلكترونيات أبوظبي', 'ade@example.com', '+971-2-555-1111', 'wholesale', True),
            ('Sharjah Trading Co', 'شركة الشارقة التجارية', 'stc@example.com', '+971-6-333-2222', 'retail', True),
            ('Al Ain Market', 'سوق العين', 'aam@example.com', '+971-3-777-3333', 'retail', True),
            ('Dubai Retail Chain', 'سلسلة دبي التجزئة', 'drc@example.com', '+971-4-888-4444', 'wholesale', True),
        ]
        for name, name_ar, email, phone, ctype, active in customers_data:
            c = Customer(
                tenant_id=tenant_id, name=name, name_ar=name_ar, email=email,
                phone=phone, customer_type=ctype, is_active=active,
            )
            db.session.add(c)
        db.session.flush()
        print('Customers created')

        # Create Suppliers
        suppliers_data = [
            ('Apple UAE Distributor', 'موزع آبل الإمارات', 'apple@dist.ae', '+971-4-111-2222', 'TRN-APP-001'),
            ('Samsung Gulf', 'سامسونج الخليج', 'samsung@gulf.ae', '+971-4-222-3333', 'TRN-SAM-001'),
            ('Accessories World', 'عالم الاكسسوارات', 'aw@acc.ae', '+971-4-333-4444', 'TRN-ACC-001'),
        ]
        for name, name_ar, email, phone, tax in suppliers_data:
            s = Supplier(
                tenant_id=tenant_id, name=name, name_ar=name_ar, email=email,
                phone=phone, tax_number=tax, is_active=True,
            )
            db.session.add(s)
        db.session.flush()
        print('Suppliers created')

        # Create Expense Categories
        exp_cats = [
            (tenant_id, 'Rent', 'إيجار'),
            (tenant_id, 'Salaries', 'رواتب'),
            (tenant_id, 'Utilities', 'مرافق'),
            (tenant_id, 'Marketing', 'تسويق'),
            (tenant_id, 'Transport', 'نقل'),
            (tenant_id, 'Maintenance', 'صيانة'),
        ]
        for tid, name, name_ar in exp_cats:
            ec = ExpenseCategory(tenant_id=tid, name=name, name_ar=name_ar, is_active=True)
            db.session.add(ec)
        db.session.flush()
        print('Expense categories created')

        # Create Departments & Job Positions
        dept_sales = Department(tenant_id=tenant_id, name='Sales', name_ar='المبيعات', is_active=True)
        dept_acc = Department(tenant_id=tenant_id, name='Accounting', name_ar='المحاسبة', is_active=True)
        dept_wh = Department(tenant_id=tenant_id, name='Warehouse', name_ar='المستودع', is_active=True)
        db.session.add_all([dept_sales, dept_acc, dept_wh])
        db.session.flush()

        jobs = [
            (dept_sales.id, 'Sales Representative', 'مندوب مبيعات'),
            (dept_sales.id, 'Cashier', 'كاشير'),
            (dept_acc.id, 'Accountant', 'محاسب'),
            (dept_wh.id, 'Warehouse Supervisor', 'مشرف مستودع'),
        ]
        for did, name, name_ar in jobs:
            jp = JobPosition(tenant_id=tenant_id, department_id=did, name=name, name_ar=name_ar, is_active=True)
            db.session.add(jp)
        db.session.flush()
        print('Departments & jobs created')

        # Create Employees
        employees_data = [
            (tenant_id, 'أحمد محمد', 'Ahmed Mohamed', '050-111-2222', 'ahmed@azad.ae', dept_sales.id, 8500),
            (tenant_id, 'محمد علي', 'Mohamed Ali', '050-222-3333', 'mohamed@azad.ae', dept_sales.id, 9000),
            (tenant_id, 'فاطمة حسن', 'Fatima Hassan', '050-333-4444', 'fatima@azad.ae', dept_acc.id, 12000),
            (tenant_id, 'علي عبدالله', 'Ali Abdullah', '050-444-5555', 'ali@azad.ae', dept_wh.id, 7000),
            (tenant_id, 'سارة خالد', 'Sara Khaled', '050-555-6666', 'sara@azad.ae', dept_sales.id, 8000),
        ]
        for tid, name_ar, name_en, phone, email, dept_id, salary in employees_data:
            emp = Employee(
                tenant_id=tid, name=name_en, name_ar=name_ar,
                phone=phone, email=email, branch_id=branch_main.id,
                basic_salary=Decimal(str(salary)), is_active=True, currency='AED',
                joined_date=datetime.now(timezone.utc).date(),
            )
            db.session.add(emp)
        db.session.flush()
        print('Employees created')

        # Set tenant created_by
        tenant.created_by = owner_user.id
        db.session.commit()
        print('Base data committed.')

        # Create sample Sales
        from services.sale_service import SaleService
        cash_customer = Customer.query.filter_by(tenant_id=tenant_id, customer_type='walkin').first()
        wholesale_customer = Customer.query.filter_by(tenant_id=tenant_id, customer_type='wholesale').first()
        sales_user = next((u for u in created_users if u.username == 'sales'), created_users[0])
        for i in range(3):
            try:
                SaleService.create_sale(
                    customer=cash_customer,
                    seller=sales_user,
                    lines_data=[
                        {'product': created_products[i], 'quantity': 2, 'discount_percent': 0, 'unit_price': None},
                        {'product': created_products[i+1], 'quantity': 1, 'discount_percent': 5, 'unit_price': None},
                    ],
                    warehouse_id=wh_main.id,
                    currency='AED',
                    user_exchange_rate=1,
                    payment_data={'amount': 0, 'payment_method': '', 'currency': 'AED', 'exchange_rate': 1} if i == 2 else None,
                )
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f'  Sale {i+1} skipped: {e}')
        print('Sample sales created')

        # Create sample Purchases
        from services.purchase_service import PurchaseService
        supplier = Supplier.query.filter_by(tenant_id=tenant_id).first()
        for i in range(2):
            try:
                PurchaseService.create_purchase(
                    user=owner_user,
                    supplier_data={'id': supplier.id},
                    lines_data=[
                        {'product_id': created_products[i].id, 'quantity': 10, 'unit_price': created_products[i].cost_price * Decimal('0.9') if created_products[i].cost_price else Decimal('100')},
                        {'product_id': created_products[i+2].id, 'quantity': 5, 'unit_price': created_products[i+2].cost_price * Decimal('0.9') if created_products[i+2].cost_price else Decimal('100')},
                    ],
                    warehouse_id=wh_main.id,
                    currency='AED',
                )
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f'  Purchase {i+1} skipped: {e}')
        print('Sample purchases created')

        # Create sample Expenses
        from models import Expense
        from datetime import date
        expense_cats = ExpenseCategory.query.filter_by(tenant_id=tenant_id).all()
        for i, ec in enumerate(expense_cats[:4]):
            try:
                exp = Expense(
                    tenant_id=tenant_id,
                    category_id=ec.id,
                    amount=Decimal(str(1000 + i * 500)),
                    currency='AED',
                    expense_date=date.today(),
                    description=f'Sample expense: {ec.name}',
                    created_by=owner_user.id,
                    is_active=True,
                )
                db.session.add(exp)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f'  Expense {i+1} skipped: {e}')
        print('Sample expenses created')

        db.session.commit()
        print('\n=== SEEDING COMPLETE ===')
        print(f'Tenant: {tenant.name} (ID: {tenant_id})')
        print(f'Users: {len(created_users)}')
        print(f'Products: {len(created_products)}')
        print(f'GL Accounts: {len(gl_accounts_data)}')
        print(f'Sales: 3, Purchases: 2, Expenses: 4')


if __name__ == '__main__':
    app = create_app()
    print('Step 1: Purging demo data...')
    truncate_tables(app)
    print('\nStep 2: Resetting sequences...')
    reset_sequences(app)
    print('\nStep 3: Creating professional seeds...')
    create_seeds(app)
    print('\nDone!')
