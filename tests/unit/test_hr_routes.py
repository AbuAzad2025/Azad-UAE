"""Tests for HR Core module - Attendance, Leaves, Departments"""
import pytest
from datetime import datetime, timezone, date
from models import Department, Attendance, LeaveType, LeaveRequest, HRContract


class TestHRModels:
    def test_department_creation(self, app, db_session, sample_tenant):
        d = Department(tenant_id=sample_tenant.id, name='Engineering')
        db_session.add(d)
        db_session.commit()
        assert d.id

    def test_leave_type_creation(self, app, db_session, sample_tenant):
        lt = LeaveType(tenant_id=sample_tenant.id, name='Annual', days_per_year=30)
        db_session.add(lt)
        db_session.commit()
        assert lt.days_per_year == 30

    def test_leave_request_creation(self, app, db_session, sample_tenant, sample_user):
        lt = LeaveType(tenant_id=sample_tenant.id, name='Sick')
        db_session.add(lt)
        db_session.flush()
        lr = LeaveRequest(
            tenant_id=sample_tenant.id,
            user_id=sample_user.id,
            leave_type_id=lt.id,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 7, 3),
            duration=3,
            state='draft',
        )
        db_session.add(lr)
        db_session.commit()
        assert lr.id
        assert lr.state == 'draft'

    def test_attendance_clock_in(self, app, db_session, sample_tenant, sample_user):
        att = Attendance(
            tenant_id=sample_tenant.id,
            user_id=sample_user.id,
            check_in=datetime.now(timezone.utc),
            state='draft',
        )
        db_session.add(att)
        db_session.commit()
        assert att.id
        assert att.check_out is None

    def test_attendance_clock_out(self, app, db_session, sample_tenant, sample_user):
        from datetime import timedelta
        check_in = datetime.now(timezone.utc) - timedelta(hours=8)
        att = Attendance(
            tenant_id=sample_tenant.id,
            user_id=sample_user.id,
            check_in=check_in,
            check_out=datetime.now(timezone.utc),
            work_hours=8.0,
            state='validated',
        )
        db_session.add(att)
        db_session.commit()
        assert att.work_hours == 8.0

    def test_hr_contract_creation(self, app, db_session, sample_tenant, sample_user):
        c = HRContract(
            tenant_id=sample_tenant.id,
            user_id=sample_user.id,
            date_start=date(2026, 1, 1),
            wage=5000,
            state='open',
        )
        db_session.add(c)
        db_session.commit()
        assert c.id


class TestHRTenantIsolation:
    def test_leave_tenant_isolation(self, app, db_session, sample_user):
        import uuid
        uid = uuid.uuid4().hex[:6]
        t1 = __import__('models').Tenant(slug='hr1-' + uid, name='HR T1-' + uid, name_ar='إتش آر 1')
        t2 = __import__('models').Tenant(slug='hr2-' + uid, name='HR T2-' + uid, name_ar='إتش آر 2')
        db_session.add_all([t1, t2])
        db_session.flush()
        from datetime import date
        l1 = LeaveRequest(tenant_id=t1.id, user_id=sample_user.id, date_from=date(2026,7,1), date_to=date(2026,7,1), duration=1)
        l2 = LeaveRequest(tenant_id=t2.id, user_id=sample_user.id, date_from=date(2026,7,2), date_to=date(2026,7,3), duration=2)
        db_session.add_all([l1, l2])
        db_session.commit()
        assert LeaveRequest.query.filter_by(tenant_id=t1.id).count() == 1
        assert LeaveRequest.query.filter_by(tenant_id=t2.id).count() == 1
