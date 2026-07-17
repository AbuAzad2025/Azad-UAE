from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import _chain_query, unauthenticated_client


def _partner_mock(pid=1):
    partner = MagicMock()
    partner.id = pid
    partner.tenant_id = 1
    partner.name = "Test Partner"
    partner.scope_type = "company"
    partner.scope_id = None
    partner.get_balance_summary.return_value = {"balance": Decimal("0")}
    return partner


def _tenant_query_chain(**terminals):
    q = _chain_query(**terminals)
    partner = terminals.get("first") or _partner_mock()
    q.filter_by.return_value.first_or_404.return_value = partner
    if terminals.get("not_found"):
        q.filter_by.return_value.first_or_404.side_effect = NotFound()
    return q


def _dist_tx_query_chain(items=None):
    q = MagicMock()
    q.filter_by.return_value = q
    q.filter.return_value = q
    q.order_by.return_value.limit.return_value.all.return_value = items or []
    return q


def _permission_denied(mock_user, denied_codes):
    mock_user.is_owner = False
    mock_user.has_permission.side_effect = lambda code: code not in denied_codes


@pytest.fixture
def partners_client(app_factory, bypass_permission_auth):
    with (
        patch("routes.partners.render_template", return_value="ok") as render,
        patch(
            "routes.partners.tenant_query",
            side_effect=lambda model: _tenant_query_chain(all=[]),
        ),
        patch("routes.partners.db.session", MagicMock()) as session,
        patch("routes.partners.PartnerService") as service,
        patch("routes.partners.PartnerProfitDistribution") as dist_model,
        patch("routes.partners.PartnerTransaction") as tx_model,
    ):
        dist_model.query = _dist_tx_query_chain()
        tx_model.query = _dist_tx_query_chain()
        from routes.partners import partners_bp

        app = app_factory(partners_bp)
        client = app.test_client()
        client._partners_mocks = {
            "render": render,
            "session": session,
            "service": service,
            "dist_model": dist_model,
            "tx_model": tx_model,
        }
        yield client


class TestPartnersIndex:
    def test_index_returns_200(self, partners_client):
        resp = partners_client.get("/partners/")
        assert resp.status_code == 200

    def test_index_with_scope_filter(self, partners_client):
        with patch(
            "routes.partners.tenant_query", return_value=_tenant_query_chain(all=[])
        ) as tq:
            resp = partners_client.get("/partners/?scope=branch")
            assert resp.status_code == 200
            chain = tq.return_value
            chain.filter_by.assert_called_with(scope_type="branch")

    def test_index_renders_template(self, partners_client):
        partners_client._partners_mocks["render"].return_value = "index-page"
        resp = partners_client.get("/partners/")
        assert resp.status_code == 200
        assert (
            "partners/index.html"
            in partners_client._partners_mocks["render"].call_args[0][0]
        )


class TestPartnersCreate:
    def test_create_get_returns_200(self, partners_client):
        resp = partners_client.get("/partners/create")
        assert resp.status_code == 200
        assert (
            "partners/create.html"
            in partners_client._partners_mocks["render"].call_args[0][0]
        )

    def test_create_post_success_redirects(self, partners_client):
        resp = partners_client.post(
            "/partners/create",
            data={
                "name": "New Partner",
                "scope_type": "company",
                "investment_amount": "1000",
                "share_percentage": "25",
            },
        )
        assert resp.status_code in (302, 303)
        partners_client._partners_mocks["session"].add.assert_called_once()
        partners_client._partners_mocks["session"].commit.assert_called_once()

    def test_create_post_exception_rolls_back(self, partners_client):
        with patch("utils.db_safety.db.session") as mock_safety_session:
            mock_safety_session.commit.side_effect = RuntimeError("db fail")
            resp = partners_client.post(
                "/partners/create",
                data={
                    "name": "Bad Partner",
                    "scope_type": "company",
                },
            )
        assert resp.status_code == 200
        mock_safety_session.rollback.assert_called_once()


class TestPartnersView:
    def test_view_returns_200(self, partners_client):
        partner = _partner_mock(5)
        with patch(
            "routes.partners.tenant_query",
            return_value=_tenant_query_chain(first=partner),
        ):
            resp = partners_client.get("/partners/5")
        assert resp.status_code == 200
        partners_client._partners_mocks["render"].assert_called()
        kwargs = partners_client._partners_mocks["render"].call_args[1]
        assert kwargs["partner"] is partner

    def test_view_includes_distributions_and_transactions(self, partners_client):
        partner = _partner_mock(3)
        dist_q = _dist_tx_query_chain([MagicMock()])
        tx_q = _dist_tx_query_chain([MagicMock()])
        with (
            patch(
                "routes.partners.tenant_query",
                return_value=_tenant_query_chain(first=partner),
            ),
            patch("routes.partners.PartnerProfitDistribution") as dist_model,
            patch("routes.partners.PartnerTransaction") as tx_model,
        ):
            dist_model.query = dist_q
            tx_model.query = tx_q
            resp = partners_client.get("/partners/3")
        assert resp.status_code == 200


class TestPartnersEdit:
    def test_edit_get_returns_200(self, partners_client):
        partner = _partner_mock(2)
        with patch(
            "routes.partners.tenant_query",
            return_value=_tenant_query_chain(first=partner),
        ):
            resp = partners_client.get("/partners/2/edit")
        assert resp.status_code == 200
        assert (
            "partners/edit.html"
            in partners_client._partners_mocks["render"].call_args[0][0]
        )

    def test_edit_post_success_redirects(self, partners_client):
        partner = _partner_mock(2)
        with patch(
            "routes.partners.tenant_query",
            return_value=_tenant_query_chain(first=partner),
        ):
            resp = partners_client.post(
                "/partners/2/edit",
                data={
                    "name": "Updated Partner",
                    "scope_type": "company",
                    "investment_amount": "500",
                    "share_percentage": "10",
                },
            )
        assert resp.status_code in (302, 303)
        partners_client._partners_mocks["session"].commit.assert_called()

    def test_edit_post_exception_rolls_back(self, partners_client):
        partner = _partner_mock(2)
        with patch("utils.db_safety.db.session") as mock_safety_session:
            mock_safety_session.commit.side_effect = RuntimeError("fail")
            with patch(
                "routes.partners.tenant_query",
                return_value=_tenant_query_chain(first=partner),
            ):
                resp = partners_client.post(
                    "/partners/2/edit", data={"name": "X", "scope_type": "company"}
                )
        assert resp.status_code == 200
        mock_safety_session.rollback.assert_called_once()


class TestPartnersStatement:
    def test_statement_with_date_args(self, partners_client):
        partner = _partner_mock(4)
        stmt = {"opening": Decimal("0"), "closing": Decimal("100")}
        partners_client._partners_mocks[
            "service"
        ].get_partner_statement.return_value = stmt
        with patch(
            "routes.partners.tenant_query",
            return_value=_tenant_query_chain(first=partner),
        ):
            resp = partners_client.get(
                "/partners/4/statement",
                query_string={"start_date": "2025-01-01", "end_date": "2025-06-30"},
            )
        assert resp.status_code == 200
        partners_client._partners_mocks[
            "service"
        ].get_partner_statement.assert_called_once()
        call_args = partners_client._partners_mocks[
            "service"
        ].get_partner_statement.call_args[0]
        assert call_args[0] == 4
        assert str(call_args[1]) == "2025-01-01"
        assert str(call_args[2]) == "2025-06-30"

    def test_statement_default_start_is_month_start(self, partners_client):
        partner = _partner_mock(4)
        partners_client._partners_mocks[
            "service"
        ].get_partner_statement.return_value = {}
        with patch(
            "routes.partners.tenant_query",
            return_value=_tenant_query_chain(first=partner),
        ):
            resp = partners_client.get(
                "/partners/4/statement",
                query_string={"end_date": "2025-06-15"},
            )
        assert resp.status_code == 200
        call_args = partners_client._partners_mocks[
            "service"
        ].get_partner_statement.call_args[0]
        assert str(call_args[1]) == "2025-06-01"


class TestPartnersDistributions:
    def test_distributions_returns_200(self, partners_client):
        dist_q = MagicMock()
        dist_q.filter_by.return_value = dist_q
        dist_q.order_by.return_value.limit.return_value.all.return_value = []
        with patch("routes.partners.PartnerProfitDistribution") as dist_model:
            dist_model.query = dist_q
            resp = partners_client.get("/partners/distributions")
        assert resp.status_code == 200
        assert (
            "partners/distributions.html"
            in partners_client._partners_mocks["render"].call_args[0][0]
        )

    def test_distributions_with_status_filter(self, partners_client):
        dist_q = MagicMock()
        dist_q.filter_by.return_value = dist_q
        dist_q.order_by.return_value.limit.return_value.all.return_value = []
        with patch("routes.partners.PartnerProfitDistribution") as dist_model:
            dist_model.query = dist_q
            resp = partners_client.get("/partners/distributions?status=draft")
        assert resp.status_code == 200
        dist_q.filter_by.assert_any_call(status="draft")


class TestPartnersDistribute:
    def test_distribute_get_returns_200(self, partners_client):
        resp = partners_client.get("/partners/distribute")
        assert resp.status_code == 200
        assert (
            "partners/distribute.html"
            in partners_client._partners_mocks["render"].call_args[0][0]
        )

    def test_distribute_post_success(self, partners_client):
        partners_client._partners_mocks["service"].create_distributions.return_value = [
            1,
            2,
        ]
        resp = partners_client.post(
            "/partners/distribute",
            data={
                "period_start": "2025-05-01",
                "period_end": "2025-05-31",
            },
        )
        assert resp.status_code in (302, 303)
        partners_client._partners_mocks[
            "service"
        ].create_distributions.assert_called_once()

    def test_distribute_post_exception(self, partners_client):
        partners_client._partners_mocks[
            "service"
        ].create_distributions.side_effect = ValueError("no profit")
        resp = partners_client.post(
            "/partners/distribute",
            data={
                "period_start": "2025-05-01",
                "period_end": "2025-05-31",
            },
        )
        assert resp.status_code == 200


class TestPartnersApprovePayDistribution:
    def test_approve_distribution_success(self, partners_client):
        partners_client._partners_mocks[
            "service"
        ].approve_distribution.return_value = True
        resp = partners_client.post("/partners/distributions/7/approve")
        assert resp.status_code in (302, 303)
        partners_client._partners_mocks[
            "service"
        ].approve_distribution.assert_called_once_with(7, 42, tenant_id=1)

    def test_approve_distribution_failure(self, partners_client):
        partners_client._partners_mocks[
            "service"
        ].approve_distribution.return_value = False
        resp = partners_client.post("/partners/distributions/7/approve")
        assert resp.status_code in (302, 303)

    def test_pay_distribution_success(self, partners_client):
        partners_client._partners_mocks["service"].pay_distribution.return_value = True
        resp = partners_client.post("/partners/distributions/9/pay")
        assert resp.status_code in (302, 303)
        partners_client._partners_mocks[
            "service"
        ].pay_distribution.assert_called_once_with(9, tenant_id=1)

    def test_pay_distribution_failure(self, partners_client):
        partners_client._partners_mocks["service"].pay_distribution.return_value = False
        resp = partners_client.post("/partners/distributions/9/pay")
        assert resp.status_code in (302, 303)


class TestPartnersAddTransaction:
    def test_add_transaction_deposit(self, partners_client):
        partners_client._partners_mocks["service"].add_transaction.return_value = 99
        resp = partners_client.post(
            "/partners/3/tx",
            data={
                "transaction_type": "deposit",
                "amount": "500",
                "notes": "extra investment",
            },
        )
        assert resp.status_code in (302, 303)
        call_kw = partners_client._partners_mocks["service"].add_transaction.call_args[
            1
        ]
        assert call_kw["amount"] == Decimal("500")
        assert call_kw["transaction_type"] == "deposit"

    def test_add_transaction_withdrawal_negates_amount(self, partners_client):
        partners_client._partners_mocks["service"].add_transaction.return_value = 100
        resp = partners_client.post(
            "/partners/3/tx",
            data={
                "transaction_type": "withdrawal",
                "amount": "250",
            },
        )
        assert resp.status_code in (302, 303)
        call_kw = partners_client._partners_mocks["service"].add_transaction.call_args[
            1
        ]
        assert call_kw["amount"] == Decimal("-250")

    def test_add_transaction_partner_not_found(self, partners_client):
        partners_client._partners_mocks["service"].add_transaction.return_value = None
        resp = partners_client.post(
            "/partners/3/tx",
            data={
                "transaction_type": "adjustment",
                "amount": "10",
            },
        )
        assert resp.status_code in (302, 303)

    def test_add_transaction_exception(self, partners_client):
        partners_client._partners_mocks[
            "service"
        ].add_transaction.side_effect = RuntimeError("fail")
        resp = partners_client.post(
            "/partners/3/tx",
            data={
                "transaction_type": "deposit",
                "amount": "1",
            },
        )
        assert resp.status_code in (302, 303)


class TestPartnersApiPreviewPnl:
    def test_api_preview_pnl_returns_json(self, partners_client):
        pnl = {"revenue": 1000, "expenses": 400, "net_profit": 600}
        partners_client._partners_mocks[
            "service"
        ].calculate_scope_profit.return_value = pnl
        resp = partners_client.get(
            "/partners/api/preview-pnl",
            query_string={
                "start": "2025-01-01",
                "end": "2025-06-30",
                "scope_type": "branch",
                "scope_id": "2",
            },
        )
        assert resp.status_code == 200
        assert resp.get_json() == pnl
        partners_client._partners_mocks[
            "service"
        ].calculate_scope_profit.assert_called_once()


class TestPartnersAuth:
    def test_unauthenticated_index_returns_401(self, partners_client):
        with unauthenticated_client(partners_client):
            resp = partners_client.get("/partners/")
            assert resp.status_code in (302, 401)

    def test_unauthenticated_create_returns_401(self, partners_client):
        with unauthenticated_client(partners_client):
            resp = partners_client.get("/partners/create")
            assert resp.status_code in (302, 401)

    def test_forbidden_without_manage_users(self, partners_client, mock_user):
        _permission_denied(mock_user, {"manage_users"})
        with (
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
        ):
            resp = partners_client.get("/partners/create")
        assert resp.status_code == 403

    def test_forbidden_create_post_without_manage_users(
        self, partners_client, mock_user
    ):
        _permission_denied(mock_user, {"manage_users"})
        with (
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
        ):
            resp = partners_client.post("/partners/create", data={"name": "X"})
        assert resp.status_code == 403

    def test_forbidden_pay_without_manage_payments(self, partners_client, mock_user):
        _permission_denied(mock_user, {"manage_payments"})
        with (
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
        ):
            resp = partners_client.post("/partners/distributions/1/pay")
        assert resp.status_code == 403

    def test_forbidden_add_transaction_without_manage_payments(
        self, partners_client, mock_user
    ):
        _permission_denied(mock_user, {"manage_payments"})
        with (
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
        ):
            resp = partners_client.post(
                "/partners/1/tx",
                data={
                    "transaction_type": "deposit",
                    "amount": "10",
                },
            )
        assert resp.status_code == 403
