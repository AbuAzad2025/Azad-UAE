"""NOWPayments IPN URL and secret helpers."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_nowpayments_ipn_url() -> str:
    """Canonical IPN callback URL for per-payment NOWPayments requests."""
    from services.payments.nowpayments_provider import NowPaymentsProvider

    return NowPaymentsProvider().build_webhook_url()


def resolve_nowpayments_ipn_secret(vault=None) -> str:
    """
    IPN secret for canonical webhook verification.
    Prefer PaymentVault DB value; fall back to Config / env NOWPAYMENTS_IPN_SECRET.
    """
    if vault is not None:
        secret = (getattr(vault, "nowpayments_ipn_secret", None) or "").strip()
        if secret:
            return secret
    try:
        from models.payment_vault import PaymentVault

        row = PaymentVault.get_platform_vault()
        if row:
            secret = (getattr(row, "nowpayments_ipn_secret", None) or "").strip()
            if secret:
                return secret
    except Exception:
        logger.debug("Failed to load NOWPayments IPN secret from PaymentVault", exc_info=True)

    return (NowPaymentsProvider().ipn_secret or "").strip()
