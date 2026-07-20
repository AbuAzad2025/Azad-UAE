"""Payment gateway webhook verification and processing."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone

from sqlalchemy import or_

from extensions import db
from utils.db_safety import atomic_transaction
from models import Donation, PackagePurchase
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class WebhookService:
    @staticmethod
    def verify_nowpayments_signature(payload, signature, ipn_secret):
        if not ipn_secret:
            logger.warning("NOWPayments IPN secret not configured")
            return False

        expected_signature = hmac.new(
            ipn_secret.encode("utf-8"),
            payload,
            hashlib.sha512,
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    @staticmethod
    def process_nowpayments_webhook(data):
        try:
            payment_id = data.get("payment_id")
            payment_status = data.get("payment_status")
            order_id = data.get("order_id", "")

            logger.info("NOWPayments webhook received: %s - %s", payment_id, payment_status)

            if order_id.startswith("PURCHASE_"):
                return WebhookService._process_purchase_webhook(data)
            if order_id.startswith("DONATION_"):
                return WebhookService._process_donation_webhook(data)
            if order_id.startswith("STORE_"):
                return WebhookService._process_store_order_webhook(data)

            logger.warning("Unknown order type: %s", order_id)
            return {"success": False, "error": "Unknown order type"}

        except Exception as e:
            logger.error("Webhook processing error: %s", e)
            return {"success": False, "error": "Webhook processing failed"}

    @staticmethod
    def _process_purchase_webhook(data):
        payment_status = data.get("payment_status")
        payment_id = data.get("payment_id")

        purchase = PackagePurchase.query.filter_by(transaction_id=payment_id).first()

        if not purchase:
            logger.warning("Purchase not found for payment_id: %s", payment_id)
            return {"success": False, "error": "Purchase not found"}

        if (
            payment_status == "finished"
            and purchase.payment_status == "completed"
            and purchase.activation_status == "activated"
        ):
            return {
                "success": True,
                "message": "Purchase already activated (idempotent)",
            }

        if payment_status == "finished":
            purchase.payment_status = "completed"
            purchase.activation_status = "activated"
            purchase.activation_date = datetime.now(timezone.utc)

            NotificationService.notify_purchase_activated(
                purchase.package.name_ar if purchase.package else "N/A",
                purchase.customer_name,
            )

            logger.info("Purchase %s completed and activated", purchase.id)

        elif payment_status in ("failed", "expired"):
            purchase.payment_status = "failed"
            logger.warning("Purchase %s failed", purchase.id)

        with atomic_transaction("webhook_process_purchase"):
            db.session.flush()

        return {"success": True, "message": f"Purchase updated to {payment_status}"}

    @staticmethod
    def _process_donation_webhook(data):
        payment_status = data.get("payment_status")
        payment_id = data.get("payment_id")

        donation = Donation.query.filter(
            or_(
                Donation.transaction_hash == payment_id,
                Donation.gateway_transaction_id == payment_id,
            ),
        ).first()

        if not donation:
            logger.warning("Donation not found for payment_id: %s", payment_id)
            return {"success": False, "error": "Donation not found"}

        if donation.status == "completed" and payment_status == "finished":
            return {
                "success": True,
                "message": "Donation already completed (idempotent)",
            }

        if payment_status == "finished":
            donation.status = "completed"
            donation.completed_at = datetime.now(timezone.utc)

            NotificationService.notify_payment_received(
                float(donation.amount_usd),
                donation.donor_name or "مجهول",
                donation.payment_method,
            )

            logger.info("Donation %s completed", donation.id)

        elif payment_status in ("failed", "expired"):
            donation.status = "failed"
            logger.warning("Donation %s failed", donation.id)

        with atomic_transaction("webhook_process_donation"):
            db.session.flush()

        return {"success": True, "message": f"Donation updated to {payment_status}"}

    @staticmethod
    def _process_store_order_webhook(data):
        from models import Sale
        from services.store_online_payment_service import StoreOnlinePaymentService
        from services.store_order_service import StoreOrderService

        payment_status = data.get("payment_status")
        payment_id = str(data.get("payment_id", ""))
        order_id = data.get("order_id", "")

        parsed = StoreOnlinePaymentService.parse_store_order_id(order_id)
        if not parsed:
            return {"success": False, "error": "Invalid store order id"}

        sale_id, tenant_id = parsed
        sale = Sale.query.filter_by(
            id=sale_id,
            tenant_id=tenant_id,
            source="online_store",
        ).first()
        if not sale:
            return {"success": False, "error": "Store sale not found"}

        if payment_id and sale.checkout_gateway_ref and sale.checkout_gateway_ref != payment_id:
            logger.warning("Gateway ref mismatch for sale %s", sale.sale_number)

        if payment_status == "finished" and sale.status == "confirmed":
            from services.azad_platform_fee_service import AzadPlatformFeeService

            AzadPlatformFeeService.record_store_online_fee(
                sale,
                gateway_reference=payment_id or getattr(sale, "checkout_gateway_ref", None),
            )
            with atomic_transaction("webhook_process_store_order"):
                db.session.flush()

            return {
                "success": True,
                "message": "Store order already confirmed (idempotent)",
            }

        if payment_status == "finished":
            if sale.status != "confirmed":
                try:
                    with atomic_transaction("webhook_confirm_store_order"):
                        StoreOrderService.confirm_order(sale, mark_paid=True)
                except ValueError as exc:
                    logger.warning("Store order confirm skipped: %s", exc)
            logger.info("Store order %s paid via gateway", sale.sale_number)
        elif payment_status in ("failed", "expired", "refunded"):
            if sale.status == "pending":
                with atomic_transaction("webhook_cancel_store_order"):
                    StoreOrderService.cancel_order(sale)
            logger.warning("Store order %s payment %s", sale.sale_number, payment_status)

        return {"success": True, "message": f"Store order updated to {payment_status}"}

    @staticmethod
    def verify_stripe_signature(payload, signature, webhook_secret):
        if not webhook_secret:
            logger.warning("Stripe webhook secret not configured")
            return False

        try:
            import stripe

            stripe.Webhook.construct_event(payload, signature, webhook_secret)
            return True
        except Exception as e:
            logger.error("Stripe signature verification failed: %s", e)
            return False

    @staticmethod
    def process_stripe_webhook(data):
        try:
            event_type = data.get("type")
            event_data = data.get("data", {}).get("object", {})

            logger.info("Stripe webhook received: %s", event_type)

            if event_type == "payment_intent.succeeded":
                return WebhookService._process_stripe_payment_success(event_data)
            if event_type == "payment_intent.payment_failed":
                return WebhookService._process_stripe_payment_failed(event_data)

            logger.info("Unhandled Stripe event: %s", event_type)
            return {"success": True, "message": "Event acknowledged"}

        except Exception as e:
            logger.error("Stripe webhook processing error: %s", e)
            return {"success": False, "error": "Webhook processing failed"}

    @staticmethod
    def _process_stripe_payment_success(payment_intent):
        amount = payment_intent.get("amount") / 100
        customer_email = payment_intent.get("receipt_email")

        logger.info("Stripe payment succeeded: $%s from %s", amount, customer_email)

        NotificationService.notify_payment_received(
            amount,
            customer_email or "Unknown",
            "Stripe",
        )

        return {"success": True, "message": "Payment processed"}

    @staticmethod
    def _process_stripe_payment_failed(payment_intent):
        customer_email = payment_intent.get("receipt_email")
        error_message = payment_intent.get("last_payment_error", {}).get("message", "Unknown error")

        logger.warning("Stripe payment failed for %s: %s", customer_email, error_message)

        NotificationService.notify_security_alert(
            "فشل دفعة Stripe",
            f"فشلت دفعة من {customer_email}: {error_message}",
        )

        return {"success": True, "message": "Payment failure processed"}
