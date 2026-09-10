"""Coverage boost for routes/ledger.py.

Targets: lines 178, 295, 691.
Real response paths via test client; services/DB mocked only at boundaries.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.test_ledger_routes import (
    _ledger_patches,
    _mock_account,
)


@pytest.fixture
def ledger_cov2_client(app_factory, bypass_permission_auth):
    from routes.ledger import ledger_bp

    app = app_factory(ledger_bp)
    return app.test_client()


@pytest.fixture
def ledger_cov2_admin_client(app_factory, bypass_admin_auth):
    from routes.ledger import ledger_bp

    app = app_factory(ledger_bp)
    return app.test_client()


class TestGlPeriodsInnerGuard:
    """Line 178: POST /ledger/periods with view_ledger but without manage_ledger."""

    def test_post_aborts_when_manage_ledger_missing(self, ledger_cov2_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.side_effect = lambda code: code != "manage_ledger"
        with (
            _ledger_patches(),
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
        ):
            resp = ledger_cov2_client.post(
                "/ledger/periods",
                data={"year": "2026", "month": "5", "action": "close"},
                follow_redirects=False,
            )
        assert resp.status_code == 403


class TestAccountsTreeFallbackTenant:
    """Line 295: tenant None, not platform-owner-empty -> require_active_tenant_id."""

    def test_fallback_to_required_tenant(self, ledger_cov2_client):
        with (
            _ledger_patches(),
            patch("utils.tenanting.get_active_tenant_id", return_value=None),
            patch("utils.tenanting.is_platform_owner", return_value=False),
            patch("utils.tenanting.require_active_tenant_id", return_value=1),
            patch("routes.ledger.GLService.get_accounts_tree", return_value=[]),
        ):
            resp = ledger_cov2_client.get("/ledger/accounts-tree")
        assert resp.status_code == 200


class TestAdminDashboardHighBalance:
    """Line 691: high-balance account appended when abs(balance) > 1000."""

    def test_high_balance_branch_appended(self, ledger_cov2_admin_client):
        high = _mock_account(code="1101", balance=Decimal("5000"))
        high.id = 101
        low = _mock_account(code="1102", balance=Decimal("50"))
        low.id = 102
        acct_q = MagicMock()
        acct_q.count.return_value = 2
        acct_q.filter_by.return_value.count.return_value = 2
        acct_q.filter.return_value.all.return_value = [high]
        acct_q.filter_by.return_value.all.return_value = [high, low]
        acct_q.order_by.return_value.limit.return_value.all.return_value = []
        entry_q = MagicMock()
        entry_q.count.return_value = 5
        entry_q.filter_by.return_value.count.return_value = 4
        entry_q.order_by.return_value.limit.return_value.all.return_value = []
        scoped_q = MagicMock()
        scoped_q.count.return_value = 1
        scoped_q.filter_by.return_value.count.return_value = 1
        tenant_q = MagicMock()
        tenant_q.count.return_value = 0
        tenant_q.filter_by.return_value.count.return_value = 0
        with (
            _ledger_patches(),
            patch("utils.gl_tenant.gl_account_query", return_value=acct_q),
            patch("utils.gl_tenant.gl_entry_query", return_value=entry_q),
            patch("utils.gl_tenant.scoped_model_query", return_value=scoped_q),
            patch("utils.tenanting.tenant_query", return_value=tenant_q),
            patch(
                "services.gl_service.GLService.get_all_account_balances",
                return_value={101: Decimal("5000"), 102: Decimal("50")},
            ),
            patch("routes.ledger.render_template", return_value="ok") as render,
        ):
            resp = ledger_cov2_admin_client.get("/ledger/admin-dashboard")
        assert resp.status_code == 200
        kwargs = render.call_args[1]
        assert len(kwargs["high_balance_accounts"]) == 1
        assert kwargs["high_balance_accounts"][0]["balance"] == Decimal("5000")
