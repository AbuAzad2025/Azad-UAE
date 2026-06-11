"""Tests for Helpdesk/Tickets module"""
import pytest
from models import TicketCategory, TicketPriority, Ticket, TicketComment


class TestTicketModels:
    def test_ticket_category_creation(self, app, db_session, sample_tenant):
        c = TicketCategory(tenant_id=sample_tenant.id, name='Technical')
        db_session.add(c)
        db_session.commit()
        assert c.id

    def test_ticket_priority_creation(self, app, db_session, sample_tenant):
        p = TicketPriority(tenant_id=sample_tenant.id, name='High', sla_hours=4)
        db_session.add(p)
        db_session.commit()
        assert p.sla_hours == 4

    def test_ticket_creation(self, app, db_session, sample_tenant):
        t = Ticket(tenant_id=sample_tenant.id, subject='Test Ticket', body='Issue description')
        db_session.add(t)
        db_session.commit()
        assert t.id
        assert t.status == 'open'

    def test_ticket_comment(self, app, db_session, sample_tenant, sample_user):
        t = Ticket(tenant_id=sample_tenant.id, subject='Comment Test')
        db_session.add(t)
        db_session.flush()
        c = TicketComment(
            tenant_id=sample_tenant.id,
            ticket_id=t.id,
            user_id=sample_user.id,
            body='Test comment',
        )
        db_session.add(c)
        db_session.commit()
        assert len(t.comments) == 1

    def test_ticket_number_generation(self, app, db_session, sample_tenant):
        """Verify custom number field is populated"""
        t = Ticket(tenant_id=sample_tenant.id, subject='Number Test', number='TKT-202606-0001')
        db_session.add(t)
        db_session.commit()
        assert t.number == 'TKT-202606-0001'

    def test_ticket_sla_deadline(self, app, db_session, sample_tenant):
        from datetime import datetime, timedelta, timezone
        p = TicketPriority(tenant_id=sample_tenant.id, name='Urgent', sla_hours=2)
        db_session.add(p)
        db_session.flush()
        expected = datetime.now(timezone.utc) + timedelta(hours=2)
        t = Ticket(tenant_id=sample_tenant.id, subject='SLA Test', priority_id=p.id, sla_deadline=expected)
        db_session.add(t)
        db_session.commit()
        assert t.sla_deadline is not None


class TestTicketTenantIsolation:
    def test_ticket_tenant_isolation(self, app, db_session):
        t1 = __import__('models').Tenant(slug='tkt1', name='TKT T1', name_ar='تيكيت 1')
        t2 = __import__('models').Tenant(slug='tkt2', name='TKT T2', name_ar='تيكيت 2')
        db_session.add_all([t1, t2])
        db_session.flush()
        tk1 = Ticket(tenant_id=t1.id, subject='Ticket T1')
        tk2 = Ticket(tenant_id=t2.id, subject='Ticket T2')
        db_session.add_all([tk1, tk2])
        db_session.commit()
        assert Ticket.query.filter_by(tenant_id=t1.id).count() == 1
        assert Ticket.query.filter_by(tenant_id=t2.id).count() == 1
