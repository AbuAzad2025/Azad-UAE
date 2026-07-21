from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from models import Employee, PayrollTransaction, SalaryAdvance
from services.payroll_service import PayrollService


def _employee(db_session, sample_branch, sample_tenant, **kwargs):
    emp = Employee(
        name=kwargs.get("name", "Ali"),
        name_ar=kwargs.get("name_ar", "علي"),
        branch_id=sample_branch.id,
        tenant_id=sample_tenant.id,
        basic_salary=Decimal(kwargs.get("basic_salary", "5000")),
        employment_type=kwargs.get("employment_type", "salary"),
        is_active=True,
    )
    db_session.add(emp)
    db_session.flush()
    return emp


class TestBranchTenantHelpers:
    def test_branch_tenant_id_missing_branch(self, db_session):
        with pytest.raises(ValueError, match="الفرع"):
            PayrollService._branch_tenant_id(999999)

    def test_branch_tenant_id_no_tenant(self, db_session):
        branch = MagicMock(tenant_id=None)
        with patch("services.payroll_service.db.session.get", return_value=branch):
            with pytest.raises(ValueError, match="شركة"):
                PayrollService._branch_tenant_id(1)

    def test_require_employee_tenant_id_missing(self):
        emp = MagicMock(tenant_id=None)
        with pytest.raises(ValueError, match="شركة"):
            PayrollService._require_employee_tenant_id(emp)


class TestCreateEmployee:
    def test_create_employee_success(self, db_session, sample_branch, sample_tenant):
        emp = PayrollService.create_employee(
            {
                "name": "Sara",
                "branch_id": sample_branch.id,
                "basic_salary": "4000",
                "joined_date": "2024-03-01",
            }
        )
        assert emp.tenant_id == sample_tenant.id
        assert emp.name == "Sara"

    def test_create_employee_requires_branch(self):
        with pytest.raises(ValueError, match="فرع"):
            PayrollService.create_employee({"name": "X"})

    def test_create_employee_commit_failure(self, db_session, sample_branch):
        with patch("services.payroll_service.db.session.flush", side_effect=RuntimeError("db")):
            with pytest.raises(RuntimeError):
                PayrollService.create_employee(
                    {
                        "name": "Fail",
                        "branch_id": sample_branch.id,
                        "basic_salary": "1000",
                    }
                )


class TestCreateAdvance:
    def test_create_advance_success(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant)
        gl_entry = MagicMock(id=77)
        with (
            patch("services.payroll_service.GLService.ensure_core_accounts"),
            patch(
                "services.payroll_service.GLService.get_default_liquidity_account",
                return_value="1100",
            ),
            patch("services.payroll_service.post_or_fail", return_value=gl_entry),
            patch("services.payroll_service.db.session.flush"),
        ):
            adv = PayrollService.create_advance(emp.id, "500", "loan", user_id=1)
        assert adv.gl_entry_id == 77
        assert adv.tenant_id == sample_tenant.id

    def test_create_advance_branch_scope_denied(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant)
        actor = MagicMock()
        with (
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch(
                "utils.branching.branch_scope_id_for",
                return_value=sample_branch.id + 99,
            ),
        ):
            with pytest.raises(ValueError, match="فرع"):
                PayrollService.create_advance(emp.id, "100", "x", user_id=1, actor_user=actor)

    def test_create_advance_tenant_mismatch(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant)
        actor = MagicMock()
        with (
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.branching.branch_scope_id_for", return_value=None),
            patch(
                "utils.tenanting.get_active_tenant_id",
                return_value=sample_tenant.id + 50,
            ),
        ):
            with pytest.raises(ValueError, match="شركتك"):
                PayrollService.create_advance(emp.id, "100", "x", user_id=1, actor_user=actor)

    def test_create_advance_commit_failure(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant)
        gl_entry = MagicMock(id=1)
        with (
            patch("services.payroll_service.GLService.ensure_core_accounts"),
            patch(
                "services.payroll_service.GLService.get_default_liquidity_account",
                return_value="1100",
            ),
            patch("services.payroll_service.post_or_fail", return_value=gl_entry),
            patch(
                "services.payroll_service.db.session.flush",
                side_effect=RuntimeError("fail"),
            ),
        ):
            with pytest.raises(RuntimeError):
                PayrollService.create_advance(emp.id, "50", "x", user_id=1)


class TestProcessPayroll:
    @staticmethod
    def _run_payroll(emp, **kwargs):
        gl_entry = MagicMock(id=88)
        patches = [
            patch("services.payroll_service.GLService.ensure_core_accounts"),
            patch(
                "services.payroll_service.GLService.get_default_liquidity_account",
                return_value="1100",
            ),
            patch(
                "services.payroll_service.GLService.get_account_code_for_concept",
                return_value="6100",
            ),
            patch("services.payroll_service.post_or_fail", return_value=gl_entry),
            patch("services.payroll_service.PayrollService.post_payroll_accruals"),
            patch("services.payroll_service.db.session.flush"),
        ]
        for p in patches:
            p.start()
        try:
            return PayrollService.process_payroll(
                employee_id=emp.id,
                month=kwargs.get("month", 3),
                year=kwargs.get("year", 2026),
                days_worked=kwargs.get("days_worked", 0),
                allowances=kwargs.get("allowances", 0),
                deductions=kwargs.get("deductions", 0),
                user_id=1,
                actor_user=kwargs.get("actor_user"),
            )
        finally:
            for p in reversed(patches):
                p.stop()

    def test_process_salary_employee(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="6000")
        txn = self._run_payroll(emp)
        assert txn.net_salary == Decimal("6000")
        assert txn.gl_entry_id == 88

    def test_process_daily_employee(self, db_session, sample_branch, sample_tenant):
        emp = _employee(
            db_session,
            sample_branch,
            sample_tenant,
            employment_type="daily",
            basic_salary="100",
        )
        txn = self._run_payroll(emp, days_worked=20)
        assert txn.basic_amount == Decimal("2000")

    def test_process_duplicate_blocked(self, db_session, sample_branch, sample_tenant, sample_user):
        emp = _employee(db_session, sample_branch, sample_tenant)
        existing = PayrollTransaction(
            employee_id=emp.id,
            month=4,
            year=2026,
            basic_amount=Decimal("1"),
            allowances=Decimal("0"),
            deductions=Decimal("0"),
            advances_deducted=Decimal("0"),
            net_salary=Decimal("1"),
            branch_id=sample_branch.id,
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
            status="paid",
        )
        db_session.add(existing)
        db_session.flush()
        with pytest.raises(ValueError, match="تمت معالجة"):
            self._run_payroll(emp, month=4, year=2026)

    def test_process_with_deductions(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="5000")
        txn = self._run_payroll(emp, deductions=200)
        assert txn.deductions == Decimal("200")

    def test_process_negative_net_partial_advance(self, db_session, sample_branch, sample_tenant, sample_user):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="1000")
        adv = SalaryAdvance(
            employee_id=emp.id,
            amount=Decimal("1500"),
            total_amount=Decimal("1500"),
            deducted_amount=Decimal("0"),
            remaining_amount=Decimal("1500"),
            status="approved",
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
        )
        db_session.add(adv)
        db_session.flush()
        txn = self._run_payroll(emp, allowances=0, deductions=0)
        assert txn.net_salary == Decimal("0")
        assert txn.advances_deducted == Decimal("1000")

    def test_process_negative_net_raises(self, db_session, sample_branch, sample_tenant, sample_user):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="100")
        adv = SalaryAdvance(
            employee_id=emp.id,
            amount=Decimal("500"),
            total_amount=Decimal("500"),
            deducted_amount=Decimal("0"),
            remaining_amount=Decimal("0"),
            status="approved",
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
        )
        db_session.add(adv)
        db_session.flush()
        with pytest.raises(ValueError, match="سالب"):
            self._run_payroll(emp, deductions=200)

    def test_process_advance_total_fallback_in_summary(self, db_session, sample_branch, sample_tenant, sample_user):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="3000")
        adv = SalaryAdvance(
            employee_id=emp.id,
            amount=Decimal("400"),
            total_amount=Decimal("400"),
            deducted_amount=Decimal("100"),
            remaining_amount=Decimal("0"),
            is_deducted=False,
            status="approved",
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
        )
        db_session.add(adv)
        db_session.flush()
        txn = self._run_payroll(emp)
        assert txn.advances_deducted == Decimal("300")

    def test_process_clamps_over_deducted_advance_total(self, db_session, sample_branch, sample_tenant, sample_user):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="2000")
        adv = SalaryAdvance(
            employee_id=emp.id,
            amount=Decimal("100"),
            total_amount=Decimal("100"),
            deducted_amount=Decimal("150"),
            remaining_amount=Decimal("0"),
            is_deducted=False,
            status="approved",
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
        )
        db_session.add(adv)
        db_session.flush()
        txn = self._run_payroll(emp)
        assert txn.advances_deducted == Decimal("0")

    def test_process_multiple_advances_stops_when_applied(self, db_session, sample_branch, sample_tenant, sample_user):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="1000")
        adv1 = SalaryAdvance(
            employee_id=emp.id,
            amount=Decimal("600"),
            total_amount=Decimal("600"),
            deducted_amount=Decimal("0"),
            remaining_amount=Decimal("600"),
            status="approved",
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
        )
        adv2 = SalaryAdvance(
            employee_id=emp.id,
            amount=Decimal("500"),
            total_amount=Decimal("500"),
            deducted_amount=Decimal("0"),
            remaining_amount=Decimal("500"),
            status="approved",
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
        )
        adv3 = SalaryAdvance(
            employee_id=emp.id,
            amount=Decimal("100"),
            total_amount=Decimal("100"),
            deducted_amount=Decimal("0"),
            remaining_amount=Decimal("100"),
            status="approved",
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
        )
        db_session.add_all([adv1, adv2, adv3])
        db_session.flush()
        txn = self._run_payroll(emp)
        assert txn.advances_deducted == Decimal("1000")
        assert adv3.is_deducted is False

    def test_process_skips_exhausted_advance_in_distribution(
        self, db_session, sample_branch, sample_tenant, sample_user
    ):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="1000")
        exhausted = SalaryAdvance(
            employee_id=emp.id,
            amount=Decimal("100"),
            total_amount=Decimal("100"),
            deducted_amount=Decimal("100"),
            remaining_amount=Decimal("0"),
            status="approved",
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
        )
        active = SalaryAdvance(
            employee_id=emp.id,
            amount=Decimal("200"),
            total_amount=Decimal("200"),
            deducted_amount=Decimal("0"),
            remaining_amount=Decimal("200"),
            status="approved",
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
        )
        db_session.add_all([exhausted, active])
        db_session.flush()
        txn = self._run_payroll(emp)
        assert txn.advances_deducted == Decimal("200")

    def test_process_actor_branch_denied(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant)
        actor = MagicMock()
        with (
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.branching.branch_scope_id_for", return_value=999),
        ):
            with pytest.raises(ValueError, match="فرع"):
                self._run_payroll(emp, actor_user=actor)

    def test_process_actor_tenant_mismatch(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant)
        actor = MagicMock()
        with (
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.branching.branch_scope_id_for", return_value=None),
            patch(
                "utils.tenanting.get_active_tenant_id",
                return_value=sample_tenant.id + 99,
            ),
        ):
            with pytest.raises(ValueError, match="شركتك"):
                self._run_payroll(emp, actor_user=actor)

    def test_process_advance_fallback_remaining(self, db_session, sample_branch, sample_tenant, sample_user):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="2000")
        adv = SalaryAdvance(
            employee_id=emp.id,
            amount=Decimal("300"),
            total_amount=Decimal("300"),
            deducted_amount=Decimal("100"),
            remaining_amount=Decimal("0"),
            status="approved",
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
        )
        db_session.add(adv)
        db_session.flush()
        txn = self._run_payroll(emp)
        assert txn.advances_deducted == Decimal("200")

    def test_process_advance_fully_deducted_flag(self, db_session, sample_branch, sample_tenant, sample_user):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="500")
        adv = SalaryAdvance(
            employee_id=emp.id,
            amount=Decimal("500"),
            total_amount=Decimal("500"),
            deducted_amount=Decimal("0"),
            remaining_amount=Decimal("500"),
            status="approved",
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
        )
        db_session.add(adv)
        db_session.flush()
        self._run_payroll(emp)
        assert adv.is_deducted is True
        assert adv.fully_deducted_at is not None

    def test_process_commit_failure(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant)
        gl_entry = MagicMock(id=9)
        with (
            patch("services.payroll_service.GLService.ensure_core_accounts"),
            patch(
                "services.payroll_service.GLService.get_default_liquidity_account",
                return_value="1100",
            ),
            patch(
                "services.payroll_service.GLService.get_account_code_for_concept",
                return_value="6100",
            ),
            patch("services.payroll_service.post_or_fail", return_value=gl_entry),
            patch("services.payroll_service.PayrollService.post_payroll_accruals"),
            patch(
                "services.payroll_service.db.session.flush",
                side_effect=RuntimeError("db"),
            ),
        ):
            with pytest.raises(RuntimeError):
                PayrollService.process_payroll(emp.id, 9, 2026, 0, 0, 0, user_id=1)

    def test_process_accrual_warning_logged(self, db_session, sample_branch, sample_tenant, app):
        emp = _employee(db_session, sample_branch, sample_tenant)
        gl_entry = MagicMock(id=5)
        with (
            patch("services.payroll_service.GLService.ensure_core_accounts"),
            patch(
                "services.payroll_service.GLService.get_default_liquidity_account",
                return_value="1100",
            ),
            patch(
                "services.payroll_service.GLService.get_account_code_for_concept",
                return_value="6100",
            ),
            patch("services.payroll_service.post_or_fail", return_value=gl_entry),
            patch(
                "services.payroll_service.PayrollService.post_payroll_accruals",
                side_effect=RuntimeError("accrual"),
            ),
            patch("services.payroll_service.db.session.flush"),
        ):
            txn = PayrollService.process_payroll(emp.id, 5, 2026, 0, 0, 0, user_id=1)
        assert txn.gl_entry_id == 5


class TestAccrualCalculations:
    def test_eos_zero_salary(self):
        assert PayrollService._calculate_eos_monthly_provision(0) == Decimal("0")

    def test_eos_unlimited(self):
        val = PayrollService._calculate_eos_monthly_provision(3000, "unlimited")
        assert val > Decimal("0")

    def test_eos_limited(self):
        val = PayrollService._calculate_eos_monthly_provision(3000, "limited")
        assert val > Decimal("0")

    def test_leave_zero_salary(self):
        assert PayrollService._calculate_leave_monthly_accrual(0) == Decimal("0")

    def test_leave_accrual_positive(self):
        assert PayrollService._calculate_leave_monthly_accrual(2400, 30) > Decimal("0")

    def test_post_payroll_accruals_none_when_zero(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="0")
        assert PayrollService.post_payroll_accruals(emp, 1, 2026, 1) is None

    def test_post_payroll_accruals_posts_lines(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="6000")
        emp.contract_type = "limited"
        emp.annual_leave_days = 30
        gl_entry = MagicMock()
        with (
            patch("services.payroll_service.GLService.ensure_core_accounts"),
            patch(
                "services.payroll_service.GLService.get_account_code_for_concept",
                return_value="6190",
            ),
            patch("services.payroll_service.post_or_fail", return_value=gl_entry) as post,
        ):
            result = PayrollService.post_payroll_accruals(emp, 6, 2026, 1)
        assert result is gl_entry
        assert post.called

    def test_post_payroll_accruals_leave_only(self, db_session, sample_branch, sample_tenant):
        emp = _employee(db_session, sample_branch, sample_tenant, basic_salary="6000")
        gl_entry = MagicMock()
        with (
            patch(
                "services.payroll_service.PayrollService._calculate_eos_monthly_provision",
                return_value=Decimal("0"),
            ),
            patch("services.payroll_service.GLService.ensure_core_accounts"),
            patch(
                "services.payroll_service.GLService.get_account_code_for_concept",
                return_value="6220",
            ),
            patch("services.payroll_service.post_or_fail", return_value=gl_entry),
        ):
            result = PayrollService.post_payroll_accruals(emp, 6, 2026, 1)
        assert result is gl_entry


class TestGenerateBranchPayroll:
    def test_generate_skips_daily_and_existing(self, db_session, sample_branch, sample_tenant, sample_user):
        sal = _employee(db_session, sample_branch, sample_tenant, employment_type="salary")
        _employee(
            db_session,
            sample_branch,
            sample_tenant,
            employment_type="daily",
            name="Daily",
        )
        existing = PayrollTransaction(
            employee_id=sal.id,
            month=7,
            year=2026,
            basic_amount=Decimal("1"),
            allowances=Decimal("0"),
            deductions=Decimal("0"),
            advances_deducted=Decimal("0"),
            net_salary=Decimal("1"),
            branch_id=sample_branch.id,
            tenant_id=sample_tenant.id,
            created_by=sample_user.id,
            status="paid",
        )
        db_session.add(existing)
        db_session.flush()
        with patch("services.payroll_service.PayrollService.process_payroll") as proc:
            generated, skipped = PayrollService.generate_branch_payroll(sample_branch.id, 7, 2026, user_id=1)
        assert generated == 0
        assert skipped >= 2
        proc.assert_not_called()

    def test_generate_processes_salary_employees(self, db_session, sample_branch, sample_tenant):
        _employee(db_session, sample_branch, sample_tenant, name="Pay Me")
        with patch("services.payroll_service.PayrollService.process_payroll") as proc:
            generated, skipped = PayrollService.generate_branch_payroll(sample_branch.id, 8, 2026, user_id=1)
        assert generated == 1
        proc.assert_called_once()
