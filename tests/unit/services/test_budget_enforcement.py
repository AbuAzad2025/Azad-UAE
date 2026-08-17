"""Budget enforcement — check_budget and integration tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from models import Budget, BudgetLine, GLAccount
from services.budget_enforcement import check_budget_for_account


def _make_budget(db_session, sample_tenant, account, budgeted=Decimal("10000"), enforcement="hard", branch_id=None):
    budget = Budget(
        tenant_id=sample_tenant.id,
        budget_number="BUD-2026-001",
        name_ar="موازنة 2026",
        fiscal_year=2026,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        total_budgeted=budgeted,
        status="active",
        enforcement=enforcement,
        branch_id=branch_id,
    )
    db_session.add(budget)
    db_session.flush()

    line = BudgetLine(
        tenant_id=sample_tenant.id,
        budget_id=budget.id,
        account_id=account.id,
        budgeted_amount=budgeted,
    )
    db_session.add(line)
    db_session.flush()
    return budget


class TestCheckBudget:
    def test_no_active_budget_returns_none(self, db_session, sample_tenant, sample_gl_accounts):
        result = check_budget_for_account(sample_tenant.id, "6500", 500)
        assert result is None

    def test_hard_enforcement_blocks_overrun(self, db_session, sample_tenant, sample_gl_accounts):
        acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="6500").first()
        if not acct:
            acct = GLAccount(
                tenant_id=sample_tenant.id,
                code="6500",
                name="Misc Expenses",
                name_ar="مصروفات متنوعة",
                type="expense",
                is_active=True,
                is_header=False,
            )
            db_session.add(acct)
            db_session.flush()

        _make_budget(db_session, sample_tenant, acct, budgeted=Decimal("5000"), enforcement="hard")

        result = check_budget_for_account(sample_tenant.id, "6500", 6000)
        assert result is not None
        assert result["allowed"] is False
        assert result["enforcement"] == "hard"

    def test_hard_enforcement_allows_within_budget(self, db_session, sample_tenant, sample_gl_accounts):
        acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="6500").first()
        if not acct:
            acct = GLAccount(
                tenant_id=sample_tenant.id,
                code="6500",
                name="Misc Expenses",
                name_ar="مصروفات متنوعة",
                type="expense",
                is_active=True,
                is_header=False,
            )
            db_session.add(acct)
            db_session.flush()

        _make_budget(db_session, sample_tenant, acct, budgeted=Decimal("10000"), enforcement="hard")

        result = check_budget_for_account(sample_tenant.id, "6500", 2000)
        assert result is not None
        assert result["allowed"] is True

    def test_warn_enforcement_allows_with_warning(self, db_session, sample_tenant, sample_gl_accounts):
        acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="6500").first()
        if not acct:
            acct = GLAccount(
                tenant_id=sample_tenant.id,
                code="6500",
                name="Misc Expenses",
                name_ar="مصروفات متنوعة",
                type="expense",
                is_active=True,
                is_header=False,
            )
            db_session.add(acct)
            db_session.flush()

        _make_budget(db_session, sample_tenant, acct, budgeted=Decimal("3000"), enforcement="warn")

        result = check_budget_for_account(sample_tenant.id, "6500", 5000)
        assert result is not None
        assert result["allowed"] is True
        assert "تحذير" in result["message"]

    def test_budget_model_check_budget_method(self, db_session, sample_tenant, sample_gl_accounts):
        acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="6500").first()
        if not acct:
            acct = GLAccount(
                tenant_id=sample_tenant.id,
                code="6500",
                name="Misc Expenses",
                name_ar="مصروفات متنوعة",
                type="expense",
                is_active=True,
                is_header=False,
            )
            db_session.add(acct)
            db_session.flush()

        budget = _make_budget(db_session, sample_tenant, acct, budgeted=Decimal("8000"), enforcement="hard")
        result = budget.check_budget(acct.id, Decimal("1000"))
        assert result["allowed"] is True
        assert result["budgeted"] == Decimal("8000")
        assert result["enforcement"] == "hard"

    def test_draft_budget_returns_allowed(self, db_session, sample_tenant, sample_gl_accounts):
        acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="6500").first()
        if not acct:
            acct = GLAccount(
                tenant_id=sample_tenant.id,
                code="6500",
                name="Misc Expenses",
                name_ar="مصروفات متنوعة",
                type="expense",
                is_active=True,
                is_header=False,
            )
            db_session.add(acct)
            db_session.flush()

        budget = _make_budget(db_session, sample_tenant, acct, budgeted=Decimal("1000"))
        budget.status = "draft"
        db_session.flush()

        result = check_budget_for_account(sample_tenant.id, "6500", 99999)
        assert result is None
