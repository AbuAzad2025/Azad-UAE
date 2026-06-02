"""Seed purchases for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Purchase, PurchaseLine, Product, Warehouse, User, Tenant
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
        
        for tid, prefix, curr in [(alhazem_id, "PUR-AHZ", "AED"), (nasrallah_id, "PUR-NSR", "ILS")]:
            products = Product.query.filter_by(tenant_id=tid).all()
            wh = Warehouse.query.filter_by(tenant_id=tid).first()
            user = User.query.filter_by(tenant_id=tid).first()
            
            if not (products and wh and user):
                print(f"Skip {prefix}: missing data")
                continue
            
            count = 0
            for i in range(12):
                p = random.choice(products)
                qty = random.randint(20, 100)
                cost = float(p.cost_price)
                total = Decimal(str(qty)) * Decimal(str(cost))
                
                if Purchase.query.filter_by(tenant_id=tid, purchase_number=f"{prefix}-{20260001+i}").first():
                    continue
                
                pur = Purchase(tenant_id=tid, purchase_number=f"{prefix}-{20260001+i}",
                              warehouse_id=wh.id, supplier_name="Default Supplier",
                              subtotal=total, tax_amount=total*Decimal("0.05"),
                              total_amount=total*Decimal("1.05"), amount_aed=total*Decimal("1.05"),
                              currency=curr, status="confirmed", user_id=user.id)
                db.session.add(pur); db.session.flush()
                
                pl = PurchaseLine(tenant_id=tid, purchase_id=pur.id, product_id=p.id,
                                  quantity=Decimal(str(qty)), unit_cost=Decimal(str(cost)), line_total=total)
                db.session.add(pl); count += 1
            db.session.commit()
            print(f"{prefix} purchases added: {count}")
        print("✅ Purchases seeded successfully")


if __name__ == "__main__":
    seed()
