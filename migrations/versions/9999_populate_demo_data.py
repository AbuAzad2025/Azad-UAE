"""Comprehensive Demo Data Population — Branches, Users, Store, Customers, Partners, Suppliers, Products

Revision ID: 9999_populate_demo_data
Revises: 9999_provision_demo_sovereign
"""
from alembic import op
import sqlalchemy as sa

revision = "9999_populate_demo_data"
down_revision = "9999_provision_demo_sovereign"
branch_labels = None
depends_on = None

from app import create_app
from extensions import db
from models.tenant import Tenant
from models.branch import Branch
from models.warehouse import Warehouse
from models.cash_box import CashBox
from models.user import User, Role
from models.customer import Customer
from models.supplier import Supplier
from models.partner import Partner
from models.product import Product, ProductCategory
from models.tenant_store import TenantStore
from models.payroll import Employee, PayrollTransaction
from models.sale import Sale
from models.purchase import Purchase
from models.expense import Expense, ExpenseCategory

# ── Config ────────────────────────────────────────────────────────────────
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

# Employees per branch (username, full_name_ar, role_slug)
# (username, full_name_ar, role_slug, branch_code)
BRANCH_EMPLOYEES = [
    ("demo_dbx1", "موظف دبي ١", "demo_cashier", "DBX"),
    ("demo_dbx2", "موظف دبي ٢", "demo_warehouse", "DBX"),
    ("demo_auh1", "موظف أبوظبي ١", "demo_cashier", "AUH"),
    ("demo_auh2", "موظف أبوظبي ٢", "demo_warehouse", "AUH"),
    ("demo_shj1", "موظف الشارقة ١", "demo_cashier", "SHJ"),
    ("demo_shj2", "موظف الشارقة ٢", "demo_warehouse", "SHJ"),
]

# General employees at MAIN (username, full_name_ar, role_slug)
GENERAL_EMPLOYEES = [
    ("demo_accountant", "محاسب عام", "demo_accountant"),
    ("demo_cashier1", "أمين صندوق رئيسي", "demo_cashier"),
    ("demo_warehouse1", "أمين مستودع رئيسي", "demo_warehouse"),
    ("demo_manager", "مدير عام", "admin"),
]

# Products per warehouse (name_ar, category_idx, regular_price, cost_price, current_stock)
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


def upgrade():
    app = create_app()
    with app.app_context():
        demo = Tenant.query.filter_by(slug='demo').first()
        if not demo:
            print("Demo tenant not found — run 9999_provision_demo_sovereign first.")
            return
        tid = demo.id
        main_branch = Branch.query.filter_by(tenant_id=tid, is_main=True).first()
        main_wh = Warehouse.query.filter_by(tenant_id=tid, is_main=True).first()

        # ── 1. Enable store ──────────────────────────────────────────────
        demo.enable_store = True
        if not TenantStore.query.filter_by(tenant_id=tid).first():
            store = TenantStore(
                tenant_id=tid,
                warehouse_id=main_wh.id,
                is_enabled=True,
                platform_disabled=False,
                store_slug="demo",
                title="متجر ديمو",
                tagline="المتجر التجريبي لمنصة أزاديكسا",
                phone="0500000000",
                email="demo@azad.com",
                notify_whatsapp_on_order=False,
                notify_email_on_order=True,
            )
            db.session.add(store)

        # ── 2. Additional branches + per-branch warehouse & cashbox ──────
        branch_map = {"MAIN": (main_branch, main_wh)}  # code -> (branch, warehouse)
        demo_admin = User.query.filter_by(username='demo_admin').first()

        for bdata in BRANCHES:
            existing = Branch.query.filter_by(tenant_id=tid, code=bdata["code"]).first()
            if existing:
                branch_map[bdata["code"]] = (existing, Warehouse.query.filter_by(
                    tenant_id=tid, branch_id=existing.id
                ).first())
                continue
            br = Branch(
                name=bdata["name"],
                code=bdata["code"],
                tenant_id=tid,
                city=bdata.get("city"),
                is_main=False,
                is_active=True,
            )
            db.session.add(br)
            db.session.flush()

            wh = Warehouse(
                name=f"مخزن {bdata['name']}",
                tenant_id=tid,
                branch_id=br.id,
                warehouse_type="general",
                is_main=False,
            )
            db.session.add(wh)

            cb = CashBox(
                name_ar=f"صندوق {bdata['name']}",
                code=bdata["code"],
                tenant_id=tid,
                branch_id=br.id,
                box_type="cash",
                currency="ILS",
                current_balance=0,
                is_active=True,
                is_default=False,
            )
            db.session.add(cb)
            branch_map[bdata["code"]] = (br, wh)
        db.session.flush()

        # ── 3. Product categories ────────────────────────────────────────
        cat_objs = []
        for cdata in CATEGORIES:
            existing = ProductCategory.query.filter_by(tenant_id=tid, name=cdata["name"]).first()
            if existing:
                cat_objs.append(existing)
                continue
            cat = ProductCategory(tenant_id=tid, name=cdata["name"], name_ar=cdata["name_ar"], is_active=True)
            db.session.add(cat)
            db.session.flush()
            cat_objs.append(cat)

        # ── 4. Customers ─────────────────────────────────────────────────
        for cdata in CUSTOMERS:
            if Customer.query.filter_by(tenant_id=tid, name=cdata["name"]).first():
                continue
            cust = Customer(
                tenant_id=tid,
                name=cdata["name"],
                name_ar=cdata.get("name_ar"),
                phone=cdata.get("phone"),
                customer_type=cdata["customer_type"],
                balance=0,
                is_active=True,
            )
            db.session.add(cust)

        # ── 5. Suppliers ─────────────────────────────────────────────────
        for sdata in SUPPLIERS:
            if Supplier.query.filter_by(tenant_id=tid, name=sdata["name"]).first():
                continue
            sup = Supplier(
                tenant_id=tid,
                name=sdata["name"],
                name_ar=sdata.get("name_ar"),
                phone=sdata.get("phone"),
                company_name=sdata.get("company_name"),
                is_active=True,
            )
            db.session.add(sup)

        # ── 6. Partners ──────────────────────────────────────────────────
        for pdata in PARTNERS:
            if Partner.query.filter_by(tenant_id=tid, name=pdata["name"]).first():
                continue
            scope_id = None
            if pdata["scope_type"] == "branch":
                # assign to a random non-main branch
                non_main = Branch.query.filter_by(tenant_id=tid, is_main=False).first()
                scope_id = non_main.id if non_main else None
            partner = Partner(
                tenant_id=tid,
                name=pdata["name"],
                partner_type=pdata["partner_type"],
                scope_type=pdata["scope_type"],
                scope_id=scope_id,
                share_percentage=pdata.get("share_percentage"),
                is_active=True,
            )
            db.session.add(partner)

        # ── 7. Roles ─────────────────────────────────────────────────────
        role_map = {}
        for rdata in DEMO_ROLES:
            r = _get_or_create_role(rdata["slug"], rdata["name"])
            role_map[rdata["slug"]] = r
        role_map["admin"] = Role.query.filter_by(slug='admin').first()

        # ── 8. Branch employees (2 per branch) ────────────────────────────
        branch_codes = [b["code"] for b in BRANCHES]
        for username, full_name_ar, role_slug, br_code in BRANCH_EMPLOYEES:
            if User.query.filter_by(username=username).first():
                continue
            br, _ = branch_map.get(br_code, (None, None))
            u = User(
                username=username,
                email=f"{username}@demo.azad.com",
                tenant_id=tid,
                branch_id=br.id if br else None,
                role_id=role_map[role_slug].id,
                full_name_ar=full_name_ar,
                is_active=True,
                is_owner=False,
            )
            u.set_password('Demo@2026')
            db.session.add(u)

        # ── 9. General employees at MAIN ─────────────────────────────────
        for username, full_name_ar, role_slug in GENERAL_EMPLOYEES:
            if User.query.filter_by(username=username).first():
                continue
            u = User(
                username=username,
                email=f"{username}@demo.azad.com",
                tenant_id=tid,
                branch_id=main_branch.id,
                role_id=role_map[role_slug].id,
                full_name_ar=full_name_ar,
                is_active=True,
                is_owner=False,
            )
            u.set_password('Demo@2026')
            db.session.add(u)

        db.session.flush()

        # ── 10. Products (3 per branch warehouse) ────────────────────────
        all_branches = [("MAIN", main_branch, main_wh)] + [
            (b["code"], branch_map[b["code"]][0], branch_map[b["code"]][1])
            for b in BRANCHES
        ]
        product_idx = 0
        for br_code, br, wh in all_branches:
            for i in range(3):
                if product_idx >= len(PRODUCTS):
                    break
                pdata = PRODUCTS[product_idx]
                name_ar, cat_idx, price, cost, stock = pdata
                sku = f"DEMO-{br_code}-{i+1:03d}"
                if Product.query.filter_by(tenant_id=tid, sku=sku).first():
                    product_idx += 1
                    continue
                prod = Product(
                    tenant_id=tid,
                    name_ar=name_ar,
                    name=name_ar,
                    sku=sku,
                    category_id=cat_objs[cat_idx].id,
                    regular_price=price,
                    cost_price=cost,
                    current_stock=stock,
                    has_serial_number=False,
                    unit="قطعة",
                    is_active=True,
                )
                db.session.add(prod)
                product_idx += 1

        # ── 11. Partner products (1 per partner) ─────────────────────────
        partners = Partner.query.filter_by(tenant_id=tid).all()
        for i, partner in enumerate(partners):
            sku = f"DEMO-PARTNER-{i+1:03d}"
            if Product.query.filter_by(tenant_id=tid, sku=sku).first():
                continue
            prod = Product(
                tenant_id=tid,
                name_ar=f"منتج {partner.name}",
                name=f"Product {partner.name}",
                sku=sku,
                category_id=cat_objs[i % len(cat_objs)].id,
                regular_price=500 + (i * 100),
                cost_price=350 + (i * 70),
                partner_price=450 + (i * 90),
                current_stock=30,
                has_serial_number=False,
                unit="قطعة",
                is_active=True,
            )
            db.session.add(prod)

        # ── 12. Update tenant business metadata ──────────────────────────
        demo.business_type = "multi_branch_retail"

        # ── 13. Employees & Payroll ────────────────────────────────────
        employee_data = [
            ("demo_manager", 5000),
            ("demo_accountant", 4000),
            ("demo_cashier1", 4500),
        ]
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

        # ── 14. Expense Categories ─────────────────────────────────────
        exp_cat_names = ["إيجار", "كهرباء وماء", "صيانة"]
        exp_cats = {}
        for cn in exp_cat_names:
            c = ExpenseCategory.query.filter_by(tenant_id=tid, name=cn).first()
            if not c:
                c = ExpenseCategory(tenant_id=tid, name=cn)
                db.session.add(c)
                db.session.flush()
            exp_cats[cn] = c

        # ── 15. Sales (3) ──────────────────────────────────────────────
        customers = Customer.query.filter_by(tenant_id=tid).limit(3).all()
        seller = User.query.filter_by(tenant_id=tid, username="demo_admin").first()
        sale_data = [1500, 3200, 850]
        for i, cust in enumerate(customers):
            sn = f"DEMO-SALE-{i+1:03d}"
            if not Sale.query.filter_by(tenant_id=tid, sale_number=sn).first():
                db.session.add(Sale(
                    tenant_id=tid, sale_number=sn,
                    customer_id=cust.id, seller_id=seller.id,
                    sale_date=db.func.current_date(),
                    total_amount=sale_data[i], amount=sale_data[i],
                    currency="ILS", amount_aed=sale_data[i],
                    prices_include_vat=False, source="manual", is_active=True,
                ))

        # ── 16. Purchases (3) ──────────────────────────────────────────
        suppliers = Supplier.query.filter_by(tenant_id=tid).limit(3).all()
        purch_data = [2200, 1800, 950]
        for i, sup in enumerate(suppliers):
            pn = f"DEMO-PUR-{i+1:03d}"
            if not Purchase.query.filter_by(tenant_id=tid, purchase_number=pn).first():
                db.session.add(Purchase(
                    tenant_id=tid, purchase_number=pn,
                    supplier_name=sup.name,
                    purchase_date=db.func.current_date(),
                    total_amount=purch_data[i], amount=purch_data[i],
                    currency="ILS", amount_aed=purch_data[i],
                    prices_include_vat=False,
                    freight=0, insurance=0, customs_duty=0, other_landed_cost=0,
                    user_id=seller.id,
                ))

        # ── 17. Expenses (3) ───────────────────────────────────────────
        exp_data = [("إيجار", 2000), ("كهرباء وماء", 450), ("صيانة", 300)]
        for i, (cn, amt) in enumerate(exp_data):
            en = f"DEMO-EXP-{i+1:03d}"
            if not Expense.query.filter_by(tenant_id=tid, expense_number=en).first():
                db.session.add(Expense(
                    tenant_id=tid, expense_number=en,
                    category_id=exp_cats[cn].id,
                    description=f"{cn} - شهر يوليو",
                    amount=amt, currency="ILS", amount_aed=amt,
                    expense_date=db.func.current_date(),
                    payment_method="cash", user_id=seller.id,
                ))

        db.session.commit()
        print("Demo tenant fully populated with branches, users, store, customers, partners, suppliers, products, employees, payroll, sales, purchases, and expenses.")


def downgrade():
    """Remove all demo-populated data except the base tenant skeleton."""
    app = create_app()
    with app.app_context():
        demo = Tenant.query.filter_by(slug='demo').first()
        if not demo:
            return
        tid = demo.id

        # Delete in dependency order
        Expense.query.filter_by(tenant_id=tid).delete()
        ExpenseCategory.query.filter_by(tenant_id=tid).delete()
        Purchase.query.filter_by(tenant_id=tid).delete()
        Sale.query.filter_by(tenant_id=tid).delete()
        PayrollTransaction.query.filter_by(tenant_id=tid).delete()
        Employee.query.filter_by(tenant_id=tid).delete()
        Product.query.filter_by(tenant_id=tid).delete()
        ProductCategory.query.filter_by(tenant_id=tid).delete()
        Customer.query.filter_by(tenant_id=tid).delete()
        Supplier.query.filter_by(tenant_id=tid).delete()
        Partner.query.filter_by(tenant_id=tid).delete()
        TenantStore.query.filter_by(tenant_id=tid).delete()
        # Delete non-admin demo users
        User.query.filter(
            User.tenant_id == tid,
            User.username != 'demo_admin',
        ).delete()
        # Delete non-main branches (cascades to warehouses, cashboxes via FK)
        Branch.query.filter(
            Branch.tenant_id == tid,
            Branch.is_main == False,
        ).delete()
        # Clean up demo-specific roles
        for slug in ["demo_accountant", "demo_cashier", "demo_warehouse"]:
            Role.query.filter_by(slug=slug).delete()

        db.session.commit()
        print("Demo population data removed.")
