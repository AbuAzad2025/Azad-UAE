"""Seed employees for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Employee, Tenant
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
        
        # Alhazem Employees
        data = [
            ("Mohammad Alhazem", "محمد الحازم", "sales", Decimal("5000")),
            ("Sami Mechanic", "سامي ميكانيكي", "service", Decimal("4500")),
            ("Rami Driver", "رامي سائق", "logistics", Decimal("3500")),
            ("Huda Reception", "هدى استقبال", "admin", Decimal("4000")),
            ("Tarek Inventory", "طارق مخزن", "warehouse", Decimal("3800")),
            ("Fadi Sales", "فادي مبيعات", "sales", Decimal("4200")),
            ("Lina Accountant", "لينا محاسبة", "finance", Decimal("4800")),
        ]
        count = 0
        for name, name_ar, dept, salary in data:
            if Employee.query.filter_by(tenant_id=alhazem_id, name=name).first(): continue
            e = Employee(tenant_id=alhazem_id, name=name, name_ar=name_ar, employment_type=dept,
                         basic_salary=salary, currency="AED", is_active=True,
                         joined_date=date(2025, random.randint(1,12), random.randint(1,28)))
            db.session.add(e); count += 1
        db.session.commit()
        print(f"Alhazem employees added: {count}")
        
        # Nasrallah Employees
        data = [
            ("Khaled Nasrallah", "خالد نصر الله", "sales", Decimal("3500")),
            ("Marwan Helper", "مروان مساعد", "service", Decimal("2800")),
            ("Fadi Cashier", "فادي كاشير", "admin", Decimal("3000")),
            ("Lina Sales", "لينا مبيعات", "sales", Decimal("3200")),
            ("Omar Warehouse", "عمر مخزن", "warehouse", Decimal("2900")),
            ("Sana Admin", "سناء إدارية", "admin", Decimal("3100")),
        ]
        count = 0
        for name, name_ar, dept, salary in data:
            if Employee.query.filter_by(tenant_id=nasrallah_id, name=name).first(): continue
            e = Employee(tenant_id=nasrallah_id, name=name, name_ar=name_ar, employment_type=dept,
                         basic_salary=salary, currency="ILS", is_active=True,
                         joined_date=date(2025, random.randint(1,12), random.randint(1,28)))
            db.session.add(e); count += 1
        db.session.commit()
        print(f"Nasrallah employees added: {count}")
        print("✅ Employees seeded successfully")


if __name__ == "__main__":
    seed()
