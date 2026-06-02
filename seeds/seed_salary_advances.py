"""Seed salary advances for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import SalaryAdvance, Employee, User, Tenant
from datetime import date, datetime, timezone
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
        
        for tid, curr in [(alhazem_id, "AED"), (nasrallah_id, "ILS")]:
            employees = Employee.query.filter_by(tenant_id=tid, is_active=True).all()
            user = User.query.filter_by(tenant_id=tid).first()
            
            if not (employees and user):
                print(f"Skip tenant {tid}: missing data")
                continue
            
            count = 0
            for emp in employees:
                # Give 1-2 advances to each employee
                for _ in range(random.randint(1, 2)):
                    amount = Decimal(str(random.randint(500, 2000)))
                    advance = SalaryAdvance(
                        tenant_id=tid,
                        employee_id=emp.id,
                        amount=amount,
                        date=date(2026, random.randint(1,5), random.randint(1,28)),
                        description=random.choice(["Emergency", "Medical", "Family", "Personal"]),
                        status=random.choice(["approved", "paid", "pending"]),
                        is_deducted=random.choice([True, False]),
                        created_by=user.id
                    )
                    db.session.add(advance); count += 1
            db.session.commit()
            print(f"Tenant {tid} salary advances added: {count}")
        print("✅ Salary advances seeded successfully")


if __name__ == "__main__":
    seed()
