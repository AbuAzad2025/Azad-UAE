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
            assert lead.status == 'new'

    def test_create_lead_no_active_tenant_raises(self, app, db_session):
        with app.app_context():
            from models import User
            user = User.query.first()
            if not user:
                pytest.skip('No user')
            data = {'name': 'X'}
            with pytest.raises(ValueError):
                CRMLeadService.create_lead(data, user)

    def test_update_lead(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            data = {'name': 'Old Name', 'email': 'old@test.com', 'status': 'new', 'source': 'web'}
            lead = CRMLeadService.create_lead(data, sample_user)
            updated = CRMLeadService.update_lead(lead, {'name': 'New Name'}, sample_user)
            assert updated.name == 'New Name'

    def test_delete_lead(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            data = {'name': 'Del', 'email': 'd@test.com', 'status': 'new', 'source': 'web'}
            lead = CRMLeadService.create_lead(data, sample_user)
            CRMLeadService.delete_lead(lead, sample_user)
            from extensions import db
            db.session.commit()
            assert db.session.get(type(lead), lead.id) is None

    def test_validate_tenant_mismatch_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            from models import CRMLead
            other_lead = CRMLead(tenant_id=999999, name='Other', status='new', source='web')
            db_session.add(other_lead)
            db_session.flush()
            with pytest.raises(ValueError):
                CRMLeadService._validate_tenant(other_lead, sample_user)

    def test_get_lead_stats(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            data = {'name': 'L1', 'email': 'l1@test.com', 'status': 'new', 'source': 'web'}
            CRMLeadService.create_lead(data, sample_user)
            stats = CRMLeadService.get_lead_stats(sample_user)
            assert 'total' in stats
            assert stats['total'] >= 1
