"""Tests for CRM Pipeline module - CRMStage, CRMTeam, CRMLead, CRMActivity"""
import pytest
from models import CRMStage, CRMTeam, CRMTeamMember, CRMLead, CRMActivity


class TestCRMModels:
    def test_crm_stage_creation(self, app, db_session, sample_tenant):
        s = CRMStage(tenant_id=sample_tenant.id, name='New', sequence=0, probability=10)
        db_session.add(s)
        db_session.commit()
        assert s.id
        assert s.name == 'New'
        assert s.tenant_id == sample_tenant.id

    def test_crm_team_creation(self, app, db_session, sample_tenant, sample_user):
        t = CRMTeam(tenant_id=sample_tenant.id, name='Sales Team', leader_id=sample_user.id)
        db_session.add(t)
        db_session.commit()
        assert t.id
        member = CRMTeamMember(team_id=t.id, user_id=sample_user.id)
        db_session.add(member)
        db_session.commit()
        assert len(t.members) == 1

    def test_crm_lead_creation(self, app, db_session, sample_tenant):
        stage = CRMStage(tenant_id=sample_tenant.id, name='Qualified', sequence=1)
        db_session.add(stage)
        db_session.flush()
        lead = CRMLead(
            tenant_id=sample_tenant.id,
            name='Test Lead',
            email='test@example.com',
            stage_id=stage.id,
            expected_revenue=50000,
        )
        db_session.add(lead)
        db_session.commit()
        assert lead.id
        assert lead.stage_id == stage.id

    def test_crm_activity_creation(self, app, db_session, sample_tenant, sample_user):
        lead = CRMLead(tenant_id=sample_tenant.id, name='Activity Lead')
        db_session.add(lead)
        db_session.flush()
        act = CRMActivity(
            tenant_id=sample_tenant.id,
            lead_id=lead.id,
            user_id=sample_user.id,
            activity_type='call',
            summary='Test call',
        )
        db_session.add(act)
        db_session.commit()
        assert len(lead.activities) == 1


class TestCRMTenantIsolation:
    def test_lead_tenant_isolation(self, app, db_session):
        """Create leads for two tenants and verify they don't overlap"""
        import uuid
        uid = uuid.uuid4().hex[:6]
        t1 = __import__('models').Tenant(slug='crm1-' + uid, name='CRM T1-' + uid, name_ar='سي آر إم 1')
        t2 = __import__('models').Tenant(slug='crm2-' + uid, name='CRM T2-' + uid, name_ar='سي آر إم 2')
        db_session.add_all([t1, t2])
        db_session.flush()

        l1 = CRMLead(tenant_id=t1.id, name='Lead T1')
        l2 = CRMLead(tenant_id=t2.id, name='Lead T2')
        db_session.add_all([l1, l2])
        db_session.commit()

        assert CRMLead.query.filter_by(tenant_id=t1.id).count() == 1
        assert CRMLead.query.filter_by(tenant_id=t2.id).count() == 1
        assert CRMLead.query.filter_by(tenant_id=t1.id).first().name == 'Lead T1'
