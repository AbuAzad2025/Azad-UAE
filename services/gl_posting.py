"""
Mandatory GL posting — no financial document commits without a balanced journal entry.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from models.tenant import Tenant
from services.gl_helpers import assert_period_open
from services.gl_service import GLService
from utils.currency_utils import (
    convert_and_quantize_aed,
    get_system_default_currency,
    resolve_default_currency,
    resolve_tenant_base_currency,
)

logger = logging.getLogger(__name__)

_BASE_QUANTUM = Decimal("0.001")
_ROUNDING_PLUG_MAX = Decimal("0.01")


class GlPostingError(Exception):
    """Raised when a journal entry cannot be posted."""


class UnbalancedJournalEntryError(GlPostingError):
    """Raised when Sum(debit) != Sum(credit) in a journal entry."""


def _normalize_lines_to_base(lines, *, currency, exchange_rate, base_currency, tenant_id):
    """Convert line amounts to the tenant base currency with strict quantization.

    The General Ledger is stored in base currency only: every line's
    ``debit``/``credit`` is routed through ``convert_and_quantize_aed``
    (Decimal, 0.001, ROUND_HALF_UP; base-currency fast-track) and the original
    transaction-currency values are preserved in ``original_debit`` /
    ``original_credit`` so the persisted line keeps both perspectives.

    Independent per-line rounding can drift the totals by a few fils; a
    deterministic plug moves the residual (up to 0.01) onto the largest line
    of the heavier side so Sum(debit) == Sum(credit) holds exactly in base.
    """
    converted = []
    for line in lines:
        orig_debit = Decimal(str(line.get("debit", 0) or 0))
        orig_credit = Decimal(str(line.get("credit", 0) or 0))
        new_line = dict(line)
        new_line["debit"] = convert_and_quantize_aed(
            orig_debit, currency, exchange_rate, base_currency=base_currency, tenant_id=tenant_id
        )
        new_line["credit"] = convert_and_quantize_aed(
            orig_credit, currency, exchange_rate, base_currency=base_currency, tenant_id=tenant_id
        )
        new_line.setdefault("original_debit", orig_debit)
        new_line.setdefault("original_credit", orig_credit)
        converted.append(new_line)

    total_debit = sum(line["debit"] for line in converted)
    total_credit = sum(line["credit"] for line in converted)
    diff = (total_debit - total_credit).quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
    if diff and abs(diff) <= _ROUNDING_PLUG_MAX:
        side = "debit" if diff > 0 else "credit"
        target = max(converted, key=lambda line: line[side])
        target[side] = (target[side] - diff).quantize(_BASE_QUANTUM, rounding=ROUND_HALF_UP)
        logger.info("GL rounding plug: adjusted %s by %s (base %s)", side, diff, base_currency)
    return converted


def post_or_fail(
    lines,
    *,
    description,
    reference_type=None,
    reference_id=None,
    date=None,
    currency=None,
    exchange_rate=1.0,
    branch_id=None,
    user_id=None,
    tenant_id=None,
    commit=False,
):
    """
    Post a journal entry with mandatory validation flow.

    New flow: Draft → Validated → Posted
    - Entry is created as 'draft'
    - Must pass validation (balance, header account checks)
    - Only then can be posted to GL

    Args:
        lines: صفحات القيد المحاسبي — المبالغ بعملة المستند (currency) ويتم
               تحويلها إلى عملة أساس المستأجر عند هذه البوابة قبل الحفظ
        description: وصف القيد
        reference_type: نوع المرجع
        reference_id: رقم المرجع
        date: تاريخ القيد
        currency: عملة مبالغ السطور (تُحوَّل إلى عملة الأساس عند الترحيل)
        exchange_rate: سعر الصرف من currency إلى عملة الأساس
        branch_id: معرف الفرع
        user_id: معرف المستخدم
        tenant_id: معرف المستأجر
        commit: If False (default), the caller owns the transaction boundary.
                Use True for standalone calls (e.g. admin UI journal entry)
                that are not wrapped in an outer atomic_transaction.
    """
    # Resolve currency from tenant if not explicitly provided
    if currency is None:
        try:
            t = db.session.get(Tenant, tenant_id) if tenant_id else Tenant.get_current()
            currency = resolve_default_currency(t)
        except (LookupError, AttributeError, TypeError, ValueError):
            currency = get_system_default_currency()

    if not lines:
        raise GlPostingError(f'لا يمكن ترحيل "{description}" بدون سطور قيد.')

    assert_balanced_lines(lines, currency=currency)

    entry_date = date or datetime.now(timezone.utc)
    assert_period_open(entry_date, tenant_id)

    # The GL is stored in the tenant base currency only: convert and quantize
    # every line at this final gateway before anything is persisted.
    base_currency = resolve_tenant_base_currency(tenant_id=tenant_id)
    if exchange_rate is None:
        rate = Decimal("1")
    else:
        rate = Decimal(str(exchange_rate))
    if rate <= 0:
        if (currency or "").upper() != (base_currency or "").upper():
            raise GlPostingError(f'سعر صرف غير صالح للقيد "{description}": {exchange_rate}')
        rate = Decimal("1")
    lines = _normalize_lines_to_base(
        lines,
        currency=currency,
        exchange_rate=rate,
        base_currency=base_currency,
        tenant_id=tenant_id,
    )

    try:
        # Create entry as draft first
        entry = GLService.create_journal_entry(
            date=entry_date,
            description=description,
            lines=lines,
            user_id=user_id,
            branch_id=branch_id,
            reference_type=reference_type,
            reference_id=reference_id,
            tenant_id=tenant_id,
            currency=currency,
            exchange_rate=exchange_rate,
            entry_type="auto",
        )

        # Validate the entry (sets status to 'validated' or 'error')
        from services.advanced_journal_manager import AdvancedJournalEntryManager

        validated_entry = AdvancedJournalEntryManager.validate_entry(
            entry_id=entry.id,
            validated_by=user_id,
            tenant_id=tenant_id,
            commit=False,  # Don't commit yet, we'll commit after posting
        )

        if validated_entry.status == "error":
            raise GlPostingError(f'Validation failed for entry "{description}": {validated_entry.validation_errors}')

        # Post the validated entry
        posted_entry = AdvancedJournalEntryManager.post_entry(
            entry_id=entry.id,
            posted_by=user_id,
            post_notes=None,
            commit=commit,
        )

        return posted_entry
    except Exception as exc:
        raise GlPostingError(str(exc)) from exc


_CURRENCY_TOLERANCE = {
    "JOD": Decimal("0.00001"),
    "BHD": Decimal("0.00001"),
    "KWD": Decimal("0.00001"),
    "OMR": Decimal("0.00001"),
    "QAR": Decimal("0.00001"),
    "ILS": Decimal("0.001"),
    "AED": Decimal("0.001"),
    "USD": Decimal("0.001"),
    "EUR": Decimal("0.001"),
}
_DEFAULT_TOLERANCE = Decimal("0.001")


def assert_balanced_lines(lines, *, currency=None, tolerance=None):
    if tolerance is None:
        tolerance = _CURRENCY_TOLERANCE.get((currency or "").upper(), _DEFAULT_TOLERANCE)
    total_debit = sum(Decimal(str(line.get("debit", 0) or 0)) for line in lines)
    total_credit = sum(Decimal(str(line.get("credit", 0) or 0)) for line in lines)
    if abs(total_debit - total_credit) > tolerance:
        raise UnbalancedJournalEntryError(f"القيد غير متوازن: مدين={total_debit} دائن={total_credit}")
