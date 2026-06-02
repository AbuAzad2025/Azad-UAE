"""Seed expenses for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Expense, ExpenseCategory, Tenant, User
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
        
        # Alhazem Expenses
        data = [
            ("Rent", "Shop Rent", "إيجار", Decimal("5000")),
            ("Salaries", "Staff Salaries", "رواتب", Decimal("12000")),
            ("Utilities", "Electricity", "كهرباء", Decimal("800")),
            ("Utilities", "Water", "مياه", Decimal("200")),
            ("Marketing", "Social Ads", "إعلانات", Decimal("1500")),
            ("Maintenance", "AC Repair", "مكيف", Decimal("600")),
            ("Rent", "Warehouse Rent", "إيجار مخزن", Decimal("2000")),
            ("Salaries", "Bonus", "مكافأة", Decimal("3000")),
            ("Utilities", "Internet", "انترنت", Decimal("300")),
            ("Marketing", "Flyers", "برشورات", Decimal("400")),
        ]
        cat_objs = {}
        cat_names = set(d[0] for d in data)
        for cname in cat_names:
            c = ExpenseCategory.query.filter_by(name=cname).first()
            if not c:
                c = ExpenseCategory(tenant_id=alhazem_id, name=cname)
                db.session.add(c); db.session.flush()
            cat_objs[cname] = c
        
        user = User.query.filter_by(tenant_id=alhazem_id).first()
        count = 0
        for i, (cat_name, desc, desc_ar, amount) in enumerate(data):
            exp = Expense(tenant_id=alhazem_id, category_id=cat_objs[cat_name].id, description=desc,
                          expense_number=f"EXP-AHZ-{20260001+i}",
                          amount=amount, currency="AED", amount_aed=amount,
                          payment_method="cash", user_id=user.id if user else None,
                          expense_date=datetime(2026, random.randint(1,5), random.randint(1,28), tzinfo=timezone.utc),
                          status="approved")
            db.session.add(exp); count += 1
        db.session.commit()
        print(f"Alhazem expenses added: {count}")
        
        # Nasrallah Expenses
        data = [
            ("Rent", "Store Rent", "إيجار", Decimal("3000")),
            ("Salaries", "Staff Salaries", "رواتب", Decimal("8000")),
            ("Utilities", "Electricity", "كهرباء", Decimal("500")),
            ("Transport", "Delivery Fuel", "وقود", Decimal("400")),
            ("Supplies", "Packaging", "تغليف", Decimal("600")),
            ("Rent", "Office Rent", "إيجار مكتب", Decimal("1500")),
            ("Salaries", "Overtime", "ساعات إضافية", Decimal("1200")),
            ("Utilities", "Phone", "هاتف", Decimal("250")),
            ("Transport", "Shipping", "شحن", Decimal("800")),
            ("Supplies", "Stationery", "قرطاسية", Decimal("350")),
        ]
        cat_objs = {}
        cat_names = set(d[0] for d in data)
        for cname in cat_names:
            c = ExpenseCategory.query.filter_by(name=cname).first()
            if not c:
                c = ExpenseCategory(tenant_id=nasrallah_id, name=cname)
                db.session.add(c); db.session.flush()
            cat_objs[cname] = c
        
        user = User.query.filter_by(tenant_id=nasrallah_id).first()
        count = 0
        for i, (cat_name, desc, desc_ar, amount) in enumerate(data):
            exp = Expense(tenant_id=nasrallah_id, category_id=cat_objs[cat_name].id, description=desc,
                          expense_number=f"EXP-NSR-{20260001+i}",
                          amount=amount, currency="ILS", amount_aed=amount,
                          payment_method="cash", user_id=user.id if user else None,
                          expense_date=datetime(2026, random.randint(1,5), random.randint(1,28), tzinfo=timezone.utc),
                          status="approved")
            db.session.add(exp); count += 1
        db.session.commit()
        print(f"Nasrallah expenses added: {count}")
        print("✅ Expenses seeded successfully")


if __name__ == "__main__":
    seed()
