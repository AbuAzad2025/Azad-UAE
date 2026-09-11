"""Coverage-4 for services.ticket_service — else/except/fallback arcs.

Real behavior paths; mocks only at DB/session boundary (db.session, query).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.ticket_service import TicketService


@pytest.fixture()
def ctx(app):
    with app.app_context():
        yield


class TestTenantListings:
    def test_categories_without_tid_skips_filter(self, ctx, mocker):
        from models import TicketCategory

        seen = {}

        class _Q:
            def filter(self, *a):
                seen["filtered"] = seen.get("filtered", 0) + 1
                return self

            def all(self):
                return ["c1"]

        mocker.patch.object(TicketCategory, "query", new_callable=mocker.PropertyMock, return_value=_Q())
        assert TicketService.tenant_categories(None) == ["c1"]
        assert seen.get("filtered", 0) == 1

    def test_priorities_without_tid(self, ctx, mocker):
        from models import TicketPriority

        class _Q:
            def filter(self, *a):
                return self

            def all(self):
                return ["p"]

        mocker.patch.object(TicketPriority, "query", new_callable=mocker.PropertyMock, return_value=_Q())
        assert TicketService.tenant_priorities(None) == ["p"]

    def test_customers_ordered_without_tid(self, ctx, mocker):
        from models import Customer

        class _Q:
            def filter(self, *a):
                return self

            def order_by(self, *a):
                return self

            def all(self):
                return ["cu"]

        mocker.patch.object(Customer, "query", new_callable=mocker.PropertyMock, return_value=_Q())
        assert TicketService.tenant_customers(None) == ["cu"]

    def test_users_empty_without_tid(self, ctx):
        assert TicketService.tenant_users(None) == []
        assert TicketService.tenant_users(0) == []

    def test_validate_tenant_passes_when_same(self, ctx, mocker):
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=5)
        TicketService._validate_tenant(MagicMock(tenant_id=5), MagicMock())

    def test_validate_tenant_skips_when_no_active(self, ctx, mocker):
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=None)
        TicketService._validate_tenant(MagicMock(tenant_id=99), MagicMock())


class TestNextNumber:
    def test_no_last_returns_0001(self, ctx, mocker):
        from models import Ticket

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = None
        mocker.patch.object(Ticket, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        num = TicketService._next_number(3)
        assert num.endswith("-0001")

    def test_malformed_number_falls_back_to_0001(self, ctx, mocker):
        from models import Ticket

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = MagicMock(number="GARBAGE-NO-DIGITS-XYZ")
        mocker.patch.object(Ticket, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        num = TicketService._next_number(3)
        assert num.endswith("-0001")

    def test_last_without_number_falls_back(self, ctx, mocker):
        from models import Ticket

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.first.return_value = MagicMock(number=None)
        mocker.patch.object(Ticket, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        assert TicketService._next_number(3).endswith("-0001")


class TestCreateTicketArcs:
    def test_owner_without_tid_gets_number_none(self, ctx, mocker):
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=None)
        mocker.patch("services.ticket_service.is_global_owner_user", return_value=True)
        sess = mocker.patch("services.ticket_service.db.session")
        sess.flush.return_value = None
        t = TicketService.create_ticket({"subject": "s"}, MagicMock())
        assert t.tenant_id == 0
        assert t.number is None

    def test_no_active_tenant_non_owner_rejected(self, ctx, mocker):
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=None)
        mocker.patch("services.ticket_service.is_global_owner_user", return_value=False)
        with pytest.raises(ValueError, match="نشطة"):
            TicketService.create_ticket({"subject": "s"}, MagicMock())

    def test_priority_with_zero_sla_has_no_deadline(self, ctx, mocker):
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=2)
        mocker.patch("services.ticket_service.is_global_owner_user", return_value=False)
        mocker.patch("services.ticket_service.TicketService._next_number", return_value="TKT-1")
        sess = mocker.patch("services.ticket_service.db.session")
        sess.flush.return_value = None
        sess.get.return_value = MagicMock(sla_hours=0)
        t = TicketService.create_ticket({"subject": "s", "priority_id": 9}, MagicMock())
        assert t.sla_deadline is None

    def test_priority_missing_has_no_deadline(self, ctx, mocker):
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=2)
        mocker.patch("services.ticket_service.is_global_owner_user", return_value=False)
        mocker.patch("services.ticket_service.TicketService._next_number", return_value="TKT-1")
        sess = mocker.patch("services.ticket_service.db.session")
        sess.flush.return_value = None
        sess.get.return_value = None
        t = TicketService.create_ticket({"subject": "s", "priority_id": 4242}, MagicMock())
        assert t.sla_deadline is None

    def test_flush_error_propagates(self, ctx, mocker):
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=2)
        mocker.patch("services.ticket_service.is_global_owner_user", return_value=False)
        mocker.patch("services.ticket_service.TicketService._next_number", return_value="TKT-1")
        sess = mocker.patch("services.ticket_service.db.session")
        sess.flush.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError):
            TicketService.create_ticket({"subject": "s"}, MagicMock())


class TestStateMachineArcs:
    def _ticket(self):
        return MagicMock(tenant_id=7, status="open", id=1)

    def test_assign_clears_user_when_none(self, ctx, mocker):
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=7)
        sess = mocker.patch("services.ticket_service.db.session")
        sess.get.return_value = self._ticket()
        sess.flush.return_value = None
        t = TicketService.assign_ticket(1, None, MagicMock())
        assert t.assigned_user_id is None

    def test_assign_missing_ticket(self, ctx, mocker):
        sess = mocker.patch("services.ticket_service.db.session")
        sess.get.return_value = None
        with pytest.raises(ValueError, match="غير موجودة"):
            TicketService.assign_ticket(999, 1, MagicMock())

    def test_add_comment_non_open_skips_touch(self, ctx, mocker):
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=7)
        sess = mocker.patch("services.ticket_service.db.session")
        ticket = MagicMock(tenant_id=7, status="closed", id=3)
        sess.get.return_value = ticket
        sess.flush.return_value = None
        before = ticket.updated_at
        TicketService.add_comment(3, {"body": "hi"}, MagicMock(id=5))
        assert ticket.updated_at is before

    def test_add_comment_requires_body(self, ctx, mocker):
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=7)
        sess = mocker.patch("services.ticket_service.db.session")
        sess.get.return_value = MagicMock(tenant_id=7, status="open", id=4)
        with pytest.raises(ValueError, match="التعليق"):
            TicketService.add_comment(4, {}, MagicMock())

    def test_search_with_all_filters(self, ctx, mocker):
        user = MagicMock()
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=7)
        mocker.patch("services.ticket_service.is_global_owner_user", return_value=False)
        mocker.patch("services.ticket_service.branch_scope_id_for", return_value=None)
        from models import Ticket

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = ["t"]
        mocker.patch.object(Ticket, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        out = TicketService.search_tickets(
            {"status": "open", "category_id": 2, "assigned_user_id": 3, "search": "printer"},
            user,
        )
        assert out == ["t"]

    def test_search_owner_skips_branch_scope(self, ctx, mocker):
        user = MagicMock()
        mocker.patch("services.ticket_service.get_active_tenant_id", return_value=None)
        mocker.patch("services.ticket_service.is_global_owner_user", return_value=True)
        from models import Ticket

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = []
        mocker.patch.object(Ticket, "query", new_callable=mocker.PropertyMock, return_value=mock_q)
        assert TicketService.search_tickets({}, user) == []
