"""Seed cheques for Alhazem and Nasrallah tenants - due, post-dated, and bounced."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Cheque, Customer, Supplier, User, Tenant
from datetime import date, timedelta
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
        
        for tid, prefix, curr in [(alhazem_id, "CHQ-AHZ", "AED"), (nasrallah_id, "CHQ-NSR", "ILS")]:
            customers = Customer.query.filter_by(tenant_id=tid).limit(5).all()
            suppliers = Supplier.query.filter_by(tenant_id=tid).limit(5).all()
            user = User.query.filter_by(tenant_id=tid).first()
            
            if not (customers and suppliers and user):
                print(f"Skip {prefix}: missing data")
                continue
            
            count = 0
            today = date(2026, 6, 2)
            
            # Incoming cheques from customers (due/post-dated)
            for i, cust in enumerate(customers):
                # Due cheques (already due)
                due_date = today - timedelta(days=random.randint(1, 30))
                chq = Cheque(
                    tenant_id=tid,
                    cheque_number=f"{prefix}-IN-{20260001+i}",
                    cheque_bank_number=str(random.randint(1000000, 9999999)),
                    cheque_type="incoming",
                    bank_name=random.choice(["Emirates NBD", "ADCB", "FAB", "Mashreq", "RAKBank"]),
                    bank_branch="Main Branch",
                    account_number=str(random.randint(1000000000, 9999999999)),
                    amount=Decimal(str(random.randint(1000, 10000))),
                    currency=curr,
                    exchange_rate=Decimal("1"),
                    amount_aed=Decimal(str(random.randint(1000, 10000))),
                    issue_date=today - timedelta(days=random.randint(30, 60)),
                    due_date=due_date,
                    deposit_date=today - timedelta(days=random.randint(1, 15)),
                    status=random.choice(["cleared", "pending", "deposited"])
                )
                db.session.add(chq); count += 1
                
                # Post-dated cheques (future due date)
                future_date = today + timedelta(days=random.randint(15, 90))
                chq2 = Cheque(
                    tenant_id=tid,
                    cheque_number=f"{prefix}-PD-{20260001+i}",
                    cheque_bank_number=str(random.randint(1000000, 9999999)),
                    cheque_type="incoming",
                    bank_name=random.choice(["Emirates NBD", "ADCB", "FAB", "Mashreq", "RAKBank"]),
                    bank_branch="Main Branch",
                    account_number=str(random.randint(1000000000, 9999999999)),
                    amount=Decimal(str(random.randint(2000, 15000))),
                    currency=curr,
                    exchange_rate=Decimal("1"),
                    amount_aed=Decimal(str(random.randint(2000, 15000))),
                    issue_date=today - timedelta(days=random.randint(5, 20)),
                    due_date=future_date,
                    status="pending"
                )
                db.session.add(chq2); count += 1
            
            # Outgoing cheques to suppliers
            for i, supp in enumerate(suppliers):
                # Bounced cheques
                chq = Cheque(
                    tenant_id=tid,
                    cheque_number=f"{prefix}-OUT-{20260001+i}",
                    cheque_bank_number=str(random.randint(1000000, 9999999)),
                    cheque_type="outgoing",
                    bank_name=random.choice(["Emirates NBD", "ADCB", "FAB", "Mashreq", "RAKBank"]),
                    bank_branch="Main Branch",
                    account_number=str(random.randint(1000000000, 9999999999)),
                    amount=Decimal(str(random.randint(3000, 12000))),
                    currency=curr,
                    exchange_rate=Decimal("1"),
                    amount_aed=Decimal(str(random.randint(3000, 12000))),
                    issue_date=today - timedelta(days=random.randint(20, 45)),
                    due_date=today - timedelta(days=random.randint(5, 15)),
                    deposit_date=today - timedelta(days=random.randint(1, 10)),
                    clearance_date=today - timedelta(days=random.randint(1, 5)),
                    status="bounced"
                )
                db.session.add(chq); count += 1
                
                # Due cheques (need to be paid)
                due_date = today - timedelta(days=random.randint(1, 20))
                chq2 = Cheque(
                    tenant_id=tid,
                    cheque_number=f"{prefix}-DUE-{20260001+i}",
                    cheque_bank_number=str(random.randint(1000000, 9999999)),
                    cheque_type="outgoing",
                    bank_name=random.choice(["Emirates NBD", "ADCB", "FAB", "Mashreq", "RAKBank"]),
                    bank_branch="Main Branch",
                    account_number=str(random.randint(1000000000, 9999999999)),
                    amount=Decimal(str(random.randint(2000, 8000))),
                    currency=curr,
                    exchange_rate=Decimal("1"),
                    amount_aed=Decimal(str(random.randint(2000, 8000))),
                    issue_date=today - timedelta(days=random.randint(30, 60)),
                    due_date=due_date,
                    status="pending"
                )
                db.session.add(chq2); count += 1
            db.session.commit()
            print(f"{prefix} cheques added: {count}")
        print("✅ Cheques seeded successfully")


if __name__ == "__main__":
    seed()
