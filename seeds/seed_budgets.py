"""Seed budgets for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Budget, BudgetLine, GLAccount, Tenant
from datetime import date
from decimal import Decimal

app = create_app()


def get_tenant_ids():
    t1 = Tenant.query.filter_by(slug="alhazem").first()
    t2 = Tenant.query.filter_by(slug="nasrallah").first()
    return (t1.id if t1 else 8, t2.id if t2 else 2)


def seed():
    with app.app_context():
        # Budgets are global, not tenant-specific
        # Get expense accounts from both tenants
        alhazem_id, nasrallah_id = get_tenant_ids()
        expense_accounts = GLAccount.query.filter_by(type="expense").limit(5).all()
        
        if not expense_accounts:
            print("Skip: no expense accounts found")
            return
        
        # Create annual budget for 2026
        budget = Budget(
            budget_number="BUD-2026-001",
            name_ar="الميزانية السنوية 2026",
            name_en="Annual Budget 2026",
            fiscal_year=2026,
            period_type="annual",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            total_budgeted=Decimal("500000"),
            status="active"
        )
        db.session.add(budget); db.session.flush()
        
        # Add budget lines
        count = 0
        for acc in expense_accounts:
            amount = Decimal(str(random.randint(50000, 150000)))
            line = BudgetLine(
                budget_id=budget.id,
                account_id=acc.id,
                budgeted_amount=amount
            )
            db.session.add(line); count += 1
        db.session.commit()
        print(f"Budget added with {count} lines")
        print("✅ Budgets seeded successfully")


if __name__ == "__main__":
    seed()
