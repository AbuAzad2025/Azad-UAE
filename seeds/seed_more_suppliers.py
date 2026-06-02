"""Seed additional suppliers for Alhazem and Nasrallah tenants."""
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
        
        # Alhazem Additional Suppliers
        data = [
            ("Auto Parts International", "0503000001", "premium"),
            ("Gulf Lubricants", "0503000002", "regular"),
            ("Battery World", "0503000003", "regular"),
            ("Tire Kingdom", "0503000004", "premium"),
            ("Auto Accessories Co", "0503000005", "regular"),
            ("Brake Systems Ltd", "0503000006", "regular"),
            ("Engine Parts Inc", "0503000007", "premium"),
            ("Auto Electrical", "0503000008", "regular"),
            ("Suspension Masters", "0503000009", "regular"),
            ("Cooling Systems", "0503000010", "regular"),
        ]
        count = 0
        for name, phone, stype in data:
            if Supplier.query.filter_by(tenant_id=alhazem_id, name=name).first(): continue
            s = Supplier(tenant_id=alhazem_id, name=name, phone=phone, supplier_type=stype)
            db.session.add(s); count += 1
        db.session.commit()
        print(f"Alhazem additional suppliers added: {count}")
        
        # Nasrallah Additional Suppliers
        data = [
            ("Electronics Hub", "0593000001", "premium"),
            ("Building Materials Co", "0593000002", "regular"),
            ("Hardware Kingdom", "0593000003", "regular"),
            ("Plumbing Supplies", "0593000004", "regular"),
            ("Electrical Equipment", "0593000005", "premium"),
            ("Tools Warehouse", "0593000006", "regular"),
            ("Paint & Decor", "0593000007", "regular"),
            ("Construction Materials", "0593000008", "premium"),
            ("Home Improvement", "0593000009", "regular"),
            ("Industrial Supplies", "0593000010", "regular"),
        ]
        count = 0
        for name, phone, stype in data:
            if Supplier.query.filter_by(tenant_id=nasrallah_id, name=name).first(): continue
            s = Supplier(tenant_id=nasrallah_id, name=name, phone=phone, supplier_type=stype)
            db.session.add(s); count += 1
        db.session.commit()
        print(f"Nasrallah additional suppliers added: {count}")
        print("✅ Additional suppliers seeded successfully")


if __name__ == "__main__":
    seed()
