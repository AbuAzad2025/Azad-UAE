"""Coverage-4 for services.hr_service — else/except arcs (real paths)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.hr_service import (
    HRService,
    ImmutableRecordError,
    LeaveBalanceService,
    OvertimeService,
    PayrollBatch,
    PayrollEngine,
    PayrollService,
)


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield
        db_session.rollback()


class TestBranchCheck:
    def test_owner_bypasses(self, mocker):
        mocker.patch("services.hr_service.is_global_owner_user", return_value=True)
        HRService._branch_check(MagicMock(), branch_id=999)

    def test_mismatch_raises(self, mocker):
        mocker.patch("services.hr_service.is_global_owner_user", return_value=False)
        mocker.patch("services.hr_service.branch_scope_id_for", return_value=1)
        with pytest.raises(ValueError):
            HRService._branch_check(MagicMock(), branch_id=2)

    def test_match_passes(self, mocker):
        mocker.patch("services.hr_service.is_global_owner_user", return_value=False)
        mocker.patch("services.hr_service.branch_scope_id_for", return_value=1)
        HRService._branch_check(MagicMock(), branch_id=1)


class TestPayrollEngineMath:
    def test_compute_daily_rate_paths(self):
        # daily_rate + days_worked arc
        assert PayrollEngine.compute_net_salary(1000, daily_rate=Decimal("50"), days_worked=10) == Decimal("500.00")
        # raw_basic in (0,31] treated as days arc
        assert PayrollEngine.compute_net_salary(20, daily_rate=Decimal("50")) == Decimal("1000.00")
        # daily_rate without days and big basic -> earned=basic arc
        assert PayrollEngine.compute_net_salary(5000, daily_rate=Decimal("50")) == Decimal("5000.00")
        # no daily rate, zero earned -> rate 0 arc
        assert PayrollEngine.compute_net_salary(0) == Decimal("0.00")

    def test_negative_guard_positive(self):
        out = PayrollEngine.process_with_negative_guard(5000)
        assert out == {"net_salary": Decimal("5000.00"), "clamped": False, "debt": Decimal("0")}

    def test_negative_guard_registers_debt(self, mocker):
        reg = mocker.patch.object(PayrollEngine, "register_employee_debt", return_value={})
        out = PayrollEngine.process_with_negative_guard(
            100, deductions=5000, employee_id=3, tenant_id=1, month=1, year=2026
        )
        assert out["clamped"] is True
        assert out["net_salary"] == Decimal("0")
        reg.assert_called_once()

    def test_negative_guard_no_employee_no_register(self, mocker):
        reg = mocker.patch.object(PayrollEngine, "register_employee_debt")
        out = PayrollEngine.process_with_negative_guard(100, deductions=5000)
        assert out["clamped"] is True
        reg.assert_not_called()

    def test_can_edit_true_false(self):
        assert PayrollEngine.can_edit(SimpleNamespace(status="draft")) is True
        assert PayrollEngine.can_edit(SimpleNamespace(status="approved")) is False

    def test_assert_mutable_raises(self):
        with pytest.raises(ImmutableRecordError):
            PayrollEngine.assert_mutable(SimpleNamespace(status="paid"))

    def test_register_debt_shape(self):
        entry = PayrollEngine.register_employee_debt(1, 2, "100.5", 3, 2026)
        assert entry["amount"] == Decimal("100.50")
        assert entry["employee_id"] == 1


class TestPayrollServiceGuards:
    def test_batch_mutable_raises(self):
        with pytest.raises(ImmutableRecordError):
            PayrollService.assert_batch_mutable(SimpleNamespace(status="paid"))

    def test_update_allowances_mutable(self):
        tx = SimpleNamespace(status="draft", allowances=Decimal("0"))
        PayrollService.update_allowances(tx, 150)
        assert tx.allowances == Decimal("150")

    def test_update_allowances_locked_batch(self):
        with pytest.raises(ImmutableRecordError):
            PayrollService.update_allowances(
                SimpleNamespace(status="draft"), 10, batch=SimpleNamespace(status="approved")
            )

    def test_approve_batch_empty_raises(self):
        with pytest.raises(ValueError):
            PayrollService.approve_batch(PayrollBatch([], status="draft"), user_id=1)


class TestLeaveAndOvertime:
    def test_list_departments_no_tid(self, mocker):
        mocker.patch.object(HRService, "_tid", return_value=None)
        assert HRService.list_departments(MagicMock()) == []

    def test_list_active_users_none(self):
        assert HRService.list_active_users(None) == []

    def test_create_department_no_tid(self, mocker):
        mocker.patch.object(HRService, "_tid", return_value=None)
        with pytest.raises(ValueError):
            HRService.create_department({}, MagicMock())

    def test_overtime_approve_reject_wrong_state(self):
        with pytest.raises(ValueError):
            OvertimeService.approve_entry(SimpleNamespace(status="approved"), MagicMock(id=1))
        with pytest.raises(ValueError):
            OvertimeService.reject_entry(SimpleNamespace(status="rejected"), MagicMock(id=1), "no")

    def test_overtime_pay_math(self):
        assert OvertimeService.calculate_overtime_pay(2600, 2, 1.5) == Decimal("37.50")

    def test_get_balance_none_and_list_empty(self, mocker):
        from models import LeaveBalance

        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.first.return_value = None
        mock_q.all.return_value = []
        mocker.patch.object(LeaveBalance, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        assert LeaveBalanceService.get_balance(1, 2, 2026) is None
        assert LeaveBalanceService.list_balances(1, 2026) == []

    def test_carry_forward_no_balance(self, mocker):
        from models import LeaveBalance

        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.first.return_value = None
        mocker.patch.object(LeaveBalance, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        assert LeaveBalanceService.carry_forward_leave(1, 2, 2025) is None

    def test_carry_forward_zero_remaining(self, mocker):
        from models import LeaveBalance

        bal = SimpleNamespace(remaining_days=Decimal("0"))
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.first.return_value = bal
        mocker.patch.object(LeaveBalance, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        assert LeaveBalanceService.carry_forward_leave(1, 2, 2025) is None

    def test_unpaid_leave_no_match(self, mocker):
        from models.payroll import EmployeeLeave

        leave = SimpleNamespace(start_date=date(2025, 1, 1), end_date=date(2025, 1, 2), days_taken=2)
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [leave]
        mocker.patch.object(EmployeeLeave, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        assert PayrollEngine.get_unpaid_leave_deduction(SimpleNamespace(id=1), 6, 2026) == 0
