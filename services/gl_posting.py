"""
Mandatory GL posting — no financial document commits without a balanced journal entry.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from utils.currency_utils import get_system_default_currency, resolve_default_currency


class GlPostingError(Exception):
    """Raised when a journal entry cannot be posted."""


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
):
    # Resolve currency from tenant if not explicitly provided
    if currency is None:
        try:
            from models.tenant import Tenant
            t = Tenant.query.get(tenant_id) if tenant_id else Tenant.get_current()
            currency = resolve_default_currency(t)
        except Exception:
            currency = get_system_default_currency()

    from services.gl_helpers import assert_period_open
    from services.gl_service import GLService

    if not lines:
        raise GlPostingError(f'لا يمكن ترحيل "{description}" بدون سطور قيد.')

    entry_date = date or datetime.now(timezone.utc)
    assert_period_open(entry_date, tenant_id)

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
            tenant_id=tenant_id,
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
