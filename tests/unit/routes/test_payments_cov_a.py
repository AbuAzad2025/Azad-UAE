"""Coverage for routes/payments.py gaps — file A.

Targets: arcs 116->118, 158->160, 260->264, 398->407; lines 509, 973.
Uses test client with mocks only at DB/external boundaries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def payments_cov_a_client(app_factory, bypass_permission_auth):
    from routes.payments import payments_bp
    from routes.public import public_bp

    app = app_factory(payments_bp, public_bp)
    return app.test_client()


def _mock_receipt_item(**kwargs):
    r = MagicMock()
    r.id = kwargs.get("id", 1)
    r.receipt_number = kwargs.get("receipt_number", "REC-001")
    r.receipt_date = kwargs.get("receipt_date", datetime.now(UTC))
    r.amount = kwargs.get("amount", Decimal("100"))
    r.currency = kwargs.get("currency", "AED")
    r.amount_aed = kwargs.get("amount_aed", Decimal("100"))
    r.direction = kwargs.get("direction", "incoming")
    r.customer = MagicMock()
    r.customer.name = kwargs.get("customer_name", "Customer A")
    r.supplier_name = None
    r.payment_method = kwargs.get("payment_method", "cash")
    r.payment_confirmed = kwargs.get("payment_confirmed", True)
    r.confirmation_date = None
    r.rejection_reason = None
    r.cheque_id = None
    r.source_type = kwargs.get("source_type", "manual")
    r.notes = ""
    r.branch_id = kwargs.get("branch_id")
    r.branch = None
    r.user_id = 42
    r.tenant_id = 1
    return r


def _mock_payment_item(**kwargs):
    p = MagicMock()
    p.id = kwargs.get("id", 2)
    p.payment_number = kwargs.get("payment_number", "PAY-001")
    p.payment_date = kwargs.get("payment_date", datetime.now(UTC))
    p.amount = kwargs.get("amount", Decimal("50"))
    p.currency = "AED"
    p.amount_aed = Decimal("50")
    p.direction = kwargs.get("direction", "outgoing")
    p.supplier_name = kwargs.get("supplier_name", "Supplier B")
    p.payment_method = "cash"
    p.payment_confirmed = True
    p.confirmation_date = None
    p.rejection_reason = None
    p.cheque_id = None
    p.payment_type = "bill_payment"
    p.notes = ""
    p.branch_id = kwargs.get("branch_id")
    p.branch = None
    p.user_id = 42
    p.tenant_id = 1
    return p


def _list_query(items, count=None):
    q = MagicMock()
    q.count.return_value = count if count is not None else len(items)
    q.order_by.return_value.limit.return_value.all.return_value = items
    q.filter.return_value = q
    q.join.return_value = q
    return q


class TestPaymentsCovAUnpaidSalesNoBranch:
    """Arc 116->118: _scoped_customer_unpaid_sales with branch_id None."""

    def test_customer_balance_no_branch_scope(self, payments_cov_a_client):
        customer = SimpleNamespace(id=7, name="NoBranch Customer")
        sale = SimpleNamespace(
            id=11,
            sale_number="S-11",
            sale_date=datetime.now(UTC),
            total_amount=Decimal("200"),
            balance_due=Decimal("200"),
            exchange_rate=Decimal("1"),
            currency="AED",
        )

        def tenant_query_side(model):
            name = getattr(model, "__name__", str(model))
            if name == "Customer":
                q = MagicMock()
                q.filter.return_value = q
                q.first.return_value = customer
                return q
            if name == "Sale":
                q = MagicMock()
                q.filter.return_value = q
                q.order_by.return_value.all.return_value = [sale]
                return q
            return MagicMock()

        with (
            patch("routes.payments.tenant_query", side_effect=tenant_query_side),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch(
                "routes.payments.PaymentService.get_customer_balance_scoped",
                return_value=Decimal("200"),
            ),
            patch("routes.payments.resolve_default_currency", return_value="AED"),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
        ):
            resp = payments_cov_a_client.get("/payments/api/customer-balance/7")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["balance_aed"] == 200.0
        assert body["data"]["unpaid_sales"][0]["sale_number"] == "S-11"


class TestPaymentsCovAUnknownDirectionTotals:
    """Arc 158->160: receipt item with direction neither incoming nor outgoing."""

    def test_receipts_json_unknown_direction(self, payments_cov_a_client):
        receipt = _mock_receipt_item(direction="mystery", amount=Decimal("75"))
        payment = _mock_payment_item(direction="mystery", amount=Decimal("25"))

        def tenant_query_side(model):
            name = getattr(model, "__name__", str(model))
            if name == "Receipt":
                return _list_query([receipt])
            if name == "Payment":
                return _list_query([payment])
            return _list_query([])

        with (
            patch("routes.payments.tenant_query", side_effect=tenant_query_side),
            patch("routes.payments.get_active_tenant_id", return_value=1),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.should_show_all_branch_columns", return_value=False),
        ):
            resp = payments_cov_a_client.get("/payments/receipts?format=json")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["totals"]["total_incoming"] == 0.0
        assert body["data"]["totals"]["total_outgoing"] == 0.0
        assert len(body["data"]["payments"]) == 2


class TestPaymentsCovAReceiptsNoTenant:
    """Arc 260->264: receipts list with active tenant id None."""

    def test_receipts_list_tid_none(self, payments_cov_a_client):
        receipt = _mock_receipt_item()
        payment = _mock_payment_item()

        def tenant_query_side(model):
            name = getattr(model, "__name__", str(model))
            if name == "Receipt":
                return _list_query([receipt])
            if name == "Payment":
                return _list_query([payment])
            return _list_query([])

        with (
            patch("routes.payments.tenant_query", side_effect=tenant_query_side),
            patch("routes.payments.get_active_tenant_id", return_value=None),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.should_show_all_branch_columns", return_value=False),
            patch("routes.payments.render_template", return_value="ok"),
        ):
            resp = payments_cov_a_client.get("/payments/receipts")
        assert resp.status_code == 200


class TestPaymentsCovACustomerSearchNoQuery:
    """Arc 398->407: customer search-entities without q filter."""

    def test_search_customers_without_q(self, payments_cov_a_client):
        customer = SimpleNamespace(id=3, name="NoQ Customer", phone="050", email="n@t.com")
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.limit.return_value.all.return_value = [customer]
        with patch("routes.payments._scoped_customers_query", return_value=q):
            resp = payments_cov_a_client.get("/payments/search-entities?type=customer")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"][0]["name"] == "NoQ Customer"
        q.filter.assert_not_called()


class TestPaymentsCovARestorePaymentMissing:
    """Line 509: restore_payment aborts 404 when archived record is None."""

    def test_restore_payment_archived_none_404(self, payments_cov_a_client):
        with (
            patch("routes.payments.get_active_tenant_id", return_value=1),
            patch(
                "routes.payments.PaymentService.find_archived_record",
                return_value=None,
            ),
        ):
            resp = payments_cov_a_client.post("/payments/payments/987654/restore")
        assert resp.status_code == 404


class TestPaymentsCovAPrintReceiptTenantMismatch:
    """Line 973: print_receipt aborts 404 when assert_tenant_record is falsy."""

    def test_print_receipt_tenant_check_404(self, payments_cov_a_client):
        receipt = _mock_receipt_item()
        with (
            patch("routes.payments.tenant_get", return_value=receipt),
            patch("routes.payments.assert_tenant_record", return_value=False),
        ):
            resp = payments_cov_a_client.get("/payments/receipts/1/print")
        assert resp.status_code == 404
