"""Seed payroll transactions for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import PayrollTransaction, Employee, User, Branch, Tenant
from datetime import date
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
            branch = Branch.query.filter_by(tenant_id=tid).first()
            
            if not (employees and user):
                print(f"Skip tenant {tid}: missing data")
                continue
            
            count = 0
            # Create payroll for Jan-May 2026
            for month in range(1, 6):
                for emp in employees:
                    # Check if already exists
                    existing = PayrollTransaction.query.filter_by(
                        tenant_id=tid, employee_id=emp.id, month=month, year=2026
                    ).first()
                    if existing:
                        continue
                    
                    basic = emp.basic_salary or Decimal("3000")
                    allowance = Decimal(str(random.randint(200, 1000)))
                    deduction = Decimal(str(random.randint(0, 300)))
                    advance = Decimal(str(random.randint(0, 500)))
                    net = basic + allowance - deduction - advance
                    
                    payroll = PayrollTransaction(
                        tenant_id=tid,
                        employee_id=emp.id,
                        month=month,
                        year=2026,
                        basic_amount=basic,
                        days_worked=Decimal("30"),
                        allowances=allowance,
                        deductions=deduction,
                        advances_deducted=advance,
                        net_salary=net,
                        payment_date=date(2026, month, 25),
                        status="paid",
                        branch_id=branch.id if branch else None,
                        notes=f"Salary for {month}/2026",
                        created_by=user.id
                    )
                    db.session.add(payroll); count += 1
            db.session.commit()
            print(f"Tenant {tid} payroll transactions added: {count}")
        print("✅ Payroll seeded successfully")


if __name__ == "__main__":
    seed()
