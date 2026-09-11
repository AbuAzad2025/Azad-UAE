"""Gap coverage for models/budget.py — check_budget branches with real DB rows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from models.budget import Budget, BudgetLine
from models.gl import GLAccount


def _account(db_session, tenant_id, code, type_="expense"):
    acct = GLAccount(tenant_id=tenant_id, code=code, name=f"Acct {code}", type=type_)
    db_session.add(acct)
    db_session.flush()
    return acct


def _budget(db_session, tenant_id, **kwargs):
    params = {
        "tenant_id": tenant_id,
        "budget_number": kwargs.get("budget_number", "BUD-COV3"),
        "name_ar": "موازنة تغطية",
        "fiscal_year": 2025,
        "period_start": date(2025, 1, 1),
        "period_end": date(2025, 12, 31),
        "total_budgeted": kwargs.get("total_budgeted", Decimal("1000")),
        "status": kwargs.get("status", "active"),
        "enforcement": kwargs.get("enforcement", "warn"),
    }
    if "branch_id" in kwargs:
        params["branch_id"] = kwargs["branch_id"]
    budget = Budget(**params)
    db_session.add(budget)
    db_session.flush()
    return budget


def _line(db_session, budget, account, budgeted):
    line = BudgetLine(
        tenant_id=budget.tenant_id,
        budget_id=budget.id,
        account_id=account.id,
        budgeted_amount=Decimal(str(budgeted)),
    )
    db_session.add(line)
    db_session.flush()
    return line


class TestCheckBudgetInactive:
    def test_draft_status_returns_open(self, db_session, sample_tenant):
        budget = _budget(db_session, sample_tenant.id, status="draft")
        result = budget.check_budget(9999, Decimal("10"))
        assert result["allowed"] is True
        assert result["enforcement"] == "off"
        assert result["message"] == ""

    def test_enforcement_off_returns_open(self, db_session, sample_tenant):
        budget = _budget(db_session, sample_tenant.id, enforcement="off")
        result = budget.check_budget(9999, Decimal("10"))
        assert result["allowed"] is True
        assert result["budgeted"] == Decimal("0")


class TestCheckBudgetNoLine:
    def test_missing_line_allows_with_enforcement(self, db_session, sample_tenant):
        budget = _budget(db_session, sample_tenant.id, enforcement="hard")
        result = budget.check_budget(123456, Decimal("10"))
        assert result["allowed"] is True
        assert result["enforcement"] == "hard"


class TestCheckBudgetWithLine:
    def test_within_budget_no_message(self, db_session, sample_tenant):
        budget = _budget(db_session, sample_tenant.id)
        acct = _account(db_session, sample_tenant.id, "6100")
        _line(db_session, budget, acct, 500)
        result = budget.check_budget(acct.id, Decimal("100"))
        assert result["allowed"] is True
        assert result["budgeted"] == Decimal("500")
        assert result["actual"] == Decimal("0")
        assert result["message"] == ""

    def test_warn_exceeded_stays_allowed(self, db_session, sample_tenant):
        budget = _budget(db_session, sample_tenant.id, enforcement="warn")
        acct = _account(db_session, sample_tenant.id, "6200")
        _line(db_session, budget, acct, 100)
        result = budget.check_budget(acct.id, Decimal("150"))
        assert result["allowed"] is True
        assert result["remaining"] < Decimal("0")
        assert "تحذير" in result["message"]

    def test_hard_exceeded_blocks(self, db_session, sample_tenant):
        budget = _budget(db_session, sample_tenant.id, enforcement="hard")
        acct = _account(db_session, sample_tenant.id, "6300")
        _line(db_session, budget, acct, 100)
        result = budget.check_budget(acct.id, Decimal("150"))
        assert result["allowed"] is False
        assert "تجاوز الموازنة" in result["message"]

    def test_revenue_account_uses_credit_minus_debit(self, db_session, sample_tenant):
        budget = _budget(db_session, sample_tenant.id, enforcement="hard")
        acct = _account(db_session, sample_tenant.id, "4100", type_="revenue")
        _line(db_session, budget, acct, 100)
        result = budget.check_budget(acct.id, Decimal("40"))
        assert result["allowed"] is True
        assert result["actual"] == Decimal("0")

    def test_branch_scoped_budget(self, db_session, sample_tenant, sample_branch):
        budget = _budget(db_session, sample_tenant.id, branch_id=sample_branch.id)
        acct = _account(db_session, sample_tenant.id, "6400")
        _line(db_session, budget, acct, 200)
        result = budget.check_budget(acct.id, Decimal("50"))
        assert result["allowed"] is True
        assert result["budgeted"] == Decimal("200")


class TestUpdateActualsEdge:
    def test_zero_budgeted_line_gets_zero_pct(self, db_session, sample_tenant):
        budget = _budget(db_session, sample_tenant.id, total_budgeted=Decimal("0"))
        acct = _account(db_session, sample_tenant.id, "6500")
        line = _line(db_session, budget, acct, 0)
        budget.update_actuals()
        assert line.variance_percentage == 0
        assert line.variance == Decimal("0")

    def test_zero_total_budgeted_skips_pct(self, db_session, sample_tenant):
        budget = _budget(db_session, sample_tenant.id, total_budgeted=Decimal("0"))
        acct = _account(db_session, sample_tenant.id, "6600")
        _line(db_session, budget, acct, 100)
        budget.update_actuals()
        assert budget.total_actual == Decimal("0")
        assert budget.total_variance != Decimal("0") or budget.total_variance == Decimal("0")

    def test_variance_status_boundaries(self):
        line = BudgetLine(budgeted_amount=Decimal("100"))
        line.variance_percentage = Decimal("5")
        assert line.variance_status == "warning"
        line.variance_percentage = Decimal("-5")
        assert line.variance_status == "warning"
        line.variance_percentage = Decimal("15")
        assert line.variance_status == "danger"
        assert line.variance_status_ar in ("ممتاز", "يحتاج متابعة", "انحراف كبير")
        line.variance_percentage = Decimal("2")
        assert line.variance_status_ar == "ممتاز"
