"""Push-to-terminal payment gateway for POS card transactions.

Provider-neutral adapter layer. The first (and currently only) provider is
Stripe Terminal: the backend mints short-lived connection tokens and creates
``card_present`` PaymentIntents; the register's browser then pushes the
payment to the paired reader via Stripe's Terminal JS SDK.

When no provider is configured (missing API keys) the service reports
``configured=False`` and the register keeps the existing manual card flow —
this module never touches the payment vault or the GL; settlement posting
stays on the proven manual path until a provider confirms the charge.

All network calls use stdlib urllib with a hard timeout so a hung provider
can never wedge the checkout UI thread.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)

_STRIPE_API_BASE = "https://api.stripe.com"
_PROVIDER_TIMEOUT_SECONDS = 10
_MINOR_UNIT_QUANTUM = Decimal("0.01")

PROVIDER_STRIPE_TERMINAL = "stripe_terminal"


class PosTerminalError(Exception):
    """Safe, user-presentable terminal failure (no raw provider payloads)."""


def _stripe_secret_key() -> str:
    return (os.getenv("STRIPE_SECRET_KEY") or "").strip()


def is_configured(provider: str = PROVIDER_STRIPE_TERMINAL) -> bool:
    """True when the requested provider has the credentials it needs."""
    if provider == PROVIDER_STRIPE_TERMINAL:
        return bool(_stripe_secret_key())
    return False


def terminal_status(provider: str = PROVIDER_STRIPE_TERMINAL) -> dict:
    return {"provider": provider, "configured": is_configured(provider)}


def amount_to_minor_units(amount, currency: str = "AED") -> int:
    """Exact minor-unit conversion (AED fils): quantize then scale."""
    value = Decimal(str(amount or "0")).quantize(_MINOR_UNIT_QUANTUM, rounding=ROUND_HALF_UP)
    if value <= 0:
        raise PosTerminalError("المبلغ يجب أن يكون أكبر من صفر.")
    return int(value * 100)


def _stripe_post(path: str, params: dict) -> dict:
    key = _stripe_secret_key()
    if not key:
        raise PosTerminalError("الدفع الطرفي غير مهيأ لهذه الشركة.")
    body = urllib.parse.urlencode(params, doseq=True).encode("utf-8")
    req = urllib.request.Request(
        f"{_STRIPE_API_BASE}{path}",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_PROVIDER_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        logger.warning("Stripe Terminal HTTP %s on %s", exc.code, path)
        raise PosTerminalError("رفض مزود الدفع العملية. حاول مرة أخرى أو استخدم الدفع اليدوي.") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Stripe Terminal transport failure on %s: %s", path, type(exc).__name__)
        raise PosTerminalError("تعذر الوصول إلى مزود الدفع. تحقق من الاتصال أو استخدم الدفع اليدوي.") from exc


def create_connection_token() -> str:
    """Short-lived token the browser uses to connect to the reader."""
    payload = _stripe_post("/v1/terminal/connection_tokens", {})
    secret = payload.get("secret")
    if not secret:
        raise PosTerminalError("استجابة غير مكتملة من مزود الدفع.")
    return secret


def create_terminal_payment_intent(
    amount,
    *,
    currency: str = "AED",
    tenant_id: int | None = None,
    sale_reference: str | None = None,
) -> dict:
    """Create a card_present PaymentIntent ready for reader collection."""
    minor = amount_to_minor_units(amount, currency)
    params = {
        "amount": str(minor),
        "currency": (currency or "AED").lower(),
        "capture_method": "automatic",
        "payment_method_types[]": "card_present",
    }
    if tenant_id is not None:
        params["metadata[tenant_id]"] = str(tenant_id)
    if sale_reference:
        params["metadata[sale_reference]"] = str(sale_reference)[:200]
    payload = _stripe_post("/v1/payment_intents", params)
    intent_id = payload.get("id")
    client_secret = payload.get("client_secret")
    if not intent_id or not client_secret:
        raise PosTerminalError("استجابة غير مكتملة من مزود الدفع.")
    return {
        "id": intent_id,
        "client_secret": client_secret,
        "amount_minor": minor,
        "currency": params["currency"],
        "status": payload.get("status", ""),
    }
