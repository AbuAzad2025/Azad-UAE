"""
Mandatory GL posting — no financial document commits without a balanced journal entry.
"""
from __future__ import annotations

from decimal import Decimal


class GlPostingError(Exception):
    """Raised when a journal entry cannot be posted."""


def post_or_fail(
    lines,
    *,
    description,
    reference_type=None,
    reference_id=None,
    date=None,
    currency='AED',
    exchange_rate=1.0,
    branch_id=None,
    user_id=None,
):
    from services.gl_service import GLService

    if not lines:
        raise GlPostingError(f'لا يمكن ترحيل "{description}" بدون سطور قيد.')

    try:
        return GLService.post_entry(
            lines,
            description=description,
            reference_type=reference_type,
            reference_id=reference_id,
            date=date,
            currency=currency,
            exchange_rate=exchange_rate,
            branch_id=branch_id,
            user_id=user_id,
        )
    except Exception as exc:
        raise GlPostingError(str(exc)) from exc


def assert_balanced_lines(lines, *, tolerance=Decimal('0.001')):
    total_debit = sum(Decimal(str(l.get('debit', 0) or 0)) for l in lines)
    total_credit = sum(Decimal(str(l.get('credit', 0) or 0)) for l in lines)
    if abs(total_debit - total_credit) > tolerance:
        raise GlPostingError(
            f'القيد غير متوازن: مدين={total_debit} دائن={total_credit}'
        )
