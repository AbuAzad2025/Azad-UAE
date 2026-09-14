"""Gap100 for routes/admin_ledger.py — invalid code/type edit (236-240) +
trial-balance nonzero arcs (404-412)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_account(**kwargs):
    account = MagicMock()
    account.id = kwargs.get("id", 1)
    account.code = kwargs.get("code", "1201")
    account.type = kwargs.get("type", "asset")
    account.name = "Cash"
    return account


def _accounts_query_for(account):
    q = MagicMock(name="admin_accounts_query")

    def filter_by(**kwargs):
        inner = MagicMock()
        if kwargs.get("id") is not None:
            inner.first_or_404.return_value = account
            inner.first.return_value = account
        elif kwargs == {"is_active": True, "is_header": False}:
            inner.order_by.return_value.all.return_value = [account]
        else:
            inner.first.return_value = None
            inner.order_by.return_value.all.return_value = []
        return inner

    q.filter_by.side_effect = filter_by
    return q


@pytest.fixture
def admin_ledger_cov100_client(app_factory, bypass_admin_auth):
    from routes.admin_ledger import admin_ledger_bp

    app = app_factory(admin_ledger_bp)
    return app.test_client()


class TestEditAccountInvalidCodeType:
    def test_post_mismatched_code_type_redirects(self, admin_ledger_cov100_client):
        account = _mock_account(code="1201", type="asset")
        with (
            patch("routes.admin_ledger.gl_account_query", return_value=_accounts_query_for(account)),
            patch("routes.admin_ledger.render_template", return_value="ok"),
            patch("routes.admin_ledger.validate_account_code_type", return_value=False),
            patch("routes.admin_ledger.db.session"),
        ):
            resp = admin_ledger_cov100_client.post(
                "/admin/ledger/accounts/1/edit",
                data={"code": "2101", "type": "asset", "name": "Cash"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert "/admin/ledger/accounts/1/edit" in resp.headers["Location"]


class TestTrialBalanceNonzero:
    def test_debit_and_credit_rows_and_totals(self, admin_ledger_cov100_client):
        debit_acct = _mock_account(id=1, code="1101")
        credit_acct = _mock_account(id=2, code="2101", type="liability")

        def _accounts():
            q = MagicMock(name="tb_accounts_query")

            def filter_by(**kwargs):
                inner = MagicMock()
                inner.order_by.return_value.all.return_value = [debit_acct, credit_acct]
                return inner

            q.filter_by.side_effect = filter_by
            return q

        with (
            patch("routes.admin_ledger.gl_account_query", return_value=_accounts()),
            patch("routes.admin_ledger.render_template", return_value="ok") as render,
            patch(
                "routes.admin_ledger.GLService.get_all_account_balances",
                return_value={1: 150, 2: -40},
            ),
        ):
            resp = admin_ledger_cov100_client.get("/admin/ledger/reports/trial-balance")
        assert resp.status_code == 200
        kwargs = render.call_args[1]
        assert len(kwargs["trial_balance_data"]) == 2
        assert kwargs["total_debit"] == 150
        assert kwargs["total_credit"] == 40

    def test_zero_balances_excluded(self, admin_ledger_cov100_client):
        zero_acct = _mock_account(id=3, code="1102")

        def _accounts():
            q = MagicMock(name="tb_zero_accounts_query")

            def filter_by(**kwargs):
                inner = MagicMock()
                inner.order_by.return_value.all.return_value = [zero_acct]
                return inner

            q.filter_by.side_effect = filter_by
            return q

        with (
            patch("routes.admin_ledger.gl_account_query", return_value=_accounts()),
            patch("routes.admin_ledger.render_template", return_value="ok") as render,
            patch(
                "routes.admin_ledger.GLService.get_all_account_balances",
                return_value={},
            ),
        ):
            resp = admin_ledger_cov100_client.get("/admin/ledger/reports/trial-balance")
        assert resp.status_code == 200
        assert render.call_args[1]["trial_balance_data"] == []
