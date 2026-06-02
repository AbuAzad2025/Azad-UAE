"""Seed standalone payments for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Payment, Customer, Supplier, User, Branch, Tenant
from datetime import datetime, timezone, date
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
        
        for tid, prefix, curr in [(alhazem_id, "PAY-AHZ", "AED"), (nasrallah_id, "PAY-NSR", "ILS")]:
            customers = Customer.query.filter_by(tenant_id=tid).limit(5).all()
            suppliers = Supplier.query.filter_by(tenant_id=tid).limit(5).all()
            user = User.query.filter_by(tenant_id=tid).first()
            branch = Branch.query.filter_by(tenant_id=tid).first()
            
            if not (customers and suppliers and user):
                print(f"Skip {prefix}: missing data")
                continue
            
            count = 0
            # Customer payments (incoming)
            for i, cust in enumerate(customers):
                amount = Decimal(str(random.randint(500, 5000)))
                p = Payment(
                    tenant_id=tid,
                    payment_number=f"{prefix}-IN-{20260001+i}",
                    payment_type="customer",
                    direction="incoming",
                    customer_id=cust.id,
                    amount=amount,
                    currency=curr,
                    exchange_rate=Decimal("1"),
                    amount_aed=amount,
                    payment_method=random.choice(["cash", "card", "bank_transfer"]),
                    branch_id=branch.id if branch else None,
                    payment_confirmed=True,
                    created_at=datetime(2026, random.randint(1,5), random.randint(1,28), random.randint(9,17), tzinfo=timezone.utc)
                )
                db.session.add(p); count += 1
            
            # Supplier payments (outgoing)
            for i, supp in enumerate(suppliers):
                amount = Decimal(str(random.randint(1000, 10000)))
                p = Payment(
                    tenant_id=tid,
                    payment_number=f"{prefix}-OUT-{20260001+i}",
                    payment_type="supplier",
                    direction="outgoing",
                    supplier_id=supp.id,
                    supplier_name=supp.name,
                    amount=amount,
                    currency=curr,
                    exchange_rate=Decimal("1"),
                    amount_aed=amount,
                    payment_method=random.choice(["cash", "bank_transfer", "cheque"]),
                    branch_id=branch.id if branch else None,
                    payment_confirmed=True,
                    created_at=datetime(2026, random.randint(1,5), random.randint(1,28), random.randint(9,17), tzinfo=timezone.utc)
                )
                db.session.add(p); count += 1
            db.session.commit()
            print(f"{prefix} payments added: {count}")
        print("✅ Payments seeded successfully")


if __name__ == "__main__":
    seed()
