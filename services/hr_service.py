from datetime import datetime, timezone, date
from decimal import Decimal
from extensions import db
from models import (
    Department, JobPosition, HRContract, Attendance, LeaveType, LeaveRequest, User, Branch
)
from utils.tenanting import get_active_tenant_id
from utils.branching import branch_scope_id_for
from utils.auth_helpers import is_global_owner_user


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
            db.session.commit()
        except Exception:
            db.session.rollback()
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
        delta = now - att.check_in
        hours = Decimal(str(round(delta.total_seconds() / 3600, 2)))
        att.check_out = now
        att.work_hours = hours
        att.state = 'validated'
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
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
            db.session.commit()
        except Exception:
            db.session.rollback()
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
            db.session.commit()
        except Exception:
            db.session.rollback()
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
            db.session.commit()
        except Exception:
            db.session.rollback()
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
            db.session.commit()
        except Exception:
            db.session.rollback()
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
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return contract
