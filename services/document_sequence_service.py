"""
خدمة الترقيم الذكي للمستندات - Document Sequence Service
Odoo-style ir.sequence for Azadexa
"""

from datetime import datetime, timezone
from flask import current_app
from sqlalchemy.exc import OperationalError
from extensions import db
from models import DocumentSequence


_MAX_LOCK_RETRIES = 3


def _safe_for_update(query, label='row'):
    """Execute SELECT … FOR UPDATE with savepoint-based retry.

    Uses savepoints so that a failed lock attempt does NOT roll back the
    caller's entire transaction.  On final failure, aborts — never silently
    drops the lock.

    Rationale: The previous try/except pattern silently fell back to an unlocked
    read when the lock could not be acquired, opening the door to race
    conditions where two concurrent transactions read the same value and
    both update it incorrectly.
    """
    for attempt in range(1, _MAX_LOCK_RETRIES + 1):
        savepoint = db.session.begin_nested()
        try:
            result = query.with_for_update().first()
            savepoint.commit()
            return result
        except OperationalError:
            savepoint.rollback()
            if attempt == _MAX_LOCK_RETRIES:
                current_app.logger.critical(
                    'Row-level lock acquisition failed after %d attempts for %s — aborting to prevent race condition.',
                    _MAX_LOCK_RETRIES, label,
                )
                raise
            current_app.logger.warning(
                'Lock contention on %s (attempt %d/%d) — retrying.',
                label, attempt, _MAX_LOCK_RETRIES,
            )
    raise RuntimeError(f'Failed to acquire row lock for {label}')


class DocumentSequenceService:

    @staticmethod
    def get_or_create(tenant_id, code, prefix=None, pattern=None, counter_reset='year', branch_scoped=False):
        """Get existing sequence or create default."""
        seq = DocumentSequence.query.filter_by(
            tenant_id=tenant_id, code=code
        ).first()
        if seq:
            return seq

        defaults = {
            'sale': ('SALE', '{prefix}-{year}-{counter:04d}', 'year', False),
            'purchase': ('PUR', '{prefix}-{year}-{counter:04d}', 'year', False),
            'payment': ('PAY', '{prefix}-{year}-{counter:04d}', 'year', False),
            'receipt': ('REC', '{prefix}-{year}-{counter:04d}', 'year', False),
            'gl_entry': ('GL', '{prefix}-{year}-{counter:04d}', 'year', False),
            'cheque': ('CHQ', '{prefix}-{year}-{counter:04d}', 'year', False),
            'invoice': ('INV', '{prefix}-{year}-{counter:04d}', 'year', False),
            'return': ('RET', '{prefix}-{year}-{counter:04d}', 'year', False),
            'expense': ('EXP', '{prefix}-{year}-{counter:04d}', 'year', False),
        }

        default = defaults.get(code, ('DOC', '{prefix}-{year}-{counter:04d}', 'year', False))
        seq = DocumentSequence(
            tenant_id=tenant_id,
            code=code,
            name=code.replace('_', ' ').title(),
            prefix=prefix or default[0],
            pattern=pattern or default[1],
            counter_reset=counter_reset or default[2],
            branch_scoped=branch_scoped if branch_scoped is not None else default[3],
        )
        db.session.add(seq)
        db.session.flush()
        return seq

    @staticmethod
    def next_number(tenant_id, code, branch_code=None, date=None):
        """
        Generate the next document number atomically.
        Uses SELECT FOR UPDATE with retry logic to prevent race conditions.
        """
        seq = DocumentSequenceService.get_or_create(tenant_id, code)
        if not seq.is_active:
            raise ValueError(f'Sequence {code} is inactive.')

        date = date or datetime.now(timezone.utc)

        # Lock the sequence row with retry logic
        locked = _safe_for_update(
            db.session.query(DocumentSequence).filter_by(id=seq.id),
            label=f'DocumentSequence({code})'
        )

        if not locked:
            raise ValueError(f'Sequence {code} not found after lock.')

        number = locked.get_next_number(branch_code=branch_code, date=date)
        db.session.flush()
        return number

    @staticmethod
    def preview(tenant_id, code, branch_code=None, date=None):
        """Preview next number without consuming the counter."""
        seq = DocumentSequenceService.get_or_create(tenant_id, code)
        date = date or datetime.now(timezone.utc)
        # Simulate without incrementing
        ctx = {
            'prefix': seq.prefix,
            'year': date.strftime('%Y'),
            'month': date.strftime('%m'),
            'day': date.strftime('%d'),
            'branch': branch_code or '',
            'tenant': str(seq.tenant_id),
            'counter': seq.counter,
        }
        pattern = seq.pattern
        for pad in [2, 3, 4, 5, 6]:
            placeholder = f'{{counter:0{pad}d}}'
            if placeholder in pattern:
                pattern = pattern.replace(placeholder, f'{seq.counter:0{pad}d}')
                break
        else:
            pattern = pattern.replace('{counter}', str(seq.counter))
        for key, val in ctx.items():
            if key != 'counter':
                pattern = pattern.replace(f'{{{key}}}', str(val))
        return pattern
