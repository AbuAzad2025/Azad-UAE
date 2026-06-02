"""Seed additional merchant customers for Alhazem and Nasrallah tenants."""
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
        
        # Alhazem Merchants
        data = [
            ("Abu Dhabi Auto", "أبوظبي أوتو", "merchant", "0502000001", "abudhabi@example.com"),
            ("Dubai Motors", "دبي موتورز", "merchant", "0502000002", "dubai@example.com"),
            ("Sharjah Battery", "الشارقة بطاريات", "merchant", "0502000003", "sharjah@example.com"),
            ("Ajman Spare Parts", "عجمان قطع غيار", "merchant", "0502000004", "ajman@example.com"),
            ("Ras Al Khaimah Auto", "رأس الخيمة", "merchant", "0502000005", "rak@example.com"),
            ("Fujairah Garage", "فجيرة كراج", "merchant", "0502000006", "fujairah@example.com"),
            ("Umm Al Quwain Service", "أم القيوين", "merchant", "0502000007", "uaq@example.com"),
            ("Al Ain Battery Shop", "العين بطاريات", "merchant", "0502000008", "alain@example.com"),
            ("Dibba Auto Parts", "دبا قطع غيار", "merchant", "0502000009", "dibba@example.com"),
            ("Khor Fakkan Motors", "خورفكان", "merchant", "0502000010", "khor@example.com"),
        ]
        count = 0
        for name, name_ar, ctype, phone, email in data:
            if Customer.query.filter_by(tenant_id=alhazem_id, name=name).first(): continue
            c = Customer(tenant_id=alhazem_id, name=name, name_ar=name_ar, customer_type=ctype, phone=phone, email=email)
            db.session.add(c); count += 1
        db.session.commit()
        print(f"Alhazem merchants added: {count}")
        
        # Nasrallah Merchants
        data = [
            ("Gaza Hardware", "عتاد غزة", "merchant", "0592000001", "gaza@example.com"),
            ("Ramallah Electronics", "رام الله إلكترونيات", "merchant", "0592000002", "ramallah@example.com"),
            ("Nablus Tools", "نابلس أدوات", "merchant", "0592000003", "nablus@example.com"),
            ("Hebron Construction", "الخليل بناء", "merchant", "0592000004", "hebron@example.com"),
            ("Bethlehem Supplies", "بيت لحم مستلزمات", "merchant", "0592000005", "bethlehem@example.com"),
            ("Jericho Materials", "أريحا مواد", "merchant", "0592000006", "jericho@example.com"),
            ("Tulkarm Building", "طولكرم بناء", "merchant", "0592000007", "tulkarm@example.com"),
            ("Qalqilya Hardware", "قلقيلية عتاد", "merchant", "0592000008", "qalqilya@example.com"),
            ("Jenin Construction", "جنين بناء", "merchant", "0592000009", "jenin@example.com"),
            ("Salfit Supplies", "سلفيت مستلزمات", "merchant", "0592000010", "salfit@example.com"),
        ]
        count = 0
        for name, name_ar, ctype, phone, email in data:
            if Customer.query.filter_by(tenant_id=nasrallah_id, name=name).first(): continue
            c = Customer(tenant_id=nasrallah_id, name=name, name_ar=name_ar, customer_type=ctype, phone=phone, email=email)
            db.session.add(c); count += 1
        db.session.commit()
        print(f"Nasrallah merchants added: {count}")
        print("✅ Merchants seeded successfully")


if __name__ == "__main__":
    seed()
