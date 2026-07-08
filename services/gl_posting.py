"""
Mandatory GL posting — no financial document commits without a balanced journal entry.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from extensions import db
from models.tenant import Tenant
from services.gl_helpers import assert_period_open
from services.gl_service import GLService
from utils.currency_utils import get_system_default_currency, resolve_default_currency


class GlPostingError(Exception):
    """Raised when a journal entry cannot be posted."""


class UnbalancedJournalEntryError(GlPostingError):
    """Raised when Sum(debit) != Sum(credit) in a journal entry."""


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
            entry_type='auto',
        )

        # Validate the entry (sets status to 'validated' or 'error')
        from services.advanced_journal_manager import AdvancedJournalEntryManager
        validated_entry = AdvancedJournalEntryManager.validate_entry(
            entry_id=entry.id,
            validated_by=user_id,
            tenant_id=tenant_id,
            commit=False  # Don't commit yet, we'll commit after posting
        )

        if validated_entry.status == 'error':
            db.session.rollback()
            raise GlPostingError(
                f'Validation failed for entry "{description}": {validated_entry.validation_errors}'
            )

        # Post the validated entry
        posted_entry = AdvancedJournalEntryManager.post_entry(
            entry_id=entry.id,
            posted_by=user_id,
            post_notes=None,
            commit=commit,
        )

        return posted_entry
    except Exception as exc:
        db.session.rollback()
        raise GlPostingError(str(exc)) from exc


_CURRENCY_TOLERANCE = {
    'JOD': Decimal('0.00001'),
    'BHD': Decimal('0.00001'),
    'KWD': Decimal('0.00001'),
    'OMR': Decimal('0.00001'),
    'QAR': Decimal('0.00001'),
    'ILS': Decimal('0.001'),
    'AED': Decimal('0.001'),
    'USD': Decimal('0.001'),
    'EUR': Decimal('0.001'),
}
_DEFAULT_TOLERANCE = Decimal('0.001')


def assert_balanced_lines(lines, *, currency=None, tolerance=None):
    if tolerance is None:
        tolerance = _CURRENCY_TOLERANCE.get((currency or '').upper(), _DEFAULT_TOLERANCE)
    total_debit = sum(Decimal(str(l.get('debit', 0) or 0)) for l in lines)
    total_credit = sum(Decimal(str(l.get('credit', 0) or 0)) for l in lines)
    if abs(total_debit - total_credit) > tolerance:
        raise UnbalancedJournalEntryError(
            f'القيد غير متوازن: مدين={total_debit} دائن={total_credit}'
        )
