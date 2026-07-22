"""Unrealized FX Revaluation Service.

Month-end revaluation of open foreign-currency AR (Sales) and AP (Purchases)
to current exchange rates, posting unrealized FX gain/loss to GL.

Design:
  - revaluate_open_items(): scan all open AR/AP in non-base currencies,
    compute unrealized diff, post GL entries tagged with a batch marker.
  - reverse_previous_revaluation(): find and reverse the prior period's
    revaluation entries (unwinds them before the new month's revaluation).
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from utils.db_safety import atomic_transaction
from utils.currency_utils import (
    resolve_tenant_base_currency,
    convert_and_quantize_aed,
)
from utils.gl_reference_types import GLRef
from services.gl_service import GLService
from services.gl_posting import post_or_fail
from services.exchange_rate_service import ExchangeRateService

logger = logging.getLogger(__name__)

_REVALUATION_TAG = "FX_REVALUATION"
_THRESHOLD = Decimal("0.01")


def _current_rate(from_currency: str, to_currency: str, tenant_id: int | None) -> Decimal:
    rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction(
        from_currency,
        to_currency,
        tenant_id=tenant_id,
    )
    return Decimal(str(rate_info["rate"]))


def _open_sales(tenant_id: int | None, base_currency: str):
    from models import Sale

    q = Sale.query.filter(
        Sale.payment_status.in_(["unpaid", "partial"]),
        Sale.currency != base_currency,
        Sale.status != "cancelled",
    )
    if tenant_id is not None:
        q = q.filter(Sale.tenant_id == tenant_id)
    return q.all()


def _open_purchases(tenant_id: int | None, base_currency: str):
    from models import Purchase

    q = Purchase.query.filter(
        Purchase.currency != base_currency,
        Purchase.status != "cancelled",
    )
    if tenant_id is not None:
        q = q.filter(Purchase.tenant_id == tenant_id)
    results = []
    for p in q.all():
        paid = p.get_paid_amount()
        balance = Decimal(str(p.amount_aed or 0)) - Decimal(str(paid or 0))
        if balance > _THRESHOLD:
            results.append((p, balance))
    return results


def revaluate_open_items(tenant_id: int | None = None) -> dict:
    """Run month-end revaluation for all open foreign-currency AR/AP.

    Returns a summary dict with keys: ar_count, ap_count, ar_diff, ap_diff,
    entry_ids.
    """
    base_currency = resolve_tenant_base_currency(tenant_id=tenant_id)
    summary = {
        "ar_count": 0,
        "ap_count": 0,
        "ar_diff": Decimal("0"),
        "ap_diff": Decimal("0"),
        "entry_ids": [],
        "errors": [],
    }

    open_sales = _open_sales(tenant_id, base_currency)
    open_purchases = _open_purchases(tenant_id, base_currency)

    if not open_sales and not open_purchases:
        logger.info("No open foreign-currency items to revaluate for tenant %s", tenant_id)
        return summary

    now = datetime.now(timezone.utc)
    ar_concept = GLService.get_account_code_for_concept(
        "AR",
        tenant_id=tenant_id,
        fallback_key="receivable",
    )
    ap_concept = GLService.get_account_code_for_concept(
        "AP",
        tenant_id=tenant_id,
        fallback_key="payable",
    )
    fx_gain = GLService.get_account_code_for_concept(
        "FX_GAIN",
        tenant_id=tenant_id,
        fallback_key="fx_gain",
    )
    fx_loss = GLService.get_account_code_for_concept(
        "FX_LOSS",
        tenant_id=tenant_id,
        fallback_key="fx_loss",
    )

    with atomic_transaction("fx_revaluation"):
        if open_sales:
            _post_ar_revaluation(
                open_sales,
                base_currency,
                tenant_id,
                now,
                ar_concept,
                fx_gain,
                fx_loss,
                summary,
            )
        if open_purchases:
            _post_ap_revaluation(
                open_purchases,
                base_currency,
                tenant_id,
                now,
                ap_concept,
                fx_gain,
                fx_loss,
                summary,
            )

    return summary


def _post_ar_revaluation(open_sales, base_currency, tenant_id, now, ar_concept, fx_gain, fx_loss, summary):
    all_lines = []
    total_fx_diff = Decimal("0")

    for sale in open_sales:
        current = _current_rate(sale.currency, base_currency, tenant_id)
        original = Decimal(str(sale.exchange_rate or 1))
        if current == original:
            continue

        original_aed = Decimal(str(sale.amount_aed or 0))
        revalued = convert_and_quantize_aed(
            Decimal(str(sale.amount or 0)),
            sale.currency,
            current,
            base_currency=base_currency,
            tenant_id=tenant_id,
        )
        fx_diff = (revalued - original_aed).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if abs(fx_diff) <= _THRESHOLD:
            continue

        summary["ar_count"] += 1
        total_fx_diff += fx_diff
        desc = f"Unrealized FX Revaluation — Sale #{sale.sale_number} ({sale.currency})"

        if fx_diff > 0:
            all_lines.extend(
                [
                    {"account": ar_concept, "concept_code": "AR", "debit": fx_diff, "description": desc},
                    {"account": fx_gain, "concept_code": "FX_GAIN", "credit": fx_diff, "description": desc},
                ]
            )
        else:
            gain = abs(fx_diff)
            all_lines.extend(
                [
                    {"account": fx_loss, "concept_code": "FX_LOSS", "debit": gain, "description": desc},
                    {"account": ar_concept, "concept_code": "AR", "credit": gain, "description": desc},
                ]
            )

    if all_lines and total_fx_diff != 0:
        entry = post_or_fail(
            all_lines,
            description=f"FX Revaluation — AR — {now.strftime('%Y-%m')}",
            reference_type=GLRef.FX_GAIN_LOSS,
            reference_id=0,
            date=now.replace(tzinfo=None),
            currency=base_currency,
            exchange_rate=Decimal("1"),
            branch_id=None,
            tenant_id=tenant_id,
        )
        entry.notes = f"{_REVALUATION_TAG}|{now.strftime('%Y-%m')}"
        db.session.flush()
        summary["ar_diff"] = total_fx_diff
        summary["entry_ids"].append(entry.id)


def _post_ap_revaluation(open_purchases, base_currency, tenant_id, now, ap_concept, fx_gain, fx_loss, summary):
    all_lines = []
    total_fx_diff = Decimal("0")

    for purchase, balance_aed in open_purchases:
        current = _current_rate(purchase.currency, base_currency, tenant_id)
        original = Decimal(str(purchase.exchange_rate or 1))
        if current == original:
            continue

        original_aed = Decimal(str(purchase.amount_aed or 0))
        revalued = convert_and_quantize_aed(
            Decimal(str(purchase.amount or 0)),
            purchase.currency,
            current,
            base_currency=base_currency,
            tenant_id=tenant_id,
        )
        fx_diff = (revalued - original_aed).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if abs(fx_diff) <= _THRESHOLD:
            continue

        summary["ap_count"] += 1
        total_fx_diff += fx_diff
        desc = f"Unrealized FX Revaluation — Purchase #{purchase.purchase_number} ({purchase.currency})"

        if fx_diff > 0:
            all_lines.extend(
                [
                    {"account": fx_loss, "concept_code": "FX_LOSS", "debit": fx_diff, "description": desc},
                    {"account": ap_concept, "concept_code": "AP", "credit": fx_diff, "description": desc},
                ]
            )
        else:
            gain = abs(fx_diff)
            all_lines.extend(
                [
                    {"account": ap_concept, "concept_code": "AP", "debit": gain, "description": desc},
                    {"account": fx_gain, "concept_code": "FX_GAIN", "credit": gain, "description": desc},
                ]
            )

    if all_lines and total_fx_diff != 0:
        entry = post_or_fail(
            all_lines,
            description=f"FX Revaluation — AP — {now.strftime('%Y-%m')}",
            reference_type=GLRef.FX_GAIN_LOSS,
            reference_id=0,
            date=now.replace(tzinfo=None),
            currency=base_currency,
            exchange_rate=Decimal("1"),
            branch_id=None,
            tenant_id=tenant_id,
        )
        entry.notes = f"{_REVALUATION_TAG}|{now.strftime('%Y-%m')}"
        db.session.flush()
        summary["ap_diff"] = total_fx_diff
        summary["entry_ids"].append(entry.id)


def reverse_previous_revaluation(
    period_month: str,
    tenant_id: int | None = None,
) -> list[int]:
    """Reverse all revaluation entries for a given period (YYYY-MM format).

    Finds GL entries tagged with the revaluation marker and calls
    ``GLJournalEntry.reverse_entry()`` on each. Returns a list of
    reversed entry IDs.
    """
    from models.gl import GLJournalEntry

    tag = f"{_REVALUATION_TAG}|{period_month}"
    q = GLJournalEntry.query.filter(
        GLJournalEntry.notes.like(f"%{tag}%"),
        GLJournalEntry.status == "posted",
        GLJournalEntry.is_reversed.is_(False),
    )
    if tenant_id is not None:
        q = q.filter(GLJournalEntry.tenant_id == tenant_id)

    reversed_ids = []
    with atomic_transaction("fx_revaluation_reversal"):
        for entry in q.all():
            reversed_entry = entry.reverse_entry(
                description=f"Reverse FX Revaluation — {period_month}",
            )
            reversed_ids.append(reversed_entry.id)

    return reversed_ids
