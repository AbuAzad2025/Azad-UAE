"""CRM Lead Service unit tests."""
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from services.crm_lead_service import CRMLeadService


class TestCRMLeadService:
    def test_create_lead(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            data = {
                'name': 'Test Lead',
                'email': 'lead@test.com',
                'phone': '0501234567',
                'company': 'TestCo',
                'status': 'new',
                'source': 'website',
                'estimated_value': '1000',
            }
            lead = CRMLeadService.create_lead(data, sample_user)
            assert lead.id is not None
            assert lead.name == 'Test Lead'
            assert lead.tenant_id == sample_tenant.id
            assert lead.status == 'open'

    def test_create_lead_no_active_tenant_raises(self, app, db_session):
        from extensions import db
        from models import User, Role
        with app.app_context():
            role = Role.query.filter_by(name='employee').first()
            if not role:
                role = Role(name='employee', slug='employee')
                db.session.add(role)
                db.session.commit()
            import uuid as _uuid
            uid = _uuid.uuid4().hex[:6]
            user = User(username='no_tenant_user_' + uid, email='no_tenant_' + uid + '@test.com', password_hash='x', role_id=role.id, tenant_id=None, is_active=True)
            db.session.add(user)
            db.session.commit()
            data = {'name': 'X'}
            with pytest.raises(ValueError):
                CRMLeadService.create_lead(data, user)

    def test_update_lead(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            data = {'name': 'Old Name', 'email': 'old@test.com', 'status': 'new', 'source': 'web'}
            lead = CRMLeadService.create_lead(data, sample_user)
            updated = CRMLeadService.update_lead(lead.id, {'name': 'New Name'}, sample_user)
            assert updated.name == 'New Name'

    def test_delete_lead(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            data = {'name': 'Del', 'email': 'd@test.com', 'status': 'new', 'source': 'web'}
            lead = CRMLeadService.create_lead(data, sample_user)
            from extensions import db
            db.session.delete(lead)
            db.session.commit()
            assert db.session.get(type(lead), lead.id) is None

    def test_validate_tenant_mismatch_raises(self, app, db_session, sample_tenant, sample_user):
        from extensions import db
        from models import CRMLead, Tenant
        import uuid as _uuid
        with app.app_context():
            other_tenant = Tenant(name='Other CRM-' + _uuid.uuid4().hex[:6], name_ar='اختبار', slug='other-crm-' + _uuid.uuid4().hex[:6], email='oc@test.com')
            db.session.add(other_tenant)
            db.session.commit()
            other_lead = CRMLead(tenant_id=other_tenant.id, name='Other', status='new', source='web')
            db_session.add(other_lead)
            db_session.flush()
            with pytest.raises(ValueError):
                CRMLeadService._validate_tenant(other_lead, sample_user)

    def test_get_lead_stats(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            data = {'name': 'L1', 'email': 'l1@test.com', 'status': 'new', 'source': 'web'}
            CRMLeadService.create_lead(data, sample_user)
            stats = CRMLeadService.get_pipeline_stats(sample_user)
            assert isinstance(stats, list)
