"""Seed products for Alhazem and Nasrallah tenants."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Product, ProductCategory, Tenant
from decimal import Decimal

app = create_app()


def get_tenant_ids():
    t1 = Tenant.query.filter_by(slug="alhazem").first()
    t2 = Tenant.query.filter_by(slug="nasrallah").first()
    return (t1.id if t1 else 8, t2.id if t2 else 2)


def seed():
    with app.app_context():
        alhazem_id, nasrallah_id = get_tenant_ids()
        print(f"Tenant IDs: alhazem={alhazem_id}, nasrallah={nasrallah_id}")
        
        # Alhazem Products
        cats = {c.name: c for c in ProductCategory.query.filter_by(tenant_id=alhazem_id).all()}
        items = [
            (cats.get("Car Batteries"), "Exide 45Ah Battery", "بطارية اكسايد 45", "BAT-EX-45", "111000000001", 120, 200, 60),
            (cats.get("Car Batteries"), "Bosch 55Ah Battery", "بطارية بوش 55", "BAT-BO-55", "111000000002", 140, 230, 45),
            (cats.get("Car Batteries"), "Delkor 80Ah Battery", "بطارية ديلكور 80", "BAT-DK-80", "111000000003", 220, 380, 35),
            (cats.get("Car Batteries"), "Optima YellowTop", "أوبتما", "BAT-OP-YT", "111000000004", 350, 600, 20),
            (cats.get("Tires"), "Goodyear 195/65R15", "جوديير", "TIR-GY-195", "111000000005", 180, 320, 40),
            (cats.get("Tires"), "Bridgestone 215/60R16", "بريدجستون", "TIR-BR-215", "111000000006", 250, 420, 30),
            (cats.get("Tires"), "Continental 225/50R17", "كونتيننتال", "TIR-CN-225", "111000000007", 300, 500, 25),
            (cats.get("Motor Oil"), "Mobil 1 0W-40 4L", "موبيل 1", "OIL-MB-0W40", "111000000008", 120, 200, 80),
            (cats.get("Motor Oil"), "Shell Helix 10W-40 4L", "شل هيليكس", "OIL-SH-10W40", "111000000009", 90, 150, 90),
            (cats.get("Motor Oil"), "Total Quartz 5W-30 4L", "توتال", "OIL-TQ-5W30", "111000000010", 100, 170, 70),
        ]
        cat_parts = ProductCategory(tenant_id=alhazem_id, name="Spare Parts", name_ar="قطع غيار")
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
            if Product.query.filter_by(tenant_id=alhazem_id, sku=sku).first(): continue
            p = Product(tenant_id=alhazem_id, category_id=cat.id, name=name, name_ar=name_ar, sku=sku,
                        barcode=bc, cost_price=Decimal(str(cost)), regular_price=Decimal(str(price)),
                        current_stock=Decimal(str(stock)), min_stock_alert=Decimal("10"), unit="piece", is_active=True)
            db.session.add(p); count += 1
        db.session.commit()
        print(f"Alhazem products added: {count}")
        
        # Nasrallah Products
        cats = {c.name: c for c in ProductCategory.query.filter_by(tenant_id=nasrallah_id).all()}
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
        cat_plumb = ProductCategory(tenant_id=nasrallah_id, name="Plumbing", name_ar="سباكة")
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
            if Product.query.filter_by(tenant_id=nasrallah_id, sku=sku).first(): continue
            p = Product(tenant_id=nasrallah_id, category_id=cat.id, name=name, name_ar=name_ar, sku=sku,
                        barcode=bc, cost_price=Decimal(str(cost)), regular_price=Decimal(str(price)),
                        current_stock=Decimal(str(stock)), min_stock_alert=Decimal("10"), unit="piece", is_active=True)
            db.session.add(p); count += 1
        db.session.commit()
        print(f"Nasrallah products added: {count}")
        print("✅ Products seeded successfully")


if __name__ == "__main__":
    seed()
