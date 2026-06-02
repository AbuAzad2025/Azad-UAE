"""Seed product serials for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import ProductSerial, Product, Tenant

app = create_app()


def get_tenant_ids():
    t1 = Tenant.query.filter_by(slug="alhazem").first()
    t2 = Tenant.query.filter_by(slug="nasrallah").first()
    return (t1.id if t1 else 8, t2.id if t2 else 2)


def seed():
    with app.app_context():
        alhazem_id, nasrallah_id = get_tenant_ids()
        print(f"Tenant IDs: alhazem={alhazem_id}, nasrallah={nasrallah_id}")
        
        for prefix in ["AHZ", "NSR"]:
            products = Product.query.filter_by(tenant_id=alhazem_id if prefix == "AHZ" else nasrallah_id).limit(15).all()
            
            if not products:
                print(f"Skip {prefix}: no products found")
                continue
            
            count = 0
            for prod in products:
                # Add 2-5 serial numbers per product
                for i in range(random.randint(2, 5)):
                    serial = f"{prefix}-{prod.id:04d}-{random.randint(1000, 9999)}"
                    if ProductSerial.query.filter_by(serial_number=serial).first():
                        continue
                    ps = ProductSerial(
                        product_id=prod.id,
                        serial_number=serial,
                        status=random.choice(["available", "sold", "returned"])
                    )
                    db.session.add(ps); count += 1
            db.session.commit()
            print(f"{prefix} product serials added: {count}")
        print("✅ Product serials seeded successfully")


if __name__ == "__main__":
    seed()
