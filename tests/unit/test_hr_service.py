"""HR Service unit tests."""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, date, timedelta
from services.hr_service import HRService


class TestHRService:
    def test_clock_in(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            att = HRService.clock_in(sample_user)
            assert att.id is not None
            assert att.user_id == sample_user.id
            assert att.check_in is not None
            assert att.state == 'draft'

    def test_clock_in_twice_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            HRService.clock_in(sample_user)
            with pytest.raises(ValueError):
                HRService.clock_in(sample_user)

    def test_clock_out(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            HRService.clock_in(sample_user)
            att = HRService.clock_out(sample_user)
            assert att.check_out is not None
            assert att.work_hours is not None
            assert att.state == 'validated'

    def test_clock_out_without_clock_in_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            with pytest.raises(ValueError):
                HRService.clock_out(sample_user)

    def test_get_attendance(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            HRService.clock_in(sample_user)
            result = HRService.get_attendance(sample_user)
            assert len(result) >= 1

    def test_request_leave(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            from models import LeaveType
            lt = LeaveType(tenant_id=sample_tenant.id, name='Annual')
            db_session.add(lt)
            db_session.flush()
            data = {
                'leave_type_id': lt.id,
                'date_from': str(date.today()),
                'date_to': str(date.today() + timedelta(days=2)),
                'reason': 'Vacation',
            }
            leave = HRService.request_leave(data, sample_user)
            assert leave.id is not None
            assert leave.duration == Decimal('3')
            assert leave.state == 'draft'

    def test_request_leave_invalid_dates_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            from models import LeaveType
            lt = LeaveType(tenant_id=sample_tenant.id, name='Annual')
            db_session.add(lt)
            db_session.flush()
            data = {
                'leave_type_id': lt.id,
                'date_from': str(date.today()),
                'date_to': str(date.today() - timedelta(days=1)),
            }
            with pytest.raises(ValueError):
                HRService.request_leave(data, sample_user)

    def test_approve_leave(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            from models import LeaveType
            lt = LeaveType(tenant_id=sample_tenant.id, name='Annual')
            db_session.add(lt)
            db_session.flush()
            data = {
                'leave_type_id': lt.id,
                'date_from': str(date.today()),
                'date_to': str(date.today()),
            }
            leave = HRService.request_leave(data, sample_user)
            approved = HRService.approve_leave(leave.id, sample_user)
            assert approved.state == 'approved'

    def test_refuse_leave(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            from models import LeaveType
            lt = LeaveType(tenant_id=sample_tenant.id, name='Annual')
            db_session.add(lt)
            db_session.flush()
            data = {
                'leave_type_id': lt.id,
                'date_from': str(date.today()),
                'date_to': str(date.today()),
            }
            leave = HRService.request_leave(data, sample_user)
            refused = HRService.refuse_leave(leave.id, sample_user, reason='busy')
            assert refused.state == 'refused'
            assert refused.rejected_reason == 'busy'

    def test_list_leaves(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            from models import LeaveType
            lt = LeaveType(tenant_id=sample_tenant.id, name='Annual')
            db_session.add(lt)
            db_session.flush()
            data = {
                'leave_type_id': lt.id,
                'date_from': str(date.today()),
                'date_to': str(date.today()),
            }
            HRService.request_leave(data, sample_user)
            result = HRService.list_leaves({}, sample_user)
            assert len(result) >= 1

    def test_create_department(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            dept = HRService.create_department({'name': 'IT', 'name_ar': 'تقنية المعلومات'}, sample_user)
            assert dept.id is not None
            assert dept.name == 'IT'

    def test_list_departments(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            HRService.create_department({'name': 'HR'}, sample_user)
            result = HRService.list_departments(sample_user)
            assert len(result) >= 1

    def test_create_contract(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            contract = HRService.create_contract({
                'user_id': sample_user.id,
                'wage': '5000',
                'date_start': str(date.today()),
            }, sample_user)
            assert contract.id is not None
            assert contract.wage == Decimal('5000')
