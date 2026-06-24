"""Ticket service — assignment, state machine, SLA, tenant isolation."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


class TestTenantGuard:
    """_validate_tenant — multi-tenant isolation."""

    def test_rejects_cross_tenant_access(self, mocker):
        ticket = MagicMock(tenant_id=2)
        user = MagicMock()
        mocker.patch('services.ticket_service.get_active_tenant_id', return_value=1)

        from services.ticket_service import TicketService

        with pytest.raises(ValueError, match='لا تنتمي'):
            TicketService._validate_tenant(ticket, user)


class TestTicketNumbering:
    """_next_number — sequential auto-assignment."""

    def test_increments_from_last_ticket(self, app, mocker):
        from models import Ticket

        last = MagicMock(number='TKT-202506-0007')
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = last
        mocker.patch.object(Ticket, 'query', new_callable=mocker.PropertyMock, return_value=mock_q)

        from services.ticket_service import TicketService

        with app.app_context():
            num = TicketService._next_number(1)
        assert num.endswith('-0008')


class TestCreateTicket:
    """create_ticket — validation, SLA escalation deadline."""

    def test_requires_subject(self, app, mocker):
        mocker.patch('services.ticket_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.ticket_service.is_global_owner_user', return_value=False)

        from services.ticket_service import TicketService

        with app.app_context():
            with pytest.raises(ValueError, match='عنوان'):
                TicketService.create_ticket({}, MagicMock())

    def test_creates_with_sla_from_priority(self, app, mocker):
        mocker.patch('services.ticket_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.ticket_service.is_global_owner_user', return_value=False)
        mocker.patch('services.ticket_service.TicketService._next_number', return_value='TKT-202506-0001')
        priority = MagicMock(sla_hours=24)
        mock_session = mocker.patch('services.ticket_service.db.session')
        mock_session.get.return_value = priority

        from services.ticket_service import TicketService

        with app.app_context():
            ticket = TicketService.create_ticket(
                {'subject': 'Printer down', 'priority_id': 3, 'body': 'details'},
                MagicMock(),
            )
        assert ticket.subject == 'Printer down'
        assert ticket.sla_deadline is not None
        mock_session.commit.assert_called_once()


class TestStateTransitions:
    """assign / resolve / close / reopen — lifecycle."""

    def _ticket(self, tenant_id=1):
        t = MagicMock(tenant_id=tenant_id, status='open', id=1)
        return t

    def test_assign_ticket(self, app, mocker):
        ticket = self._ticket()
        mock_session = mocker.patch('services.ticket_service.db.session')
        mock_session.get.return_value = ticket
        mocker.patch('services.ticket_service.get_active_tenant_id', return_value=1)

        from services.ticket_service import TicketService

        with app.app_context():
            result = TicketService.assign_ticket(1, 9, MagicMock())
        assert result.assigned_user_id == 9
        mock_session.commit.assert_called_once()

    def test_resolve_sets_resolved_timestamp(self, app, mocker):
        ticket = self._ticket()
        mock_session = mocker.patch('services.ticket_service.db.session')
        mock_session.get.return_value = ticket
        mocker.patch('services.ticket_service.get_active_tenant_id', return_value=1)

        from services.ticket_service import TicketService

        with app.app_context():
            TicketService.resolve_ticket(1, MagicMock())
        assert ticket.status == 'resolved'
        assert ticket.resolved_at is not None

    def test_close_ticket(self, app, mocker):
        ticket = self._ticket()
        mock_session = mocker.patch('services.ticket_service.db.session')
        mock_session.get.return_value = ticket
        mocker.patch('services.ticket_service.get_active_tenant_id', return_value=1)

        from services.ticket_service import TicketService

        with app.app_context():
            TicketService.close_ticket(1, MagicMock())
        assert ticket.status == 'closed'

    def test_reopen_clears_resolution(self, app, mocker):
        ticket = self._ticket()
        ticket.status = 'closed'
        ticket.resolved_at = datetime.now(timezone.utc)
        ticket.closed_at = datetime.now(timezone.utc)
        mock_session = mocker.patch('services.ticket_service.db.session')
        mock_session.get.return_value = ticket
        mocker.patch('services.ticket_service.get_active_tenant_id', return_value=1)

        from services.ticket_service import TicketService

        with app.app_context():
            TicketService.reopen_ticket(1, MagicMock())
        assert ticket.status == 'open'
        assert ticket.resolved_at is None


class TestCommentsAndSearch:
    """add_comment / search_tickets — attachment boundaries via validation."""

    def test_comment_requires_body(self, app, mocker):
        ticket = MagicMock(tenant_id=1, id=1, status='open')
        mock_session = mocker.patch('services.ticket_service.db.session')
        mock_session.get.return_value = ticket
        mocker.patch('services.ticket_service.get_active_tenant_id', return_value=1)

        from services.ticket_service import TicketService

        with app.app_context():
            with pytest.raises(ValueError, match='نص التعليق'):
                TicketService.add_comment(1, {}, MagicMock(id=2))

    def test_search_filters_by_tenant(self, app, mocker):
        from models import Ticket

        mocker.patch('services.ticket_service.get_active_tenant_id', return_value=5)
        mocker.patch('services.ticket_service.is_global_owner_user', return_value=False)
        mocker.patch('services.ticket_service.branch_scope_id_for', return_value=None)
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = []
        mocker.patch.object(Ticket, 'query', new_callable=mocker.PropertyMock, return_value=mock_q)

        from services.ticket_service import TicketService

        with app.app_context():
            TicketService.search_tickets({'status': 'open', 'search': 'printer'}, MagicMock())
        assert mock_q.filter.called
