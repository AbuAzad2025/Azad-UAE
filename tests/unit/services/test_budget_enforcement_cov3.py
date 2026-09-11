"""Coverage boost for services/budget_enforcement.py.

Targets: branch_id filter (tenant-global vs branch-specific budgets),
missing-GL-account fast path. Real check_budget_for_account calls.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal


def _budget(db_session, tenant, account, budgeted="10000", enforcement="hard", branch_id=None):
    from models import Budget, BudgetLine

    budget = Budget(
        tenant_id=tenant.id,
        budget_number=f"BUD-{budgeted}-{enforcement}-{branch_id or 'g'}",
        name_ar="budget",
        fiscal_year=2026,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        total_budgeted=Decimal(budgeted),
        status="active",
        enforcement=enforcement,
        branch_id=branch_id,
    )
    db_session.add(budget)
    db_session.flush()
    db_session.add(
        BudgetLine(tenant_id=tenant.id, budget_id=budget.id, account_id=account.id, budgeted_amount=Decimal(budgeted))
    )
    db_session.flush()
    return budget


def _account(db_session, tenant, code="6510"):
    from models import GLAccount

    acct = GLAccount.query.filter_by(tenant_id=tenant.id, code=code).first()
    if acct is None:
        acct = GLAccount(
            tenant_id=tenant.id,
            code=code,
            name=f"Acct {code}",
            name_ar="حساب",
            type="expense",
            is_active=True,
            is_header=False,
        )
        db_session.add(acct)
        db_session.flush()
    return acct


class TestBranchFilter:
    def test_branch_specific_budget_matched(self, db_session, sample_tenant, sample_branch, sample_gl_accounts):
        from services.budget_enforcement import check_budget_for_account

        acct = _account(db_session, sample_tenant)
        _budget(db_session, sample_tenant, acct, budgeted="1000", branch_id=sample_branch.id)
        result = check_budget_for_account(sample_tenant.id, acct.code, 5000, branch_id=sample_branch.id)
        assert result is not None
        assert result["allowed"] is False

    def test_global_budget_applies_to_branch_query(self, db_session, sample_tenant, sample_branch, sample_gl_accounts):
        from services.budget_enforcement import check_budget_for_account

        acct = _account(db_session, sample_tenant, code="6520")
        _budget(db_session, sample_tenant, acct, budgeted="10000", branch_id=None)
        result = check_budget_for_account(sample_tenant.id, acct.code, 100, branch_id=sample_branch.id)
        assert result is not None
        assert result["allowed"] is True

    def test_other_branch_budget_invisible(self, db_session, sample_tenant, sample_branch, sample_gl_accounts):
        import uuid

        from models import Branch
        from services.budget_enforcement import check_budget_for_account

        acct = _account(db_session, sample_tenant, code="6530")
        other = Branch(
            tenant_id=sample_tenant.id,
            name=f"O {uuid.uuid4().hex[:4]}",
            code=f"OB{uuid.uuid4().hex[:4]}",
            is_active=True,
        )
        db_session.add(other)
        db_session.flush()
        _budget(db_session, sample_tenant, acct, budgeted="1000", branch_id=other.id)
        assert check_budget_for_account(sample_tenant.id, acct.code, 99999, branch_id=sample_branch.id) is None


class TestMissingAccount:
    def test_unknown_code_returns_none(self, db_session, sample_tenant, sample_gl_accounts):
        from models import GLAccount
        from services.budget_enforcement import check_budget_for_account

        acct = _account(db_session, sample_tenant, code="6540")
        _budget(db_session, sample_tenant, acct, budgeted="100")
        assert check_budget_for_account(sample_tenant.id, "NOPE-9999", 10) is None
        assert GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="NOPE-9999").first() is None
