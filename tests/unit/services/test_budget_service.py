"""Budget service — CRUD workflow and variance report tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from models import Budget, BudgetLine
from services.budget_service import BudgetService
from tests.factories import GLAccountFactory


def _make_account(db_session, tenant, code, name="Account"):
    acct = GLAccountFactory(
        tenant=tenant,
        code=code,
        name=name,
        name_ar=name,
        type="expense",
        is_active=True,
        is_header=False,
    )
    db_session.commit()
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
        acct = _make_account(db_session, sample_tenant, "6500", "Expenses")
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


def _q3(value):
    return Decimal(str(value)).quantize(Decimal("0.001"))


class TestCreateBudget:
    def test_create_budget_with_lines_and_totals(self, db_session, sample_tenant, sample_user, sample_branch):
        _make_account(db_session, sample_tenant, "6200", "Rent")
        _make_account(db_session, sample_tenant, "6100", "Salaries")

        budget = BudgetService.create_budget(
            {
                "name_ar": "موازنة التشغيل",
                "name_en": "Operating Budget",
                "fiscal_year": 2026,
                "period_start": date(2026, 1, 1),
                "period_end": date(2026, 12, 31),
                "enforcement": "hard",
                "branch_id": sample_branch.id,
                "notes": "yearly plan",
                "lines": [
                    {"account_code": "6100", "budgeted_amount": "120000.500", "notes": "payroll"},
                    {"account_code": "6200", "budgeted_amount": "30000.250"},
                ],
            },
            sample_user,
        )

        assert budget.id is not None
        assert budget.status == "draft"
        assert budget.budget_number.startswith("BUD")
        assert budget.enforcement == "hard"
        assert budget.branch_id == sample_branch.id
        assert budget.created_by == sample_user.id
        assert len(budget.lines) == 2
        by_account = {line.account.code: line for line in budget.lines}
        assert by_account["6100"].budgeted_amount == _q3("120000.500")
        assert by_account["6200"].notes is None
        assert budget.total_budgeted == _q3("150000.750")

    def test_create_budget_unknown_account_raises(self, db_session, sample_tenant, sample_user):
        with pytest.raises(ValueError):
            BudgetService.create_budget(
                {
                    "name_ar": "موازنة فاشلة",
                    "fiscal_year": 2026,
                    "period_start": date(2026, 1, 1),
                    "period_end": date(2026, 12, 31),
                    "lines": [{"account_code": "NOPE-999", "budgeted_amount": "100"}],
                },
                sample_user,
            )

    def test_create_budget_defaults(self, db_session, sample_tenant, sample_user):
        budget = BudgetService.create_budget(
            {
                "name_ar": "موازنة افتراضية",
                "fiscal_year": "2027",
                "period_start": date(2027, 1, 1),
                "period_end": date(2027, 12, 31),
            },
            sample_user,
        )
        assert budget.period_type == "annual"
        assert budget.enforcement == "warn"
        assert budget.total_budgeted == Decimal("0.000")


class TestUpdateBudgetRegression:
    """Regression: update_budget previously crashed with item assignment (TypeError)."""

    def test_update_scalar_fields_persisted(self, db_session, sample_tenant, sample_user, sample_branch):
        budget = BudgetService.create_budget(
            {
                "name_ar": "قبل التعديل",
                "fiscal_year": 2026,
                "period_start": date(2026, 1, 1),
                "period_end": date(2026, 12, 31),
            },
            sample_user,
        )
        updated = BudgetService.update_budget(
            budget,
            {
                "name_en": "After Edit",
                "notes": "updated notes",
                "enforcement": "hard",
                "branch_id": sample_branch.id,
            },
        )
        assert updated.name_ar == "قبل التعديل"
        assert updated.name_en == "After Edit"
        assert updated.notes == "updated notes"
        assert updated.enforcement == "hard"
        assert updated.branch_id == sample_branch.id

    def test_update_replaces_lines_and_recalculates(self, db_session, sample_tenant, sample_user):
        _make_account(db_session, sample_tenant, "6300", "Old")
        acct_new = _make_account(db_session, sample_tenant, "6400", "New")

        budget = BudgetService.create_budget(
            {
                "name_ar": "موازنة سطور",
                "fiscal_year": 2026,
                "period_start": date(2026, 1, 1),
                "period_end": date(2026, 12, 31),
                "lines": [{"account_code": "6300", "budgeted_amount": "1000"}],
            },
            sample_user,
        )
        old_line_ids = {line.id for line in budget.lines}

        BudgetService.update_budget(
            budget,
            {"lines": [{"account_code": "6400", "budgeted_amount": "2500.750"}]},
        )
        db_session.flush()

        current_ids = {line.id for line in budget.lines}
        assert current_ids.isdisjoint(old_line_ids)
        assert len(budget.lines) == 1
        assert budget.lines[0].account_id == acct_new.id
        assert budget.total_budgeted == _q3("2500.750")
        remaining = BudgetLine.query.filter_by(id=old_line_ids.pop()).first()
        assert remaining is None

    def test_update_unknown_account_raises(self, db_session, sample_tenant, sample_user):
        budget = BudgetService.create_budget(
            {
                "name_ar": "موازنة",
                "fiscal_year": 2026,
                "period_start": date(2026, 1, 1),
                "period_end": date(2026, 12, 31),
            },
            sample_user,
        )
        with pytest.raises(ValueError):
            BudgetService.update_budget(budget, {"lines": [{"account_code": "GHOST", "budgeted_amount": "1"}]})

    def test_update_non_draft_raises(self, db_session, sample_tenant, sample_user):
        budget = BudgetService.create_budget(
            {
                "name_ar": "موازنة معتمدة",
                "fiscal_year": 2026,
                "period_start": date(2026, 1, 1),
                "period_end": date(2026, 12, 31),
            },
            sample_user,
        )
        BudgetService.approve_budget(budget, sample_user)
        with pytest.raises(ValueError):
            BudgetService.update_budget(budget, {"name_en": "should fail"})


class TestBudgetTransitionsExtra:
    def test_submit_draft_becomes_active(self, db_session, sample_tenant, sample_user):
        budget = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-SUB-001",
            name_ar="موازنة إرسال",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="draft",
        )
        db_session.add(budget)
        db_session.flush()
        result = BudgetService.submit_budget(budget)
        assert result.status == "active"

    def test_submit_non_draft_raises(self, db_session, sample_tenant, sample_user):
        budget = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-SUB-002",
            name_ar="موازنة مرسلة",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="active",
        )
        db_session.add(budget)
        db_session.flush()
        with pytest.raises(ValueError):
            BudgetService.submit_budget(budget)

    def test_activate_closed_raises(self, db_session, sample_tenant, sample_user):
        budget = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-ACT-001",
            name_ar="موازنة مغلقة",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="closed",
        )
        db_session.add(budget)
        db_session.flush()
        with pytest.raises(ValueError):
            BudgetService.activate_budget(budget)


class TestBudgetQueries:
    def test_list_filters(self, db_session, sample_tenant, sample_user, sample_branch):
        b1 = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-LST-001",
            name_ar="نشطة",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="active",
            branch_id=sample_branch.id,
        )
        b2 = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-LST-002",
            name_ar="مسودة 2027",
            fiscal_year=2027,
            period_start=date(2027, 1, 1),
            period_end=date(2027, 12, 31),
            status="draft",
        )
        db_session.add_all([b1, b2])
        db_session.commit()

        active_only = BudgetService.list_budgets(sample_user, filters={"status": "active"})
        assert all(b.status == "active" for b in active_only)
        assert len(active_only) >= 1

        fy = BudgetService.list_budgets(sample_user, filters={"fiscal_year": "2027"})
        assert [b.fiscal_year for b in fy] == [2027]

        br = BudgetService.list_budgets(sample_user, filters={"branch_id": str(sample_branch.id)})
        assert all(b.branch_id == sample_branch.id for b in br)
        assert len(br) >= 1

    def test_get_budget_found_and_missing(self, db_session, sample_tenant, sample_user):
        budget = Budget(
            tenant_id=sample_tenant.id,
            budget_number="BUD-GET-001",
            name_ar="موازنة جلب",
            fiscal_year=2026,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            status="draft",
        )
        db_session.add(budget)
        db_session.commit()

        found = BudgetService.get_budget(budget.id, sample_user)
        assert found.id == budget.id
        with pytest.raises(ValueError):
            BudgetService.get_budget(99999999, sample_user)


class TestVarianceReport:
    def test_variance_report_shape_and_math(self, db_session, sample_tenant, sample_user):
        _make_account(db_session, sample_tenant, "6505", "Marketing")
        budget = BudgetService.create_budget(
            {
                "name_ar": "موازنة انحراف",
                "fiscal_year": 2026,
                "period_start": date(2026, 1, 1),
                "period_end": date(2026, 12, 31),
                "enforcement": "warn",
                "lines": [{"account_code": "6505", "budgeted_amount": "8000"}],
            },
            sample_user,
        )

        report = BudgetService.variance_report(budget.id, sample_user)

        assert report["budget"].id == budget.id
        assert len(report["lines"]) == 1
        line = report["lines"][0]
        assert line["account_code"] == "6505"
        assert line["account_name"] == "Marketing"
        # No GL postings exist in the period: actual is exactly zero.
        assert _q3(line["actual"]) == Decimal("0.000")
        assert _q3(line["budgeted"]) == Decimal("8000")
        assert _q3(line["variance"]) == Decimal("-8000")
        assert _q3(line["variance_percentage"]) == Decimal("-100.00")
        assert line["variance_status"] == "danger"
        assert line["variance_status_ar"] == "انحراف كبير"
        assert _q3(report["total_budgeted"]) == Decimal("8000")
        assert _q3(report["total_actual"]) == Decimal("0")
        assert _q3(report["total_variance"]) == Decimal("-8000")
