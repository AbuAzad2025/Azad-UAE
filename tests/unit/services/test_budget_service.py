"""Budget service — CRUD workflow and variance report tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from extensions import db
from models import Budget, BudgetLine, GLAccount
from services.budget_service import BudgetService


def _make_account(tenant_id, code, name="Account"):
    acct = GLAccount(
        tenant_id=tenant_id,
        code=code,
        name=name,
        name_ar=name,
        type="expense",
        is_active=True,
        is_header=False,
    )
    db.session.add(acct)
    db.session.flush()
    return acct


class TestBudgetWorkflow:
    def test_approve_budget(self, db_session, sample_tenant, sample_user):
        budget = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-TEST-001",
            name_ar="موازنة تجربة",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="draft",
        )
        db_session.add(budget)
        db_session.flush()

        BudgetService.approve_budget(budget, sample_user)
        assert budget.status == "approved"
        assert budget.approved_by == sample_user.id

    def test_approve_non_draft_raises(self, db_session, sample_tenant, sample_user):
        budget = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-TEST-002",
            name_ar="موازنة 2",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="approved",
        )
        db_session.add(budget)
        db_session.flush()
        with pytest.raises(ValueError):
            BudgetService.approve_budget(budget, sample_user)

    def test_activate_budget(self, db_session, sample_tenant, sample_user):
        budget = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-TEST-003",
            name_ar="موازنة 3",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="approved",
        )
        db_session.add(budget)
        db_session.flush()

        BudgetService.activate_budget(budget)
        assert budget.status == "active"

    def test_close_budget(self, db_session, sample_tenant, sample_user):
        budget = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-TEST-004",
            name_ar="موازنة 4",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="active",
        )
        db_session.add(budget)
        db_session.flush()

        BudgetService.close_budget(budget)
        assert budget.status == "closed"

    def test_delete_draft_budget(self, db_session, sample_tenant, sample_user):
        budget = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-TEST-005",
            name_ar="موازنة 5",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="draft",
        )
        db_session.add(budget)
        db_session.flush()
        bid = budget.id
        BudgetService.delete_budget(budget)
        assert db_session.get(Budget, bid) is None

    def test_delete_active_budget_raises(self, db_session, sample_tenant, sample_user):
        budget = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-TEST-006",
            name_ar="موازنة 6",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="active",
        )
        db_session.add(budget)
        db_session.flush()
        with pytest.raises(ValueError):
            BudgetService.delete_budget(budget)

    def test_recalculate_totals(self, db_session, sample_tenant):
        acct = _make_account(sample_tenant.id, "6500", "Expenses")
        budget = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-TEST-007",
            name_ar="موازنة 7",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="draft",
        )
        db_session.add(budget)
        db_session.flush()

        line = BudgetLine(
            tenant_id=sample_tenant.id,
            budget_id=budget.id,
            account_id=acct.id,
            budgeted_amount=Decimal("5000"),
        )
        db_session.add(line)
        db_session.flush()

        BudgetService._recalculate_totals(budget)
        assert budget.total_budgeted == Decimal("5000")
