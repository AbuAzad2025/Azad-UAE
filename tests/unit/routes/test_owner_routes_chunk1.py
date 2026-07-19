"""
Chunk 1 — routes/owner.py first 3 endpoints:
   1. GET /owner/master-login-info
   2. GET /owner/                     (redirects to dashboard)
   3. GET /owner/dashboard            (stats aggregation page)
"""

from decimal import Decimal
from itertools import cycle
from unittest.mock import MagicMock

import pytest

from tests.unit.routes.test_owner_routes import _owner_route_patches


def _make_dashboard_query(first_results=None, scalar_results=None):
    """Chain-query mock modeling db.session.query().filter().first()/.scalar().

    Models the query chains used by the dashboard route so that every
    ``db.session.query(...).filter(...)`` resolves to a self-referencing
    chain, with ``.first()`` / ``.scalar()`` returning the next value
    from the supplied iterables (cycling indefinitely).
    """
    q = MagicMock(name="dashboard_query")
    q.return_value = q
    for m in (
        "filter",
        "filter_by",
        "order_by",
        "join",
        "outerjoin",
        "group_by",
        "limit",
        "offset",
        "select_from",
    ):
        getattr(q, m).return_value = q

    q.first.return_value = (0, Decimal("0"), Decimal("0"))
    q.scalar.return_value = Decimal("0")
    q.join.return_value.filter.return_value.distinct.return_value.count.return_value = 0
    q.join.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
    q.outerjoin.return_value.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
    q.filter.return_value.group_by.return_value.all.return_value = []
    q.select_from.return_value.join.return_value.filter.return_value.scalar.return_value = Decimal(
        "0"
    )

    if first_results:
        q.first.side_effect = cycle(first_results)
    if scalar_results:
        q.scalar.side_effect = cycle(scalar_results)
    return q


@pytest.fixture
def owner_client(app_factory, bypass_owner_auth):
    with _owner_route_patches():
        from routes.owner import owner_bp

        app = app_factory(
            owner_bp,
            {"SQLALCHEMY_DATABASE_URI": "postgresql://user:pass@localhost/testdb"},
        )
        yield app.test_client()


class TestMasterLoginInfo:
    """GET /owner/master-login-info — template + master password info."""

    def test_returns_200_and_renders_template(self, owner_client, mocker):
        mock_status = {"enabled": True, "expires_at": "2026-06-23T23:59:59"}
        mock_password = "BREAK-GLASS-123"

        mocker.patch("utils.master_login.master_login_status", return_value=mock_status)
        mocker.patch(
            "utils.master_login.build_today_master_cleartext",
            return_value=mock_password,
        )
        mock_render = mocker.patch(
            "routes.owner.core.render_template", return_value="<html>rendered</html>"
        )

        resp = owner_client.get("/owner/master-login-info")

        assert resp.status_code == 200
        mock_render.assert_called_once_with(
            "owner/master_login_info.html",
            status=mock_status,
            today_password=mock_password,
        )


class TestOwnerRoot:
    """GET /owner/ — redirects to /owner/dashboard."""

    def test_root_redirects_to_dashboard(self, owner_client):
        resp = owner_client.get("/owner/")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/owner/dashboard")


class TestOwnerDashboard:
    """GET /owner/dashboard — many aggregated stats."""

    def test_returns_200_empty_stats(self, owner_client, mocker):
        mocker.patch("routes.owner.core.get_active_tenant_id", return_value=None)
        mocker.patch("routes.owner.core._owner_branch_scope", return_value=None)

        mocker.patch("utils.owner_panel.build_platform_overview", return_value={})
        mocker.patch("utils.owner_panel.build_tenant_management_rows", return_value=[])
        mocker.patch("utils.owner_panel.build_branding_overview_rows", return_value=[])
        mocker.patch("utils.owner_panel.build_system_health_summary", return_value={})
        mocker.patch(
            "services.backup_service.BackupService.list_backups", return_value=[]
        )
        mocker.patch("routes.owner.core.render_template", return_value="ok")

        resp = owner_client.get("/owner/dashboard")
        assert resp.status_code == 200

    def test_returns_200_with_data(self, owner_client, mocker):
        mocker.patch("routes.owner.core.get_active_tenant_id", return_value=None)
        mocker.patch("routes.owner.core._owner_branch_scope", return_value=None)

        mock_query = _make_dashboard_query(
            first_results=[
                (10, 5000.0, 500.0),
                (120, 60000.0),
                (80000.0, 40000.0),
                (15000.0, 25),
            ],
            scalar_results=[
                250000.0,
                30000.0,
                15000.0,
            ],
        )
        mocker.patch("routes.owner.core.db.session.query", mock_query)

        mocker.patch("utils.owner_panel.build_platform_overview", return_value={})
        mocker.patch("utils.owner_panel.build_tenant_management_rows", return_value=[])
        mocker.patch("utils.owner_panel.build_branding_overview_rows", return_value=[])
        mocker.patch("utils.owner_panel.build_system_health_summary", return_value={})
        mocker.patch(
            "services.backup_service.BackupService.list_backups", return_value=[]
        )
        mocker.patch("routes.owner.core.render_template", return_value="ok")

        resp = owner_client.get("/owner/dashboard")
        assert resp.status_code == 200
