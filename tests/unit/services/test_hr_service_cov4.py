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


class TestAttendanceScopingEdges:
    def test_get_attendance_no_tenant_no_dates(self, mocker, db_session):
        mocker.patch.object(HRService, "_tid", return_value=None)
        rows = HRService.get_attendance(MagicMock(id=1))
        assert isinstance(rows, list)

    def test_get_attendance_with_dates(self, mocker, db_session, sample_tenant, sample_user):
        from datetime import datetime

        from models import Attendance

        rec = Attendance(
            tenant_id=sample_tenant.id,
            user_id=sample_user.id,
            check_in=datetime(2026, 6, 15, 9, 0),
            check_out=datetime(2026, 6, 15, 17, 0),
        )
        db_session.add(rec)
        db_session.flush()

        rows = HRService.get_attendance(sample_user, date_from="2026-06-01", date_to="2026-06-30")
        assert any(r.id == rec.id for r in rows)

    def test_report_attendance_no_tid_owner(self, mocker, db_session):
        mocker.patch.object(HRService, "_tid", return_value=None)
        mocker.patch("services.hr_service.is_global_owner_user", return_value=True)
        rows = HRService.report_attendance({}, MagicMock(id=1))
        assert isinstance(rows, list)

    def test_report_attendance_no_tid_unscoped(self, mocker, db_session):
        mocker.patch.object(HRService, "_tid", return_value=None)
        mocker.patch("services.hr_service.is_global_owner_user", return_value=False)
        mocker.patch("services.hr_service.branch_scope_id_for", return_value=None)
        rows = HRService.report_attendance(
            {"user_id": 1, "date_from": "2026-01-01", "date_to": "2026-01-31"}, MagicMock(id=1)
        )
        assert isinstance(rows, list)


class TestLeaveListingEdges:
    def test_list_leaves_no_tid_branch_scope(self, mocker, db_session):
        mocker.patch.object(HRService, "_tid", return_value=None)
        mocker.patch("services.hr_service.is_global_owner_user", return_value=False)
        mocker.patch("services.hr_service.branch_scope_id_for", return_value=7)
        rows = HRService.list_leaves({"state": "draft", "user_id": 1}, MagicMock(id=1))
        assert isinstance(rows, list)

    def test_list_leaves_owner_bypass(self, mocker, db_session):
        mocker.patch.object(HRService, "_tid", return_value=None)
        mocker.patch("services.hr_service.is_global_owner_user", return_value=True)
        rows = HRService.list_leaves({}, MagicMock(id=1))
        assert isinstance(rows, list)


class TestLeaveBalanceRealDb:
    def _leave_type(self, db_session, sample_tenant, days_per_year=21, max_carry_forward=10, suffix="L"):
        from models import LeaveType

        lt = LeaveType(
            tenant_id=sample_tenant.id,
            name=f"{suffix}-type",
            days_per_year=days_per_year,
            max_carry_forward=max_carry_forward,
        )
        db_session.add(lt)
        db_session.flush()
        return lt

    def test_get_or_create_balance_creates_(self, db_session, sample_tenant, sample_user):
        lt = self._leave_type(db_session, sample_tenant, days_per_year=21, max_carry_forward=10)
        bal = LeaveBalanceService.get_or_create_balance(sample_user.id, lt.id, 2026, tenant_id=sample_tenant.id)
        assert bal.entitled_days == 21
        assert bal.remaining_days == 21
        again = LeaveBalanceService.get_or_create_balance(sample_user.id, lt.id, 2026, tenant_id=sample_tenant.id)
        assert again.id == bal.id

    def test_get_or_create_balance_zero_days(self, db_session, sample_tenant, sample_user):
        lt = self._leave_type(db_session, sample_tenant, days_per_year=0, max_carry_forward=0, suffix="Z")
        bal = LeaveBalanceService.get_or_create_balance(sample_user.id, lt.id, 2025, tenant_id=sample_tenant.id)
        assert bal.entitled_days == 0

    def test_accrue_leave_updates_balance(self, db_session, sample_tenant, sample_user):
        lt = self._leave_type(db_session, sample_tenant, days_per_year=21, max_carry_forward=0, suffix="A")
        bal = LeaveBalanceService.accrue_leave(sample_user.id, lt.id, 2026, 3, tenant_id=sample_tenant.id)
        assert bal.taken_days == 3
        assert bal.remaining_days == 18

    def test_carry_forward_leave_caps_at_max(self, db_session, sample_tenant, sample_user):
        lt = self._leave_type(db_session, sample_tenant, days_per_year=21, max_carry_forward=10, suffix="CF")
        LeaveBalanceService.accrue_leave(sample_user.id, lt.id, 2025, 2, tenant_id=sample_tenant.id)
        new_bal = LeaveBalanceService.carry_forward_leave(sample_user.id, lt.id, 2025, tenant_id=sample_tenant.id)
        assert new_bal.year == 2026
        assert new_bal.carried_forward == 10

    def test_carry_forward_leave_without_cap(self, db_session, sample_tenant, sample_user):
        lt = self._leave_type(db_session, sample_tenant, days_per_year=21, max_carry_forward=None, suffix="NC")
        LeaveBalanceService.accrue_leave(sample_user.id, lt.id, 2024, 2, tenant_id=sample_tenant.id)
        new_bal = LeaveBalanceService.carry_forward_leave(sample_user.id, lt.id, 2024, tenant_id=sample_tenant.id)
        assert new_bal.carried_forward == 19

    def test_get_balance_found(self, db_session, sample_tenant, sample_user):
        lt = self._leave_type(db_session, sample_tenant, suffix="G")
        LeaveBalanceService.get_or_create_balance(sample_user.id, lt.id, 2026, tenant_id=sample_tenant.id)
        found = LeaveBalanceService.get_balance(sample_user.id, lt.id, 2026, tenant_id=sample_tenant.id)
        assert found is not None
        assert LeaveBalanceService.list_balances(sample_user.id, 2026, tenant_id=sample_tenant.id)


class TestOvertimeRealDb:
    def _entry_data(self, sample_user, sample_branch, **overrides):
        data = {
            "user_id": sample_user.id,
            "branch_id": sample_branch.id,
            "overtime_date": date(2026, 3, 1),
            "hours": "2",
            "rate_multiplier": "1.5",
            "overtime_type": "weekend",
            "notes": "cov4",
        }
        data.update(overrides)
        return data

    def test_create_approve_reject_list(self, db_session, sample_tenant, sample_user, sample_branch):
        from models import OvertimeEntry

        entry = OvertimeService.create_entry(self._entry_data(sample_user, sample_branch), sample_user)
        assert entry.status == "pending"
        assert isinstance(entry, OvertimeEntry)

        approved = OvertimeService.approve_entry(entry, sample_user)
        assert approved.status == "approved"
        assert approved.approved_by == sample_user.id

        entry2 = OvertimeService.create_entry(
            self._entry_data(sample_user, sample_branch, overtime_date=date(2026, 3, 8)), sample_user
        )
        rejected = OvertimeService.reject_entry(entry2, sample_user, "not needed")
        assert rejected.status == "rejected"
        assert rejected.rejected_reason == "not needed"

        rows = OvertimeService.list_entries(sample_user, {"user_id": sample_user.id, "status": "approved"})
        assert any(e.id == approved.id for e in rows)
        rows_all = OvertimeService.list_entries(sample_user, {})
        assert len(rows_all) >= 2
        rows_dated = OvertimeService.list_entries(sample_user, {"date_from": "2026-03-01", "date_to": "2026-03-31"})
        assert isinstance(rows_dated, list)
        assert LeaveBalanceService._tid(sample_user) is not None

    def test_create_entry_without_branch(self, db_session, sample_tenant, sample_user, sample_branch):
        data = self._entry_data(sample_user, sample_branch)
        data["branch_id"] = None
        entry = OvertimeService.create_entry(data, sample_user)
        assert entry.branch_id is None
        assert entry.rate_multiplier == Decimal("1.5")
