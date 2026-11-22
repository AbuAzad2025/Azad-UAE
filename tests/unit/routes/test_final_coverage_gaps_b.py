"""Last remaining statement gaps in a set of small route/model modules.

Every test here drives one specific uncovered statement through its real
callable (direct helper call or HTTP request) with the surrounding services
mocked at the boundary.  Production code and existing tests are untouched.
"""

from __future__ import annotations

import sys
from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from flask import Blueprint

from tests.unit.routes.test_cheques_routes import _cheque_patches, _mock_cheque
from tests.unit.routes.test_ledger_routes import _ledger_patches

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fake_stripe(mocker, event):
    """Install a minimal fake `stripe` module for the webhook route."""
    stripe_mod = MagicMock(name="stripe")
    stripe_mod.error.SignatureVerificationError = type("SignatureVerificationError", (Exception,), {})
    stripe_mod.Webhook.construct_event.return_value = event
    mocker.patch.dict(sys.modules, {"stripe": stripe_mod})
    return stripe_mod


# ---------------------------------------------------------------------------
# routes/public.py — lines 83-84
# ---------------------------------------------------------------------------


class TestPublicGaps:
    def test_active_stores_degrades_when_service_fails(self):
        from routes import public as pub

        with patch("services.user_service.UserService.active_tenants", side_effect=RuntimeError("db down")):
            assert pub._active_stores() == []


# ---------------------------------------------------------------------------
# routes/ai_routes/assistant.py — lines 292-293
# ---------------------------------------------------------------------------


class TestAssistantGaps:
    def test_excel_training_failure_is_logged_and_swallowed(self):
        from routes.ai_routes import assistant

        # An empty sheet with three detectable columns still reaches the
        # training hook; no Product rows are created so no DB is touched.
        df = pd.DataFrame(columns=["name", "part_number", "price"])
        user = SimpleNamespace(id=42, tenant_id=1)
        with (
            patch("routes.ai_routes.assistant.get_active_tenant_id", return_value=1),
            patch("pandas.read_excel", return_value=df),
            patch(
                "routes.ai_routes.assistant.PlatformQueryService.warehouse_in_tenant",
                return_value=SimpleNamespace(name="Main"),
            ),
            patch("routes.ai_routes.assistant.atomic_transaction", return_value=nullcontext()),
            patch("routes.ai_routes.assistant._train_ai_from_excel", side_effect=RuntimeError("trainer down")),
            patch("routes.ai_routes.assistant.logger.exception") as logged,
        ):
            result = assistant._process_excel_intelligently(MagicMock(), 7, user)

        assert result["success"] is True
        logged.assert_called_once()


# ---------------------------------------------------------------------------
# routes/reports.py — lines 490 and 492
# ---------------------------------------------------------------------------


@pytest.fixture
def gap_reports_client(app_factory, bypass_reports_auth):
    from routes.reports import reports_bp

    app = app_factory(reports_bp)
    with patch("routes.reports.render_template", return_value="ok"):
        yield app.test_client()


class TestReportsGaps:
    def test_inactive_warehouse_export_is_forbidden(self, gap_reports_client, mock_user):
        mock_user.is_admin.return_value = True
        warehouse = SimpleNamespace(id=5, tenant_id=1, branch_id=1, is_active=False)
        with (
            patch("utils.tenanting.tenant_get_or_404", return_value=warehouse),
            patch("utils.branching.user_can_access_branch", return_value=True),
        ):
            resp = gap_reports_client.get("/reports/inventory-reconciliation/export?warehouse_id=5&branch_id=1")
        assert resp.status_code == 403

    def test_warehouse_from_another_branch_export_is_forbidden(self, gap_reports_client, mock_user):
        mock_user.is_admin.return_value = True
        warehouse = SimpleNamespace(id=5, tenant_id=1, branch_id=2, is_active=True)
        with (
            patch("utils.tenanting.tenant_get_or_404", return_value=warehouse),
            patch("utils.branching.user_can_access_branch", return_value=True),
        ):
            resp = gap_reports_client.get("/reports/inventory-reconciliation/export?warehouse_id=5&branch_id=1")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# routes/quotations.py — lines 157 and 169
# ---------------------------------------------------------------------------


@pytest.fixture
def quotations_gap_client(app_factory, bypass_permission_auth):
    from routes.quotations import quotations_bp

    app = app_factory(quotations_bp)
    # The convert route redirects with url_for("sales.view", ...).
    sales_bp = Blueprint("sales", __name__)

    @sales_bp.route("/sales/<int:id>")
    def view(id):
        return "ok"

    app.register_blueprint(sales_bp)
    return app.test_client()


class TestQuotationsGaps:
    def test_convert_skips_accessible_warehouse_outside_branch(self, quotations_gap_client):
        quotation = SimpleNamespace(
            id=1,
            tenant_id=1,
            warehouse_id=None,
            branch_id=2,
            lines=[SimpleNamespace(product_id=3, quantity=1)],
        )
        sale = SimpleNamespace(id=10)
        with (
            patch("routes.quotations.QuotationService.get_quotation", return_value=quotation),
            patch("utils.branching.get_accessible_warehouse_ids", return_value=[9]),
            patch("routes.quotations.Warehouse.query") as warehouse_query,
            patch("routes.quotations.atomic_transaction", return_value=nullcontext()),
            patch("routes.quotations.QuotationService.convert_to_sale", return_value=sale),
        ):
            warehouse_query.filter_by.return_value.first.return_value = None
            resp = quotations_gap_client.post("/quotations/1/convert", follow_redirects=False)

        assert resp.status_code == 302
        assert "/sales/" in resp.location

    def test_convert_rejects_selected_warehouse_outside_branch(self, quotations_gap_client):
        quotation = SimpleNamespace(id=1, tenant_id=1, warehouse_id=5, branch_id=2, lines=[])
        with (
            patch("routes.quotations.QuotationService.get_quotation", return_value=quotation),
            patch("routes.quotations.Warehouse.query") as warehouse_query,
        ):
            warehouse_query.filter_by.return_value.first.return_value = None
            resp = quotations_gap_client.post("/quotations/1/convert", follow_redirects=False)

        assert resp.status_code == 302
        assert "/quotations/1" in resp.location


# ---------------------------------------------------------------------------
# routes/billing_webhooks.py — lines 135-136
# ---------------------------------------------------------------------------


class TestBillingWebhookGaps:
    def test_stripe_dedup_backend_unavailable_returns_503(self, app, client, mocker):
        from routes.payment_vault import WebhookDedupUnavailable

        app.config["STRIPE_WEBHOOK_SECRET"] = "whsec_final_gap"
        _fake_stripe(
            mocker,
            {"id": "evt_final_gap", "type": "unhandled.event", "data": {"object": {}}},
        )
        with patch("routes.billing_webhooks._is_duplicate", side_effect=WebhookDedupUnavailable("no backend")):
            resp = client.post("/billing-webhook/stripe", data=b"payload")

        assert resp.status_code == 503
        assert resp.get_json()["message"] == "Webhook temporarily unavailable"


# ---------------------------------------------------------------------------
# routes/owner/shared.py — lines 230-232
# ---------------------------------------------------------------------------


class TestOwnerSharedGaps:
    def test_owner_branch_scope_delegates_to_decorator_helper(self):
        from routes.owner import shared

        with patch("utils.decorators.branch_scope_id", return_value=7) as scope:
            assert shared._owner_branch_scope() == 7
        scope.assert_called_once_with()


# ---------------------------------------------------------------------------
# routes/returns.py — line 106
# ---------------------------------------------------------------------------


@pytest.fixture
def returns_gap_app(app_factory, bypass_permission_auth):
    from routes.returns import returns_bp

    return app_factory(returns_bp)


class TestReturnsGaps:
    def test_idempotency_error_short_circuits_create(self, returns_gap_app):
        from services.idempotency_service import IdempotencyHashMismatchError

        client = returns_gap_app.test_client()
        with (
            patch("routes.returns.tenant_get_or_404"),
            patch("routes.returns.atomic_transaction", return_value=nullcontext()),
            patch("routes.returns.IdempotencyService.begin", side_effect=IdempotencyHashMismatchError),
        ):
            resp = client.post(
                "/returns/api/create",
                json={"sale_id": 10, "lines": [{"sale_line_id": 1, "quantity": 1}]},
                headers={"Idempotency-Key": "reused-with-new-payload"},
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# routes/cheques.py — line 449
# ---------------------------------------------------------------------------


@pytest.fixture
def gap_cheques_client(app_factory, bypass_permission_auth):
    from routes.cheques import cheques_bp

    app = app_factory(cheques_bp)
    return app.test_client()


class TestChequesGaps:
    def test_posted_cheque_amount_change_is_refused(self, gap_cheques_client):
        cheque = _mock_cheque(amount=Decimal("1000"))
        gl_query = MagicMock()
        gl_query.filter.return_value.first.return_value = MagicMock()
        with (
            _cheque_patches(cheque=cheque),
            patch("models.GLJournalEntry.query", gl_query),
            patch("routes.cheques._refuse") as refuse,
        ):
            resp = gap_cheques_client.post(
                "/cheques/1/edit",
                data={"amount": "2000"},
                follow_redirects=False,
            )

        assert resp is not None
        refuse.assert_called_once()
        assert isinstance(refuse.call_args.args[0], ValueError)


# ---------------------------------------------------------------------------
# routes/api_docs.py — line 33
# ---------------------------------------------------------------------------


class TestApiDocsGaps:
    def test_authenticated_non_admin_role_is_404(self, app_factory, mocker):
        from routes.api_docs import api_docs_bp

        user = MagicMock(is_authenticated=True)
        user.role.slug = "manager"
        mocker.patch("flask_login.utils._get_user", return_value=user)
        app = app_factory(api_docs_bp)

        with patch("routes.api_docs._api_docs_public", return_value=False):
            resp = app.test_client().get("/api-docs/openapi.json")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# routes/ledger.py — line 432
# ---------------------------------------------------------------------------


@pytest.fixture
def gap_ledger_client(app_factory, bypass_permission_auth):
    from routes.ledger import ledger_bp

    app = app_factory(ledger_bp)
    return app.test_client()


class TestLedgerGaps:
    def test_missing_account_statement_returns_404(self, gap_ledger_client):
        with (
            _ledger_patches(statement=None),
            patch("routes.ledger.GLService.get_scoped_account_or_404", return_value=MagicMock()),
        ):
            resp = gap_ledger_client.get("/ledger/account/999/statement")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# models — reachable statements (TYPE_CHECKING imports are unreachable at runtime)
# ---------------------------------------------------------------------------


class TestModelGaps:
    def test_tenant_secret_repr(self):
        from models.tenant_secret import TenantSecret

        secret = TenantSecret(name="zatca-csid", tenant_id=3)
        assert repr(secret) == "<TenantSecret zatca-csid tenant=3>"

    def test_transient_customer_locked_returns_self(self):
        from models.customer import Customer

        customer = Customer(name="Transient")
        assert customer._locked() is customer

    def test_einvoice_repr(self):
        from models.einvoice import EInvoice

        invoice = EInvoice(country="SA", sale_id=12, format="ubl-2.1")
        assert repr(invoice) == "<EInvoice SA sale=12 ubl-2.1>"
