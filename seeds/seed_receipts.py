"""Seed payment receipts for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Receipt, Sale, Customer, User, Branch, Tenant
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
        
        for tid, prefix, curr in [(alhazem_id, "REC-AHZ", "AED"), (nasrallah_id, "REC-NSR", "ILS")]:
            sales = Sale.query.filter_by(tenant_id=tid, payment_status="unpaid").limit(15).all()
            user = User.query.filter_by(tenant_id=tid).first()
            branch = Branch.query.filter_by(tenant_id=tid).first()
            
            if not (sales and user and branch):
                print(f"Skip {prefix}: missing data")
                continue
            
            count = 0
            for i, sale in enumerate(sales):
                if Receipt.query.filter_by(tenant_id=tid, source_id=sale.id).first():
                    continue
                
                amount = min(sale.balance_due, sale.total_amount * Decimal("0.5"))
                receipt = Receipt(
                    tenant_id=tid,
                    receipt_number=f"{prefix}-{20260001+i}",
                    source_type="sale",
                    source_id=sale.id,
                    direction="incoming",
                    customer_id=sale.customer_id,
                    amount=amount,
                    currency=curr,
                    exchange_rate=Decimal("1"),
                    amount_aed=amount,
                    payment_method=random.choice(["cash", "card", "bank_transfer"]),
                    branch_id=branch.id,
                    receipt_date=datetime(2026, random.randint(1,5), random.randint(1,28), random.randint(9,17), tzinfo=timezone.utc),
                    user_id=user.id
                )
                db.session.add(receipt)
                
                # Update sale payment status
                sale.paid_amount += amount
                sale.paid_amount_aed += amount
                sale.balance_due -= amount
                if sale.balance_due <= 0:
                    sale.payment_status = "paid"
                else:
                    sale.payment_status = "partial"
                count += 1
            db.session.commit()
            print(f"{prefix} receipts added: {count}")
        print("✅ Receipts seeded successfully")


if __name__ == "__main__":
    seed()
