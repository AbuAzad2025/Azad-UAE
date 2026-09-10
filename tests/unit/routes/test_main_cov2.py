"""Coverage boost for routes/main.py.

Targets: line 31 + arcs 137->141, 139-140, 301->309.
Real response paths via test client; services/DB mocked only at boundaries.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query


@contextmanager
def _main_cov2_patches(**kwargs):
    with ExitStack() as stack:
        stack.enter_context(patch("routes.main.render_template", return_value="ok"))
        tid = kwargs.get("tid", 1)
        stack.enter_context(patch("routes.main.get_active_tenant_id", return_value=tid))
        stack.enter_context(patch("routes.main.branch_scope_id", return_value=kwargs.get("branch_scope")))
        stack.enter_context(patch("utils.tenanting.tenant_query", return_value=_chain_query(count=5)))
        stack.enter_context(patch("routes.main.get_visible_products_query", return_value=_chain_query(count=10)))
        stack.enter_context(
            patch(
                "services.main_site_service.MainSiteService.count_active_products",
                return_value=kwargs.get("products_count", 0),
            )
        )
        stack.enter_context(patch("routes.main.StockService.get_low_stock_products", return_value=[]))
        stack.enter_context(patch("routes.main.StockService.get_out_of_stock_products", return_value=[]))
        stack.enter_context(patch("routes.main.db.session"))
        stack.enter_context(patch("extensions.db.session"))
        yield


@pytest.fixture
def main_cov2_client(app_factory, bypass_permission_auth):
    from routes.auth import auth_bp
    from routes.main import main_bp

    app = app_factory(main_bp, auth_bp)
    return app.test_client()


class TestLoginAlias:
    """Line 31: /login redirects to auth.login."""

    def test_login_alias_redirects(self, main_cov2_client):
        resp = main_cov2_client.get("/login", follow_redirects=False)
        assert resp.status_code == 302


def _dashboard_query_side_effect():
    def _query(*_args, **_kwargs):
        q = MagicMock()
        q.filter.return_value = q
        q.join.return_value = q
        q.select_from.return_value = q
        q.scalar.return_value = 0
        q.first.return_value = (0, 0)
        q.all.return_value = []
        return q

    return _query


class TestDashboardUsageSummary:
    """Arc 137->141: tid falsy skips usage-summary lookup."""

    def test_dashboard_without_tid_skips_usage(self, main_cov2_client, bypass_permission_auth):
        bypass_permission_auth.can_see_costs.return_value = False
        with (
            _main_cov2_patches(tid=None),
            patch("routes.main.db.session.query", side_effect=_dashboard_query_side_effect()),
            patch("routes.main.render_template", return_value="ok") as render,
        ):
            resp = main_cov2_client.get("/dashboard")
        assert resp.status_code == 200
        assert "usage_summary" in render.call_args[1]["stats"]

    """Arc 139-140: usage-summary exception is swallowed with error log."""

    def test_dashboard_usage_exception_swallowed(self, main_cov2_client, bypass_permission_auth):
        bypass_permission_auth.can_see_costs.return_value = False
        tenant = MagicMock()
        with (
            _main_cov2_patches(tid=1),
            patch("routes.main.db.session.query", side_effect=_dashboard_query_side_effect()),
            patch("routes.main.db.session.get", return_value=tenant),
            patch(
                "utils.tenant_limits.get_tenant_usage_summary",
                side_effect=RuntimeError("limits down"),
            ),
        ):
            resp = main_cov2_client.get("/dashboard")
        assert resp.status_code == 200


class TestProfileUpdateEmptyEmail:
    """Arc 301->309: email field present but sanitizes to empty."""

    def test_empty_sanitized_email_skips_update(self, main_cov2_client, bypass_permission_auth):
        with (
            patch("utils.sanitizer.InputSanitizer.sanitize_email", return_value=""),
            patch("routes.main.db.session"),
        ):
            resp = main_cov2_client.post(
                "/my-profile/update",
                data={"email": "   "},
                follow_redirects=False,
            )
        assert resp.status_code == 302
