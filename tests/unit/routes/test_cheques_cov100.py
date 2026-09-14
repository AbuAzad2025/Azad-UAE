"""Gap100 for routes/cheques.py — untyped-cheque arc (317->319) + tenant-less view (369->371)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query


def _mock_cheque(**kwargs):
    c = MagicMock()
    c.id = kwargs.get("id", 1)
    c.tenant_id = kwargs.get("tenant_id", 1)
    c.branch_id = kwargs.get("branch_id", 1)
    c.cheque_number = kwargs.get("cheque_number", "CHQ-001")
    c.cheque_bank_number = kwargs.get("cheque_bank_number", "BNK-001")
    c.cheque_type = kwargs.get("cheque_type", "incoming")
    c.status = kwargs.get("status", "pending")
    c.currency = kwargs.get("currency", "AED")
    c.update_status_based_on_date = MagicMock()
    return c


@pytest.fixture
def cheques_cov100_client(app_factory, bypass_permission_auth):
    from routes.cheques import cheques_bp

    app = app_factory(cheques_bp)
    return app.test_client()


class TestChequeCreateUntyped:
    def test_create_other_type_skips_receive_and_issue(self, cheques_cov100_client):
        cheque = _mock_cheque(id=77, cheque_type="transfer")
        with (
            patch("routes.cheques.render_template", return_value="ok"),
            patch("routes.cheques.get_active_tenant_id", return_value=1),
            patch("routes.cheques.branch_scope_id", return_value=None),
            patch("routes.cheques._scoped_customers_query", return_value=_chain_query(all=[])),
            patch("routes.cheques._scoped_suppliers_query", return_value=_chain_query(all=[])),
            patch("routes.cheques.resolve_default_currency", return_value="AED"),
            patch("routes.cheques.get_system_default_currency", return_value="AED"),
            patch("routes.cheques.CurrencyService.get_all_rates", return_value={}),
            patch("routes.cheques._resolve_transaction_rate", return_value=1),
            patch("routes.cheques.generate_number", return_value="CHQ-NEW"),
            patch("routes.cheques.calculate_amount_aed"),
            patch("routes.cheques.process_cheque_receive") as recv,
            patch("routes.cheques.process_cheque_issue") as issue,
            patch("routes.cheques.LoggingCore.log_audit"),
            patch("extensions.limiter.limit", return_value=lambda f: f),
            patch("extensions.db.session"),
            patch("services.cheque_service.ChequeService.create_cheque", return_value=cheque),
        ):
            resp = cheques_cov100_client.post(
                "/cheques/create",
                data={
                    "cheque_type": "transfer",
                    "amount": "250",
                    "issue_date": "2026-01-01",
                    "due_date": "2026-02-01",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        recv.assert_not_called()
        issue.assert_not_called()


class TestChequeViewWithoutTenant:
    def test_view_without_current_tenant(self, cheques_cov100_client):
        cheque = _mock_cheque(id=78, currency="AED")
        with (
            patch("routes.cheques.render_template", return_value="ok") as render,
            patch("routes.cheques._get_cheque_or_404", return_value=cheque),
            patch("routes.cheques._ensure_cheque_scope", return_value=True),
            patch("models.Tenant.get_current", return_value=None),
            patch("routes.cheques.ExchangeRateService.get_latest_rate", return_value=1),
        ):
            resp = cheques_cov100_client.get("/cheques/78")
        assert resp.status_code == 200
        assert render.call_args.kwargs["is_foreign_currency"] is True


class TestIncomingWithoutStatus:
    def test_incoming_no_status_filter(self, cheques_cov100_client):
        with (
            patch("routes.cheques.render_template", return_value="ok") as render,
            patch("routes.cheques.get_active_tenant_id", return_value=1),
            patch("routes.cheques.branch_scope_id", return_value=None),
            patch("routes.cheques.Cheque.update_all_statuses"),
            patch(
                "routes.cheques._scoped_cheques_query",
                return_value=_chain_query(all=[_mock_cheque()]),
            ),
            patch("routes.cheques.Cheque.get_statistics", return_value={}),
        ):
            resp = cheques_cov100_client.get("/cheques/incoming")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "cheques/incoming.html"
