"""
Integration tests: Expenses routes — real business logic via POST /expenses/create.
"""

import uuid
from decimal import Decimal

from models.gl import GLJournalEntry
from utils.gl_reference_types import GLRef


class TestExpensesCreate:
    def test_create_expense_creates_gl_entry(self, app, db_session, client):
        tid = str(uuid.uuid4())[:8]
        from models import Tenant, Branch, User, Role, ExpenseCategory

        tenant = Tenant(
            name=f"EXP {tid}",
            name_ar=f"EXP {tid}",
            slug=f"exp-test-{tid}",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant)
        db_session.flush()

        branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"BR{tid[:4]}")
        db_session.add(branch)
        db_session.flush()

        role = Role(name=f"Admin {tid}", slug=f"admin-{tid}", is_active=True)
        db_session.add(role)
        db_session.flush()

        user = User(
            username=f"exp-{tid}",
            email=f"exp-{tid}@t.com",
            full_name="Expenser",
            role_id=role.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            is_active=True,
            is_owner=True,
        )
        user.set_password("x")
        db_session.add(user)
        db_session.flush()

        cat = ExpenseCategory(
            tenant_id=tenant.id,
            name=f"Office {tid}",
            gl_account_code="6500",
            is_active=True,
        )
        db_session.add(cat)
        db_session.commit()

        from services.gl_service import GLService

        GLService.ensure_core_accounts(tenant_id=tenant.id)
        db_session.commit()

        with client:
            resp = client.post(
                "/auth/login",
                data={
                    "username": user.username,
                    "password": "x",
                },
                follow_redirects=True,
            )
            assert resp.status_code == 200

            resp = client.post(
                "/expenses/create",
                data={
                    "amount": "250.50",
                    "currency": "AED",
                    "exchange_rate": "1",
                    "description": f"Office supplies {tid}",
                    "category_id": str(cat.id),
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )

        assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"

        from models import Expense

        expense = Expense.query.filter_by(tenant_id=tenant.id).first()
        assert expense is not None, "Expense was not created"
        assert expense.amount == Decimal("250.50"), f"amount={expense.amount}"
        assert expense.category_id == cat.id

        gl_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type == GLRef.EXPENSE,
            GLJournalEntry.reference_id == expense.id,
        ).all()
        assert len(gl_entries) >= 1, f"Expected >=1 entry, got {len(gl_entries)}"
        total_debit = sum((e.total_debit or 0) for e in gl_entries)
        total_credit = sum((e.total_credit or 0) for e in gl_entries)
        assert total_debit == total_credit == Decimal("250.50"), f"GL: debit={total_debit} credit={total_credit}"
