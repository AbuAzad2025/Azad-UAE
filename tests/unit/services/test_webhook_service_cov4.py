"""Cov4: webhook_service — signature/nowpayments/stripe dispatch arcs."""

from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal
from unittest.mock import patch

from services.webhook_service import WebhookService


def test_verify_nowpayments_signature_branches():
    assert WebhookService.verify_nowpayments_signature(b"p", "s", "") is False
    assert WebhookService.verify_nowpayments_signature(b"p", "s", None) is False
    payload = b'{"a":1}'
    sig = hmac.new(b"secret", payload, hashlib.sha512).hexdigest()
    assert WebhookService.verify_nowpayments_signature(payload, sig, "secret") is True
    assert WebhookService.verify_nowpayments_signature(payload, "0" * 128, "secret") is False


def test_process_nowpayments_routing_and_errors():
    out = WebhookService.process_nowpayments_webhook(
        {"payment_id": "1", "payment_status": "finished", "order_id": "PURCHASE_9"}
    )
    assert out["success"] is False  # purchase not found branch
    out = WebhookService.process_nowpayments_webhook(
        {"payment_id": "2", "payment_status": "finished", "order_id": "DONATION_9"}
    )
    assert out["success"] is False  # donation not found branch
    out = WebhookService.process_nowpayments_webhook(
        {"payment_id": "3", "payment_status": "finished", "order_id": "STORE_1"}
    )
    assert out["success"] is False  # invalid store order id branch
    out = WebhookService.process_nowpayments_webhook(
        {"payment_id": "4", "payment_status": "finished", "order_id": "WEIRD_X"}
    )
    assert out == {"success": False, "error": "Unknown order type"}
    out = WebhookService.process_nowpayments_webhook(None)
    assert out == {"success": False, "error": "Webhook processing failed"}


def test_purchase_webhook_finished_failed_idempotent(db_session, sample_tenant):
    from models import PackagePurchase

    po = PackagePurchase(
        tenant_id=sample_tenant.id,
        transaction_id="cov4-pay-1",
        payment_status="pending",
        activation_status="pending",
        customer_name="C",
    )
    db_session.add(po)
    db_session.flush()
    out = WebhookService._process_purchase_webhook({"payment_id": "cov4-pay-1", "payment_status": "finished"})
    assert out["success"] is True
    assert po.activation_status == "activated"
    out = WebhookService._process_purchase_webhook({"payment_id": "cov4-pay-1", "payment_status": "finished"})
    assert out["message"] == "Purchase already activated (idempotent)"
    out = WebhookService._process_purchase_webhook({"payment_id": "cov4-pay-1", "payment_status": "expired"})
    assert po.payment_status == "failed"


def test_donation_webhook_finished_failed_idempotent(db_session):
    from models.donation import Donation

    d = Donation(
        amount_usd=Decimal("10"),
        payment_method="crypto",
        status="pending",
        donor_name="D",
        transaction_hash="cov4-tx-1",
    )
    db_session.add(d)
    db_session.flush()
    out = WebhookService._process_donation_webhook({"payment_id": "cov4-tx-1", "payment_status": "finished"})
    assert out["success"] is True
    assert d.status == "completed"
    out = WebhookService._process_donation_webhook({"payment_id": "cov4-tx-1", "payment_status": "finished"})
    assert out["message"] == "Donation already completed (idempotent)"
    d.status = "pending"
    db_session.flush()
    out = WebhookService._process_donation_webhook({"payment_id": "cov4-tx-1", "payment_status": "failed"})
    assert d.status == "failed"
    # gateway_transaction_id lookup branch
    d2 = Donation(amount_usd=Decimal("5"), payment_method="card", status="pending", gateway_transaction_id="cov4-gw-2")
    db_session.add(d2)
    db_session.flush()
    out = WebhookService._process_donation_webhook({"payment_id": "cov4-gw-2", "payment_status": "finished"})
    assert d2.status == "completed"


def test_store_order_webhook_branches(db_session, sample_tenant, sample_customer, sample_user, sample_warehouse):
    from datetime import datetime as dt

    from models import Sale

    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number="STORE-COV4-WH",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        warehouse_id=sample_warehouse.id,
        sale_date=dt.now(),
        source="online_store",
        status="pending",
        subtotal=Decimal("10"),
        total_amount=Decimal("10"),
        amount=Decimal("10"),
        amount_aed=Decimal("10"),
    )
    db_session.add(sale)
    db_session.flush()
    with patch(
        "services.store_online_payment_service.StoreOnlinePaymentService.parse_store_order_id",
        return_value=(sale.id, sample_tenant.id),
    ):
        out = WebhookService._process_store_order_webhook(
            {"payment_id": "gw-1", "payment_status": "finished", "order_id": f"STORE_{sample_tenant.id}_{sale.id}"}
        )
        assert out["success"] is True
        out = WebhookService._process_store_order_webhook(
            {"payment_id": "gw-1", "payment_status": "refunded", "order_id": f"STORE_{sample_tenant.id}_{sale.id}"}
        )
        assert out["success"] is True
    # sale-not-found branch
    with patch(
        "services.store_online_payment_service.StoreOnlinePaymentService.parse_store_order_id",
        return_value=(999999999, sample_tenant.id),
    ):
        out = WebhookService._process_store_order_webhook(
            {"payment_id": "gw-1", "payment_status": "finished", "order_id": "STORE_X"}
        )
        assert out == {"success": False, "error": "Store sale not found"}


def test_stripe_signatures_and_dispatch():
    assert WebhookService.verify_stripe_signature(b"p", "s", "") is False
    with patch.dict("sys.modules", {"stripe": None}):
        assert WebhookService.verify_stripe_signature(b"p", "s", "whsec") is False
    out = WebhookService.process_stripe_webhook(
        {"type": "payment_intent.succeeded", "data": {"object": {"amount": 2500, "receipt_email": "a@b.c"}}}
    )
    assert out == {"success": True, "message": "Payment processed"}
    out = WebhookService.process_stripe_webhook(
        {
            "type": "payment_intent.payment_failed",
            "data": {"object": {"receipt_email": "a@b.c", "last_payment_error": {"message": "declined"}}},
        }
    )
    assert out == {"success": True, "message": "Payment failure processed"}
    out = WebhookService.process_stripe_webhook({"type": "something.else", "data": {}})
    assert out == {"success": True, "message": "Event acknowledged"}
    assert WebhookService.process_stripe_webhook(None)["success"] is False
