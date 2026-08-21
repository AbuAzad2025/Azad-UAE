"""Shared, route-agnostic helpers for the POS checkout flow."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from flask_babel import gettext

from services.pricing_service import PricingService
from utils.currency_utils import convert_and_quantize_aed

_TENDER_CASH_METHOD = "cash"
_TENDER_CARD_METHODS = ("card", "bank_transfer", "e_wallet")


def _pos_standard_price(product, customer_type, quantity):
    """Tier-aware standard POS price via PricingService, quantized to 0.001."""
    price = PricingService.get_price(product, customer_type, quantity)
    return Decimal(str(price)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _promotion_evaluation_json(evaluation):
    """Serialize PromotionService.evaluate_cart output for JSON responses."""
    if not evaluation:
        return {
            "lines": [],
            "subtotal_before": 0.0,
            "total_discount": 0.0,
            "subtotal_after": 0.0,
            "applied_rules": [],
            "upsell_prompts": [],
        }
    return {
        "lines": [
            {
                "product_id": line["product_id"],
                "quantity": float(line["quantity"]),
                "unit_price": float(line["unit_price"]),
                "original_total": float(line["original_total"]),
                "discount_amount": float(line["discount_amount"]),
                "adjusted_total": float(line["adjusted_total"]),
            }
            for line in evaluation["lines"]
        ],
        "subtotal_before": float(evaluation["subtotal_before"]),
        "total_discount": float(evaluation["total_discount"]),
        "subtotal_after": float(evaluation["subtotal_after"]),
        "applied_rules": [
            {
                "campaign_id": rule["campaign_id"],
                "name": rule["name"],
                "campaign_type": rule["campaign_type"],
                "discount_amount": float(rule["discount_amount"]),
            }
            for rule in evaluation["applied_rules"]
        ],
        "upsell_prompts": evaluation["upsell_prompts"],
    }


def _parse_split_tenders(raw_payments, default_currency, default_rate):
    """Validate the Phase 2 ``payments`` array into tender chunk dicts.

    Returns ``(chunks, error_message)`` — exactly one of the two is set.
    Amounts stay ``Decimal``; conversion happens per chunk in SaleService.
    """
    if not isinstance(raw_payments, list) or not raw_payments:
        return None, gettext("قائمة الدفعات غير صالحة.")
    chunks = []
    for chunk in raw_payments:
        if not isinstance(chunk, dict):
            return None, gettext("بيانات الدفعة غير صالحة.")
        try:
            amount = Decimal(str(chunk.get("amount") or "0"))
        except (InvalidOperation, TypeError, ValueError):
            return None, gettext("مبلغ الدفعة غير صالح.")
        if amount <= Decimal("0"):
            return None, gettext("مبلغ الدفعة يجب أن يكون أكبر من صفر.")
        method = (chunk.get("payment_method") or chunk.get("method") or "").strip()
        if not method:
            return None, gettext("يرجى اختيار طريقة الدفع لكل دفعة.")
        try:
            rate = Decimal(str(chunk.get("exchange_rate") or default_rate or "1"))
        except (InvalidOperation, TypeError, ValueError):
            return None, gettext("سعر الصرف غير صالح.")
        chunks.append(
            {
                "amount": amount,
                "payment_method": method,
                "currency": (chunk.get("currency") or default_currency).strip().upper(),
                "exchange_rate": rate,
                "reference_number": (chunk.get("reference_number") or "").strip() or None,
                "cheque_number": chunk.get("cheque_number"),
                "cheque_date": chunk.get("cheque_date"),
                "bank_name": chunk.get("bank_name"),
                "notes": chunk.get("notes"),
            }
        )
    return chunks, None


def _tender_chunk_aed(chunk, tenant_id):
    """Exact base-currency amount of a parsed tender chunk."""
    return convert_and_quantize_aed(
        chunk["amount"],
        chunk["currency"],
        chunk["exchange_rate"],
        tenant_id=tenant_id,
    )


def _accumulate_session_tender(session, chunk, tenant_id):
    """Accumulate per-tender session totals for a split-tender chunk."""
    method = chunk.get("payment_method")
    chunk_aed = _tender_chunk_aed(chunk, tenant_id)
    if method == _TENDER_CASH_METHOD:
        session.total_cash_sales = Decimal(str(session.total_cash_sales or 0)) + chunk_aed
    elif method in _TENDER_CARD_METHODS:
        session.total_card_sales = Decimal(str(session.total_card_sales or 0)) + chunk_aed


def _compute_change_due(
    sale,
    payments_data,
    payment_data,
    payment_currency,
    payment_exchange_rate,
    tenant_id,
):
    """Cash change owed when the tender exceeds the invoice total.

    Reporting metadata only — the overpayment itself is still booked as
    customer prepayment credit by SaleService (unchanged behavior).
    """
    sale_total_aed = getattr(sale, "amount_aed", None)
    if not isinstance(sale_total_aed, Decimal):
        return Decimal("0")
    tendered_aed = Decimal("0")
    cash_tendered = False
    if payments_data:
        for chunk in payments_data:
            tendered_aed += _tender_chunk_aed(chunk, tenant_id)
            if chunk.get("payment_method") == _TENDER_CASH_METHOD:
                cash_tendered = True
    elif payment_data and payment_data.get("payment_method") == _TENDER_CASH_METHOD:
        cash_tendered = True
        tendered_aed = convert_and_quantize_aed(
            payment_data.get("amount", 0),
            payment_currency,
            payment_exchange_rate,
            tenant_id=tenant_id,
        )
    if not cash_tendered:
        return Decimal("0")
    return max(tendered_aed - sale_total_aed, Decimal("0"))
