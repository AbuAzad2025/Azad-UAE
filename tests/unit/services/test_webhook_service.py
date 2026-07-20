"""Unit tests for WebhookService."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from extensions import db
from models import Donation, Package, PackagePurchase, Sale
from services.webhook_service import WebhookService


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    yield
    db_session.rollback()


def _np_sig(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha512).hexdigest()


def _package(db_session):
    slug = f"pkg-{uuid.uuid4().hex[:8]}"
    row = Package(
        name_ar="باقة",
        name_en="Package",
        slug=slug,
        price=99.0,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _purchase(db_session, package, payment_id="pay-purchase-1", **kwargs):
    row = PackagePurchase(
        package_id=package.id,
        customer_name="Buyer",
        customer_email="buyer@example.com",
        payment_method="crypto",
        payment_status=kwargs.get("payment_status", "pending"),
        amount_paid=99.0,
        transaction_id=payment_id,
        activation_status=kwargs.get("activation_status", "pending"),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _donation(db_session, payment_id="pay-donation-1", **kwargs):
    row = Donation(
        amount_usd=Decimal("25"),
        payment_method="crypto",
        transaction_hash=kwargs.get("transaction_hash", payment_id),
        gateway_transaction_id=kwargs.get("gateway_transaction_id"),
        status=kwargs.get("status", "pending"),
        gateway_name="nowpayments",
    )
    db_session.add(row)
    db_session.flush()
    return row


def _store_sale(db_session, sample_tenant, sample_customer, sample_user, **kwargs):
    row = Sale(
        tenant_id=sample_tenant.id,
        sale_number=f"STORE-{uuid.uuid4().hex[:6]}",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        sale_date=datetime.now(timezone.utc),
        subtotal=Decimal("100"),
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        amount_aed=Decimal("100"),
        source="online_store",
        status=kwargs.get("status", "pending"),
        checkout_gateway_ref=kwargs.get("checkout_gateway_ref"),
    )
    db_session.add(row)
    db_session.flush()
    return row


class TestVerifyNowpaymentsSignature:
    def test_no_secret(self):
        assert WebhookService.verify_nowpayments_signature(b"{}", "sig", "") is False

    def test_valid_and_invalid(self):
        secret = "ipn-secret"
        payload = b'{"payment_id":"1"}'
        sig = _np_sig(secret, payload)
        assert WebhookService.verify_nowpayments_signature(payload, sig, secret) is True
        assert WebhookService.verify_nowpayments_signature(payload, "bad", secret) is False


class TestProcessNowpaymentsWebhook:
    def test_unknown_order_type(self):
        result = WebhookService.process_nowpayments_webhook(
            {
                "payment_id": "x",
                "payment_status": "finished",
                "order_id": "OTHER_1",
            }
        )
        assert result["success"] is False

    def test_processing_exception(self, mocker):
        mocker.patch.object(
            WebhookService,
            "_process_purchase_webhook",
            side_effect=RuntimeError("boom"),
        )
        result = WebhookService.process_nowpayments_webhook(
            {
                "payment_id": "x",
                "payment_status": "finished",
                "order_id": "PURCHASE_1",
            }
        )
        assert result["success"] is False


class TestPurchaseWebhook:
    def test_not_found(self):
        result = WebhookService._process_purchase_webhook(
            {
                "payment_id": "missing",
                "payment_status": "finished",
            }
        )
        assert result["success"] is False

    def test_idempotent(self, db_session):
        pkg = _package(db_session)
        purchase = _purchase(
            db_session,
            pkg,
            payment_status="completed",
            activation_status="activated",
        )
        result = WebhookService._process_purchase_webhook(
            {
                "payment_id": purchase.transaction_id,
                "payment_status": "finished",
            }
        )
        assert "idempotent" in result["message"]

    def test_finished_activates(self, db_session, mocker):
        pkg = _package(db_session)
        purchase = _purchase(db_session, pkg, payment_id=f"pay-{uuid.uuid4().hex[:6]}")
        notify = mocker.patch("services.webhook_service.NotificationService.notify_purchase_activated")

        result = WebhookService._process_purchase_webhook(
            {
                "payment_id": purchase.transaction_id,
                "payment_status": "finished",
            }
        )
        db_session.refresh(purchase)
        assert result["success"] is True
        assert purchase.payment_status == "completed"
        assert purchase.activation_status == "activated"
        notify.assert_called_once()

    def test_failed_status(self, db_session):
        pkg = _package(db_session)
        purchase = _purchase(db_session, pkg, payment_id=f"pay-fail-{uuid.uuid4().hex[:6]}")
        result = WebhookService._process_purchase_webhook(
            {
                "payment_id": purchase.transaction_id,
                "payment_status": "failed",
            }
        )
        db_session.refresh(purchase)
        assert result["success"] is True
        assert purchase.payment_status == "failed"

    def test_commit_failure(self, db_session, mocker):
        pkg = _package(db_session)
        purchase = _purchase(db_session, pkg, payment_id=f"pay-db-{uuid.uuid4().hex[:6]}")
        mocker.patch.object(db.session, "commit", side_effect=RuntimeError("db"))
        with pytest.raises(RuntimeError, match="db"):
            WebhookService._process_purchase_webhook(
                {
                    "payment_id": purchase.transaction_id,
                    "payment_status": "waiting",
                }
            )


class TestDonationWebhook:
    def test_not_found(self):
        assert (
            WebhookService._process_donation_webhook(
                {
                    "payment_id": "missing",
                    "payment_status": "finished",
                }
            )["success"]
            is False
        )

    def test_idempotent(self, db_session):
        donation = _donation(db_session, status="completed")
        result = WebhookService._process_donation_webhook(
            {
                "payment_id": donation.transaction_hash,
                "payment_status": "finished",
            }
        )
        assert "idempotent" in result["message"]

    def test_finished_via_gateway_id(self, db_session, mocker):
        gateway_id = f"gateway-{uuid.uuid4().hex[:10]}"
        donation = _donation(
            db_session,
            payment_id=gateway_id,
            transaction_hash=f"hash-{uuid.uuid4().hex[:10]}",
            gateway_transaction_id=gateway_id,
        )
        mocker.patch("services.webhook_service.NotificationService.notify_payment_received")
        result = WebhookService._process_donation_webhook(
            {
                "payment_id": gateway_id,
                "payment_status": "finished",
            }
        )
        updated = db.session.get(Donation, donation.id)
        assert result["success"] is True
        assert updated.status == "completed"

    def test_expired_marks_failed(self, db_session):
        donation = _donation(db_session, payment_id=f"don-exp-{uuid.uuid4().hex[:6]}")
        WebhookService._process_donation_webhook(
            {
                "payment_id": donation.transaction_hash,
                "payment_status": "expired",
            }
        )
        db_session.refresh(donation)
        assert donation.status == "failed"

    def test_commit_failure(self, db_session, mocker):
        donation = _donation(db_session, payment_id=f"don-db-{uuid.uuid4().hex[:6]}")
        mocker.patch.object(db.session, "commit", side_effect=RuntimeError("db"))
        with pytest.raises(RuntimeError):
            WebhookService._process_donation_webhook(
                {
                    "payment_id": donation.transaction_hash,
                    "payment_status": "waiting",
                }
            )


class TestStoreOrderWebhook:
    def test_invalid_order_id(self):
        result = WebhookService._process_store_order_webhook(
            {
                "order_id": "BAD_1_2",
                "payment_status": "finished",
            }
        )
        assert result["error"] == "Invalid store order id"

    def test_sale_not_found(self):
        result = WebhookService._process_store_order_webhook(
            {
                "order_id": "STORE_999999_888888",
                "payment_status": "finished",
            }
        )
        assert result["error"] == "Store sale not found"

    def test_gateway_ref_mismatch_logs(self, db_session, sample_tenant, sample_customer, sample_user, mocker):
        sale = _store_sale(
            db_session,
            sample_tenant,
            sample_customer,
            sample_user,
            checkout_gateway_ref="ref-old",
        )
        mocker.patch("services.store_order_service.StoreOrderService.confirm_order")
        order_id = f"STORE_{sale.id}_{sample_tenant.id}"
        WebhookService._process_store_order_webhook(
            {
                "order_id": order_id,
                "payment_id": "ref-new",
                "payment_status": "finished",
            }
        )

    def test_idempotent_confirmed_records_fee(self, db_session, sample_tenant, sample_customer, sample_user, mocker):
        sale = _store_sale(
            db_session,
            sample_tenant,
            sample_customer,
            sample_user,
            status="confirmed",
            checkout_gateway_ref="ref-1",
        )
        fee = mocker.patch("services.azad_platform_fee_service.AzadPlatformFeeService.record_store_online_fee")
        order_id = f"STORE_{sale.id}_{sample_tenant.id}"
        result = WebhookService._process_store_order_webhook(
            {
                "order_id": order_id,
                "payment_id": "ref-1",
                "payment_status": "finished",
            }
        )
        assert "idempotent" in result["message"]
        fee.assert_called_once()

    def test_confirms_pending_sale(self, db_session, sample_tenant, sample_customer, sample_user, mocker):
        sale = _store_sale(db_session, sample_tenant, sample_customer, sample_user, status="pending")
        confirm = mocker.patch("services.store_order_service.StoreOrderService.confirm_order")
        order_id = f"STORE_{sale.id}_{sample_tenant.id}"
        result = WebhookService._process_store_order_webhook(
            {
                "order_id": order_id,
                "payment_id": "ref-2",
                "payment_status": "finished",
            }
        )
        assert result["success"] is True
        confirm.assert_called_once_with(sale, mark_paid=True)

    def test_confirm_value_error_skipped(self, db_session, sample_tenant, sample_customer, sample_user, mocker):
        sale = _store_sale(db_session, sample_tenant, sample_customer, sample_user, status="pending")
        mocker.patch(
            "services.store_order_service.StoreOrderService.confirm_order",
            side_effect=ValueError("skip"),
        )
        order_id = f"STORE_{sale.id}_{sample_tenant.id}"
        assert (
            WebhookService._process_store_order_webhook(
                {
                    "order_id": order_id,
                    "payment_status": "finished",
                }
            )["success"]
            is True
        )

    def test_cancel_pending_on_failure(self, db_session, sample_tenant, sample_customer, sample_user, mocker):
        sale = _store_sale(db_session, sample_tenant, sample_customer, sample_user, status="pending")
        cancel = mocker.patch("services.store_order_service.StoreOrderService.cancel_order")
        order_id = f"STORE_{sale.id}_{sample_tenant.id}"
        WebhookService._process_store_order_webhook(
            {
                "order_id": order_id,
                "payment_status": "refunded",
            }
        )
        cancel.assert_called_once_with(sale)

    def test_idempotent_commit_failure(self, db_session, sample_tenant, sample_customer, sample_user, mocker):
        sale = _store_sale(
            db_session,
            sample_tenant,
            sample_customer,
            sample_user,
            status="confirmed",
        )
        mocker.patch("services.azad_platform_fee_service.AzadPlatformFeeService.record_store_online_fee")
        mocker.patch.object(db.session, "commit", side_effect=RuntimeError("db"))
        order_id = f"STORE_{sale.id}_{sample_tenant.id}"
        with pytest.raises(RuntimeError):
            WebhookService._process_store_order_webhook(
                {
                    "order_id": order_id,
                    "payment_status": "finished",
                }
            )


class TestStripe:
    def test_verify_no_secret(self):
        assert WebhookService.verify_stripe_signature(b"{}", "sig", "") is False

    def test_verify_success_and_failure(self, mocker):
        stripe = MagicMock()
        mocker.patch.dict("sys.modules", {"stripe": stripe})
        assert WebhookService.verify_stripe_signature(b"{}", "sig", "whsec") is True
        stripe.Webhook.construct_event.side_effect = ValueError("bad")
        assert WebhookService.verify_stripe_signature(b"{}", "sig", "whsec") is False

    def test_process_success_event(self, mocker):
        notify = mocker.patch("services.webhook_service.NotificationService.notify_payment_received")
        result = WebhookService.process_stripe_webhook(
            {
                "type": "payment_intent.succeeded",
                "data": {"object": {"amount": 5000, "receipt_email": "a@b.com"}},
            }
        )
        assert result["success"] is True
        notify.assert_called_once()

    def test_process_failed_event(self, mocker):
        alert = mocker.patch("services.webhook_service.NotificationService.notify_security_alert")
        result = WebhookService.process_stripe_webhook(
            {
                "type": "payment_intent.payment_failed",
                "data": {
                    "object": {
                        "receipt_email": "a@b.com",
                        "last_payment_error": {"message": "card declined"},
                    },
                },
            }
        )
        assert result["success"] is True
        alert.assert_called_once()

    def test_unhandled_event(self):
        result = WebhookService.process_stripe_webhook({"type": "customer.created", "data": {}})
        assert result["message"] == "Event acknowledged"

    def test_process_exception(self, mocker):
        mocker.patch.object(
            WebhookService,
            "_process_stripe_payment_success",
            side_effect=RuntimeError("boom"),
        )
        result = WebhookService.process_stripe_webhook(
            {
                "type": "payment_intent.succeeded",
                "data": {"object": {}},
            }
        )
        assert result["success"] is False


class TestRouting:
    def test_routes_purchase_donation_store(self, mocker):
        purchase = mocker.patch.object(WebhookService, "_process_purchase_webhook", return_value={"ok": 1})
        donation = mocker.patch.object(WebhookService, "_process_donation_webhook", return_value={"ok": 2})
        store = mocker.patch.object(WebhookService, "_process_store_order_webhook", return_value={"ok": 3})

        WebhookService.process_nowpayments_webhook({"order_id": "PURCHASE_1"})
        purchase.assert_called_once()
        WebhookService.process_nowpayments_webhook({"order_id": "DONATION_1"})
        donation.assert_called_once()
        WebhookService.process_nowpayments_webhook({"order_id": "STORE_1_2"})
        store.assert_called_once()
