"""Coverage for routes/payments.py gaps — file B.

Targets: arcs 738->926, 804->926, 1212->1231, 1296->1303, 1320->1323,
1375->1561, 1475->1486; lines 1217, 1219.
Uses test client with mocks only at DB/external boundaries.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def payments_cov_b_client(app_factory, bypass_permission_auth):
    from flask import Blueprint

    from routes.payments import payments_bp
    from routes.public import public_bp

    purchases_stub = Blueprint("purchases", __name__)

    @purchases_stub.route("/purchases/<int:id>")
    def view(id):
        return "purchase-ok"

    app = app_factory(payments_bp, public_bp, purchases_stub)
    return app.test_client()


@contextmanager
def _atomic_ok():
    ctx = MagicMock()
    ctx.__enter__.return_value = ctx
    ctx.__exit__.return_value = False
    with patch("routes.payments.atomic_transaction", return_value=ctx):
        yield ctx


def _receipt_for_delete(**kwargs):
    r = MagicMock()
    r.id = kwargs.get("id", 21)
    r.receipt_number = kwargs.get("receipt_number", "REC-DEL-21")
    r.branch_id = kwargs.get("branch_id")
    r.source_type = kwargs.get("source_type", "sale")
    r.source_id = kwargs.get("source_id", 5)
    r.cheque_id = kwargs.get("cheque_id")
    r.cheque = kwargs.get("cheque")
    r.amount = kwargs.get("amount", Decimal("100"))
    r.amount_aed = kwargs.get("amount_aed", Decimal("100"))
    r.tenant_id = 1
    return r


def _payment_for_delete(**kwargs):
    p = MagicMock()
    p.id = kwargs.get("id", 31)
    p.payment_number = kwargs.get("payment_number", "PAY-DEL-31")
    p.branch_id = kwargs.get("branch_id")
    p.cheque_id = kwargs.get("cheque_id")
    p.cheque = kwargs.get("cheque")
    p.supplier_id = kwargs.get("supplier_id", 9)
    p.amount_aed = kwargs.get("amount_aed", Decimal("60"))
    p.tenant_id = 1
    return p


class TestPaymentsCovBVoucherFallthrough:
    """Arcs 738->926 and 804->926: unknown party_type falls to final redirect."""

    def test_voucher_incoming_unknown_party(self, payments_cov_b_client):
        with (
            patch("routes.payments.resolve_default_currency", return_value="AED"),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
            patch("utils.decorators.branch_scope_id", return_value=None),
        ):
            resp = payments_cov_b_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "incoming",
                    "party_type": "mystery",
                    "party_id": "1",
                    "amount": "10",
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert resp.location.endswith("/payments/receipts")

    def test_voucher_outgoing_unknown_party(self, payments_cov_b_client):
        with (
            patch("routes.payments.resolve_default_currency", return_value="AED"),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
            patch("utils.decorators.branch_scope_id", return_value=None),
        ):
            resp = payments_cov_b_client.post(
                "/payments/voucher/submit",
                data={
                    "direction": "outgoing",
                    "party_type": "mystery",
                    "party_id": "1",
                    "amount": "10",
                    "payment_method": "cash",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert resp.location.endswith("/payments/receipts")


class TestPaymentsCovBDeleteReceipt:
    """Arc 1212->1231 and lines 1217/1219: sale adjustment branches."""

    def test_delete_receipt_sale_none_skips_adjustment(self, payments_cov_b_client):
        receipt = _receipt_for_delete()
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch(
                "routes.payments.PaymentService.get_sale_for_receipt",
                return_value=None,
            ),
            patch("services.archive_service.ArchiveService") as archive_cls,
            patch("routes.payments.LoggingCore"),
            _atomic_ok(),
        ):
            resp = payments_cov_b_client.post("/payments/receipts/21/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert archive_cls.return_value.archive_record.called

    def test_delete_receipt_clamps_negative_paid_amounts(self, payments_cov_b_client):
        receipt = _receipt_for_delete(amount=Decimal("100"), amount_aed=Decimal("100"))
        sale = MagicMock()
        sale.paid_amount = Decimal("10")
        sale.paid_amount_aed = Decimal("5")
        sale.amount_aed = Decimal("200")
        sale.balance_due = Decimal("195")
        sale.payment_status = "partial"
        with (
            patch("routes.payments.tenant_get_or_404", return_value=receipt),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch(
                "routes.payments.PaymentService.get_sale_for_receipt",
                return_value=sale,
            ),
            patch("services.archive_service.ArchiveService"),
            patch("routes.payments.LoggingCore"),
            _atomic_ok(),
        ):
            resp = payments_cov_b_client.post("/payments/receipts/21/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert sale.paid_amount == 0
        assert sale.paid_amount_aed == 0


class TestPaymentsCovBDeletePayment:
    """Arcs 1296->1303 (cheque None) and 1320->1323 (supplier None)."""

    def test_delete_payment_linked_without_cheque_object(self, payments_cov_b_client):
        payment = _payment_for_delete(cheque_id=9, cheque=None)
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("services.archive_service.ArchiveService") as archive_cls,
            patch("routes.payments.LoggingCore"),
            _atomic_ok(),
        ):
            resp = payments_cov_b_client.post("/payments/payments/31/delete", follow_redirects=False)
        assert resp.status_code == 302
        assert archive_cls.return_value.archive_record.call_count == 1

    def test_delete_payment_supplier_missing(self, payments_cov_b_client):
        payment = _payment_for_delete(cheque_id=None, supplier_id=33)
        with (
            patch("routes.payments.tenant_get_or_404", return_value=payment),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("services.gl_service.GLService.reverse_entry"),
            patch(
                "routes.payments.PaymentService.get_supplier_by_id",
                return_value=None,
            ),
            patch("routes.payments.PaymentService.delete_payment"),
            patch("routes.payments.LoggingCore"),
            _atomic_ok(),
        ):
            resp = payments_cov_b_client.post("/payments/payments/31/delete", follow_redirects=False)
        assert resp.status_code == 302


class TestPaymentsCovBCreatePaymentHead:
    """Arc 1375->1561: HEAD falls past GET and POST guards to final render."""

    def test_create_payment_head_renders_form(self, payments_cov_b_client):
        purchase = MagicMock(
            id=8,
            branch_id=None,
            supplier_id=2,
            supplier_name="Head Supplier",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=Decimal("1"),
            currency="AED",
        )
        supplier = MagicMock(id=2)
        with (
            patch("routes.payments.tenant_get_or_404", return_value=purchase),
            patch("routes.payments.tenant_get", return_value=supplier),
            patch(
                "routes.payments.PaymentService.get_confirmed_purchase_paid_total",
                return_value=Decimal("0"),
            ),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
            patch("utils.decorators.branch_scope_id", return_value=None),
            patch("routes.payments.render_template", return_value="ok"),
        ):
            resp = payments_cov_b_client.head("/payments/create_payment/8")
        assert resp.status_code == 200


class TestPaymentsCovBCreatePaymentCard:
    """Arc 1475->1486: card payment without card_last4."""

    def test_create_payment_card_without_last4(self, payments_cov_b_client):
        purchase = MagicMock(
            id=8,
            branch_id=1,
            supplier_id=2,
            supplier_name="Card Supplier",
            tenant_id=1,
            amount_aed=Decimal("500"),
            exchange_rate=Decimal("1"),
            currency="AED",
        )
        supplier = MagicMock(id=2, tenant_id=1)
        supplier.apply_payment = MagicMock()
        session = MagicMock()
        session.add = MagicMock()
        session.flush = MagicMock()
        with (
            patch("routes.payments.tenant_get_or_404", return_value=purchase),
            patch("routes.payments.tenant_get", return_value=supplier),
            patch(
                "routes.payments.PaymentService.get_confirmed_purchase_paid_total",
                return_value=Decimal("0"),
            ),
            patch("routes.payments.PaymentService._post_supplier_fx_gain_loss"),
            patch(
                "routes.payments._resolve_transaction_rate",
                return_value=Decimal("1"),
            ),
            patch("utils.helpers.generate_number", return_value="PAY-1001"),
            patch("routes.payments.resolve_tenant_base_currency", return_value="AED"),
            patch("routes.payments.get_active_tenant_id", return_value=1),
            patch("routes.payments.get_system_default_currency", return_value="AED"),
            patch("routes.payments.post_or_fail"),
            patch("services.gl_service.GLService.ensure_core_accounts"),
            patch(
                "services.gl_service.GLService.get_payment_credit_account",
                return_value="1010",
            ),
            patch(
                "services.gl_service.GLService.get_payment_credit_concept",
                return_value="CASH",
            ),
            patch("routes.payments.db.session", session),
            patch("utils.decorators.branch_scope_id", return_value=None),
            _atomic_ok(),
        ):
            resp = payments_cov_b_client.post(
                "/payments/create_payment/8",
                data={
                    "amount": "50",
                    "payment_method": "card",
                    "currency": "AED",
                    "exchange_rate": "1",
                    "reference_number_card": "REFCARD-1",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert session.add.called
        added = session.add.call_args_list[0].args[0]
        assert getattr(added, "reference_number", None) == "REFCARD-1"
        assert datetime.now(UTC) is not None
