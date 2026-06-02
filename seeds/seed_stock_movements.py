"""Seed stock movements for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import StockMovement, Product, Warehouse, User, Tenant
from datetime import datetime, timezone
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
        
        for tid in [alhazem_id, nasrallah_id]:
            products = Product.query.filter_by(tenant_id=tid).limit(15).all()
            warehouse = Warehouse.query.filter_by(tenant_id=tid).first()
            user = User.query.filter_by(tenant_id=tid).first()
            
            if not (products and warehouse and user):
                print(f"Skip tenant {tid}: missing data")
                continue
            
            count = 0
            for p in products:
                # Add stock in
                sm_in = StockMovement(
                    tenant_id=tid,
                    product_id=p.id,
                    warehouse_id=warehouse.id,
                    movement_type="in",
                    quantity=Decimal(str(random.randint(10, 50))),
                    reference_type="purchase",
                    reference_id=random.randint(1, 100),
                    user_id=user.id,
                    notes="Initial stock",
                    created_at=datetime(2026, 1, random.randint(1,28), random.randint(9,17), tzinfo=timezone.utc)
                )
                db.session.add(sm_in); count += 1
                
                # Add stock out
                sm_out = StockMovement(
                    tenant_id=tid,
                    product_id=p.id,
                    warehouse_id=warehouse.id,
                    movement_type="out",
                    quantity=Decimal(str(random.randint(5, 20))),
                    reference_type="sale",
                    reference_id=random.randint(1, 100),
                    user_id=user.id,
                    notes="Sale",
                    created_at=datetime(2026, 2, random.randint(1,28), random.randint(9,17), tzinfo=timezone.utc)
                )
                db.session.add(sm_out); count += 1
                
                # Add adjustment
                sm_adj = StockMovement(
                    tenant_id=tid,
                    product_id=p.id,
                    warehouse_id=warehouse.id,
                    movement_type="adjustment",
                    quantity=Decimal(str(random.randint(-5, 5))),
                    reference_type="inventory",
                    reference_id=random.randint(1, 100),
                    user_id=user.id,
                    notes="Stock count adjustment",
                    created_at=datetime(2026, 3, random.randint(1,28), random.randint(9,17), tzinfo=timezone.utc)
                )
                db.session.add(sm_adj); count += 1
            db.session.commit()
            print(f"Tenant {tid} stock movements added: {count}")
        print("✅ Stock movements seeded successfully")


if __name__ == "__main__":
    seed()
