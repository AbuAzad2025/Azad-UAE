"""Ticket Service unit tests."""
import pytest
from datetime import datetime, timezone, timedelta
from services.ticket_service import TicketService


class TestTicketService:
    def test_create_ticket(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            data = {
                'subject': 'Test Ticket',
                'body': 'Details here',
                'source': 'portal',
            }
            ticket = TicketService.create_ticket(data, sample_user)
            assert ticket.id is not None
            assert ticket.subject == 'Test Ticket'
            assert ticket.status == 'open'
            assert ticket.number is not None

    def test_create_ticket_no_subject_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            with pytest.raises(ValueError):
                TicketService.create_ticket({}, sample_user)

    def test_create_ticket_with_priority_sla(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            from models import TicketPriority
            prio = TicketPriority(tenant_id=sample_tenant.id, name='High', sla_hours=4)
            db_session.add(prio)
            db_session.flush()
            data = {'subject': 'Urgent', 'priority_id': prio.id}
            ticket = TicketService.create_ticket(data, sample_user)
            assert ticket.sla_deadline is not None

    def test_assign_ticket(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            ticket = TicketService.create_ticket({'subject': 'T1'}, sample_user)
            assigned = TicketService.assign_ticket(ticket.id, sample_user.id, sample_user)
            assert assigned.assigned_user_id == sample_user.id

    def test_resolve_ticket(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            ticket = TicketService.create_ticket({'subject': 'T1'}, sample_user)
            resolved = TicketService.resolve_ticket(ticket.id, sample_user)
            assert resolved.status == 'resolved'
            assert resolved.resolved_at is not None

    def test_close_ticket(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            ticket = TicketService.create_ticket({'subject': 'T1'}, sample_user)
            closed = TicketService.close_ticket(ticket.id, sample_user)
            assert closed.status == 'closed'
            assert closed.closed_at is not None

    def test_reopen_ticket(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            ticket = TicketService.create_ticket({'subject': 'T1'}, sample_user)
            TicketService.close_ticket(ticket.id, sample_user)
            reopened = TicketService.reopen_ticket(ticket.id, sample_user)
            assert reopened.status == 'open'
            assert reopened.closed_at is None

    def test_add_comment(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            ticket = TicketService.create_ticket({'subject': 'T1'}, sample_user)
            comment = TicketService.add_comment(ticket.id, {'body': 'Note'}, sample_user)
            assert comment.id is not None
            assert comment.body == 'Note'

    def test_add_comment_no_body_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            ticket = TicketService.create_ticket({'subject': 'T1'}, sample_user)
            with pytest.raises(ValueError):
                TicketService.add_comment(ticket.id, {}, sample_user)

    def test_get_ticket(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            ticket = TicketService.create_ticket({'subject': 'T1'}, sample_user)
            fetched = TicketService.get_ticket(ticket.id, sample_user)
            assert fetched.id == ticket.id

    def test_list_tickets(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            TicketService.create_ticket({'subject': 'T1'}, sample_user)
            result = TicketService.list_tickets({}, sample_user)
            assert len(result) >= 1

    def test_validate_tenant_mismatch_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            from models import Ticket
            other = Ticket(tenant_id=999999, subject='Other', status='open')
            db_session.add(other)
            db_session.flush()
            with pytest.raises(ValueError):
                TicketService._validate_tenant(other, sample_user)
