from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import (
    _chain_query,
    unauthenticated_client,
)


def _mock_ticket(**kwargs):
    ticket = MagicMock()
    ticket.id = kwargs.get("id", 1)
    ticket.tenant_id = kwargs.get("tenant_id", 1)
    ticket.subject = kwargs.get("subject", "Issue")
    ticket.status = kwargs.get("status", "open")
    return ticket


@contextmanager
def _ticket_patches(**kwargs):
    tickets = kwargs.get("tickets", [])
    with ExitStack() as stack:
        stack.enter_context(patch("routes.tickets.render_template", return_value="ok"))
        stack.enter_context(
            patch(
                "routes.tickets.get_active_tenant_id", return_value=kwargs.get("tid", 1)
            )
        )
        stack.enter_context(
            patch("routes.tickets.TicketService.search_tickets", return_value=tickets)
        )
        stack.enter_context(
            patch(
                "routes.tickets.TicketCategory.query",
                _chain_query(all=kwargs.get("categories", [])),
            )
        )
        stack.enter_context(
            patch(
                "routes.tickets.TicketPriority.query",
                _chain_query(all=kwargs.get("priorities", [])),
            )
        )
        stack.enter_context(
            patch(
                "routes.tickets.Customer.query",
                _chain_query(all=kwargs.get("customers", [])),
            )
        )
        stack.enter_context(
            patch(
                "routes.tickets.User.query", _chain_query(all=kwargs.get("users", []))
            )
        )
        stack.enter_context(patch("extensions.limiter.limit", return_value=lambda f: f))
        yield


@pytest.fixture
def tickets_client(app_factory, bypass_permission_auth):
    from routes.tickets import tickets_bp

    app = app_factory(tickets_bp)
    return app.test_client()


class TestTicketsAuth:
    def test_list_requires_login(self, tickets_client):
        with _ticket_patches(), unauthenticated_client(tickets_client):
            resp = tickets_client.get("/tickets/")
        assert resp.status_code == 401

    def test_list_forbidden_without_permission(
        self, tickets_client, bypass_permission_auth
    ):
        bypass_permission_auth.has_permission.return_value = False
        bypass_permission_auth.is_super_admin.return_value = False
        with (
            _ticket_patches(),
            patch("utils.decorators.is_global_owner_user", return_value=False),
        ):
            resp = tickets_client.get("/tickets/")
        assert resp.status_code == 403


class TestTicketsList:
    def test_list_renders(self, tickets_client):
        with _ticket_patches(tickets=[_mock_ticket()]):
            resp = tickets_client.get("/tickets/")
        assert resp.status_code == 200

    def test_list_with_filters(self, tickets_client):
        with _ticket_patches():
            resp = tickets_client.get(
                "/tickets/?status=open&category_id=1&assigned_user_id=2&search=bug"
            )
        assert resp.status_code == 200


class TestTicketsCreate:
    def test_create_get(self, tickets_client):
        with _ticket_patches():
            resp = tickets_client.get("/tickets/create")
        assert resp.status_code == 200

    def test_create_post_success(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.create_ticket",
                return_value=_mock_ticket(),
            ),
        ):
            resp = tickets_client.post(
                "/tickets/create", data={"subject": "Help"}, follow_redirects=False
            )
        assert resp.status_code == 302
        assert "/tickets/" in resp.location

    def test_create_post_error(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.create_ticket",
                side_effect=ValueError("required"),
            ),
        ):
            resp = tickets_client.post("/tickets/create", data={})
        assert resp.status_code == 200


class TestTicketsDetail:
    def test_detail_success(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.get_ticket", return_value=_mock_ticket()
            ),
        ):
            resp = tickets_client.get("/tickets/7")
        assert resp.status_code == 200

    def test_detail_cross_tenant_redirects(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.get_ticket",
                side_effect=ValueError("tenant"),
            ),
        ):
            resp = tickets_client.get("/tickets/7", follow_redirects=False)
        assert resp.status_code == 302


class TestTicketsWorkflow:
    def test_add_comment_success(self, tickets_client):
        with (
            _ticket_patches(),
            patch("routes.tickets.TicketService.add_comment", return_value=MagicMock()),
        ):
            resp = tickets_client.post(
                "/tickets/1/comment", data={"body": "note"}, follow_redirects=False
            )
        assert resp.status_code == 302

    def test_add_comment_error(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.add_comment",
                side_effect=ValueError("empty"),
            ),
        ):
            resp = tickets_client.post(
                "/tickets/1/comment", data={}, follow_redirects=False
            )
        assert resp.status_code == 302

    def test_assign_success(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.assign_ticket",
                return_value=_mock_ticket(),
            ),
        ):
            resp = tickets_client.post(
                "/tickets/1/assign",
                data={"assigned_user_id": "5"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_assign_error(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.assign_ticket",
                side_effect=ValueError("bad"),
            ),
        ):
            resp = tickets_client.post(
                "/tickets/1/assign", data={}, follow_redirects=False
            )
        assert resp.status_code == 302

    def test_resolve_success(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.resolve_ticket",
                return_value=_mock_ticket(status="resolved"),
            ),
        ):
            resp = tickets_client.post("/tickets/1/resolve", follow_redirects=False)
        assert resp.status_code == 302

    def test_resolve_error(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.resolve_ticket",
                side_effect=ValueError("gone"),
            ),
        ):
            resp = tickets_client.post("/tickets/1/resolve", follow_redirects=False)
        assert resp.status_code == 302

    def test_close_success(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.close_ticket",
                return_value=_mock_ticket(status="closed"),
            ),
        ):
            resp = tickets_client.post("/tickets/1/close", follow_redirects=False)
        assert resp.status_code == 302

    def test_close_error(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.close_ticket",
                side_effect=ValueError("gone"),
            ),
        ):
            resp = tickets_client.post("/tickets/1/close", follow_redirects=False)
        assert resp.status_code == 302

    def test_reopen_success(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.reopen_ticket",
                return_value=_mock_ticket(status="open"),
            ),
        ):
            resp = tickets_client.post("/tickets/1/reopen", follow_redirects=False)
        assert resp.status_code == 302

    def test_reopen_error(self, tickets_client):
        with (
            _ticket_patches(),
            patch(
                "routes.tickets.TicketService.reopen_ticket",
                side_effect=ValueError("gone"),
            ),
        ):
            resp = tickets_client.post("/tickets/1/reopen", follow_redirects=False)
        assert resp.status_code == 302
