from __future__ import annotations

from datetime import datetime, timezone, date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from extensions import db
from models import Attendance, Department, LeaveRequest, LeaveType
from services.hr_service import HRService, PayrollService, PayrollBatch, ImmutableRecordError


def _user(tenant_id=1, user_id=1, branch_id=1, is_owner=False):
    user = MagicMock()
    user.id = user_id
    user.tenant_id = tenant_id
    user.branch_id = branch_id
    user.is_owner = is_owner
    return user


@pytest.fixture
def hr_user(sample_user):
    return sample_user


@pytest.fixture
def leave_type(db_session, sample_tenant):
    lt = LeaveType(
        tenant_id=sample_tenant.id,
        name='Annual',
        name_ar='سنوية',
        days_per_year=30,
    )
    db_session.add(lt)
    db_session.flush()
    return lt


class TestBranchCheck:
    def test_branch_mismatch_raises(self, mocker):
        user = _user(branch_id=1)
        mocker.patch('services.hr_service.is_global_owner_user', return_value=False)
        mocker.patch('services.hr_service.branch_scope_id_for', return_value=2)
        with pytest.raises(ValueError, match='فرع آخر'):
            HRService._branch_check(user, branch_id=1)

    def test_global_owner_skips_check(self, mocker):
        user = _user(branch_id=1)
        mocker.patch('services.hr_service.is_global_owner_user', return_value=True)
        HRService._branch_check(user, branch_id=99)


class TestClockInOut:
    def test_clock_in_creates_attendance(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        att = HRService.clock_in(hr_user)
        assert att.user_id == hr_user.id
        assert att.check_out is None
        assert att.state == 'draft'

    def test_clock_in_duplicate_raises(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        HRService.clock_in(hr_user)
        with pytest.raises(ValueError, match='مفتوح'):
            HRService.clock_in(hr_user)

    def test_clock_in_with_branch(self, db_session, hr_user, sample_tenant, sample_branch, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        mocker.patch('services.hr_service.is_global_owner_user', return_value=True)
        att = HRService.clock_in(hr_user, branch_id=sample_branch.id)
        assert att.branch_id == sample_branch.id

    def test_clock_out_completes_session(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        HRService.clock_in(hr_user)
        att = HRService.clock_out(hr_user)
        assert att.check_out is not None
        assert att.state == 'validated'
        assert att.work_hours is not None

    def test_clock_out_without_session_raises(self, hr_user):
        with pytest.raises(ValueError, match='لا يوجد'):
            HRService.clock_out(hr_user)

    def test_clock_out_naive_check_in(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        att = Attendance(
            tenant_id=sample_tenant.id,
            user_id=hr_user.id,
            check_in=datetime.now().replace(tzinfo=None),
            state='draft',
        )
        db_session.add(att)
        db_session.commit()
        result = HRService.clock_out(hr_user)
        assert result.work_hours is not None


class TestAttendanceQueries:
    def test_get_attendance_filters(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        att = Attendance(
            tenant_id=sample_tenant.id,
            user_id=hr_user.id,
            check_in=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            state='validated',
        )
        db_session.add(att)
        db_session.commit()
        records = HRService.get_attendance(hr_user, date_from='2026-06-01', date_to='2026-06-30')
        assert len(records) >= 1

    def test_report_attendance_branch_scope(self, db_session, hr_user, sample_tenant, sample_branch, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        mocker.patch('services.hr_service.is_global_owner_user', return_value=False)
        mocker.patch('services.hr_service.branch_scope_id_for', return_value=sample_branch.id)
        att = Attendance(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            user_id=hr_user.id,
            check_in=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        )
        db_session.add(att)
        db_session.commit()
        records = HRService.report_attendance({'user_id': hr_user.id}, hr_user)
        assert len(records) >= 1


class TestLeaveWorkflow:
    def test_request_leave_success(self, db_session, hr_user, sample_tenant, leave_type, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        leave = HRService.request_leave({
            'leave_type_id': leave_type.id,
            'date_from': '2026-07-01',
            'date_to': '2026-07-05',
            'reason': 'vacation',
        }, hr_user)
        assert leave.duration == Decimal('5')
        assert leave.state == 'draft'

    def test_request_leave_missing_type(self, hr_user, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=1)
        with pytest.raises(ValueError, match='نوع الإجازة'):
            HRService.request_leave({'date_from': '2026-07-01', 'date_to': '2026-07-05'}, hr_user)

    def test_request_leave_invalid_dates(self, hr_user, leave_type, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=1)
        with pytest.raises(ValueError, match='تاريخ النهاية'):
            HRService.request_leave({
                'leave_type_id': leave_type.id,
                'date_from': '2026-07-10',
                'date_to': '2026-07-01',
            }, hr_user)

    def test_request_leave_wrong_tenant_type(self, db_session, hr_user, sample_tenant, mocker):
        from models import Tenant

        other_tenant = Tenant(
            name='Other Co',
            name_ar='أخرى',
            slug='other-co-hr-test',
            email='other@hr.test',
            country='AE',
            is_active=True,
        )
        db_session.add(other_tenant)
        db_session.flush()
        other_lt = LeaveType(tenant_id=other_tenant.id, name='Other')
        db_session.add(other_lt)
        db_session.flush()
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        with pytest.raises(ValueError, match='غير صالح'):
            HRService.request_leave({
                'leave_type_id': other_lt.id,
                'date_from': '2026-07-01',
                'date_to': '2026-07-02',
            }, hr_user)

    def test_approve_leave(self, db_session, hr_user, sample_tenant, leave_type, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        leave = HRService.request_leave({
            'leave_type_id': leave_type.id,
            'date_from': '2026-08-01',
            'date_to': '2026-08-02',
        }, hr_user)
        manager = _user(user_id=2)
        approved = HRService.approve_leave(leave.id, manager)
        assert approved.state == 'approved'
        assert approved.manager_id == manager.id

    def test_approve_non_draft_raises(self, db_session, hr_user, sample_tenant, leave_type, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        leave = HRService.request_leave({
            'leave_type_id': leave_type.id,
            'date_from': '2026-08-10',
            'date_to': '2026-08-11',
        }, hr_user)
        HRService.approve_leave(leave.id, _user(user_id=2))
        with pytest.raises(ValueError, match='المسودة'):
            HRService.approve_leave(leave.id, _user(user_id=2))

    def test_refuse_leave(self, db_session, hr_user, sample_tenant, leave_type, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        leave = HRService.request_leave({
            'leave_type_id': leave_type.id,
            'date_from': '2026-09-01',
            'date_to': '2026-09-02',
        }, hr_user)
        refused = HRService.refuse_leave(leave.id, _user(user_id=2), reason='busy')
        assert refused.state == 'refused'
        assert refused.rejected_reason == 'busy'

    def test_list_leaves(self, db_session, hr_user, sample_tenant, leave_type, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        HRService.request_leave({
            'leave_type_id': leave_type.id,
            'date_from': '2026-10-01',
            'date_to': '2026-10-02',
        }, hr_user)
        leaves = HRService.list_leaves({'state': 'draft'}, hr_user)
        assert len(leaves) >= 1


class TestDepartmentsAndContracts:
    def test_create_department(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        dept = HRService.create_department({'name': 'Engineering', 'name_ar': 'هندسة'}, hr_user)
        assert dept.name == 'Engineering'

    def test_create_department_no_tenant(self, hr_user, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=None)
        with pytest.raises(ValueError, match='شركة نشطة'):
            HRService.create_department({'name': 'X'}, hr_user)

    def test_list_departments(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        HRService.create_department({'name': 'Sales'}, hr_user)
        depts = HRService.list_departments(hr_user)
        assert len(depts) >= 1

    def test_list_departments_no_tenant(self, hr_user, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=None)
        assert HRService.list_departments(hr_user) == []

    def test_create_contract(self, db_session, hr_user, sample_tenant, sample_branch, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        mocker.patch('services.hr_service.is_global_owner_user', return_value=True)
        contract = HRService.create_contract({
            'user_id': hr_user.id,
            'branch_id': sample_branch.id,
            'date_start': '2026-01-01',
            'wage': '5000',
        }, hr_user)
        assert contract.wage == Decimal('5000')


class TestPayrollApproveBatch:
    def test_approve_empty_batch_raises(self, app):
        batch = PayrollBatch([], status='draft', tenant_id=1, branch_id=1, month=6, year=2026)
        with app.app_context():
            with pytest.raises(ValueError, match='لا توجد معاملات'):
                PayrollService.approve_batch(batch, user_id=1)

    def test_approve_batch_posts_gl(self, app, sample_tenant, sample_branch, sample_gl_accounts, mocker):
        tx = MagicMock()
        tx.id = 10
        tx.status = 'draft'
        tx.basic_amount = Decimal('5000')
        tx.allowances = Decimal('500')
        tx.deductions = Decimal('300')
        tx.net_salary = Decimal('5200')
        batch = PayrollBatch(
            [tx], status='draft',
            tenant_id=sample_tenant.id, branch_id=sample_branch.id,
            month=6, year=2026,
        )
        entry = MagicMock(id=55)
        mocker.patch('services.gl_posting.post_or_fail', return_value=entry)
        with app.app_context():
            result = PayrollService.approve_batch(batch, user_id=1)
        assert result.id == 55
        assert batch.status == 'approved'
        assert tx.status == 'approved'
        assert tx.gl_entry_id == 55

    def test_approve_batch_with_deductions_line(self, app, sample_tenant, sample_branch, sample_gl_accounts, mocker):
        tx = MagicMock()
        tx.id = 11
        tx.status = 'draft'
        tx.basic_amount = Decimal('4000')
        tx.allowances = Decimal('0')
        tx.deductions = Decimal('500')
        tx.net_salary = Decimal('3500')
        batch = PayrollBatch(
            [tx], status='draft',
            tenant_id=sample_tenant.id, branch_id=sample_branch.id,
            month=7, year=2026,
        )
        post = mocker.patch('services.gl_posting.post_or_fail', return_value=MagicMock(id=56))
        with app.app_context():
            PayrollService.approve_batch(batch, user_id=1)
        lines = post.call_args[0][0]
        assert len(lines) == 3


class TestPayrollEngineInService:
    def test_compute_net_with_days_worked(self):
        from services.hr_service import PayrollEngine
        net = PayrollEngine.compute_net_salary(
            Decimal('0'), daily_rate=Decimal('100'), days_worked=20,
        )
        assert net == Decimal('2000.00')

    def test_register_employee_debt(self):
        from services.hr_service import PayrollEngine
        PayrollEngine._debt_registry.clear()
        entry = PayrollEngine.register_employee_debt(5, 1, Decimal('50'), 6, 2026)
        assert entry['amount'] == Decimal('50.00')

    def test_assert_batch_mutable_locked(self):
        from services.hr_service import PayrollService, PayrollBatch, ImmutableRecordError
        batch = PayrollBatch([], status='paid')
        with pytest.raises(ImmutableRecordError):
            PayrollService.assert_batch_mutable(batch)

    def test_delete_transaction_without_batch(self, app, mocker):
        from services.hr_service import PayrollService
        tx = MagicMock(status='draft')
        delete_mock = mocker.patch('services.hr_service.db.session.delete')
        with app.app_context():
            PayrollService.delete_transaction(tx)
        delete_mock.assert_called_once_with(tx)

    def test_update_allowances_without_batch(self, app):
        from services.hr_service import PayrollService
        tx = MagicMock(status='draft')
        with app.app_context():
            PayrollService.update_allowances(tx, Decimal('300'))
        assert tx.allowances == Decimal('300')


class TestHrEdgeCases:
    def test_request_leave_no_tenant_non_owner(self, hr_user, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=None)
        mocker.patch('services.hr_service.is_global_owner_user', return_value=False)
        with pytest.raises(ValueError, match='شركة نشطة'):
            HRService.request_leave({
                'leave_type_id': 1,
                'date_from': '2026-07-01',
                'date_to': '2026-07-02',
            }, hr_user)

    def test_approve_leave_not_found(self):
        with pytest.raises(ValueError, match='غير موجود'):
            HRService.approve_leave(99999, _user(user_id=2))

    def test_refuse_leave_not_found(self):
        with pytest.raises(ValueError, match='غير موجود'):
            HRService.refuse_leave(99999, _user(user_id=2))

    def test_refuse_non_draft_raises(self, db_session, hr_user, sample_tenant, leave_type, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        leave = HRService.request_leave({
            'leave_type_id': leave_type.id,
            'date_from': '2026-11-01',
            'date_to': '2026-11-02',
        }, hr_user)
        HRService.refuse_leave(leave.id, _user(user_id=2))
        with pytest.raises(ValueError, match='المسودة'):
            HRService.refuse_leave(leave.id, _user(user_id=2))

    def test_report_attendance_date_filters(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        mocker.patch('services.hr_service.is_global_owner_user', return_value=True)
        records = HRService.report_attendance({
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        }, hr_user)
        assert isinstance(records, list)

    def test_list_leaves_user_filter(self, db_session, hr_user, sample_tenant, leave_type, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        HRService.request_leave({
            'leave_type_id': leave_type.id,
            'date_from': '2026-12-01',
            'date_to': '2026-12-02',
        }, hr_user)
        leaves = HRService.list_leaves({'user_id': hr_user.id}, hr_user)
        assert len(leaves) >= 1

    def test_create_contract_no_active_tenant(self, hr_user, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=None)
        with pytest.raises(ValueError, match='لا توجد شركة نشطة'):
            HRService.create_contract({'user_id': hr_user.id}, hr_user)

    def test_create_contract_defaults(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        mocker.patch('services.hr_service.is_global_owner_user', return_value=True)
        contract = HRService.create_contract({
            'user_id': hr_user.id,
            'department_id': None,
            'job_id': None,
        }, hr_user)
        assert contract.state == 'draft'

    def test_get_unpaid_leave_deduction_integration(self, mocker):
        from services.hr_service import PayrollEngine
        leave = MagicMock()
        leave.leave_type = 'unpaid'
        leave.status = 'approved'
        leave.start_date = MagicMock(year=2026, month=6)
        leave.end_date = MagicMock(year=2026, month=6)
        leave.days_taken = 3
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [leave]
        mocker.patch('models.payroll.EmployeeLeave.query', mock_q)
        employee = MagicMock(id=9)
        assert PayrollEngine.get_unpaid_leave_deduction(employee, 6, 2026) == 3

    def test_process_negative_guard_no_employee_id(self):
        from services.hr_service import PayrollEngine
        r = PayrollEngine.process_with_negative_guard(Decimal('100'), Decimal('0'), Decimal('500'))
        assert r['clamped'] is True
        assert r['debt'] == Decimal('400.00')


class TestHrServiceCommitRollbackPaths:
    def test_clock_in_commit_failure(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        mocker.patch.object(db.session, 'commit', side_effect=RuntimeError('commit failed'))
        rollback = mocker.patch.object(db.session, 'rollback')
        with pytest.raises(RuntimeError, match='commit failed'):
            HRService.clock_in(hr_user)
        rollback.assert_called_once()

    def test_clock_out_commit_failure(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        HRService.clock_in(hr_user)
        mocker.patch.object(db.session, 'commit', side_effect=RuntimeError('commit failed'))
        rollback = mocker.patch.object(db.session, 'rollback')
        with pytest.raises(RuntimeError, match='commit failed'):
            HRService.clock_out(hr_user)
        rollback.assert_called_once()

    def test_request_leave_commit_failure(self, db_session, hr_user, sample_tenant, leave_type, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        mocker.patch.object(db.session, 'commit', side_effect=RuntimeError('commit failed'))
        rollback = mocker.patch.object(db.session, 'rollback')
        with pytest.raises(RuntimeError, match='commit failed'):
            HRService.request_leave({
                'leave_type_id': leave_type.id,
                'date_from': '2026-07-01',
                'date_to': '2026-07-02',
            }, hr_user)
        rollback.assert_called_once()

    def test_approve_leave_commit_failure(self, db_session, hr_user, sample_tenant, leave_type, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        leave = HRService.request_leave({
            'leave_type_id': leave_type.id,
            'date_from': '2026-08-01',
            'date_to': '2026-08-02',
        }, hr_user)
        mocker.patch.object(db.session, 'commit', side_effect=RuntimeError('commit failed'))
        rollback = mocker.patch.object(db.session, 'rollback')
        with pytest.raises(RuntimeError, match='commit failed'):
            HRService.approve_leave(leave.id, _user(user_id=2))
        rollback.assert_called_once()

    def test_refuse_leave_commit_failure(self, db_session, hr_user, sample_tenant, leave_type, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        leave = HRService.request_leave({
            'leave_type_id': leave_type.id,
            'date_from': '2026-09-01',
            'date_to': '2026-09-02',
        }, hr_user)
        mocker.patch.object(db.session, 'commit', side_effect=RuntimeError('commit failed'))
        rollback = mocker.patch.object(db.session, 'rollback')
        with pytest.raises(RuntimeError, match='commit failed'):
            HRService.refuse_leave(leave.id, _user(user_id=2), reason='no')
        rollback.assert_called_once()

    def test_create_department_commit_failure(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        mocker.patch.object(db.session, 'commit', side_effect=RuntimeError('commit failed'))
        rollback = mocker.patch.object(db.session, 'rollback')
        with pytest.raises(RuntimeError, match='commit failed'):
            HRService.create_department({'name': 'Fail Dept'}, hr_user)
        rollback.assert_called_once()

    def test_create_contract_commit_failure(self, db_session, hr_user, sample_tenant, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        mocker.patch('services.hr_service.is_global_owner_user', return_value=True)
        mocker.patch.object(db.session, 'commit', side_effect=RuntimeError('commit failed'))
        rollback = mocker.patch.object(db.session, 'rollback')
        with pytest.raises(RuntimeError, match='commit failed'):
            HRService.create_contract({'user_id': hr_user.id}, hr_user)
        rollback.assert_called_once()


class TestPayrollEngineCoverageGaps:
    def test_assert_mutable_raises(self):
        from services.hr_service import PayrollEngine, ImmutableRecordError
        tx = MagicMock(status='approved')
        with pytest.raises(ImmutableRecordError):
            PayrollEngine.assert_mutable(tx)

    def test_compute_net_daily_rate_days_worked_and_basic_as_days(self):
        from services.hr_service import PayrollEngine
        assert PayrollEngine.compute_net_salary(
            Decimal('0'), daily_rate=Decimal('100'), days_worked=15,
        ) == Decimal('1500.00')
        assert PayrollEngine.compute_net_salary(
            Decimal('20'), daily_rate=Decimal('50'),
        ) == Decimal('1000.00')
        assert PayrollEngine.compute_net_salary(
            Decimal('5000'), daily_rate=Decimal('50'),
        ) == Decimal('5000.00')

    def test_process_negative_guard_positive_net(self):
        from services.hr_service import PayrollEngine
        PayrollEngine._debt_registry.clear()
        r = PayrollEngine.process_with_negative_guard(Decimal('1000'), Decimal('100'))
        assert r['clamped'] is False
        assert r['net_salary'] == Decimal('1100.00')

    def test_process_negative_guard_registers_debt(self):
        from services.hr_service import PayrollEngine
        PayrollEngine._debt_registry.clear()
        r = PayrollEngine.process_with_negative_guard(
            Decimal('100'), deductions=Decimal('500'),
            employee_id=7, tenant_id=1, month=6, year=2026, convert_to_debt=True,
        )
        assert r['clamped'] is True
        assert len(PayrollEngine._debt_registry) == 1

    def test_can_edit_locked_returns_false(self):
        from services.hr_service import PayrollEngine
        tx = MagicMock(status='paid')
        assert PayrollEngine.can_edit(tx) is False

    def test_can_edit_mutable_returns_true(self):
        from services.hr_service import PayrollEngine
        tx = MagicMock(status='draft')
        assert PayrollEngine.can_edit(tx) is True

    def test_unpaid_leave_deduction_end_date_month(self, mocker):
        from services.hr_service import PayrollEngine
        leave = MagicMock()
        leave.leave_type = 'unpaid'
        leave.status = 'approved'
        leave.start_date = MagicMock(year=2026, month=5)
        leave.end_date = MagicMock(year=2026, month=6)
        leave.days_taken = 2
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [leave]
        mocker.patch('models.payroll.EmployeeLeave.query', mock_q)
        assert PayrollEngine.get_unpaid_leave_deduction(MagicMock(id=1), 6, 2026) == 2

    def test_update_allowances_locked_batch_raises(self):
        from services.hr_service import PayrollService, PayrollBatch, ImmutableRecordError
        batch = PayrollBatch([], status='approved')
        tx = MagicMock(status='draft')
        with pytest.raises(ImmutableRecordError):
            PayrollService.update_allowances(tx, Decimal('1'), batch=batch)

    def test_delete_transaction_locked_batch_raises(self):
        from services.hr_service import PayrollService, PayrollBatch, ImmutableRecordError
        batch = PayrollBatch([], status='paid')
        tx = MagicMock(status='draft')
        with pytest.raises(ImmutableRecordError):
            PayrollService.delete_transaction(tx, batch=batch)

    def test_compute_net_basic_as_days(self):
        from services.hr_service import PayrollEngine
        net = PayrollEngine.compute_net_salary(Decimal('20'), daily_rate=Decimal('50'))
        assert net == Decimal('1000.00')


