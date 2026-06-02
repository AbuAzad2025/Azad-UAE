"""Comprehensive seed data for Alhazem and Nasrallah tenants."""
import os, random
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import (
    Tenant, User, Branch, Warehouse, Product, ProductCategory,
    Customer, Sale, SaleLine, Purchase, PurchaseLine,
    Expense, ExpenseCategory, Employee, Supplier, Payment
)
from datetime import datetime, timezone, date
from decimal import Decimal

app = create_app()
ALHAZEM_ID = 8
NASRALLAH_ID = 2


def seed_products():
    tid = ALHAZEM_ID
    cats = {c.name: c for c in ProductCategory.query.filter_by(tenant_id=tid).all()}
    items = [
        (cats.get("Car Batteries"), "Exide 45Ah", "بطارية اكسايد 45", "BAT-EX-45", "111000000001", 120, 200, 60),
        (cats.get("Car Batteries"), "Bosch 55Ah", "بطارية بوش 55", "BAT-BO-55", "111000000002", 140, 230, 45),
        (cats.get("Car Batteries"), "Delkor 80Ah", "بطارية ديلكور 80", "BAT-DK-80", "111000000003", 220, 380, 35),
        (cats.get("Car Batteries"), "Optima YellowTop", "أوبتما", "BAT-OP-YT", "111000000004", 350, 600, 20),
        (cats.get("Tires"), "Goodyear 195/65R15", "جوديير", "TIR-GY-195", "111000000005", 180, 320, 40),
        (cats.get("Tires"), "Bridgestone 215/60R16", "بريدجستون", "TIR-BR-215", "111000000006", 250, 420, 30),
        (cats.get("Tires"), "Continental 225/50R17", "كونتيننتال", "TIR-CN-225", "111000000007", 300, 500, 25),
        (cats.get("Motor Oil"), "Mobil 1 0W-40", "موبيل 1", "OIL-MB-0W40", "111000000008", 120, 200, 80),
        (cats.get("Motor Oil"), "Shell Helix 10W-40", "شل هيليكس", "OIL-SH-10W40", "111000000009", 90, 150, 90),
        (cats.get("Motor Oil"), "Total Quartz 5W-30", "توتال", "OIL-TQ-5W30", "111000000010", 100, 170, 70),
    ]
    cat_parts = ProductCategory(tenant_id=tid, name="Spare Parts", name_ar="قطع غيار")
    db.session.add(cat_parts); db.session.flush()
    items += [
        (cat_parts, "Brake Pads Toyota", "فحمات فرامل", "PRT-BP-TOY", "111000000011", 80, 140, 50),
        (cat_parts, "Spark Plug NGK", "شمعة إشعال", "PRT-SP-NGK", "111000000012", 25, 45, 100),
        (cat_parts, "Air Filter Denso", "فلتر هواء", "PRT-AF-DEN", "111000000013", 30, 55, 60),
        (cat_parts, "Alternator Bosch", "دينامو", "PRT-AL-BOS", "111000000014", 300, 550, 15),
        (cat_parts, "Radiator Denso", "ردياتير", "PRT-RD-DEN", "111000000015", 200, 380, 20),
        (cat_parts, "Shock Absorber KYB", "مساعد صدمات", "PRT-SH-KYB", "111000000016", 180, 320, 25),
    ]
    count = 0
    for cat, name, name_ar, sku, bc, cost, price, stock in items:
        if not cat: continue
        if Product.query.filter_by(tenant_id=tid, sku=sku).first(): continue
        p = Product(tenant_id=tid, category_id=cat.id, name=name, name_ar=name_ar, sku=sku,
                    barcode=bc, cost_price=Decimal(str(cost)), regular_price=Decimal(str(price)),
                    current_stock=Decimal(str(stock)), min_stock_alert=Decimal("10"), unit="piece", is_active=True)
        db.session.add(p); count += 1
    db.session.flush()
    print(f"  Alhazem products added: {count}")

    tid = NASRALLAH_ID
    cats = {c.name: c for c in ProductCategory.query.filter_by(tenant_id=tid).all()}
    items2 = [
        (cats.get("Electronics"), "Smart Switch WiFi", "مفتاح ذكي", "ELE-SW-WF", "222000000001", 35, 80, 50),
        (cats.get("Electronics"), "USB Charger 4P", "شاحن", "ELE-UC-4P", "222000000002", 20, 50, 80),
        (cats.get("Electronics"), "LED Strip RGB", "شريط LED", "ELE-LS-RGB", "222000000003", 40, 90, 40),
        (cats.get("Electronics"), "Motion Sensor", "مستشعر", "ELE-MS-LGT", "222000000004", 25, 60, 60),
        (cats.get("Electronics"), "Power Bank 20K", "باور بانك", "ELE-PB-20K", "222000000005", 60, 140, 35),
        (cats.get("Tools"), "Electric Drill 500W", "مثقاب", "TOL-ED-500", "222000000006", 120, 280, 25),
        (cats.get("Tools"), "Angle Grinder 750W", "صاروخ", "TOL-AG-750", "222000000007", 150, 350, 20),
        (cats.get("Tools"), "Tool Box 3-Layer", "صندوق أدوات", "TOL-TB-3L", "222000000008", 80, 180, 30),
        (cats.get("Paint"), "Acrylic Red 1L", "دهان أحمر", "PNT-AR-1L", "222000000009", 35, 80, 40),
        (cats.get("Paint"), "Primer White 4L", "بوية بيضاء", "PNT-PW-4L", "222000000010", 60, 130, 35),
    ]
    cat_plumb = ProductCategory(tenant_id=tid, name="Plumbing", name_ar="سباكة")
    db.session.add(cat_plumb); db.session.flush()
    items2 += [
        (cat_plumb, "PVC Pipe 1 inch", "مواسير PVC", "PLU-PP-1IN", "222000000011", 15, 35, 80),
        (cat_plumb, "Water Tap Chrome", "حنفية", "PLU-WT-CHR", "222000000012", 40, 90, 30),
        (cat_plumb, "Shower Head Set", "طقم دش", "PLU-SH-SET", "222000000013", 80, 180, 20),
        (cat_plumb, "Sink Basin", "حوض", "PLU-SB-BAS", "222000000014", 150, 320, 15),
    ]
    count = 0
    for cat, name, name_ar, sku, bc, cost, price, stock in items2:
        if not cat: continue
        if Product.query.filter_by(tenant_id=tid, sku=sku).first(): continue
        p = Product(tenant_id=tid, category_id=cat.id, name=name, name_ar=name_ar, sku=sku,
                    barcode=bc, cost_price=Decimal(str(cost)), regular_price=Decimal(str(price)),
                    current_stock=Decimal(str(stock)), min_stock_alert=Decimal("10"), unit="piece", is_active=True)
        db.session.add(p); count += 1
    db.session.flush()
    print(f"  Nasrallah products added: {count}")


def seed_customers():
    for tid, data in [(ALHAZEM_ID, [
        ("Ahmed Garage", "كراج أحمد", "regular", "0501000001"),
        ("Khaled Auto", "خالد اوتو", "merchant", "0501000002"),
        ("Omar Motors", "عمر موتورز", "partner", "0501000003"),
        ("Faisal Workshop", "ورشة فيصل", "regular", "0501000004"),
        ("Salem Spare Parts", "قطع غيار سالم", "merchant", "0501000005"),
        ("Hassan Service", "خدمات حسن", "regular", "0501000006"),
        ("Ali Battery Shop", "محل بطاريات علي", "partner", "0501000007"),
        ("Metro Garage", "مترو جراج", "merchant", "0501000008"),
        ("City Auto Care", "سيتي أوتو", "regular", "0501000009"),
        ("Royal Motors", "رويال موتورز", "partner", "0501000010"),
        ("Speed Workshop", "ورشة سبيد", "regular", "0501000011"),
        ("Turbo Auto", "توربو أوتو", "merchant", "0501000012"),
    ]), (NASRALLAH_ID, [
        ("Ramallah Hardware", "عتاد رام الله", "regular", "0591000001"),
        ("Birzeit Supplies", "مستلزمات بيرزيت", "merchant", "0591000002"),
        ("Al-Bireh Store", "متجر البيرة", "partner", "0591000003"),
        ("Nablus Trading", "تجارة نابلس", "regular", "0591000004"),
        ("Hebron Materials", "مواد الخليل", "merchant", "0591000005"),
        ("Jericho Builders", "بناة أريحا", "regular", "0591000006"),
        ("Qalqilya Shop", "محل قلقيلية", "partner", "0591000007"),
        ("Jenin Hardware", "عتاد جنين", "merchant", "0591000008"),
        ("Tulkarm Supplies", "مستلزمات طولكرم", "regular", "0591000009"),
        ("Bethlehem Store", "متجر بيت لحم", "partner", "0591000010"),
        ("Salfit Center", "مركز سلفيت", "regular", "0591000011"),
        ("Jerusalem Tools", "أدوات القدس", "merchant", "0591000012"),
    ])]:
        count = 0
        for name, name_ar, ctype, phone in data:
            if Customer.query.filter_by(tenant_id=tid, name=name).first(): continue
            c = Customer(tenant_id=tid, name=name, name_ar=name_ar, customer_type=ctype, phone=phone)
            db.session.add(c); count += 1
        db.session.flush()
        print(f"  {'Alha' if tid == ALHAZEM_ID else 'Nasrallah'} customers added: {count}")


def seed_sales():
    for tid, prefix, curr in [(ALHAZEM_ID, "SAL-AHZ", "AED"), (NASRALLAH_ID, "SAL-NSR", "ILS")]:
        seller = User.query.filter_by(tenant_id=tid).filter(User.username.like("%seller")).first()
        branch = Branch.query.filter_by(tenant_id=tid).first()
        wh = Warehouse.query.filter_by(tenant_id=tid).first()
        customers = Customer.query.filter_by(tenant_id=tid).all()
        products = Product.query.filter_by(tenant_id=tid).all()
        if not (seller and branch and wh and customers and products):
            print(f"  Skip {prefix}: missing data"); continue
        count = 0
        for i in range(20):
            cust = random.choice(customers)
            prods = random.sample(products, min(random.randint(1, 4), len(products)))
            subtotal = Decimal("0")
            lines_data = []
            for p in prods:
                qty = random.randint(1, 5)
                price = float(p.regular_price)
                line_total = Decimal(str(qty)) * Decimal(str(price))
                lines_data.append((p.id, qty, price, float(p.cost_price), line_total))
                subtotal += line_total
            tax = (subtotal * Decimal("0.05")).quantize(Decimal("0.01"))
            total = (subtotal + tax).quantize(Decimal("0.001"))
            s = Sale(tenant_id=tid, sale_number=f"{prefix}-{20260001+i}", customer_id=cust.id,
                     seller_id=seller.id, branch_id=branch.id, warehouse_id=wh.id,
                     currency=curr, exchange_rate=Decimal("1"), tax_rate=Decimal("5"),
                     subtotal=subtotal, tax_amount=tax, total_amount=total,
                     amount_aed=total, paid_amount=0, paid_amount_aed=0,
                     balance_due=total, status="confirmed", payment_status="unpaid")
            db.session.add(s); db.session.flush()
            for pid, qty, price, cost, ltotal in lines_data:
                line = SaleLine(tenant_id=tid, sale_id=s.id, product_id=pid,
                                quantity=Decimal(str(qty)), unit_price=Decimal(str(price)),
                                cost_price=Decimal(str(cost)), line_total=ltotal)
                db.session.add(line)
            count += 1
        db.session.flush()
        print(f"  {prefix} sales added: {count}")


def seed_purchases():
    for tid, prefix, curr in [(ALHAZEM_ID, "PUR-AHZ", "AED"), (NASRALLAH_ID, "PUR-NSR", "ILS")]:
        products = Product.query.filter_by(tenant_id=tid).all()
        wh = Warehouse.query.filter_by(tenant_id=tid).first()
        user = User.query.filter_by(tenant_id=tid).first()
        if not (products and wh and user): continue
        count = 0
        for i in range(12):
            p = random.choice(products)
            qty = random.randint(20, 100)
            cost = float(p.cost_price)
            total = Decimal(str(qty)) * Decimal(str(cost))
            if Purchase.query.filter_by(tenant_id=tid, purchase_number=f"{prefix}-{20260001+i}").first(): continue
            pur = Purchase(tenant_id=tid, purchase_number=f"{prefix}-{20260001+i}",
                          warehouse_id=wh.id, supplier_name="Default Supplier",
                          subtotal=total, tax_amount=total*Decimal("0.05"),
                          total_amount=total*Decimal("1.05"), amount_aed=total*Decimal("1.05"),
                          currency=curr, status="confirmed", user_id=user.id)
            db.session.add(pur); db.session.flush()
            pl = PurchaseLine(tenant_id=tid, purchase_id=pur.id, product_id=p.id,
                              quantity=Decimal(str(qty)), unit_cost=Decimal(str(cost)), line_total=total)
            db.session.add(pl); count += 1
        db.session.flush()
        print(f"  {prefix} purchases added: {count}")


def seed_expenses():
    for tid, curr, data in [
        (ALHAZEM_ID, "AED", [("Rent", "Shop Rent", "إيجار", Decimal("5000")),
                             ("Salaries", "Staff Salaries", "رواتب", Decimal("12000")),
                             ("Utilities", "Electricity", "كهرباء", Decimal("800")),
                             ("Utilities", "Water", "مياه", Decimal("200")),
                             ("Marketing", "Social Ads", "إعلانات", Decimal("1500")),
                             ("Maintenance", "AC Repair", "مكيف", Decimal("600")),
                             ("Rent", "Warehouse Rent", "إيجار مخزن", Decimal("2000")),
                             ("Salaries", "Bonus", "مكافأة", Decimal("3000")),
                             ("Utilities", "Internet", "انترنت", Decimal("300")),
                             ("Marketing", "Flyers", "برشورات", Decimal("400")),
        ]),
        (NASRALLAH_ID, "ILS", [("Rent", "Store Rent", "إيجار", Decimal("3000")),
                               ("Salaries", "Staff Salaries", "رواتب", Decimal("8000")),
                               ("Utilities", "Electricity", "كهرباء", Decimal("500")),
                               ("Transport", "Delivery Fuel", "وقود", Decimal("400")),
                               ("Supplies", "Packaging", "تغليف", Decimal("600")),
                               ("Rent", "Office Rent", "إيجار مكتب", Decimal("1500")),
                               ("Salaries", "Overtime", "ساعات إضافية", Decimal("1200")),
                               ("Utilities", "Phone", "هاتف", Decimal("250")),
                               ("Transport", "Shipping", "شحن", Decimal("800")),
                               ("Supplies", "Stationery", "قرطاسية", Decimal("350")),
        ])
    ]:
        cat_objs = {}
        cat_names = set(d[0] for d in data)
        for cname in cat_names:
            c = ExpenseCategory.query.filter_by(name=cname).first()
            if not c:
                c = ExpenseCategory(tenant_id=tid, name=cname)
                db.session.add(c); db.session.flush()
            cat_objs[cname] = c
        count = 0
        for cat_name, desc, desc_ar, amount in data:
            exp = Expense(tenant_id=tid, category_id=cat_objs[cat_name].id, description=desc,
                          amount=amount, currency=curr, amount_aed=amount,
                          expense_date=datetime(2026, random.randint(1,5), random.randint(1,28), tzinfo=timezone.utc),
                          status="approved")
            db.session.add(exp); count += 1
        db.session.flush()
        print(f"  {'Alhazem' if tid == ALHAZEM_ID else 'Nasrallah'} expenses added: {count}")


def seed_employees():
    for tid, curr, data in [
        (ALHAZEM_ID, "AED", [("Mohammad Alhazem", "محمد الحازم", "sales", Decimal("5000")),
                             ("Sami Mechanic", "سامي ميكانيكي", "service", Decimal("4500")),
                             ("Rami Driver", "رامي سائق", "logistics", Decimal("3500")),
                             ("Huda Reception", "هدى استقبال", "admin", Decimal("4000")),
                             ("Tarek Inventory", "طارق مخزن", "warehouse", Decimal("3800")),
                             ("Fadi Sales", "فادي مبيعات", "sales", Decimal("4200")),
                             ("Lina Accountant", "لينا محاسبة", "finance", Decimal("4800")),
        ]),
        (NASRALLAH_ID, "ILS", [("Khaled Nasrallah", "خالد نصر الله", "sales", Decimal("3500")),
                               ("Marwan Helper", "مروان مساعد", "service", Decimal("2800")),
                               ("Fadi Cashier", "فادي كاشير", "admin", Decimal("3000")),
                               ("Lina Sales", "لينا مبيعات", "sales", Decimal("3200")),
                               ("Omar Warehouse", "عمر مخزن", "warehouse", Decimal("2900")),
                               ("Sana Admin", "سناء إدارية", "admin", Decimal("3100")),
        ])
    ]:
        count = 0
        for name, name_ar, dept, salary in data:
            if Employee.query.filter_by(tenant_id=tid, full_name=name).first(): continue
            e = Employee(tenant_id=tid, full_name=name, full_name_ar=name_ar, department=dept,
                         base_salary=salary, currency=curr, is_active=True,
                         hire_date=date(2025, random.randint(1,12), random.randint(1,28)))
            db.session.add(e); count += 1
        db.session.flush()
        print(f"  {'Alhazem' if tid == ALHAZEM_ID else 'Nasrallah'} employees added: {count}")


def seed_suppliers():
    for tid, data in [
        (ALHAZEM_ID, [("Varta UAE", "0502000001"), ("Bosch ME", "0502000002"),
                      ("Michelin Dist", "0502000003"), ("Castrol Gulf", "0502000004"),
                      ("Exide Int", "0502000005"), ("NGK Plugs", "0502000006"),
        ]),
        (NASRALLAH_ID, [("China Direct", "0592000001"), ("Turkey Hardware", "0592000002"),
                        ("Local Factory", "0592000003"), ("Egypt Supplies", "0592000004"),
                        ("Jordan Trade", "0592000005"),
        ])
    ]:
        count = 0
        for name, phone in data:
            if Supplier.query.filter_by(tenant_id=tid, name=name).first(): continue
            s = Supplier(tenant_id=tid, name=name, phone=phone, supplier_type="regular")
            db.session.add(s); count += 1
        db.session.flush()
        print(f"  {'Alhazem' if tid == ALHAZEM_ID else 'Nasrallah'} suppliers added: {count}")


def main():
    with app.app_context():
        global ALHAZEM_ID, NASRALLAH_ID
        t1 = Tenant.query.filter_by(slug="alhazem").first()
        t2 = Tenant.query.filter_by(slug="nasrallah").first()
        if t1: ALHAZEM_ID = t1.id
        if t2: NASRALLAH_ID = t2.id
        print(f"Tenant IDs: alhazem={ALHAZEM_ID}, nasrallah={NASRALLAH_ID}")
        print("\n=== PRODUCTS ===")
        seed_products()
        print("\n=== CUSTOMERS ===")
        seed_customers()
        print("\n=== SALES ===")
        seed_sales()
        print("\n=== PURCHASES ===")
        seed_purchases()
        print("\n=== EXPENSES ===")
        seed_expenses()
        print("\n=== EMPLOYEES ===")
        seed_employees()
        print("\n=== SUPPLIERS ===")
        seed_suppliers()
        db.session.commit()
        print("\n✅ ALL DATA SEEDED SUCCESSFULLY")


if __name__ == "__main__":
    main()
