"""
Seed demo data for Alhazem and Nasrallah tenants with full setup.
"""
import os
import sys

os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import (
    Tenant, User, Role, Permission,
    Branch, Warehouse,
    Product, ProductCategory,
    Customer,
    InvoiceSettings,
    GLAccount, GLPeriod,
)
from werkzeug.security import generate_password_hash
from datetime import datetime, timezone, date
from decimal import Decimal

app = create_app()


def ensure_permissions():
    """Create essential permissions."""
    perm_codes = [
        ("manage_sales", "Manage Sales", "إدارة المبيعات", "sales"),
        ("manage_purchases", "Manage Purchases", "إدارة المشتريات", "purchases"),
        ("manage_products", "Manage Products", "إدارة المنتجات", "products"),
        ("manage_customers", "Manage Customers", "إدارة العملاء", "customers"),
        ("manage_suppliers", "Manage Suppliers", "إدارة الموردين", "suppliers"),
        ("manage_inventory", "Manage Inventory", "إدارة المخزون", "inventory"),
        ("manage_gl", "Manage GL", "إدارة الحسابات", "accounting"),
        ("manage_payments", "Manage Payments", "إدارة المدفوعات", "payments"),
        ("manage_reports", "Manage Reports", "إدارة التقارير", "reports"),
        ("manage_users", "Manage Users", "إدارة المستخدمين", "users"),
        ("manage_settings", "Manage Settings", "إدارة الإعدادات", "settings"),
        ("pos_access", "POS Access", "الوصول لنقطة البيع", "pos"),
        ("view_costs", "View Costs", "عرض التكاليف", "products"),
    ]
    perms = {}
    for code, name, name_ar, category in perm_codes:
        p = Permission.query.filter_by(code=code).first()
        if not p:
            p = Permission(code=code, name=name, name_ar=name_ar, category=category)
            db.session.add(p)
        perms[code] = p
    db.session.commit()
    return perms


def ensure_roles(perms):
    """Create roles with permissions."""
    roles = {}

    # Owner
    r_owner = Role.query.filter_by(slug="owner").first()
    if not r_owner:
        r_owner = Role(name="Owner", name_ar="مالك", slug="owner")
        db.session.add(r_owner)
    roles["owner"] = r_owner

    # Manager
    r_manager = Role.query.filter_by(slug="manager").first()
    if not r_manager:
        r_manager = Role(name="Manager", name_ar="مدير", slug="manager")
        db.session.add(r_manager)
    r_manager.permissions = [perms["manage_sales"], perms["manage_purchases"],
                             perms["manage_products"], perms["manage_customers"],
                             perms["manage_inventory"], perms["manage_reports"],
                             perms["manage_payments"], perms["pos_access"],
                             perms["view_costs"]]
    roles["manager"] = r_manager

    # Seller
    r_seller = Role.query.filter_by(slug="seller").first()
    if not r_seller:
        r_seller = Role(name="Seller", name_ar="بائع", slug="seller")
        db.session.add(r_seller)
    r_seller.permissions = [perms["manage_sales"], perms["manage_customers"],
                            perms["pos_access"]]
    roles["seller"] = r_seller

    # Accountant
    r_acct = Role.query.filter_by(slug="accountant").first()
    if not r_acct:
        r_acct = Role(name="Accountant", name_ar="محاسب", slug="accountant")
        db.session.add(r_acct)
    r_acct.permissions = [perms["manage_gl"], perms["manage_payments"],
                          perms["manage_reports"], perms["view_costs"]]
    roles["accountant"] = r_acct

    db.session.commit()
    return roles


def create_tenant(data):
    existing = Tenant.query.filter_by(slug=data["slug"]).first()
    if existing:
        print(f"  Tenant '{data['name']}' already exists (id={existing.id})")
        return existing
    t = Tenant(**data)
    db.session.add(t)
    db.session.flush()
    return t


def create_branch(tenant_id, name, code, city="HQ"):
    existing = Branch.query.filter_by(tenant_id=tenant_id, code=code).first()
    if existing:
        print(f"  Branch '{name}' already exists (id={existing.id})")
        return existing
    b = Branch(tenant_id=tenant_id, name=name, code=code, city=city, is_main=True)
    db.session.add(b)
    db.session.flush()
    return b


def create_warehouse(tenant_id, branch_id, name, code, wtype="physical"):
    existing = Warehouse.query.filter_by(tenant_id=tenant_id, code=code).first()
    if existing:
        print(f"  Warehouse '{name}' already exists (id={existing.id})")
        return existing
    w = Warehouse(tenant_id=tenant_id, branch_id=branch_id, name=name,
                  code=code, warehouse_type=wtype, is_main=True)
    db.session.add(w)
    db.session.flush()
    return w


def create_user(tenant_id, branch_id, role_id, username, email, full_name,
                full_name_ar, is_owner=False):
    existing = User.query.filter_by(username=username).first()
    if existing:
        print(f"  User '{username}' already exists (id={existing.id})")
        return existing
    u = User(
        tenant_id=tenant_id,
        branch_id=branch_id,
        role_id=role_id,
        username=username,
        email=email,
        full_name=full_name,
        full_name_ar=full_name_ar,
        is_owner=is_owner,
        is_active=True,
    )
    u.password_hash = generate_password_hash("password123", method="pbkdf2:sha256")
    db.session.add(u)
    db.session.flush()
    return u


def create_customer(tenant_id, name, name_ar, ctype, classification="regular", phone="", email=""):
    c = Customer(
        tenant_id=tenant_id,
        name=name,
        name_ar=name_ar,
        customer_type=ctype,
        customer_classification=classification,
        phone=phone,
        email=email,
    )
    db.session.add(c)
    db.session.flush()
    return c


def create_category(tenant_id, name, name_ar):
    c = ProductCategory(tenant_id=tenant_id, name=name, name_ar=name_ar)
    db.session.add(c)
    db.session.flush()
    return c


def create_product(tenant_id, category_id, name, name_ar, sku, barcode, cost, price, stock=100):
    p = Product(
        tenant_id=tenant_id,
        category_id=category_id,
        name=name,
        name_ar=name_ar,
        sku=sku,
        barcode=barcode,
        cost_price=Decimal(str(cost)),
        regular_price=Decimal(str(price)),
        current_stock=Decimal(str(stock)),
        min_stock_alert=Decimal("10"),
        unit="piece",
        is_active=True,
    )
    db.session.add(p)
    db.session.flush()
    return p


def create_gl_accounts(tenant_id):
    existing = GLAccount.query.filter_by(tenant_id=tenant_id).first()
    if existing:
        print(f"  GL Accounts already exist for tenant {tenant_id}")
        return
    accounts = [
        ("1", "Assets", "الأصول", "asset"),
        ("11", "Current Assets", "الأصول المتداولة", "asset"),
        ("1101", "Cash", "الصندوق", "asset"),
        ("1102", "Bank", "البنك", "asset"),
        ("1103", "Inventory", "المخزون", "asset"),
        ("1104", "Accounts Receivable", "ذمم مدينة", "asset"),
        ("12", "Fixed Assets", "الأصول الثابتة", "asset"),
        ("2", "Liabilities", "الالتزامات", "liability"),
        ("21", "Current Liabilities", "الالتزامات المتداولة", "liability"),
        ("2101", "Accounts Payable", "ذمم دائنة", "liability"),
        ("3", "Equity", "حقوق الملكية", "equity"),
        ("3101", "Capital", "رأس المال", "equity"),
        ("3102", "Retained Earnings", "الأرباح المحتجزة", "equity"),
        ("4", "Revenue", "الإيرادات", "revenue"),
        ("4101", "Sales Revenue", "إيرادات المبيعات", "revenue"),
        ("5", "Expenses", "المصروفات", "expense"),
        ("5101", "Cost of Goods Sold", "تكلفة البضاعة المباعة", "expense"),
        ("5102", "Salaries", "الرواتب", "expense"),
        ("5103", "Rent", "الإيجار", "expense"),
        ("5104", "Utilities", "المرافق", "expense"),
    ]
    for code, name, name_ar, atype in accounts:
        a = GLAccount(
            tenant_id=tenant_id,
            code=code,
            name=name,
            name_ar=name_ar,
            type=atype,
            is_active=True,
        )
        db.session.add(a)
    db.session.flush()


def create_invoice_settings(tenant_id):
    existing = InvoiceSettings.query.filter_by(tenant_id=tenant_id, is_active=True).first()
    if existing:
        print(f"  InvoiceSettings already exist for tenant {tenant_id}")
        return existing
    s = InvoiceSettings(
        tenant_id=tenant_id,
        is_active=True,
    )
    db.session.add(s)
    db.session.flush()
    return s


def create_gl_period(tenant_id):
    existing = GLPeriod.query.filter_by(tenant_id=tenant_id, year=2026, month=1).first()
    if existing:
        print(f"  GL Period already exists for tenant {tenant_id}")
        return
    p = GLPeriod(
        tenant_id=tenant_id,
        year=2026,
        month=1,
        is_closed=False,
    )
    db.session.add(p)
    db.session.flush()


def seed_tenant(name, slug, name_ar, country, currency, vat_country, vat_num=None):
    print(f"\n=== Seeding {name} ===")

    # 1. Tenant
    t = create_tenant({
        "name": name,
        "slug": slug,
        "name_ar": name_ar,
        "country": country,
        "default_currency": currency,
        "vat_country": vat_country,
        "vat_number": vat_num,
        "is_active": True,
    })
    print(f"  Tenant: {t.name} (id={t.id})")

    # 2. Branch
    b = create_branch(t.id, f"{name} Main", "MAIN", "HQ")
    print(f"  Branch: {b.name} (id={b.id})")

    # 3. Warehouse
    w = create_warehouse(t.id, b.id, f"{name} Warehouse", "WH01")
    print(f"  Warehouse: {w.name} (id={w.id})")

    return t, b, w


def main():
    with app.app_context():
        print("Creating demo data for Alhazem + Nasrallah...")

        # Ensure permissions and roles
        perms = ensure_permissions()
        roles = ensure_roles(perms)

        # ========== Alhazem Batteries ==========
        t1, b1, w1 = seed_tenant(
            name="Alhazem Batteries",
            slug="alhazem",
            name_ar="الحازم للبطاريات",
            country="UAE",
            currency="AED",
            vat_country="AE",
            vat_num="123456789",
        )

        # Users
        u1_owner = create_user(t1.id, b1.id, roles["owner"].id, "alhazem_owner",
                               "owner@alhazem.ae", "Ahmad Alhazem", "أحمد الحازم", is_owner=True)
        u1_mgr = create_user(t1.id, b1.id, roles["manager"].id, "alhazem_manager",
                             "manager@alhazem.ae", "Khaled Manager", "خالد المدير")
        u1_seller = create_user(t1.id, b1.id, roles["seller"].id, "alhazem_seller",
                                "seller@alhazem.ae", "Omar Seller", "عمر البائع")
        u1_acct = create_user(t1.id, b1.id, roles["accountant"].id, "alhazem_accountant",
                              "accountant@alhazem.ae", "Hassan Accountant", "حسن المحاسب")
        print(f"  Users: owner, manager, seller, accountant created")

        # Customers
        create_customer(t1.id, "Regular Customer", "عميل عادي", "regular", phone="0501111111")
        create_customer(t1.id, "Merchant Customer", "تاجر", "merchant", phone="0502222222")
        create_customer(t1.id, "Partner Customer", "شريك", "partner", phone="0503333333")
        print(f"  Customers: regular, merchant, partner created")

        # Categories
        cat1_batt = create_category(t1.id, "Car Batteries", "بطاريات السيارات")
        cat1_tires = create_category(t1.id, "Tires", "الإطارات")
        cat1_oil = create_category(t1.id, "Motor Oil", "زيوت المحركات")
        print(f"  Categories: batteries, tires, oil created")

        # Products
        create_product(t1.id, cat1_batt.id, "Varta 60Ah Battery", "بطارية فارتا 60 أمبير",
                       "BAT-VAR-60", "1234567890123", 150, 250, 50)
        create_product(t1.id, cat1_batt.id, "Amaron 70Ah Battery", "بطارية أمارون 70 أمبير",
                       "BAT-AMR-70", "1234567890124", 180, 300, 40)
        create_product(t1.id, cat1_tires.id, "Michelin 205/55R16", "ميشلان 205/55R16",
                       "TIR-MIC-205", "1234567890125", 200, 350, 30)
        create_product(t1.id, cat1_oil.id, "Castrol 5W-30 4L", "كاسترول 5W-30 4 لتر",
                       "OIL-CAS-5W30", "1234567890126", 80, 140, 100)
        print(f"  Products: 4 created")

        # Invoice Settings
        create_invoice_settings(t1.id)
        print(f"  InvoiceSettings created")

        # GL Accounts
        create_gl_accounts(t1.id)
        print(f"  GL Accounts created")

        # GL Period
        create_gl_period(t1.id)
        print(f"  GL Period created")

        # ========== Nasrallah ==========
        t2, b2, w2 = seed_tenant(
            name="Nasrallah Trading",
            slug="nasrallah",
            name_ar="نصر الله للتجارة",
            country="Palestine",
            currency="ILS",
            vat_country="PS",
        )

        # Users
        u2_owner = create_user(t2.id, b2.id, roles["owner"].id, "nasrallah_owner",
                               "owner@nasrallah.ps", "Mohammad Nasrallah", "محمد نصر الله", is_owner=True)
        u2_mgr = create_user(t2.id, b2.id, roles["manager"].id, "nasrallah_manager",
                             "manager@nasrallah.ps", "Ali Manager", "علي المدير")
        u2_seller = create_user(t2.id, b2.id, roles["seller"].id, "nasrallah_seller",
                                 "seller@nasrallah.ps", "Yousef Seller", "يوسف البائع")
        u2_acct = create_user(t2.id, b2.id, roles["accountant"].id, "nasrallah_accountant",
                              "accountant@nasrallah.ps", "Ibrahim Accountant", "إبراهيم المحاسب")
        print(f"  Users: owner, manager, seller, accountant created")

        # Customers
        create_customer(t2.id, "Local Customer", "عميل محلي", "regular", phone="0591111111")
        create_customer(t2.id, "Wholesale Customer", "عميل جملة", "merchant", phone="0592222222")
        create_customer(t2.id, "Partner Shop", "متجر شريك", "partner", phone="0593333333")
        print(f"  Customers: regular, merchant, partner created")

        # Categories
        cat2_elec = create_category(t2.id, "Electronics", "إلكترونيات")
        cat2_tools = create_category(t2.id, "Tools", "أدوات")
        cat2_paint = create_category(t2.id, "Paint", "دهانات")
        print(f"  Categories: electronics, tools, paint created")

        # Products
        create_product(t2.id, cat2_elec.id, "LED Bulb 12W", "لمبة ليد 12 واط",
                       "LED-12W", "9876543210001", 15, 35, 200)
        create_product(t2.id, cat2_elec.id, "Extension Cable 5m", "سلك تمديد 5 متر",
                       "EXT-5M", "9876543210002", 20, 45, 80)
        create_product(t2.id, cat2_tools.id, "Hammer Set", "طقم مطارق",
                       "HAM-SET", "9876543210003", 30, 70, 25)
        create_product(t2.id, cat2_paint.id, "Wall Paint White 4L", "دهان حوائط أبيض 4 لتر",
                       "PNT-WHT-4L", "9876543210004", 40, 90, 60)
        print(f"  Products: 4 created")

        # Invoice Settings
        create_invoice_settings(t2.id)
        print(f"  InvoiceSettings created")

        # GL Accounts
        create_gl_accounts(t2.id)
        print(f"  GL Accounts created")

        # GL Period
        create_gl_period(t2.id)
        print(f"  GL Period created")

        db.session.commit()

        print("\n" + "=" * 50)
        print("DEMO DATA CREATED SUCCESSFULLY")
        print("=" * 50)
        print(f"\nAlhazem (id={t1.id}):")
        print(f"  Users: alhazem_owner, alhazem_manager, alhazem_seller, alhazem_accountant")
        print(f"  Password for all: password123")
        print(f"\nNasrallah (id={t2.id}):")
        print(f"  Users: nasrallah_owner, nasrallah_manager, nasrallah_seller, nasrallah_accountant")
        print(f"  Password for all: password123")


if __name__ == "__main__":
    main()
