import logging
from datetime import datetime, timezone, date
from decimal import Decimal
from extensions import db
from utils.db_safety import atomic_transaction
from models import (
    Department, JobPosition, HRContract, Attendance, LeaveType, LeaveRequest, User, Branch,
    PayrollTransaction,
)
from utils.tenanting import get_active_tenant_id
from utils.branching import branch_scope_id_for
from utils.auth_helpers import is_global_owner_user

logger = logging.getLogger(__name__)


class ImmutableRecordError(Exception):
    """Raised when attempting to modify an immutable (approved/paid) payroll or HR record."""
    pass


class HRService:

    @staticmethod
    def _tid(user):
        return get_active_tenant_id(user)

    @staticmethod
    def _branch_check(user, branch_id=None):
        if is_global_owner_user(user):
            return
        scoped = branch_scope_id_for(user)
        if scoped is not None and branch_id is not None and int(branch_id) != int(scoped):
            raise ValueError('لا يمكنك التعامل مع سجل من فرع آخر.')

    @staticmethod
    def clock_in(user, branch_id=None):
        tid = HRService._tid(user)
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        existing = Attendance.query.filter(
            Attendance.user_id == user.id,
            Attendance.check_in >= today_start,
            Attendance.check_out.is_(None),
        ).first()
        if existing:
            raise ValueError('لديك تسجيل حضور مفتوح بالفعل. قم بتسجيل الانصراف أولاً.')
        if branch_id:
            HRService._branch_check(user, branch_id)
        att = Attendance(
            tenant_id=int(tid) if tid else 0,
            branch_id=int(branch_id) if branch_id else None,
            user_id=user.id,
            check_in=datetime.now(timezone.utc),
            state='draft',
        )
        db.session.add(att)
        try:
            db.session.flush()
        except Exception:
            raise
        return att

    @staticmethod
    def clock_out(user):
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        att = Attendance.query.filter(
            Attendance.user_id == user.id,
            Attendance.check_in >= today_start,
            Attendance.check_out.is_(None),
        ).order_by(Attendance.check_in.desc()).first()
        if not att:
            raise ValueError('لا يوجد تسجيل حضور مفتوح اليوم.')
        now = datetime.now(timezone.utc)
        check_in = att.check_in
        if check_in.tzinfo is None:
            check_in = check_in.replace(tzinfo=timezone.utc)
        delta = now - check_in
        hours = Decimal(str(round(delta.total_seconds() / 3600, 2)))
        att.check_out = now
        att.work_hours = hours
        att.state = 'validated'
        try:
            db.session.flush()
        except Exception:
            raise
        return att

    @staticmethod
    def get_attendance(user, date_from=None, date_to=None):
        tid = HRService._tid(user)
        query = Attendance.query.filter(Attendance.user_id == user.id)
        if tid is not None:
            query = query.filter(Attendance.tenant_id == tid)
        if date_from:
            query = query.filter(Attendance.check_in >= datetime.fromisoformat(date_from))
        if date_to:
            query = query.filter(Attendance.check_in <= datetime.fromisoformat(date_to).replace(hour=23, minute=59))
        return query.order_by(Attendance.check_in.desc()).all()

    @staticmethod
    def report_attendance(filters, user):
        tid = HRService._tid(user)
        query = Attendance.query
        if tid is not None:
            query = query.filter(Attendance.tenant_id == tid)
        if not is_global_owner_user(user):
            scoped = branch_scope_id_for(user)
            if scoped is not None:
                query = query.filter(Attendance.branch_id == scoped)
        if filters.get('user_id'):
            query = query.filter(Attendance.user_id == int(filters['user_id']))
        if filters.get('date_from'):
            query = query.filter(Attendance.check_in >= datetime.fromisoformat(filters['date_from']))
        if filters.get('date_to'):
            query = query.filter(Attendance.check_in <= datetime.fromisoformat(filters['date_to']).replace(hour=23, minute=59))
        return query.order_by(Attendance.check_in.desc()).all()

    @staticmethod
    def request_leave(data, user):
        tid = HRService._tid(user)
        if not tid and not is_global_owner_user(user):
            raise ValueError('لا توجد شركة نشطة.')
        if not data.get('leave_type_id'):
            raise ValueError('نوع الإجازة مطلوب.')
        date_from = datetime.strptime(data['date_from'], '%Y-%m-%d').date()
        date_to = datetime.strptime(data['date_to'], '%Y-%m-%d').date()
        if date_to < date_from:
            raise ValueError('تاريخ النهاية يجب أن يكون بعد تاريخ البداية.')
        duration = (date_to - date_from).days + 1
        leave_type = db.session.get(LeaveType, int(data['leave_type_id']))
        if not leave_type or int(leave_type.tenant_id) != int(tid or 0):
            raise ValueError('نوع الإجازة غير صالح.')
        leave = LeaveRequest(
            tenant_id=int(tid) if tid else 0,
            branch_id=int(user.branch_id) if getattr(user, 'branch_id', None) else None,
            user_id=user.id,
            leave_type_id=int(data['leave_type_id']),
            date_from=date_from,
            date_to=date_to,
            duration=Decimal(str(duration)),
            reason=data.get('reason'),
            state='draft',
            manager_id=int(data['manager_id']) if data.get('manager_id') else None,
        )
        db.session.add(leave)
        try:
            db.session.flush()
        except Exception:
            raise
        return leave

    @staticmethod
    def approve_leave(leave_id, manager):
        leave = db.session.get(LeaveRequest, int(leave_id))
        if not leave:
            raise ValueError('طلب الإجازة غير موجود.')
        if leave.state != 'draft':
            raise ValueError('يمكن الموافقة على الطلبات في حالة المسودة فقط.')
        leave.state = 'approved'
        leave.manager_id = manager.id
        leave.updated_at = datetime.now(timezone.utc)
        try:
            db.session.flush()
        except Exception:
            raise
        return leave

    @staticmethod
    def refuse_leave(leave_id, manager, reason=None):
        leave = db.session.get(LeaveRequest, int(leave_id))
        if not leave:
            raise ValueError('طلب الإجازة غير موجود.')
        if leave.state != 'draft':
            raise ValueError('يمكن رفض الطلبات في حالة المسودة فقط.')
        leave.state = 'refused'
        leave.manager_id = manager.id
        leave.rejected_reason = reason
        leave.updated_at = datetime.now(timezone.utc)
        try:
            db.session.flush()
        except Exception:
            raise
        return leave

    @staticmethod
    def list_leaves(filters, user):
        tid = HRService._tid(user)
        query = LeaveRequest.query.filter(LeaveRequest.is_active == True)
        if tid is not None:
            query = query.filter(LeaveRequest.tenant_id == tid)
        if not is_global_owner_user(user):
            scoped = branch_scope_id_for(user)
            if scoped is not None:
                query = query.filter(LeaveRequest.branch_id == scoped)
        if filters.get('state'):
            query = query.filter(LeaveRequest.state == filters['state'])
        if filters.get('user_id'):
            query = query.filter(LeaveRequest.user_id == int(filters['user_id']))
        return query.order_by(LeaveRequest.created_at.desc()).all()

    @staticmethod
    def create_department(data, user):
        tid = HRService._tid(user)
        if not tid:
            raise ValueError('لا توجد شركة نشطة.')
        dept = Department(
            tenant_id=int(tid),
            name=data.get('name'),
            name_ar=data.get('name_ar'),
            manager_id=int(data['manager_id']) if data.get('manager_id') else None,
            parent_id=int(data['parent_id']) if data.get('parent_id') else None,
            color=data.get('color', '#3b82f6'),
        )
        db.session.add(dept)
        try:
            db.session.flush()
        except Exception:
            raise
        return dept

    @staticmethod
    def list_departments(user):
        tid = HRService._tid(user)
        if not tid:
            return []
        return Department.query.filter(
            Department.tenant_id == tid,
            Department.is_active == True,
        ).order_by(Department.name).all()

    @staticmethod
    def create_contract(data, user):
        tid = HRService._tid(user)
        if not tid:
            raise ValueError('لا توجد شركة نشطة.')
        branch_id = data.get('branch_id')
        HRService._branch_check(user, branch_id)
        contract = HRContract(
            tenant_id=int(tid),
            branch_id=int(branch_id) if branch_id else None,
            user_id=int(data['user_id']),
            department_id=int(data['department_id']) if data.get('department_id') else None,
            job_id=int(data['job_id']) if data.get('job_id') else None,
            date_start=datetime.strptime(data['date_start'], '%Y-%m-%d').date() if data.get('date_start') else date.today(),
            date_end=datetime.strptime(data['date_end'], '%Y-%m-%d').date() if data.get('date_end') else None,
            wage=Decimal(str(data.get('wage', 0))),
            state=data.get('state', 'draft'),
        )
        db.session.add(contract)
        try:
            db.session.flush()
        except Exception:
            raise
        return contract


class PayrollEngine:
    LOCKED_STATUSES = ('approved', 'paid')
    _debt_registry = []

    @staticmethod
    def assert_mutable(transaction):
        if transaction.status in PayrollEngine.LOCKED_STATUSES:
            raise ImmutableRecordError(
                f'لا يمكن تعديل معاملة راتب في حالة {transaction.status}.'
            )

    @staticmethod
    def register_employee_debt(employee_id, tenant_id, amount, month, year, reason='payroll_shortfall'):
        entry = {
            'employee_id': int(employee_id),
            'tenant_id': int(tenant_id) if tenant_id is not None else None,
            'amount': Decimal(str(amount)).quantize(Decimal('0.01')),
            'month': month,
            'year': year,
            'reason': reason,
            'registered_at': datetime.now(timezone.utc),
        }
        PayrollEngine._debt_registry.append(entry)
        logger.warning(
            'Payroll debt registered: employee=%s amount=%s period=%s/%s',
            employee_id, entry['amount'], month, year,
        )
        return entry

    @staticmethod
    def compute_net_salary(basic_salary, allowances=0, deductions=0, unpaid_leave_days=0, daily_rate=None, days_worked=None):
        allow = Decimal(str(allowances or 0))
        deduct = Decimal(str(deductions or 0))
        leave_days = Decimal(str(unpaid_leave_days or 0))
        raw_basic = Decimal(str(basic_salary or 0))

        if daily_rate is not None:
            rate = Decimal(str(daily_rate))
            if days_worked is not None:
                earned = rate * Decimal(str(days_worked))
            elif raw_basic > 0 and raw_basic <= Decimal('31'):
                earned = rate * raw_basic
            else:
                earned = raw_basic
            leave_penalty = rate * leave_days
        else:
            earned = raw_basic
            rate = (earned / Decimal('30')).quantize(Decimal('0.01')) if earned > 0 else Decimal('0')
            leave_penalty = rate * leave_days

        net = earned + allow - deduct - leave_penalty
        return net.quantize(Decimal('0.01'))

    @staticmethod
    def process_with_negative_guard(
        basic_salary, allowances=0, deductions=0, unpaid_leave_days=0, daily_rate=None,
        days_worked=None, convert_to_debt=False, employee_id=None, tenant_id=None, month=None, year=None,
    ):
        net = PayrollEngine.compute_net_salary(
            basic_salary, allowances, deductions, unpaid_leave_days, daily_rate, days_worked,
        )
        if net >= Decimal('0'):
            return {'net_salary': net, 'clamped': False, 'debt': Decimal('0')}
        debt = abs(net)
        if employee_id is not None and (convert_to_debt or debt > 0):
            PayrollEngine.register_employee_debt(
                employee_id, tenant_id, debt, month, year,
            )
        return {'net_salary': Decimal('0'), 'clamped': True, 'debt': debt}

    @staticmethod
    def can_edit(transaction):
        try:
            PayrollEngine.assert_mutable(transaction)
            return True
        except ImmutableRecordError:
            return False

    @staticmethod
    def get_unpaid_leave_deduction(employee, month, year):
        from models.payroll import EmployeeLeave
        leaves = EmployeeLeave.query.filter(
            EmployeeLeave.employee_id == employee.id,
            EmployeeLeave.leave_type == 'unpaid',
            EmployeeLeave.status == 'approved',
        ).all()
        total_days = 0
        for leave in leaves:
            if leave.start_date.year == year and leave.start_date.month == month:
                total_days += leave.days_taken
            elif leave.end_date.year == year and leave.end_date.month == month:
                total_days += leave.days_taken
        return total_days


class PayrollBatch:
    """In-memory payroll run grouping for approval and GL provisioning."""

    def __init__(self, transactions, status='draft', tenant_id=None, branch_id=None, month=None, year=None):
        self.transactions = list(transactions)
        self.status = status
        self.tenant_id = tenant_id
        self.branch_id = branch_id
        self.month = month
        self.year = year


class PayrollService:
    """HR payroll orchestration — locks, net-salary guards, and GL approval."""

    @staticmethod
    def assert_batch_mutable(batch):
        if batch.status in PayrollEngine.LOCKED_STATUSES:
            raise ImmutableRecordError(
                f'لا يمكن تعديل دفعة رواتب في حالة {batch.status}.'
            )

    @staticmethod
    def update_allowances(transaction, new_allowances, batch=None):
        if batch is not None:
            PayrollService.assert_batch_mutable(batch)
        PayrollEngine.assert_mutable(transaction)
        transaction.allowances = Decimal(str(new_allowances))
        return transaction

    @staticmethod
    def delete_transaction(transaction, batch=None):
        if batch is not None:
            PayrollService.assert_batch_mutable(batch)
        PayrollEngine.assert_mutable(transaction)
        db.session.delete(transaction)

    @staticmethod
    def approve_batch(batch, user_id):
        PayrollService.assert_batch_mutable(batch)
        if not batch.transactions:
            raise ValueError('لا توجد معاملات راتب في الدفعة.')

        from services.gl_posting import post_or_fail
        from services.gl_service import GLService
        from utils.gl_reference_types import GLRef

        tenant_id = batch.tenant_id
        branch_id = batch.branch_id
        GLService.ensure_core_accounts(tenant_id=tenant_id)

        total_expense = Decimal('0')
        total_net = Decimal('0')
        total_deductions = Decimal('0')
        for tx in batch.transactions:
            total_expense += Decimal(str(tx.basic_amount or 0)) + Decimal(str(tx.allowances or 0))
            total_net += Decimal(str(tx.net_salary or 0))
            total_deductions += Decimal(str(tx.deductions or 0))

        expense_acct = GLService.get_account_code_for_concept(
            'PAYROLL_EXPENSE', branch_id=branch_id, tenant_id=tenant_id, fallback_key='salaries_expense',
        )
        payable_acct = GLService.get_account_code_for_concept(
            'PAYROLL_PAYABLE', branch_id=branch_id, tenant_id=tenant_id, fallback_key='salaries_payable',
        )

        lines = [
            {
                'account': expense_acct,
                'concept_code': 'PAYROLL_EXPENSE',
                'debit': total_expense,
                'credit': Decimal('0'),
                'description': f'Payroll expense {batch.month}/{batch.year}',
            },
            {
                'account': payable_acct,
                'concept_code': 'PAYROLL_PAYABLE',
                'debit': Decimal('0'),
                'credit': total_net,
                'description': f'Payroll payable {batch.month}/{batch.year}',
            },
        ]
        if total_deductions > Decimal('0'):
            lines.append({
                'account': payable_acct,
                'concept_code': 'PAYROLL_PAYABLE',
                'debit': Decimal('0'),
                'credit': total_deductions,
                'description': f'Payroll deductions {batch.month}/{batch.year}',
            })

        ref_id = batch.transactions[0].id
        gl_entry = post_or_fail(
            lines,
            description=f'Payroll batch approval {batch.month}/{batch.year}',
            reference_type=GLRef.PAYROLL,
            reference_id=ref_id,
            branch_id=branch_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        batch.status = 'approved'
        for tx in batch.transactions:
            tx.status = 'approved'
            tx.gl_entry_id = gl_entry.id

        return gl_entry
