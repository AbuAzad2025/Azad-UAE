"""
Billing Gateway Webhooks — processes Stripe/gateway events and provisions
purchased packages onto verified tenants.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, current_app
from extensions import db, limiter
from utils.db_safety import atomic_transaction

logger = logging.getLogger(__name__)

billing_webhook_bp = Blueprint("billing_webhook", __name__, url_prefix="/billing-webhook")

_WEBHOOK_MAX_AGE = 300


def _reject_stale_timestamp(data: dict | None):
    if not data:
        return None
    ts = data.get("timestamp") or data.get("created")
    if ts is None:
        return None
    try:
        event_time = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        if (datetime.now(timezone.utc) - event_time).total_seconds() > _WEBHOOK_MAX_AGE:
            logger.warning("Billing webhook rejected: stale timestamp %s", ts)
            return jsonify({"error": "Stale event"}), 400
    except (ValueError, TypeError):
        pass
    return None


def _is_duplicate(provider: str, event_id: str | None) -> bool:
    if not event_id:
        return False
    try:
        from extensions import cache
        key = f"billing_webhook:{provider}:{event_id}"
        if cache.get(key):
            logger.warning("Billing webhook duplicate blocked: %s %s", provider, event_id)
            return True
        cache.set(key, "1", timeout=86400)
    except Exception:
        logger.exception("Billing webhook dedup cache error")
    return False


@billing_webhook_bp.route("/stripe", methods=["POST"])
@limiter.limit("100 per minute")
def stripe_webhook():
    """Handle Stripe checkout.session.completed / invoice.payment_succeeded."""
    try:
        payload = request.data
        sig = request.headers.get("Stripe-Signature", "")
        secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
        if not secret:
            logger.warning("Stripe webhook secret not configured")
            return jsonify({"error": "Webhook not configured"}), 503

        import stripe as stripe_lib
        try:
            event = stripe_lib.Webhook.construct_event(payload, sig, secret)
        except stripe_lib.error.SignatureVerificationError:
            logger.warning("Stripe webhook signature verification failed")
            return jsonify({"error": "Invalid signature"}), 403

        event_id = event.get("id")
        if _is_duplicate("stripe", event_id):
            return jsonify({"status": "duplicate"}), 200

        stale = _reject_stale_timestamp(event.get("data", {}).get("object", {}))
        if stale:
            return stale

        event_type = event.get("type", "")
        session = event.get("data", {}).get("object", {})

        if event_type in ("checkout.session.completed", "invoice.payment_succeeded"):
            metadata = session.get("metadata", {})
            tenant_id = metadata.get("tenant_id")
            package_id = metadata.get("package_id")
            duration_type = metadata.get("duration_type", "monthly")

            if not tenant_id or not package_id:
                logger.warning(
                    "Stripe webhook missing metadata: tenant_id=%s package_id=%s",
                    tenant_id, package_id,
                )
                return jsonify({"error": "Missing metadata"}), 400

            from services.saas_provisioning_service import (
                SaaSProvisioningService,
                SaaSProvisioningError,
            )

            try:
                result = SaaSProvisioningService.activate_purchased_package(
                    tenant_id=int(tenant_id),
                    package_id=int(package_id),
                    duration_type=duration_type,
                )
                logger.info(
                    "Stripe webhook provisioned tenant %s with package %s",
                    tenant_id, package_id,
                )
                return jsonify({"success": True, "provisioning": result}), 200
            except SaaSProvisioningError as exc:
                logger.error("Stripe provisioning failed: %s", exc)
                return jsonify({"error": str(exc)}), 422

        logger.info("Stripe webhook unhandled event type: %s", event_type)
        return jsonify({"status": "acknowledged"}), 200

    except Exception:
        logger.exception("Stripe billing webhook failed")
        return jsonify({"error": "Webhook processing failed"}), 500


@billing_webhook_bp.route("/generic", methods=["POST"])
@limiter.limit("100 per minute")
def generic_webhook():
    """Handle generic payment gateway webhook via JSON body.

    Owner manual override flow — after receiving payment via WhatsApp:
    ``curl -X POST /billing-webhook/generic \\
      -H 'Content-Type: application/json' \\
      -H 'X-Webhook-Secret: SHARED_SECRET' \\
      -d '{"event":"payment_succeeded","tenant_id":1,"package_id":2,"duration_type":"monthly","transaction_id":"manual-001"}'``

    Expected payload::
        {
            "event": "payment_succeeded",
            "tenant_id": 1,
            "package_id": 2,
            "duration_type": "monthly",
            "transaction_id": "manual-001"
        }
    """
    try:
        secret = current_app.config.get("BILLING_WEBHOOK_SECRET") or current_app.config.get("SECRET_KEY")
        if secret:
            provided = request.headers.get("X-Webhook-Secret", "")
            if provided != secret:
                logger.warning("Generic webhook rejected: invalid secret")
                return jsonify({"error": "Forbidden"}), 403

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        stale = _reject_stale_timestamp(data)
        if stale:
            return stale

        event = data.get("event", "")
        transaction_id = data.get("transaction_id") or data.get("id")
        provider = data.get("provider", "generic")

        if _is_duplicate(provider, transaction_id):
            return jsonify({"status": "duplicate"}), 200

        if event not in ("payment_succeeded", "checkout.session.completed", "invoice.payment_succeeded"):
            logger.info("Generic webhook unhandled event: %s", event)
            return jsonify({"status": "acknowledged"}), 200

        tenant_id = data.get("tenant_id")
        package_id = data.get("package_id")
        duration_type = data.get("duration_type", "monthly")

        if not tenant_id or not package_id:
            return jsonify({"error": "tenant_id and package_id required"}), 400

        from services.saas_provisioning_service import (
            SaaSProvisioningService,
            SaaSProvisioningError,
        )

        result = SaaSProvisioningService.activate_purchased_package(
            tenant_id=int(tenant_id),
            package_id=int(package_id),
            duration_type=duration_type,
        )

        logger.info(
            "Generic webhook provisioned tenant %s with package %s (tx=%s)",
            tenant_id, package_id, transaction_id,
        )
        return jsonify({"success": True, "provisioning": result}), 200

    except SaaSProvisioningError as exc:
        logger.error("Generic webhook provisioning failed: %s", exc)
        return jsonify({"error": str(exc)}), 422
    except Exception:
        logger.exception("Generic billing webhook failed")
        return jsonify({"error": "Webhook processing failed"}), 500
