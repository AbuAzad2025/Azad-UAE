"""Seed GL journal entries for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import GLJournalEntry, GLJournalLine, GLAccount, User, Branch, Tenant
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
        
        for tid, prefix, curr in [(alhazem_id, "JE-AHZ", "AED"), (nasrallah_id, "JE-NSR", "ILS")]:
            accounts = GLAccount.query.filter_by(tenant_id=tid).all()
            user = User.query.filter_by(tenant_id=tid).first()
            branch = Branch.query.filter_by(tenant_id=tid).first()
            
            if not (accounts and user):
                print(f"Skip {prefix}: missing data")
                continue
            
            # Need at least 2 accounts for balanced entries
            if len(accounts) < 2:
                print(f"Skip {prefix}: need at least 2 GL accounts")
                continue
            
            count = 0
            # Create 20 manual journal entries
            for i in range(20):
                amount = Decimal(str(random.randint(1000, 50000)))
                acc1 = random.choice(accounts)
                acc2 = random.choice([a for a in accounts if a.id != acc1.id])
                
                entry = GLJournalEntry(
                    tenant_id=tid,
                    entry_number=f"{prefix}-{20260001+i}",
                    entry_date=datetime(2026, random.randint(1,5), random.randint(1,28), random.randint(9,17), tzinfo=timezone.utc),
                    description=random.choice(["Manual adjustment", "Opening balance", "Correction", "Transfer", "Reclassification"]),
                    reference_type="manual",
                    entry_type="manual",
                    currency=curr,
                    exchange_rate=Decimal("1"),
                    total_debit=amount,
                    total_credit=amount,
                    is_posted=True,
                    branch_id=branch.id if branch else None,
                    created_by=user.id
                )
                db.session.add(entry); db.session.flush()
                
                # Debit line
                line1 = GLJournalLine(
                    tenant_id=tid,
                    entry_id=entry.id,
                    account_id=acc1.id,
                    description=f"Debit to {acc1.name}",
                    debit=amount,
                    credit=Decimal("0"),
                    amount_aed=amount
                )
                db.session.add(line1)
                
                # Credit line
                line2 = GLJournalLine(
                    tenant_id=tid,
                    entry_id=entry.id,
                    account_id=acc2.id,
                    description=f"Credit from {acc2.name}",
                    debit=Decimal("0"),
                    credit=amount,
                    amount_aed=amount
                )
                db.session.add(line2)
                count += 1
            db.session.commit()
            print(f"{prefix} journal entries added: {count}")
        print("✅ GL entries seeded successfully")


if __name__ == "__main__":
    seed()
