"""Coverage boost for routes/partners.py.

Targets: arcs 87->90, 158->161 + lines 273-274, 289-290.
Real response paths via test client; PartnerService/DB mocked at boundaries.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query


def _partner_mock(pid=1):
    partner = MagicMock()
    partner.id = pid
    partner.tenant_id = 1
    partner.name = "Test Partner"
    partner.scope_type = "company"
    partner.scope_id = None
    partner.partner_type = "investor"
    partner.phone = None
    partner.email = None
    partner.address = None
    partner.id_number = None
    partner.investment_amount = Decimal("0")
    partner.share_percentage = Decimal("0")
    partner.fixed_monthly_amount = Decimal("0")
    partner.expense_share_percentage = Decimal("0")
    partner.loss_share_percentage = Decimal("0")
    partner.min_profit_threshold = Decimal("0")
    partner.is_active = True
    partner.notes = None
    partner.updated_at = None
    partner.get_balance_summary.return_value = {"balance": Decimal("0")}
    return partner


def _tenant_query_chain(**terminals):
    q = _chain_query(**terminals)
    partner = terminals.get("first") or _partner_mock()
    q.filter_by.return_value.first_or_404.return_value = partner
    return q


@pytest.fixture
def partners_cov2_client(app_factory, bypass_permission_auth):
    with (
        patch("routes.partners.render_template", return_value="ok") as render,
        patch(
            "routes.partners.tenant_query",
            side_effect=lambda model: _tenant_query_chain(all=[]),
        ),
        patch("routes.partners.db.session", MagicMock()) as session,
        patch("routes.partners.PartnerService") as service,
    ):
        from routes.partners import partners_bp

        app = app_factory(partners_bp)
        client = app.test_client()
        client._partners_mocks = {
            "render": render,
            "session": session,
            "service": service,
        }
        yield client


class TestCreateNonCompanyScope:
    """Arc 87->90: scope_type != company keeps the posted scope_id."""

    def test_create_branch_scope_keeps_scope_id(self, partners_cov2_client):
        resp = partners_cov2_client.post(
            "/partners/create",
            data={
                "name": "Branch Partner",
                "scope_type": "branch",
                "scope_id": "2",
                "investment_amount": "1000",
                "share_percentage": "25",
            },
        )
        assert resp.status_code in (302, 303)


class TestEditNonCompanyScope:
    """Arc 158->161: edit with scope_type != company keeps the posted scope_id."""

    def test_edit_branch_scope_keeps_scope_id(self, partners_cov2_client):
        partner = _partner_mock(2)
        with patch(
            "routes.partners.tenant_query",
            return_value=_tenant_query_chain(first=partner),
        ):
            resp = partners_cov2_client.post(
                "/partners/2/edit",
                data={
                    "name": "Updated Partner",
                    "scope_type": "branch",
                    "scope_id": "3",
                    "investment_amount": "500",
                    "share_percentage": "10",
                },
            )
        assert resp.status_code in (302, 303)
        assert partner.scope_type == "branch"
        assert partner.scope_id == 3


class TestApproveException:
    """Lines 273-274: approve_distribution raises -> danger flash + redirect."""

    def test_approve_exception_redirects(self, partners_cov2_client):
        partners_cov2_client._partners_mocks["service"].approve_distribution.side_effect = RuntimeError("approve down")
        resp = partners_cov2_client.post("/partners/distributions/7/approve")
        assert resp.status_code in (302, 303)


class TestPayException:
    """Lines 289-290: pay_distribution raises -> danger flash + redirect."""

    def test_pay_exception_redirects(self, partners_cov2_client):
        partners_cov2_client._partners_mocks["service"].pay_distribution.side_effect = RuntimeError("pay down")
        resp = partners_cov2_client.post("/partners/distributions/9/pay")
        assert resp.status_code in (302, 303)
