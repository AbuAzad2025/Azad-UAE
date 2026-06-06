"""NOWPayments IPN URL and secret helpers."""
from __future__ import annotations

from flask import current_app


def get_nowpayments_ipn_url() -> str:
    """Canonical IPN callback URL for per-payment NOWPayments requests."""
    base = (current_app.config.get("BASE_URL") or "").rstrip("/")
    if not base:
        return "/payment-vault/webhook/nowpayments"
    return f"{base}/payment-vault/webhook/nowpayments"


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
        pass
    return (current_app.config.get("NOWPAYMENTS_IPN_SECRET") or "").strip()
