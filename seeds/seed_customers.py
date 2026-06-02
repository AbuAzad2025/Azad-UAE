"""Seed customers for Alhazem and Nasrallah tenants."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Customer, Tenant

app = create_app()


def get_tenant_ids():
    t1 = Tenant.query.filter_by(slug="alhazem").first()
    t2 = Tenant.query.filter_by(slug="nasrallah").first()
    return (t1.id if t1 else 8, t2.id if t2 else 2)


def seed():
    with app.app_context():
        alhazem_id, nasrallah_id = get_tenant_ids()
        print(f"Tenant IDs: alhazem={alhazem_id}, nasrallah={nasrallah_id}")
        
        # Alhazem Customers
        data = [
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
        ]
        count = 0
        for name, name_ar, ctype, phone in data:
            if Customer.query.filter_by(tenant_id=alhazem_id, name=name).first(): continue
            c = Customer(tenant_id=alhazem_id, name=name, name_ar=name_ar, customer_type=ctype, phone=phone)
            db.session.add(c); count += 1
        db.session.commit()
        print(f"Alhazem customers added: {count}")
        
        # Nasrallah Customers
        data = [
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
        ]
        count = 0
        for name, name_ar, ctype, phone in data:
            if Customer.query.filter_by(tenant_id=nasrallah_id, name=name).first(): continue
            c = Customer(tenant_id=nasrallah_id, name=name, name_ar=name_ar, customer_type=ctype, phone=phone)
            db.session.add(c); count += 1
        db.session.commit()
        print(f"Nasrallah customers added: {count}")
        print("✅ Customers seeded successfully")


if __name__ == "__main__":
    seed()
