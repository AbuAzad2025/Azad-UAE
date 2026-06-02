"""Seed suppliers for Alhazem and Nasrallah tenants."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Supplier, Tenant

app = create_app()


def get_tenant_ids():
    t1 = Tenant.query.filter_by(slug="alhazem").first()
    t2 = Tenant.query.filter_by(slug="nasrallah").first()
    return (t1.id if t1 else 8, t2.id if t2 else 2)


def seed():
    with app.app_context():
        alhazem_id, nasrallah_id = get_tenant_ids()
        print(f"Tenant IDs: alhazem={alhazem_id}, nasrallah={nasrallah_id}")
        
        # Alhazem Suppliers
        data = [
            ("Varta UAE", "0502000001"),
            ("Bosch Middle East", "0502000002"),
            ("Michelin Distributor", "0502000003"),
            ("Castrol Gulf", "0502000004"),
            ("Exide International", "0502000005"),
            ("NGK Plugs", "0502000006"),
        ]
        count = 0
        for name, phone in data:
            if Supplier.query.filter_by(tenant_id=alhazem_id, name=name).first(): continue
            s = Supplier(tenant_id=alhazem_id, name=name, phone=phone, supplier_type="regular")
            db.session.add(s); count += 1
        db.session.commit()
        print(f"Alhazem suppliers added: {count}")
        
        # Nasrallah Suppliers
        data = [
            ("China Direct", "0592000001"),
            ("Turkey Hardware", "0592000002"),
            ("Local Factory", "0592000003"),
            ("Egypt Supplies", "0592000004"),
            ("Jordan Trade", "0592000005"),
        ]
        count = 0
        for name, phone in data:
            if Supplier.query.filter_by(tenant_id=nasrallah_id, name=name).first(): continue
            s = Supplier(tenant_id=nasrallah_id, name=name, phone=phone, supplier_type="regular")
            db.session.add(s); count += 1
        db.session.commit()
        print(f"Nasrallah suppliers added: {count}")
        print("✅ Suppliers seeded successfully")


if __name__ == "__main__":
    seed()
