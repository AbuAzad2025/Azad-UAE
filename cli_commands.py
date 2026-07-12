import click


def register_build_assets_command(app):
    @app.cli.command('build-assets')
    def build_assets():
        """Minify, hash, and compress static assets."""
        from utils.build_assets import build_all
        build_all()

def register_stock_commands(app):
    @app.cli.command('reconcile-stock')
    @click.option('--tenant-id', type=int, default=None, help='Tenant ID to reconcile (default: all)')
    @click.option('--commit', is_flag=True, help='Persist changes to database')
    def reconcile_stock(tenant_id, commit):
        """Reconcile ProductWarehouseStock with StockMovement and sync current_stock."""
        from services.stock_service import StockService
        result = StockService.reconcile_stock(tenant_id=tenant_id, commit=commit)
        click.echo(f"Created PWS records: {result['created']}")
        click.echo(f"Updated PWS/products: {result['updated']}")
        click.echo(f"Errors: {result['errors']}")
        click.echo(f"Total PWS records: {result['total_pws']}")
        if not commit:
            click.echo("Dry run — use --commit to persist.")
        return result

def register_backup_commands(app):
    @app.cli.command('backup')
    @click.option('--scope', default='system', help='Backup scope: system, tenant, branch, store')
    @click.option('--tenant-id', type=int, default=None, help='Tenant ID for tenant scope')
    @click.option('--branch-id', type=int, default=None, help='Branch ID for branch scope')
    def backup_cmd(scope, tenant_id, branch_id):
        """Run a manual backup."""
        from services.backup_service import BackupService
        result = BackupService.create_backup(
            manual=True,
            description=f"CLI backup ({scope})",
            scope=scope,
            tenant_id=tenant_id,
            branch_id=branch_id,
        )
        if result and result.get('success'):
            click.echo(f"Backup created: {result.get('filename')}")
        else:
            click.echo(f"Backup failed: {result}")
            raise click.ClickException("Backup failed")

def register_reset_platform_db_command(app):
    @app.cli.command('reset-platform-db')
    @click.option('--yes', is_flag=True, help='Confirm destructive wipe of all data')
    def reset_platform_db(yes):
        """Wipe database and bootstrap clean SaaS platform (owner + roles, no tenants)."""
        if not yes:
            raise click.ClickException('Refusing to wipe DB without --yes')

        from extensions import db
        from sqlalchemy import inspect as sa_inspect, text

        click.echo('Dropping all tables...')
        engine = db.engine
        with engine.begin() as conn:
            for table in sa_inspect(engine).get_table_names():
                conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))

        click.echo('Creating schema from squashed baseline migration (explicit, no db.create_all)...')
        from flask_migrate import upgrade
        upgrade(revision='head')

        click.echo('Bootstrapping clean platform (owner + roles)...')
        from utils.system_init import ensure_clean_platform
        ensure_clean_platform(app)

        from models.tenant import Tenant
        tenant_count = Tenant.query.count()
        click.echo(f'Done. Tenants in database: {tenant_count} (clean baseline -- tenants are provisioned via seed commands)')
        click.echo('Create further tenants from Owner panel when ready.')


def register_seed_demo_command(app):
    @app.cli.command('seed-demo')
    @click.option('--force', is_flag=True, help='Re-seed even if demo tenant exists')
    def seed_demo(force):
        """Provision & populate a demo tenant with branches, warehouses, users, products, partners, customers, suppliers, sales, purchases, expenses, salary advances, POS sessions, and sale returns."""
        from extensions import db
        from models.tenant import Tenant

        if Tenant.query.filter_by(slug='demo').first():
            if not force:
                click.echo('Demo tenant already exists. Use --force to re-seed.')
                return
            click.echo('Demo tenant exists — re-seeding with --force.')

        from app import create_app as _create_app
        app = _create_app()
        with app.app_context():
            _do_seed_demo(app)

def _do_seed_demo(app):
    from extensions import db
    from decimal import Decimal
    from sqlalchemy import inspect as sa_inspect, text
    from models.tenant import Tenant
    from models.branch import Branch
    from models.warehouse import Warehouse
    from models.cash_box import CashBox
    from models.user import User, Role, Permission
    from models.customer import Customer
    from models.supplier import Supplier
    from models.partner import Partner
    from models.product import Product, ProductCategory
    from models.tenant_store import TenantStore
    from models.payroll import Employee, PayrollTransaction, SalaryAdvance
    from models.product_return import ProductReturn, ProductReturnLine
    from models.pos_session import PosSession
    from models.sale import Sale
    from models.purchase import Purchase
    from models.expense import Expense, ExpenseCategory
    from services.tenant_provisioning import validate_tenant_industry, provision_tenant_gl
    from services.document_sequence_service import DocumentSequenceService
    from models import ensure_default_pos_order_types, PosOrderType

    # Ensure the (new) pos_order_types table exists before we seed into it.
    # Done on a fresh connection at the very start so it is not blocked by any
    # lock held by the seed's own session transaction further down.
    with db.engine.begin() as _conn:
        PosOrderType.__table__.create(_conn, checkfirst=True)

    SEQUENCE_CODES = ['sale', 'purchase', 'payment', 'receipt', 'gl_entry', 'cheque', 'invoice', 'return', 'expense']

    BRANCHES = [
        {"name": "فرع دبي", "code": "DBX", "city": "دبي"},
        {"name": "فرع أبوظبي", "code": "AUH", "city": "أبوظبي"},
        {"name": "فرع الشارقة", "code": "SHJ", "city": "الشارقة"},
    ]
    CATEGORIES = [
        {"name": "إلكترونيات", "name_ar": "إلكترونيات"},
        {"name": "ملابس", "name_ar": "ملابس"},
        {"name": "مواد غذائية", "name_ar": "مواد غذائية"},
        {"name": "أدوات مكتبية", "name_ar": "أدوات مكتبية"},
        {"name": "منتجات العناية الشخصية", "name_ar": "منتجات العناية الشخصية"},
    ]
    CUSTOMERS = [
        {"name": "أحمد محمد", "name_ar": "أحمد محمد", "phone": "0501111111", "customer_type": "individual"},
        {"name": "شركة النور", "name_ar": "شركة النور", "phone": "0502222222", "customer_type": "company"},
        {"name": "فاطمة علي", "name_ar": "فاطمة علي", "phone": "0503333333", "customer_type": "individual"},
        {"name": "مؤسسة السلام", "name_ar": "مؤسسة السلام", "phone": "0504444444", "customer_type": "company"},
        {"name": "خالد سعيد", "name_ar": "خالد سعيد", "phone": "0505555555", "customer_type": "individual"},
    ]
    SUPPLIERS = [
        {"name": "المورد العالمي", "name_ar": "المورد العالمي", "phone": "0506666666", "company_name": "Global Supply Co"},
        {"name": "مؤسسة الخليج", "name_ar": "مؤسسة الخليج", "phone": "0507777777", "company_name": "Gulf Trading"},
        {"name": "شركة الاتحاد", "name_ar": "شركة الاتحاد", "phone": "0508888888", "company_name": "Al-Ittihad LLC"},
        {"name": "الشرق الأوسط للتجارة", "name_ar": "الشرق الأوسط للتجارة", "phone": "0509999999", "company_name": "Middle East Trade"},
        {"name": "مصنع الإمارات", "name_ar": "مصنع الإمارات", "phone": "0501010101", "company_name": "Emirates Factory"},
    ]
    PARTNERS = [
        {"name": "شريك تجاري ١", "partner_type": "business", "scope_type": "tenant", "share_percentage": 30},
        {"name": "شريك تجاري ٢", "partner_type": "investor", "scope_type": "tenant", "share_percentage": 25},
        {"name": "شريك تجاري ٣", "partner_type": "business", "scope_type": "branch", "share_percentage": 20},
        {"name": "شريك تجاري ٤", "partner_type": "silent", "scope_type": "tenant", "share_percentage": 15},
        {"name": "شريك تجاري ٥", "partner_type": "business", "scope_type": "branch", "share_percentage": 10},
    ]
    DEMO_ROLES = [
        {"name": "محاسب", "slug": "demo_accountant"},
        {"name": "أمين صندوق", "slug": "demo_cashier"},
        {"name": "أمين مستودع", "slug": "demo_warehouse"},
    ]
    BRANCH_EMPLOYEES = [
        ("demo_dbx1", "موظف دبي ١", "demo_cashier", "DBX"),
        ("demo_dbx2", "موظف دبي ٢", "demo_warehouse", "DBX"),
        ("demo_auh1", "موظف أبوظبي ١", "demo_cashier", "AUH"),
        ("demo_auh2", "موظف أبوظبي ٢", "demo_warehouse", "AUH"),
        ("demo_shj1", "موظف الشارقة ١", "demo_cashier", "SHJ"),
        ("demo_shj2", "موظف الشارقة ٢", "demo_warehouse", "SHJ"),
    ]
    GENERAL_EMPLOYEES = [
        ("demo_accountant", "محاسب عام", "demo_accountant"),
        ("demo_cashier1", "أمين صندوق رئيسي", "demo_cashier"),
        ("demo_warehouse1", "أمين مستودع رئيسي", "demo_warehouse"),
        ("demo_manager", "مدير عام", "admin"),
    ]
    PRODUCTS = [
        ("لابتوب ديل", 0, 2500, 2000, 15),
        ("جوال سامسونج", 0, 1500, 1200, 25),
        ("سماعات بلوتوث", 0, 200, 150, 50),
        ("قميص رجالي", 1, 120, 80, 100),
        ("فستان نسائي", 1, 250, 180, 60),
        ("حذاء رياضي", 1, 350, 250, 40),
        ("أرز بسمتي", 2, 60, 45, 200),
        ("زيت زيتون", 2, 40, 30, 150),
        ("سكر", 2, 15, 10, 300),
        ("دفتر ملاحظات", 3, 25, 18, 500),
        ("أقلام حبر", 3, 10, 7, 1000),
        ("شامبو", 4, 35, 25, 80),
    ]

    def _get_or_create_role(role_slug, role_name):
        role = Role.query.filter_by(slug=role_slug).first()
        if not role:
            role = Role(name=role_name, slug=role_slug)
            db.session.add(role)
            db.session.flush()
        return role

    # 1. Provision Demo Tenant
    demo_tenant = Tenant.query.filter_by(slug='demo').first()
    if demo_tenant:
        click.echo("Dropping existing demo data...")
        tid = demo_tenant.id
        # Comprehensive wipe of every tenant-scoped table. We temporarily disable
        # FK enforcement for the session so the delete order doesn't trip over
        # ON DELETE NO ACTION constraints (e.g. stock_movements -> warehouses).
        # This is a demo-reset utility, not production runtime.
        eng_meta = sa_inspect(db.engine)
        tenant_tables = [
            t for t in eng_meta.get_table_names()
            if any(c["name"] == "tenant_id" for c in eng_meta.get_columns(t))
        ]
        db.session.execute(text("SET session_replication_role = 'replica'"))
        try:
            for t in tenant_tables:
                db.session.execute(
                    text(f"DELETE FROM {t} WHERE tenant_id = :tid"), {"tid": tid}
                )
        finally:
            db.session.execute(text("SET session_replication_role = 'origin'"))
        db.session.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tid})
        db.session.commit()
        click.echo("Old demo data removed.")

    demo_tenant = Tenant(
        name="Demo", name_ar="ديمو", slug="demo", business_type="general", is_active=True,
    )
    # Application-level industry enforcement (no DB schema change).
    validate_tenant_industry(demo_tenant.business_type, demo_tenant.industry)
    db.session.add(demo_tenant)
    db.session.flush()
    tid = demo_tenant.id

    # Seed generic, industry-neutral POS order types for the demo company.
    ensure_default_pos_order_types(tid)

    branch = Branch(name="الفرع الرئيسي", code="MAIN", tenant_id=tid, is_main=True)
    db.session.add(branch)
    db.session.flush()

    warehouse = Warehouse(name="المستودع الرئيسي", tenant_id=tid, branch_id=branch.id, warehouse_type="general", is_main=True)
    db.session.add(warehouse)

    cashbox = CashBox(name_ar="الصندوق الرئيسي", code="MAIN", tenant_id=tid, branch_id=branch.id, box_type="cash", currency="ILS", current_balance=0, is_active=True, is_default=True)
    db.session.add(cashbox)

    provision_tenant_gl(tid)  # idempotent base + industry-extension seeding
    for code in SEQUENCE_CODES:
        DocumentSequenceService.get_or_create(tid, code)

    role = Role.query.filter_by(slug='admin').first()
    if not role:
        role = Role(name='Admin', slug='admin')
        db.session.add(role)
        db.session.flush()

    demo_admin = User(username='demo_admin', email='demo@azad.com', tenant_id=tid, branch_id=branch.id, role_id=role.id, is_active=True, is_owner=False)
    demo_admin.set_password('Demo@2026')
    db.session.add(demo_admin)
    db.session.flush()

    # 2. Enable store
    demo_tenant.enable_store = True
    demo_tenant.enable_pos = True
    demo_tenant.enable_payroll = True
    if not TenantStore.query.filter_by(tenant_id=tid).first():
        store = TenantStore(tenant_id=tid, warehouse_id=warehouse.id, is_enabled=True, platform_disabled=False, store_slug="demo", title="متجر ديمو", tagline="المتجر التجريبي لمنصة أزاديكسا", phone="0500000000", email="demo@azad.com", notify_whatsapp_on_order=False, notify_email_on_order=True)
        db.session.add(store)

    # 3. Additional branches
    branch_map = {"MAIN": (branch, warehouse)}
    for bdata in BRANCHES:
        br = Branch(name=bdata["name"], code=bdata["code"], tenant_id=tid, city=bdata.get("city"), is_main=False, is_active=True)
        db.session.add(br)
        db.session.flush()
        wh = Warehouse(name=f"مخزن {bdata['name']}", tenant_id=tid, branch_id=br.id, warehouse_type="general", is_main=False)
        db.session.add(wh)
        cb = CashBox(name_ar=f"صندوق {bdata['name']}", code=bdata["code"], tenant_id=tid, branch_id=br.id, box_type="cash", currency="ILS", current_balance=0, is_active=True, is_default=False)
        db.session.add(cb)
        branch_map[bdata["code"]] = (br, wh)
    db.session.flush()

    # 4. Categories
    cat_objs = []
    for cdata in CATEGORIES:
        cat = ProductCategory(tenant_id=tid, name=cdata["name"], name_ar=cdata["name_ar"], is_active=True)
        db.session.add(cat)
        db.session.flush()
        cat_objs.append(cat)

    # 5. Customers
    for cdata in CUSTOMERS:
        cust = Customer(tenant_id=tid, name=cdata["name"], name_ar=cdata.get("name_ar"), phone=cdata.get("phone"), customer_type=cdata["customer_type"], balance=0, is_active=True)
        db.session.add(cust)

    # 6. Suppliers
    for sdata in SUPPLIERS:
        sup = Supplier(tenant_id=tid, name=sdata["name"], name_ar=sdata.get("name_ar"), phone=sdata.get("phone"), company_name=sdata.get("company_name"), is_active=True)
        db.session.add(sup)

    # 7. Partners
    for pdata in PARTNERS:
        scope_id = None
        if pdata["scope_type"] == "branch":
            non_main = Branch.query.filter_by(tenant_id=tid, is_main=False).first()
            scope_id = non_main.id if non_main else None
        partner = Partner(tenant_id=tid, name=pdata["name"], partner_type=pdata["partner_type"], scope_type=pdata["scope_type"], scope_id=scope_id, share_percentage=pdata.get("share_percentage"), is_active=True)
        db.session.add(partner)

    # 8. Roles
    role_map = {}
    for rdata in DEMO_ROLES:
        r = _get_or_create_role(rdata["slug"], rdata["name"])
        role_map[rdata["slug"]] = r
    role_map["admin"] = Role.query.filter_by(slug='admin').first()

    # 8b. Grant permissions to demo roles so permission-gated pages (e.g. /customers)
    # are actually accessible. The 'admin' slug is intentionally NOT granted
    # permissions by system_init, so we assign them here for the demo.
    def _grant_perms(role, codes):
        role.permissions = Permission.query.filter(Permission.code.in_(codes)).all()

    _grant_perms(role_map["admin"], [p.code for p in Permission.query.all()])
    _grant_perms(role_map["demo_accountant"], [
        "manage_payments", "manage_expenses", "view_reports",
        "view_ledger", "manage_ledger", "manage_payroll",
    ])
    _grant_perms(role_map["demo_cashier"], [
        "manage_sales", "manage_customers", "view_reports",
        "view_ledger", "view_kds", "manage_payments", "manage_store",
    ])
    _grant_perms(role_map["demo_warehouse"], [
        "manage_products", "manage_purchases", "manage_warehouse",
        "view_reports", "view_ledger", "manage_suppliers",
    ])
    db.session.flush()

    # 9. Branch employees
    for username, full_name_ar, role_slug, br_code in BRANCH_EMPLOYEES:
        br, _ = branch_map.get(br_code, (None, None))
        u = User(username=username, email=f"{username}@demo.azad.com", tenant_id=tid, branch_id=br.id if br else None, role_id=role_map[role_slug].id, full_name_ar=full_name_ar, is_active=True, is_owner=False)
        u.set_password('Demo@2026')
        db.session.add(u)

    # 10. General employees
    for username, full_name_ar, role_slug in GENERAL_EMPLOYEES:
        u = User(username=username, email=f"{username}@demo.azad.com", tenant_id=tid, branch_id=branch.id, role_id=role_map[role_slug].id, full_name_ar=full_name_ar, is_active=True, is_owner=False)
        u.set_password('Demo@2026')
        db.session.add(u)

    db.session.flush()

    # 11. Products
    from models.warehouse import ProductWarehouseStock
    from services.stock_service import StockService
    all_branches = [("MAIN", branch, warehouse)] + [(b["code"], branch_map[b["code"]][0], branch_map[b["code"]][1]) for b in BRANCHES]
    product_idx = 0
    for br_code, br, wh in all_branches:
        for i in range(3):
            if product_idx >= len(PRODUCTS):
                break
            pdata = PRODUCTS[product_idx]
            name_ar_text, cat_idx, price, cost, stock = pdata
            sku = f"DEMO-{br_code}-{i+1:03d}"
            prod = Product(tenant_id=tid, name_ar=name_ar_text, name=name_ar_text, sku=sku, category_id=cat_objs[cat_idx].id, regular_price=price, cost_price=cost, current_stock=stock, has_serial_number=False, unit="قطعة", is_active=True)
            db.session.add(prod)
            db.session.flush()
            # Provision opening stock (StockMovement + ProductWarehouseStock)
            StockService.add_stock(prod.id, stock, warehouse_id=wh.id, reference_type="initial", notes="رصيد افتتاحي")
            product_idx += 1

    # 12. Partner products
    partners = Partner.query.filter_by(tenant_id=tid).all()
    for i, partner in enumerate(partners):
        sku = f"DEMO-PARTNER-{i+1:03d}"
        prod = Product(tenant_id=tid, name_ar=f"منتج {partner.name}", name=f"Product {partner.name}", sku=sku, category_id=cat_objs[i % len(cat_objs)].id, regular_price=500 + (i * 100), cost_price=350 + (i * 70), partner_price=450 + (i * 90), current_stock=30, has_serial_number=False, unit="قطعة", is_active=True)
        db.session.add(prod)

    demo_tenant.business_type = "multi_branch_retail"
    provision_tenant_gl(tid)  # re-apply idempotent GL seeding now industry is finalized

    # 13. Employees & Payroll
    employee_data = [("demo_manager", 5000), ("demo_accountant", 4000), ("demo_cashier1", 4500)]
    for uname, salary in employee_data:
        user = User.query.filter_by(username=uname).first()
        if not user:
            continue
        emp = Employee.query.filter_by(tenant_id=tid, name=(user.full_name_ar or uname)).first()
        if not emp:
            emp = Employee(tenant_id=tid, name=(user.full_name_ar or uname))
            db.session.add(emp)
            db.session.flush()
        if not PayrollTransaction.query.filter_by(tenant_id=tid, employee_id=emp.id).first():
            db.session.add(PayrollTransaction(tenant_id=tid, employee_id=emp.id, net_salary=salary))

    # 14. Expense Categories
    exp_cat_names = ["إيجار", "كهرباء وماء", "صيانة"]
    exp_cats = {}
    for cn in exp_cat_names:
        c = ExpenseCategory(tenant_id=tid, name=cn)
        db.session.add(c)
        db.session.flush()
        exp_cats[cn] = c

    # 15. Sales (via SaleService so GL, customer balance, and receipts are posted)
    customers = Customer.query.filter_by(tenant_id=tid).limit(3).all()
    seller = User.query.filter_by(tenant_id=tid, username="demo_admin").first()
    from services.sale_service import SaleService
    products_for_sale = Product.query.filter_by(tenant_id=tid).limit(6).all()
    # (customer, product, total, payment_method, paid_amount)
    sale_specs = [
        (customers[0], products_for_sale[0], 1500, "cash", 1500),
        (customers[1], products_for_sale[1], 3200, "credit", 0),
        (customers[2], products_for_sale[2], 850, "bank", 500),
    ]
    for cust, prod, amount, pay_method, paid in sale_specs:
        if not cust or not prod:
            continue
        pws = ProductWarehouseStock.query.filter_by(tenant_id=tid, product_id=prod.id).first()
        sale_wh_id = pws.warehouse_id if pws else warehouse.id
        lines_data = [{"product": prod, "quantity": 1, "unit_price": Decimal(str(amount))}]
        payment_data = None
        if paid and paid > 0:
            payment_data = {
                "amount": Decimal(str(paid)),
                "payment_method": pay_method,
                "currency": "ILS",
                "exchange_rate": 1,
            }
        SaleService.create_sale(
            customer=cust, seller=seller, lines_data=lines_data,
            warehouse_id=sale_wh_id, currency="ILS", tax_rate=0,
            source="manual", payment_data=payment_data,
        )

    # 16. Purchases (via PurchaseService so GL, supplier balance, and stock are posted)
    from services.purchase_service import PurchaseService
    from services.payment_service import PaymentService
    suppliers = Supplier.query.filter_by(tenant_id=tid).limit(3).all()
    purch_products = Product.query.filter_by(tenant_id=tid).limit(6).all()
    purch_specs = [
        (suppliers[0], purch_products[3], 2200, "cash", 2200),
        (suppliers[1], purch_products[4], 1800, "credit", 0),
        (suppliers[2], purch_products[5], 950, "bank", 600),
    ]
    for sup, prod, amount, pay_method, paid in purch_specs:
        if not sup or not prod:
            continue
        pur_wh_id = warehouse.id
        lines_data = [{"product_id": prod.id, "quantity": 1, "unit_cost": Decimal(str(amount))}]
        purchase = PurchaseService.create_purchase(
            user=seller, supplier_data={"supplier_id": sup.id}, lines_data=lines_data,
            warehouse_id=pur_wh_id, currency="ILS", tax_rate=0,
        )
        if paid and paid > 0:
            PaymentService.create_payment({
                "supplier_id": sup.id,
                "amount": Decimal(str(paid)),
                "currency": "ILS",
                "payment_method": pay_method,
                "branch_id": branch.id,
                "notes": "دفعة للمورد (بذور تجريبية)",
            })

    # 17. Expenses
    exp_data = [("إيجار", 2000), ("كهرباء وماء", 450), ("صيانة", 300)]
    for i, (cn, amt) in enumerate(exp_data):
        en = f"DEMO-EXP-{i+1:03d}"
        db.session.add(Expense(tenant_id=tid, expense_number=en, category_id=exp_cats[cn].id, description=f"{cn} - شهر يوليو", amount=amt, currency="ILS", amount_aed=amt, expense_date=db.func.current_date(), payment_method="cash", user_id=seller.id))

    # 18. Salary advances (سلف) — up to 5
    employees = Employee.query.filter_by(tenant_id=tid).all()
    advance_amounts = [500, 300, 200]
    for i, emp in enumerate(employees[:3]):
        if not SalaryAdvance.query.filter_by(tenant_id=tid, employee_id=emp.id).first():
            amt = advance_amounts[i]
            adv = SalaryAdvance(
                tenant_id=tid, employee_id=emp.id, amount=amt,
                total_amount=amt, deducted_amount=0, remaining_amount=amt,
                date=db.func.current_date(), description="سلفة شهرية", status="approved",
                is_deducted=False, created_by=seller.id if seller else None,
            )
            db.session.add(adv)

    # 19. POS enablement + sessions — up to 5
    demo_tenant.enable_pos = True
    demo_tenant.enable_payroll = True
    pos_cashier = User.query.filter_by(tenant_id=tid, username="demo_cashier1").first() or seller
    pos_sessions = [
        ("MAIN", 500.0, 3200.0),
        ("DBX", 300.0, 1500.0),
    ]
    for i, (br_code, opening, total_sales) in enumerate(pos_sessions):
        br, _ = branch_map.get(br_code, (branch, warehouse))
        sess = PosSession(
            tenant_id=tid, branch_id=br.id,
            user_id=(pos_cashier.id if pos_cashier else (seller.id if seller else None)),
            session_number=f"DEMO-POS-{i+1:03d}", opening_balance_cash=opening,
            total_sales=total_sales, total_cash_sales=total_sales, status="open",
        )
        db.session.add(sess)

    # 20. Sale returns (مرتجعات) — up to 5
    sales_for_return = Sale.query.filter_by(tenant_id=tid).limit(3).all()
    return_products = Product.query.filter_by(tenant_id=tid).limit(3).all()
    for i, sale in enumerate(sales_for_return[:3]):
        prod = return_products[i % len(return_products)] if return_products else None
        if not prod:
            continue
        qty = Decimal("1")
        price = Decimal(str(prod.regular_price or 100))
        total = qty * price
        ret = ProductReturn(
            tenant_id=tid, return_number=f"DEMO-RET-{i+1:03d}", sale_id=sale.id,
            customer_id=sale.customer_id, branch_id=branch.id, currency="ILS",
            exchange_rate=1, return_reason="عيب في المنتج / تغيير رأي", status="completed",
            processed_by=(seller.id if seller else None),
            total_amount=total, refund_amount=total, amount_aed=total,
        )
        db.session.add(ret)
        db.session.flush()
        line = ProductReturnLine(
            tenant_id=tid, return_id=ret.id, product_id=prod.id,
            quantity=qty, unit_price=price, line_total=total,
        )
        db.session.add(line)
        db.session.flush()

    # Recompute customer balances from posted sales/payments
    # (stored sign convention: negative = customer owes us)
    for cust in Customer.query.filter_by(tenant_id=tid).all():
        bal = db.session.query(
            db.func.coalesce(db.func.sum(Sale.paid_amount_aed - Sale.amount_aed), 0)
        ).filter(Sale.customer_id == cust.id, Sale.status == 'confirmed', Sale.is_active == True).scalar() or Decimal('0')
        cust.balance = bal
    db.session.flush()

    db.session.commit()
    click.echo("Demo tenant seeded successfully (branches, warehouses, users, products, partners, "
               "customers, suppliers, sales, purchases, expenses, salary advances, POS sessions, returns).")

def register_sanitize_command(app):
    @app.cli.command('sanitize-legacy-industries')
    @click.option('--commit', is_flag=True, help='Persist changes to the database (default: dry run)')
    def sanitize_legacy_industries(commit):
        """Backfill legacy NULL business_type/industry and align GL ledgers for all tenants.

        1. Backfill: set business_type='general' and industry='retail' ONLY where currently NULL
           (direct SQL UPDATE).
        2. Retroactive ledger alignment: re-run the idempotent provision_tenant_gl for every tenant
           so missing industry GL accounts are seeded without duplicating existing entries.

        Dry run by default — nothing is written until --commit is supplied.
        """
        from sqlalchemy import text
        from extensions import db
        from models.tenant import Tenant
        from services.tenant_provisioning import provision_tenant_gl

        bt_null = db.session.execute(
            text("SELECT COUNT(*) FROM tenants WHERE business_type IS NULL")
        ).scalar() or 0
        ind_null = db.session.execute(
            text("SELECT COUNT(*) FROM tenants WHERE industry IS NULL")
        ).scalar() or 0

        if commit:
            db.session.execute(
                text("UPDATE tenants SET business_type = 'general' WHERE business_type IS NULL")
            )
            db.session.execute(
                text("UPDATE tenants SET industry = 'retail' WHERE industry IS NULL")
            )
            db.session.commit()
            click.echo(f"Backfilled business_type='general' on {bt_null} tenant(s); "
                       f"industry='retail' on {ind_null} tenant(s).")
        else:
            click.echo(f"Dry run: would set business_type='general' on {bt_null} NULL row(s); "
                       f"industry='retail' on {ind_null} NULL row(s). Use --commit to persist.")

        tenants = Tenant.query.all()
        click.echo(f"Aligning GL ledgers for {len(tenants)} tenant(s) (idempotent)...")
        for t in tenants:
            try:
                result = provision_tenant_gl(t.id)
                db.session.commit()
                label = getattr(t, 'name', None) or getattr(t, 'slug', None) or t.id
                click.echo(
                    f"  tenant {t.id} ({label}): GL accounts +{result.get('created_accounts', 0)} "
                    f"(skipped {result.get('skipped_accounts', 0)}), "
                    f"mappings +{result.get('created_mappings', 0)} "
                    f"(skipped {result.get('skipped_mappings', 0)})"
                )
            except Exception as e:
                db.session.rollback()
                click.echo(f"  tenant {t.id}: ERROR - {e}")
        click.echo("Done.")


def register_cli_commands(app):
    register_build_assets_command(app)
    register_stock_commands(app)
    register_backup_commands(app)
    register_reset_platform_db_command(app)
    register_seed_demo_command(app)
    register_sanitize_command(app)
