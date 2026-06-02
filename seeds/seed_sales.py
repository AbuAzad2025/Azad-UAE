"""Seed sales for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Sale, SaleLine, Customer, Product, User, Branch, Warehouse, Tenant
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
        
        for tid, prefix, curr in [(alhazem_id, "SAL-AHZ", "AED"), (nasrallah_id, "SAL-NSR", "ILS")]:
            seller = User.query.filter_by(tenant_id=tid).filter(User.username.like("%seller")).first()
            branch = Branch.query.filter_by(tenant_id=tid).first()
            wh = Warehouse.query.filter_by(tenant_id=tid).first()
            customers = Customer.query.filter_by(tenant_id=tid).all()
            products = Product.query.filter_by(tenant_id=tid).all()
            
            if not (seller and branch and wh and customers and products):
                print(f"Skip {prefix}: missing data")
                continue
            
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
            db.session.commit()
            print(f"{prefix} sales added: {count}")
        print("✅ Sales seeded successfully")


if __name__ == "__main__":
    seed()
