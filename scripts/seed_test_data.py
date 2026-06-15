"""
Seed script: populates PostgreSQL with real multi-tenant test data.
Run: python scripts/seed_test_data.py

Creates:
  - 2 tenants (AED + ILS base currencies)
  - GL accounts, branches, warehouses, roles, users
  - Customers, suppliers, product categories, products with stock
  - Currencies, exchange rates, system settings, document sequences
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from decimal import Decimal
from datetime import datetime, timezone, date
from app import create_app
from extensions import db
from models import (
    Tenant, Branch, Warehouse, User, Role, Permission,
    Product, ProductCategory, ProductWarehouseStock,
    Customer, Supplier, Currency, ExchangeRate,
    GLAccount, GLAccountMapping, GLJournalEntry, GLJournalLine,
    SystemSettings, DocumentSequence, Payment, Receipt,
    StockMovement, ProductWarehouseCost, ProductCostHistory
)

SEED_USER_PASSWORD = "test123"

TENANTS_CONFIG = [
    {
        "name": "شركة الأفق للتجارة",
        "name_ar": "شركة الأفق للتجارة",
        "name_en": "Al Ufuq Trading Co",
        "slug": "al-ufuq-trading",
        "country": "AE",
        "default_currency": "AED",
        "vat_country": "AE",
        "timezone": "Asia/Dubai",
        "phone_1": "+971501234567",
        "email": "info@ufuq.ae",
        "brand_color_primary": "#007A3D",
        "brand_color_secondary": "#D4AF37",
        "max_users": 10,
        "max_products": 5000,
        "max_customers": 2000,
    },
    {
        "name": "شركة القدس للمقاولات",
        "name_ar": "شركة القدس للمقاولات",
        "name_en": "Al Quds Contracting Co",
        "slug": "al-quds-contracting",
        "country": "PS",
        "default_currency": "ILS",
        "vat_country": "PS",
        "timezone": "Asia/Hebron",
        "phone_1": "+970599123456",
        "email": "info@quds.ps",
        "brand_color_primary": "#1a5276",
        "brand_color_secondary": "#f39c12",
        "max_users": 8,
        "max_products": 3000,
        "max_customers": 1000,
    },
]

CHART_OF_ACCOUNTS = [
    {"code": "1000", "name": "الأصول", "name_ar": "الأصول", "type": "asset", "is_header": True, "level": 1},
    {"code": "1100", "name": "النقد والبنوك", "name_ar": "النقد والبنوك", "type": "asset", "is_header": True, "level": 2},
    {"code": "1110", "name": "صندوق النقدية", "name_ar": "صندوق النقدية", "type": "asset", "level": 3, "is_reconcile": True},
    {"code": "1120", "name": "البنك - جاري", "name_ar": "البنك - جاري", "type": "asset", "level": 3, "is_reconcile": True},
    {"code": "1130", "name": "شيكات تحت التحصيل", "name_ar": "شيكات تحت التحصيل", "type": "asset", "level": 3},
    {"code": "1200", "name": "الحسابات المدينة", "name_ar": "الحسابات المدينة", "type": "asset", "level": 2},
    {"code": "1210", "name": "عملاء", "name_ar": "عملاء", "type": "asset", "level": 3, "is_reconcile": True},
    {"code": "1220", "name": "أوراق قبض", "name_ar": "أوراق قبض", "type": "asset", "level": 3},
    {"code": "1300", "name": "المخزون", "name_ar": "المخزون", "type": "asset", "level": 2},
    {"code": "1310", "name": "بضاعة", "name_ar": "بضاعة", "type": "asset", "level": 3},
    {"code": "2000", "name": "الخصوم", "name_ar": "الخصوم", "type": "liability", "is_header": True, "level": 1},
    {"code": "2100", "name": "الحسابات الدائنة", "name_ar": "الحسابات الدائنة", "type": "liability", "level": 2},
    {"code": "2110", "name": "موردون", "name_ar": "موردون", "type": "liability", "level": 3, "is_reconcile": True},
    {"code": "2120", "name": "أوراق دفع", "name_ar": "أوراق دفع", "type": "liability", "level": 3},
    {"code": "2200", "name": "الضرائب", "name_ar": "الضرائب", "type": "liability", "level": 2},
    {"code": "2210", "name": "ضريبة القيمة المضافة", "name_ar": "ضريبة القيمة المضافة", "type": "liability", "level": 3},
    {"code": "3000", "name": "حقوق الملكية", "name_ar": "حقوق الملكية", "type": "equity", "is_header": True, "level": 1},
    {"code": "3100", "name": "رأس المال", "name_ar": "رأس المال", "type": "equity", "level": 2},
    {"code": "3110", "name": "رأس مال المالك", "name_ar": "رأس مال المالك", "type": "equity", "level": 3},
    {"code": "4000", "name": "الإيرادات", "name_ar": "الإيرادات", "type": "revenue", "is_header": True, "level": 1},
    {"code": "4100", "name": "إيرادات المبيعات", "name_ar": "إيرادات المبيعات", "type": "revenue", "level": 2},
    {"code": "4110", "name": "مبيعات", "name_ar": "مبيعات", "type": "revenue", "level": 3},
    {"code": "4120", "name": "مردودات المبيعات", "name_ar": "مردودات المبيعات", "type": "revenue", "level": 3},
    {"code": "5000", "name": "التكاليف", "name_ar": "التكاليف", "type": "expense", "is_header": True, "level": 1},
    {"code": "5100", "name": "تكلفة المبيعات", "name_ar": "تكلفة المبيعات", "type": "expense", "level": 2},
    {"code": "5110", "name": "تكلفة البضاعة المباعة", "name_ar": "تكلفة البضاعة المباعة", "type": "expense", "level": 3},
    {"code": "5200", "name": "مصروفات عمومية", "name_ar": "مصروفات عمومية", "type": "expense", "level": 2},
    {"code": "5210", "name": "الرواتب والأجور", "name_ar": "الرواتب والأجور", "type": "expense", "level": 3},
    {"code": "5220", "name": "الإيجار", "name_ar": "الإيجار", "type": "expense", "level": 3},
]

GL_MAPPINGS = {
    "CASH": "1110",
    "BANK": "1120",
    "CHEQUES_UNDER_COLLECTION": "1130",
    "AR": "1210",
    "INVENTORY_ASSET": "1310",
    "AP": "2110",
    "VAT_OUTPUT": "2210",
    "VAT_INPUT": "2210",
    "SALES_REVENUE": "4110",
    "SALES_RETURNS": "4120",
    "COGS": "5110",
}

CURRENCIES = [
    {"code": "AED", "name": "درهم إماراتي", "name_ar": "درهم إماراتي", "symbol": "د.إ", "is_base": True},
    {"code": "ILS", "name": "شيكل إسرائيلي", "name_ar": "شيكل إسرائيلي", "symbol": "₪", "is_base": False},
    {"code": "USD", "name": "دولار أمريكي", "name_ar": "دولار أمريكي", "symbol": "$", "is_base": False},
]

EXCHANGE_RATES = [
    ("AED", "USD", Decimal("0.2723")),
    ("USD", "AED", Decimal("3.6730")),
    ("ILS", "USD", Decimal("0.2700")),
    ("USD", "ILS", Decimal("3.7000")),
    ("AED", "ILS", Decimal("0.9900")),
    ("ILS", "AED", Decimal("1.0100")),
]

ROLES_CONFIG = [
    {"name": "مدير النظام", "name_ar": "مدير النظام", "slug": "admin", "level": 100},
    {"name": "مدير مالي", "name_ar": "مدير مالي", "slug": "accountant", "level": 70},
    {"name": "مدير مبيعات", "name_ar": "مدير مبيعات", "slug": "sales_manager", "level": 60},
    {"name": "بائع", "name_ar": "بائع", "slug": "seller", "level": 40},
    {"name": "مشرف مشتريات", "name_ar": "مشرف مشتريات", "slug": "purchase_manager", "level": 60},
    {"name": "أمين مستودع", "name_ar": "أمين مستودع", "slug": "warehouse_keeper", "level": 30},
]

PRODUCTS_CONFIG = [
    {"name": "لابتوب Dell Latitude", "name_ar": "لابتوب Dell Latitude", "sku": "LAP-DELL-001", "regular_price": Decimal("3500.00"), "cost_price": Decimal("2800.00"), "unit": "piece", "category": "إلكترونيات"},
    {"name": "طابعة HP LaserJet", "name_ar": "طابعة HP LaserJet", "sku": "PRN-HP-001", "regular_price": Decimal("850.00"), "cost_price": Decimal("620.00"), "unit": "piece", "category": "إلكترونيات"},
    {"name": "مكتب خشبي", "name_ar": "مكتب خشبي", "sku": "FUR-DESK-001", "regular_price": Decimal("1200.00"), "cost_price": Decimal("850.00"), "unit": "piece", "category": "أثاث"},
    {"name": "كرسي مكتب", "name_ar": "كرسي مكتب", "sku": "FUR-CHR-001", "regular_price": Decimal("650.00"), "cost_price": Decimal("420.00"), "unit": "piece", "category": "أثاث"},
    {"name": "كابل USB-C 2m", "name_ar": "كابل USB-C 2m", "sku": "CBL-USBC-001", "regular_price": Decimal("45.00"), "cost_price": Decimal("22.00"), "unit": "piece", "category": "إلكترونيات"},
    {"name": "ماوس لاسلكي", "name_ar": "ماوس لاسلكي", "sku": "MOU-WRLS-001", "regular_price": Decimal("95.00"), "cost_price": Decimal("55.00"), "unit": "piece", "category": "إلكترونيات"},
    {"name": "ورق A4 (كرتون)", "name_ar": "ورق A4 (كرتون)", "sku": "PAP-A4-001", "regular_price": Decimal("120.00"), "cost_price": Decimal("80.00"), "unit": "box", "category": "قرطاسية"},
    {"name": "سماعات بلوتوث", "name_ar": "سماعات بلوتوث", "sku": "EAR-BT-001", "regular_price": Decimal("250.00"), "cost_price": Decimal("160.00"), "unit": "piece", "category": "إلكترونيات"},
]

CATEGORIES = ["إلكترونيات", "أثاث", "قرطاسية"]

SEED_PREFIX = "[SEED]"


def log(msg):
    print(f"{SEED_PREFIX} {msg}")


def seed_currencies():
    if Currency.query.first():
        log("Currencies already seeded, skipping")
        return
    for c in CURRENCIES:
        db.session.add(Currency(**c))
    db.session.commit()
    log(f"Seeded {len(CURRENCIES)} currencies")


def seed_exchange_rates():
    if ExchangeRate.query.first():
        log("Exchange rates already seeded, skipping")
        return
    now = datetime.now(timezone.utc)
    for from_cur, to_cur, rate in EXCHANGE_RATES:
        db.session.add(ExchangeRate(
            from_currency=from_cur, to_currency=to_cur,
            rate=rate, source="seed", valid_from=now
        ))
    db.session.commit()
    log(f"Seeded {len(EXCHANGE_RATES)} exchange rates")


def seed_system_settings():
    if SystemSettings.query.first():
        log("System settings already seeded, skipping")
        return
    ss = SystemSettings(
        system_name="Azadexa ERP",
        system_version="2.0.0",
        system_mode="production",
        default_language="ar",
        rtl_enabled=True,
        default_currency="AED",
        enable_tax=True,
        enable_sales=True,
        enable_purchases=True,
        enable_inventory=True,
        enable_customers=True,
        enable_suppliers=True,
        enable_expenses=True,
        enable_gl=True,
        enable_pos=True,
        enable_reports=True,
        enable_multi_warehouse=True,
        enable_multi_currency=True,
        enable_discounts=True,
        enable_returns=True,
        is_active=True,
    )
    db.session.add(ss)
    db.session.commit()
    log("System settings seeded")


def seed_roles_and_permissions(tenant):
    """Create roles for a tenant. Returns dict of slug->role."""
    roles = {}
    role_slugs = set()
    for rc in ROLES_CONFIG:
        if Role.query.filter_by(slug=rc["slug"]).first():
            existing = Role.query.filter_by(slug=rc["slug"]).first()
            roles[rc["slug"]] = existing
            role_slugs.add(rc["slug"])
            continue
        role = Role(name=rc["name"], name_ar=rc.get("name_ar", rc["name"]),
                    slug=rc["slug"], is_active=True)
        db.session.add(role)
        roles[rc["slug"]] = role
        role_slugs.add(rc["slug"])
    db.session.commit()
    return roles


def seed_tenant(tenant_config):
    """Seed one complete tenant with all its data. Returns tenant info dict."""
    name = tenant_config["name"]
    name_ar = tenant_config["name_ar"]
    slug = tenant_config["slug"]
    existing = Tenant.query.filter_by(slug=slug).first()
    if existing:
        log(f"Tenant '{name}' exists (id={existing.id}), returning existing")
        return _collect_tenant_info(existing)

    tenant = Tenant(
        name=name,
        name_ar=tenant_config["name_ar"],
        name_en=tenant_config.get("name_en"),
        slug=slug,
        country=tenant_config["country"],
        default_currency=tenant_config["default_currency"],
        vat_country=tenant_config["vat_country"],
        timezone=tenant_config.get("timezone", "Asia/Dubai"),
        phone_1=tenant_config.get("phone_1"),
        email=tenant_config.get("email"),
        brand_color_primary=tenant_config.get("brand_color_primary", "#007A3D"),
        brand_color_secondary=tenant_config.get("brand_color_secondary", "#D4AF37"),
        is_active=True,
        is_trial=False,
        subscription_plan="enterprise",
        max_users=tenant_config.get("max_users", 10),
        max_products=tenant_config.get("max_products", 5000),
        max_branches=5,
        max_warehouses=5,
        enable_gl=True,
        enable_pos=True,
        enable_cheques=True,
        enable_expenses=True,
        enable_multi_currency=True,
        enable_multi_warehouse=True,
        enable_reports=True,
        business_type="general",
        default_tax_rate=Decimal("5.00"),
    )
    db.session.add(tenant)
    db.session.commit()
    log(f"Created tenant '{name}' (id={tenant.id})")

    roles = seed_roles_and_permissions(tenant)

    branch = Branch(
        tenant_id=tenant.id, name="الفرع الرئيسي",
        code="HQ-01", city=tenant_config.get("country", "AE") == "AE" and "دبي" or "القدس",
        is_active=True, is_main=True,
    )
    db.session.add(branch)
    db.session.commit()
    log(f"  Created branch '{branch.name}' (id={branch.id})")

    warehouse = Warehouse(
        tenant_id=tenant.id, name="المستودع الرئيسي", name_ar="المستودع الرئيسي",
        code="WH-01", warehouse_type="physical",
        branch_id=branch.id, is_active=True, is_main=True,
    )
    db.session.add(warehouse)
    db.session.commit()
    log(f"  Created warehouse '{warehouse.name}' (id={warehouse.id})")

    admin_role = roles.get("admin")
    admin_user = User(
        username=f"admin_{slug[:8]}",
        email=f"admin@{slug}.com",
        full_name=f"مدير {name}",
        full_name_ar=f"مدير {name_ar}",
        tenant_id=tenant.id, role_id=admin_role.id,
        branch_id=branch.id, is_active=True, is_owner=False,
    )
    admin_user.set_password(SEED_USER_PASSWORD)
    db.session.add(admin_user)

    acct_role = roles.get("accountant")
    acct_user = User(
        username=f"acct_{slug[:8]}",
        email=f"accountant@{slug}.com",
        full_name=f"محاسب {name}",
        full_name_ar=f"محاسب {name_ar}",
        tenant_id=tenant.id, role_id=acct_role.id,
        branch_id=branch.id, is_active=True, is_owner=False,
    )
    acct_user.set_password(SEED_USER_PASSWORD)
    db.session.add(acct_user)

    seller_role = roles.get("seller")
    seller_user = User(
        username=f"seller_{slug[:8]}",
        email=f"seller@{slug}.com",
        full_name=f"بائع {name}",
        full_name_ar=f"بائع {name_ar}",
        tenant_id=tenant.id, role_id=seller_role.id,
        branch_id=branch.id, is_active=True, is_owner=False,
    )
    seller_user.set_password(SEED_USER_PASSWORD)
    db.session.add(seller_user)

    purch_role = roles.get("purchase_manager")
    purch_user = User(
        username=f"purch_{slug[:8]}",
        email=f"purchase@{slug}.com",
        full_name=f"مشتريات {name}",
        full_name_ar=f"مشتريات {name_ar}",
        tenant_id=tenant.id, role_id=purch_role.id,
        branch_id=branch.id, is_active=True, is_owner=False,
    )
    purch_user.set_password(SEED_USER_PASSWORD)
    db.session.add(purch_user)
    db.session.commit()
    log(f"  Created 5 users (admin, accountant, seller, purchase manager)")

    gl_accounts = {}
    for acct_def in CHART_OF_ACCOUNTS:
        code = acct_def["code"]
        existing_acct = GLAccount.query.filter_by(tenant_id=tenant.id, code=code).first()
        if existing_acct:
            gl_accounts[code] = existing_acct
            continue
        acct = GLAccount(
            tenant_id=tenant.id,
            code=code,
            name=acct_def["name"],
            name_ar=acct_def.get("name_ar", acct_def["name"]),
            type=acct_def["type"],
            is_header=acct_def.get("is_header", False),
            level=acct_def.get("level", 3),
            is_reconcile=acct_def.get("is_reconcile", False),
            is_active=True,
            currency=tenant.default_currency,
        )
        db.session.add(acct)
        gl_accounts[code] = acct
    db.session.commit()
    log(f"  Created {len(CHART_OF_ACCOUNTS)} GL accounts")

    for concept, code in GL_MAPPINGS.items():
        acct = gl_accounts.get(code)
        if not acct:
            continue
        existing_mapping = GLAccountMapping.query.filter_by(
            tenant_id=tenant.id, concept_code=concept, branch_id=None
        ).first()
        if existing_mapping:
            continue
        mapping = GLAccountMapping(
            tenant_id=tenant.id, concept_code=concept,
            gl_account_id=acct.id, is_active=True,
        )
        db.session.add(mapping)
    db.session.commit()
    log(f"  Created {len(GL_MAPPINGS)} GL account mappings")

    for seq_code in ["SALE", "PURCHASE", "PAYMENT", "RECEIPT", "JE", "CHEQUE"]:
        existing_seq = DocumentSequence.query.filter_by(
            tenant_id=tenant.id, code=seq_code
        ).first()
        if existing_seq:
            continue
        seq = DocumentSequence(
            tenant_id=tenant.id, code=seq_code,
            name=f"مسلسل {seq_code}",
            name_ar=f"مسلسل {seq_code}",
            pattern=f"{{prefix}}-{{year}}-{{counter:05d}}",
            prefix=seq_code,
            counter=1, counter_reset="year", is_active=True,
        )
        db.session.add(seq)
    db.session.commit()
    log(f"  Created 6 document sequences")

    category_map = {}
    for cat_name in CATEGORIES:
        existing_cat = ProductCategory.query.filter_by(
            tenant_id=tenant.id, name=cat_name
        ).first()
        if existing_cat:
            category_map[cat_name] = existing_cat
            continue
        cat = ProductCategory(
            tenant_id=tenant.id, name=cat_name, name_ar=cat_name, is_active=True
        )
        db.session.add(cat)
        category_map[cat_name] = cat
    db.session.commit()
    log(f"  Created {len(CATEGORIES)} product categories")

    products = []
    for pd in PRODUCTS_CONFIG:
        existing_p = Product.query.filter_by(
            tenant_id=tenant.id, sku=pd["sku"]
        ).first()
        if existing_p:
            products.append(existing_p)
            continue
        cat = category_map.get(pd["category"])
        prod = Product(
            tenant_id=tenant.id,
            name=pd["name"],
            name_ar=pd["name_ar"],
            sku=pd["sku"],
            regular_price=pd["regular_price"],
            cost_price=pd.get("cost_price", Decimal("0")),
            current_stock=Decimal("100"),
            unit=pd.get("unit", "piece"),
            category_id=cat.id if cat else None,
            is_active=True,
        )
        db.session.add(prod)
        products.append(prod)
    db.session.commit()
    log(f"  Created {len(PRODUCTS_CONFIG)} products")

    for prod in products:
        pws = ProductWarehouseStock.query.filter_by(
            tenant_id=tenant.id, product_id=prod.id, warehouse_id=warehouse.id
        ).first()
        if not pws:
            pws = ProductWarehouseStock(
                tenant_id=tenant.id, product_id=prod.id,
                warehouse_id=warehouse.id, quantity=Decimal("100"),
            )
            db.session.add(pws)

        pwc = ProductWarehouseCost.query.filter_by(
            tenant_id=tenant.id, product_id=prod.id, warehouse_id=warehouse.id
        ).first()
        if not pwc:
            pwc = ProductWarehouseCost(
                tenant_id=tenant.id, product_id=prod.id,
                warehouse_id=warehouse.id,
                average_cost=prod.cost_price or Decimal("0"),
                total_quantity=Decimal("100"),
                total_value=(prod.cost_price or Decimal("0")) * Decimal("100"),
                currency=tenant.default_currency,
            )
            db.session.add(pwc)
    db.session.commit()
    log(f"  Created product stock/cost records")

    customers = []
    customer_names = [
        ("شركة التعمير", "شركة التعمير", "تعمير القابضة"),
        ("مؤسسة النور", "مؤسسة النور", "نور للتجارة"),
        ("محلات السلام", "محلات السلام", "السلام للمقاولات"),
    ]
    for cname, cname_ar, cname_en in customer_names:
        existing_c = Customer.query.filter_by(
            tenant_id=tenant.id, name=cname
        ).first()
        if existing_c:
            customers.append(existing_c)
            continue
        cust = Customer(
            tenant_id=tenant.id, name=cname, name_ar=cname_ar,
            customer_type="regular", customer_classification="regular",
            preferred_currency=tenant.default_currency,
            is_active=True, balance=Decimal("0"),
        )
        db.session.add(cust)
        customers.append(cust)
    db.session.commit()
    log(f"  Created {len(customer_names)} customers")

    suppliers_list = []
    supplier_data = [
        ("المورد العالمي", "المورد العالمي", "Global Supplier"),
        ("الشركة التقنية", "الشركة التقنية", "Tech Supplies Co"),
    ]
    for sname, sname_ar, s_en in supplier_data:
        existing_s = Supplier.query.filter_by(
            tenant_id=tenant.id, name=sname
        ).first()
        if existing_s:
            suppliers_list.append(existing_s)
            continue
        sup = Supplier(
            tenant_id=tenant.id, name=sname, name_ar=sname_ar,
            name_en=s_en, preferred_currency=tenant.default_currency,
            is_active=True,
        )
        db.session.add(sup)
        suppliers_list.append(sup)
    db.session.commit()
    log(f"  Created {len(supplier_data)} suppliers")

    return {
        "tenant": tenant,
        "branch": branch,
        "warehouse": warehouse,
        "users": {"admin": admin_user, "accountant": acct_user,
                  "seller": seller_user, "purchase": purch_user},
        "customers": customers,
        "suppliers": suppliers_list,
        "products": products,
        "gl_accounts": gl_accounts,
        "categories": category_map,
    }


def _collect_tenant_info(tenant):
    """Reconstruct tenant info dict for an existing tenant (no re-creation)."""
    branch = Branch.query.filter_by(tenant_id=tenant.id, is_main=True).first()
    warehouse = Warehouse.query.filter_by(tenant_id=tenant.id, is_main=True).first()
    users_q = User.query.filter_by(tenant_id=tenant.id).all()
    users = {}
    for u in users_q:
        if "admin" in u.username:
            users["admin"] = u
        elif "acct" in u.username:
            users["accountant"] = u
        elif "seller" in u.username:
            users["seller"] = u
        elif "purch" in u.username:
            users["purchase"] = u
    if not users.get("admin") and users_q:
        users["admin"] = users_q[0]
    customers = Customer.query.filter_by(tenant_id=tenant.id).limit(5).all()
    suppliers = Supplier.query.filter_by(tenant_id=tenant.id).limit(5).all()
    products = Product.query.filter_by(tenant_id=tenant.id).limit(10).all()
    gl_accts = {a.code: a for a in GLAccount.query.filter_by(tenant_id=tenant.id).all()}
    cats = {c.name: c for c in ProductCategory.query.filter_by(tenant_id=tenant.id).all()}
    return {
        "tenant": tenant, "branch": branch, "warehouse": warehouse,
        "users": users, "customers": customers, "suppliers": suppliers,
        "products": products, "gl_accounts": gl_accts, "categories": cats,
    }


def create_platform_owner():
    """Create the platform owner user if not exists."""
    existing = User.query.filter_by(username="platform_owner").first()
    if existing:
        log(f"Platform owner exists (id={existing.id})")
        return existing
    owner_role = Role.query.filter_by(slug="developer").first()
    if not owner_role:
        owner_role = Role(name="Developer", name_ar="مطور", slug="developer", is_active=True)
        db.session.add(owner_role)
        db.session.commit()
    owner = User(
        username="platform_owner",
        email="owner@azadexa.com",
        full_name="Platform Owner",
        full_name_ar="مالك المنصة",
        tenant_id=None, role_id=owner_role.id,
        branch_id=None, is_active=True, is_owner=True,
    )
    owner.set_password(SEED_USER_PASSWORD)
    db.session.add(owner)
    db.session.commit()
    log(f"Created platform owner (id={owner.id})")
    return owner


def main():
    app = create_app()
    with app.app_context():
        log("=" * 60)
        log("Starting seed data generation...")
        log("=" * 60)

        seed_currencies()
        seed_exchange_rates()
        seed_system_settings()

        tenants_info = {}
        for tc in TENANTS_CONFIG:
            info = seed_tenant(tc)
            tenants_info[tc["slug"]] = info

        owner = create_platform_owner()

        log("=" * 60)
        log("SEED COMPLETE - Summary:")
        log("=" * 60)
        for slug, info in tenants_info.items():
            t = info["tenant"]
            log(f"  Tenant: {t.name} (id={t.id}, currency={t.default_currency})")
            log(f"    Branch: {info['branch'].name if info['branch'] else 'N/A'}")
            log(f"    Warehouse: {info['warehouse'].name if info['warehouse'] else 'N/A'}")
            log(f"    Products: {len(info['products'])}")
            log(f"    Customers: {len(info['customers'])}")
            log(f"    Suppliers: {len(info['suppliers'])}")
            for role_name, u in info["users"].items():
                log(f"    User '{role_name}': {u.username} / {SEED_USER_PASSWORD}")
        log(f"  Platform Owner: {owner.username} / {SEED_USER_PASSWORD}")
        log("=" * 60)


if __name__ == "__main__":
    main()
