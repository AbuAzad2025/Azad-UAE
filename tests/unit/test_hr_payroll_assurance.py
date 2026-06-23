from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Net Salary Computations — 8 worker scenarios
# ---------------------------------------------------------------------------

class TestNetSalaryComputation:
    """PayrollEngine.compute_net_salary — parametrized across 8 scenarios."""

    @pytest.mark.parametrize('basic,allow,deduct,unpaid,rate,expected', [
        # 1 — Normal salaried employee
        (Decimal('5000'), Decimal('500'), Decimal('300'), 0, None, Decimal('5200.00')),
        # 2 — Heavy unpaid leaves exceeding basic salary
        (Decimal('3000'), Decimal('0'), Decimal('0'), 20, None, Decimal('1000.00')),
        # 3 — Extreme deductions
        (Decimal('4000'), Decimal('0'), Decimal('4500'), 0, None, Decimal('-500.00')),
        # 4 — Zero basic, allowances only
        (Decimal('0'), Decimal('2000'), Decimal('500'), 0, None, Decimal('1500.00')),
        # 5 — Daily wage worker (2.5 days @ 200/day, 2 unpaid days)
        (Decimal('2.5'), Decimal('100'), Decimal('50'), 2, Decimal('200'), Decimal('150.00')),
        # 6 — Unpaid leave with daily_rate overrides
        (Decimal('0'), Decimal('5000'), Decimal('1000'), 5, Decimal('100'), Decimal('3500.00')),
        # 7 — All zero
        (Decimal('0'), Decimal('0'), Decimal('0'), 0, None, Decimal('0.00')),
        # 8 — Deductions exceed gross
        (Decimal('2000'), Decimal('300'), Decimal('3000'), 0, None, Decimal('-700.00')),
    ])
    def test_compute_net_salary(self, basic, allow, deduct, unpaid, rate, expected):
        from services.hr_service import PayrollEngine
        net = PayrollEngine.compute_net_salary(
            basic_salary=basic,
            allowances=allow,
            deductions=deduct,
            unpaid_leave_days=unpaid,
            daily_rate=rate,
        )
        assert net == expected


class TestNetSalaryNegativeGuard:
    """PayrollEngine.process_with_negative_guard — clamping and debt conversion."""

    def test_positive_net_no_clamp(self):
        from services.hr_service import PayrollEngine
        r = PayrollEngine.process_with_negative_guard(Decimal('5000'), Decimal('500'), Decimal('300'))
        assert r['net_salary'] == Decimal('5200.00')
        assert r['clamped'] is False
        assert r['debt'] == Decimal('0')

    def test_negative_net_clamps_to_zero(self):
        from services.hr_service import PayrollEngine
        r = PayrollEngine.process_with_negative_guard(Decimal('2000'), Decimal('0'), Decimal('3000'))
        assert r['net_salary'] == Decimal('0')
        assert r['clamped'] is True
        assert r['debt'] == Decimal('1000.00')

    def test_negative_net_registers_employee_debt(self):
        from services.hr_service import PayrollEngine
        PayrollEngine._debt_registry.clear()
        r = PayrollEngine.process_with_negative_guard(
            Decimal('2000'), Decimal('0'), Decimal('3000'),
            employee_id=42, tenant_id=1, month=6, year=2026,
        )
        assert r['net_salary'] == Decimal('0')
        assert r['debt'] == Decimal('1000.00')
        assert len(PayrollEngine._debt_registry) == 1
        assert PayrollEngine._debt_registry[0]['employee_id'] == 42
        assert PayrollEngine._debt_registry[0]['amount'] == Decimal('1000.00')

    def test_negative_net_converts_to_debt(self):
        from services.hr_service import PayrollEngine
        r = PayrollEngine.process_with_negative_guard(
            Decimal('2000'), Decimal('0'), Decimal('3000'), convert_to_debt=True
        )
        assert r['net_salary'] == Decimal('0')
        assert r['clamped'] is True
        assert r['debt'] == Decimal('1000.00')

    def test_net_zero_no_clamp(self):
        from services.hr_service import PayrollEngine
        r = PayrollEngine.process_with_negative_guard(Decimal('1000'), Decimal('0'), Decimal('1000'))
        assert r['net_salary'] == Decimal('0.00')
        assert r['clamped'] is False
        assert r['debt'] == Decimal('0')

    def test_negative_with_unpaid_leaves_and_debt_conversion(self):
        from services.hr_service import PayrollEngine
        r = PayrollEngine.process_with_negative_guard(
            Decimal('3000'), Decimal('500'), Decimal('1000'), unpaid_leave_days=15, convert_to_debt=True
        )
        # net = 3000 + 500 - 1000 - (3000/30*15) = 2500 - 1500 = 1000
        assert r['net_salary'] == Decimal('1000.00')
        assert r['clamped'] is False
        assert r['debt'] == Decimal('0')

    def test_massive_unpaid_leaves_creates_debt(self):
        from services.hr_service import PayrollEngine
        r = PayrollEngine.process_with_negative_guard(
            Decimal('3000'), Decimal('0'), Decimal('0'), unpaid_leave_days=40, convert_to_debt=True
        )
        # net = 3000 - 0 - 0 - (3000/30*40) = 3000 - 4000 = -1000
        assert r['net_salary'] == Decimal('0')
        assert r['clamped'] is True
        assert r['debt'] == Decimal('1000.00')


# ---------------------------------------------------------------------------
# Immutable Payroll Approval Lock
# ---------------------------------------------------------------------------

class TestImmutablePayrollLock:
    """PayrollEngine.assert_mutable raises ImmutableRecordError for approved/paid."""

    def test_draft_status_allows_edit(self):
        from services.hr_service import PayrollEngine, ImmutableRecordError
        tx = MagicMock()
        tx.status = 'draft'
        PayrollEngine.assert_mutable(tx)

    def test_posted_status_allows_edit(self):
        from services.hr_service import PayrollEngine
        tx = MagicMock()
        tx.status = 'posted'
        PayrollEngine.assert_mutable(tx)

    def test_approved_status_raises(self):
        from services.hr_service import PayrollEngine, ImmutableRecordError
        tx = MagicMock()
        tx.status = 'approved'
        with pytest.raises(ImmutableRecordError, match='لا يمكن تعديل'):
            PayrollEngine.assert_mutable(tx)

    def test_paid_status_raises(self):
        from services.hr_service import PayrollEngine, ImmutableRecordError
        tx = MagicMock()
        tx.status = 'paid'
        with pytest.raises(ImmutableRecordError, match='لا يمكن تعديل'):
            PayrollEngine.assert_mutable(tx)

    def test_can_edit_returns_bool(self):
        from services.hr_service import PayrollEngine
        draft = MagicMock(status='draft')
        approved = MagicMock(status='approved')
        assert PayrollEngine.can_edit(draft) is True
        assert PayrollEngine.can_edit(approved) is False


# ---------------------------------------------------------------------------
# Locked State Modification Attempts
# ---------------------------------------------------------------------------

class TestLockedModificationAttempt:
    """PayrollService blocks allowance edits and deletions on locked batches."""

    def test_allowance_edit_fails_on_approved_batch(self, app):
        from services.hr_service import PayrollService, PayrollBatch, ImmutableRecordError
        tx = MagicMock()
        tx.status = 'draft'
        tx.allowances = Decimal('500')
        batch = PayrollBatch([tx], status='approved', tenant_id=1, branch_id=1, month=6, year=2026)

        with app.app_context():
            with pytest.raises(ImmutableRecordError, match='لا يمكن تعديل دفعة'):
                PayrollService.update_allowances(tx, Decimal('800'), batch=batch)

    def test_delete_fails_on_paid_batch(self, app, mocker):
        from services.hr_service import PayrollService, PayrollBatch, ImmutableRecordError
        tx = MagicMock()
        tx.status = 'draft'
        batch = PayrollBatch([tx], status='paid', tenant_id=1, branch_id=1, month=6, year=2026)
        mocker.patch('services.hr_service.db.session.delete')

        with app.app_context():
            with pytest.raises(ImmutableRecordError, match='لا يمكن تعديل دفعة'):
                PayrollService.delete_transaction(tx, batch=batch)

    def test_draft_batch_allows_allowance_edit(self, app):
        from services.hr_service import PayrollService, PayrollBatch
        tx = MagicMock()
        tx.status = 'draft'
        batch = PayrollBatch([tx], status='draft', tenant_id=1, branch_id=1, month=6, year=2026)

        with app.app_context():
            PayrollService.update_allowances(tx, Decimal('1200'), batch=batch)

        assert tx.allowances == Decimal('1200')

    def test_locked_transaction_blocks_direct_edit(self, app):
        from services.hr_service import PayrollService, ImmutableRecordError
        tx = MagicMock()
        tx.status = 'approved'

        with app.app_context():
            with pytest.raises(ImmutableRecordError, match='لا يمكن تعديل معاملة'):
                PayrollService.update_allowances(tx, Decimal('100'))


# ---------------------------------------------------------------------------
# Unpaid Leave Deduction Lookup
# ---------------------------------------------------------------------------

class TestUnpaidLeaveDeduction:
    """PayrollEngine.get_unpaid_leave_deduction — leave query logic."""

    def test_no_unpaid_leaves(self, mocker):
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = []
        mocker.patch('models.payroll.EmployeeLeave.query', mock_q)

        from services.hr_service import PayrollEngine
        employee = MagicMock()
        employee.id = 1
        days = PayrollEngine.get_unpaid_leave_deduction(employee, 6, 2026)
        assert days == 0

    def test_with_unpaid_leaves_same_month(self, mocker):
        leave1 = MagicMock()
        leave1.leave_type = 'unpaid'
        leave1.status = 'approved'
        leave1.start_date = MagicMock(year=2026, month=6)
        leave1.end_date = MagicMock(year=2026, month=6)
        leave1.days_taken = 5

        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [leave1]
        mocker.patch('models.payroll.EmployeeLeave.query', mock_q)

        from services.hr_service import PayrollEngine
        employee = MagicMock()
        employee.id = 1
        days = PayrollEngine.get_unpaid_leave_deduction(employee, 6, 2026)
        assert days == 5

    def test_unpaid_leave_spanning_two_months(self, mocker):
        leave1 = MagicMock()
        leave1.leave_type = 'unpaid'
        leave1.status = 'approved'
        leave1.start_date = MagicMock(year=2026, month=5)
        leave1.end_date = MagicMock(year=2026, month=6)
        leave1.days_taken = 10

        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [leave1]
        mocker.patch('models.payroll.EmployeeLeave.query', mock_q)

        from services.hr_service import PayrollEngine
        employee = MagicMock()
        employee.id = 1
        days = PayrollEngine.get_unpaid_leave_deduction(employee, 6, 2026)
        assert days == 10


# ---------------------------------------------------------------------------
# Payroll Batch GL Approval
# ---------------------------------------------------------------------------

class TestPayrollBatchGLApproval:
    """Approved payroll batch posts balanced Dr Expense / Cr Payable GL lines."""

    def _make_tx(self, basic, allowances, deductions, net, tx_id=1):
        tx = MagicMock()
        tx.id = tx_id
        tx.status = 'draft'
        tx.basic_amount = Decimal(str(basic))
        tx.allowances = Decimal(str(allowances))
        tx.deductions = Decimal(str(deductions))
        tx.net_salary = Decimal(str(net))
        return tx

    def test_approve_batch_posts_balanced_gl(self, app, mocker):
        from services.hr_service import PayrollService, PayrollBatch
        mock_post = mocker.patch('services.gl_posting.post_or_fail', return_value=MagicMock(id=99))
        mocker.patch('services.gl_service.GLService.ensure_core_accounts')
        mocker.patch('services.gl_service.GLService.get_account_code_for_concept', side_effect=['6100', '2100'])

        tx1 = self._make_tx(5000, 500, 300, 5200)
        tx2 = self._make_tx(4000, 500, 4500, 0)
        batch = PayrollBatch([tx1, tx2], status='draft', tenant_id=1, branch_id=1, month=6, year=2026)

        with app.app_context():
            gl_entry = PayrollService.approve_batch(batch, user_id=1)

        assert gl_entry.id == 99
        assert batch.status == 'approved'
        assert tx1.status == 'approved'
        assert tx2.status == 'approved'
        assert mock_post.called

        lines = mock_post.call_args[0][0]
        total_debit = sum(Decimal(str(l['debit'])) for l in lines)
        total_credit = sum(Decimal(str(l['credit'])) for l in lines)
        assert total_debit == total_credit
        concepts = {l['concept_code'] for l in lines}
        assert 'PAYROLL_EXPENSE' in concepts
        assert 'PAYROLL_PAYABLE' in concepts

    def test_approve_locked_batch_raises(self, app):
        from services.hr_service import PayrollService, PayrollBatch, ImmutableRecordError
        batch = PayrollBatch([], status='paid', tenant_id=1, branch_id=1, month=6, year=2026)

        with app.app_context():
            with pytest.raises(ImmutableRecordError, match='لا يمكن تعديل دفعة'):
                PayrollService.approve_batch(batch, user_id=1)

    def test_normal_salary_cycle_full_additions(self):
        from services.hr_service import PayrollEngine
        net = PayrollEngine.compute_net_salary(
            Decimal('8000'), Decimal('1500'), Decimal('200'), unpaid_leave_days=0,
        )
        assert net == Decimal('9300.00')

    def test_excessive_unpaid_leaves_clamped_via_guard(self):
        from services.hr_service import PayrollEngine
        PayrollEngine._debt_registry.clear()
        r = PayrollEngine.process_with_negative_guard(
            Decimal('3000'), Decimal('0'), Decimal('0'), unpaid_leave_days=40,
            employee_id=7, tenant_id=1, month=6, year=2026,
        )
        assert r['net_salary'] == Decimal('0')
        assert r['clamped'] is True
        assert r['debt'] == Decimal('1000.00')

    def test_massive_deductions_net_zero(self):
        from services.hr_service import PayrollEngine
        r = PayrollEngine.process_with_negative_guard(
            Decimal('4000'), Decimal('0'), Decimal('4500'),
        )
        assert r['net_salary'] == Decimal('0')
        assert r['clamped'] is True
        assert r['debt'] == Decimal('500.00')
