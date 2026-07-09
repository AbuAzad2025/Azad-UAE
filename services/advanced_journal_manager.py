from datetime import datetime, timezone
import json
from extensions import db
from utils.db_safety import atomic_transaction
from decimal import Decimal
from sqlalchemy import event
from models.gl import GLJournalEntry, GLJournalLine
from models.journal_entry_audit import JournalEntryAudit

# ── Allowed state transitions ───────────────────────────────────────────
_VALID_TRANSITIONS = {
    'draft':     {'validated', 'error', 'cancelled'},
    'validated': {'posted', 'error', 'cancelled'},
    'error':     {'draft', 'cancelled'},  # retry after fixing
    'posted':    {'reversed', 'cancelled'},
    'reversed':  set(),  # terminal
    'cancelled': set(),  # terminal (soft-delete)
}


class AdvancedJournalEntryManager:
    """مدير القيود المحاسبية المتقدم — state-machine aware."""

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _entry_or_404(entry_id, tenant_id=None):
        from flask import abort
        from utils.gl_tenant import gl_entry_query, active_tenant_id
        tid = tenant_id if tenant_id is not None else active_tenant_id()
        entry = gl_entry_query(tenant_id=tid).filter_by(id=entry_id).first()
        if not entry:
            abort(404)
        return entry

    @staticmethod
    def _transition(entry, new_status, *, user_id=None, reason=None):
        """Enforce state machine. Raises ValueError on illegal transitions."""
        current = entry.status
        if new_status not in _VALID_TRANSITIONS.get(current, set()):
            raise ValueError(
                f'Illegal journal status transition: {current} → {new_status}. '
                f'Allowed: {sorted(_VALID_TRANSITIONS.get(current, set())) or "(none)"}'
            )
        entry.status = new_status
        if new_status == 'reversed':
            entry.is_reversed = True
        if new_status == 'posted':
            entry.is_posted = True
            entry.validated_at = entry.validated_at or datetime.now(timezone.utc)
        entry.updated_at = datetime.now(timezone.utc)

    # ── Validate ─────────────────────────────────────────────────────────

    @staticmethod
    def validate_entry(entry_id, validated_by, tenant_id=None, commit=True):
        """Mandatory validation step before posting.

        Checks:
        1. SUM(debit) == SUM(credit) (currency-aware tolerance)
        2. No header accounts used directly

        Sets status='validated' on success, 'error' on failure.

        Args:
            commit: If False, changes stay in the session without committing.
                    Caller is responsible for committing. Used by
                    reverse_entry_advanced to group validate+post atomically.
        """
        from services.gl_posting import assert_balanced_lines
        entry = AdvancedJournalEntryManager._entry_or_404(entry_id, tenant_id)
        if entry.status not in ('draft', 'error'):
            raise ValueError(f'Cannot validate entry in status: {entry.status}')

        errors = []
        # 1. Balance check
        try:
            lines_data = [
                {'debit': float(l.debit or 0), 'credit': float(l.credit or 0)}
                for l in entry.lines
            ]
            assert_balanced_lines(lines_data, currency=entry.currency)
        except Exception as exc:
            errors.append(f'Balance: {exc}')

        # 2. Header account check
        for line in entry.lines:
            if line.account and line.account.is_header:
                errors.append(f'Header account used: {line.account.full_name}')

        entry.validated_by = validated_by
        entry.validated_at = datetime.now(timezone.utc)

        if errors:
            entry.status = 'error'
            entry.validation_errors = json.dumps(errors, ensure_ascii=False)
            entry.is_posted = False
        else:
            entry.status = 'validated'
            entry.validation_errors = None

        AdvancedJournalEntryManager._log_audit(
            entry.id, 'validate', None, entry.to_dict(),
            f'Validation {"failed" if errors else "passed"}: {json.dumps(errors)}' if errors else 'Validation passed',
            validated_by,
        )
        if commit:
            try:
                db.session.flush()
            except Exception:
                db.session.rollback()
                raise
        return entry

    # ── Create ───────────────────────────────────────────────────────────

    @staticmethod
    def create_entry_with_validation(description, lines, entry_date=None, notes=None, created_by=None, **kwargs):
        """إنشاء قيد — defaults to 'draft' so it must be validated before posting."""
        from services.gl_service import GLService
        from services.gl_posting import assert_balanced_lines

        # Inline balance check (fast-fail before DB round-trip)
        total_debit = sum(line.get('debit', 0) for line in lines)
        total_credit = sum(line.get('credit', 0) for line in lines)
        if abs(total_debit - total_credit) > 0.01:
            raise ValueError(f"القيد غير متوازن: المدين {total_debit} ≠ الدائن {total_credit}")

        # Header account check
        for line in lines:
            account_code = line.get('account_code')
            if account_code:
                from utils.gl_tenant import get_gl_account_by_code, active_tenant_id
                account = get_gl_account_by_code(account_code, tenant_id=kwargs.get('tenant_id') or active_tenant_id())
                if account and account.is_header:
                    raise ValueError(f"لا يمكن القيد على الحساب الرئيسي: {account.full_name}")

        entry = GLService.create_manual_entry(
            description=description,
            lines=lines,
            entry_date=entry_date,
            notes=notes,
            created_by=created_by,
            branch_id=kwargs.get('branch_id'),
            **kwargs
        )

        # Set initial status to 'draft' (new entries must be validated)
        entry.status = 'draft'
        entry.is_posted = False

        AdvancedJournalEntryManager._log_audit(
            entry.id, 'create', None, entry.to_dict(),
            f"إنشاء قيد جديد: {description}", created_by
        )
        return entry

    # ── Update (draft only) ──────────────────────────────────────────────

    @staticmethod
    def update_entry(entry_id, updates, updated_by, reason=None, commit=True):
        """تحديث قيد محاسبي — only draft entries."""
        entry = AdvancedJournalEntryManager._entry_or_404(entry_id)
        if entry.status not in ('draft', 'error'):
            raise ValueError(f"لا يمكن تعديل قيد بحالة: {entry.status}")

        old_values = entry.to_dict()
        for field, value in updates.items():
            if hasattr(entry, field):
                setattr(entry, field, value)

        if 'lines' in updates:
            total_debit = sum(line.get('debit', 0) for line in updates['lines'])
            total_credit = sum(line.get('credit', 0) for line in updates['lines'])
            if abs(total_debit - total_credit) > 0.01:
                raise ValueError(f"القيد غير متوازن بعد التحديث: المدين {total_debit} ≠ الدائن {total_credit}")

        entry.updated_at = datetime.now(timezone.utc)
        AdvancedJournalEntryManager._log_audit(
            entry_id, 'update', old_values, entry.to_dict(),
            reason or "تحديث القيد", updated_by
        )
        try:
            if commit:
                db.session.flush()
            else:
                db.session.flush()
        except Exception:
            db.session.rollback()
            raise
        return entry

    # ── Post (requires validated status) ─────────────────────────────────

    @staticmethod
    def post_entry(entry_id, posted_by, post_notes=None, commit=True):
        """Post a validated entry to the GL.

        Args:
            commit: If True (default), performs db.session.flush().
                    If False, performs db.session.flush() instead, letting
                    the caller own the transaction boundary. Used by
                    reverse_entry_advanced and post_or_fail(commit=False)
                    to group validate+post atomically in an outer
                    atomic_transaction.
        """
        entry = AdvancedJournalEntryManager._entry_or_404(entry_id)
        if entry.status != 'validated':
            raise ValueError(
                f'Entry must be validated before posting (current status: {entry.status}). '
                'Run validate_entry() first.'
            )
        AdvancedJournalEntryManager._transition(entry, 'posted', user_id=posted_by)
        AdvancedJournalEntryManager._log_audit(
            entry_id, 'post', entry.to_dict(), entry.to_dict(),
            f'Posting: {post_notes or ""}', posted_by
        )
        try:
            if commit:
                db.session.flush()
            else:
                db.session.flush()
        except Exception:
            db.session.rollback()
            raise
        return entry

    # ── Reverse (posted only) ────────────────────────────────────────────

    @staticmethod
    def reverse_entry_advanced(entry_id, reversed_by, reason, create_reversal_entry=True, commit=True):
        """عكس قيد محاسبي — creates a reversing entry."""
        entry = AdvancedJournalEntryManager._entry_or_404(entry_id)
        if entry.status == 'reversed':
            raise ValueError("القيد معكوس مسبقاً")
        if entry.status != 'posted':
            raise ValueError(f"لا يمكن عكس قيد بحالة: {entry.status}")

        old_values = entry.to_dict()
        reversal_entry = None
        if create_reversal_entry:
            reversal_lines = []
            for line in entry.lines:
                reversal_lines.append({
                    'account_code': line.account.code,
                    'debit': line.credit,
                    'credit': line.debit,
                    'description': f"عكس: {line.description or ''}"
                })
            reversal_entry = AdvancedJournalEntryManager.create_entry_with_validation(
                description=f"عكس القيد {entry.entry_number}",
                lines=reversal_lines,
                entry_date=datetime.now().date(),
                notes=f"سبب العكس: {reason}",
                created_by=reversed_by,
                entry_type='reversing'
            )
            # Auto-validate and post the reversal atomically (no intermediate commits)
            AdvancedJournalEntryManager.validate_entry(
                reversal_entry.id, validated_by=reversed_by, commit=False)
            AdvancedJournalEntryManager.post_entry(
                reversal_entry.id, posted_by=reversed_by, commit=False)

            AdvancedJournalEntryManager._transition(entry, 'reversed', user_id=reversed_by)
            entry.reversed_entry_id = reversal_entry.id
            reversal_entry.reversed_entry_id = entry.id

        AdvancedJournalEntryManager._log_audit(
            entry_id, 'reverse', old_values, entry.to_dict(),
            f"عكس القيد - السبب: {reason}", reversed_by
        )
        if reversal_entry:
            AdvancedJournalEntryManager._log_audit(
                reversal_entry.id, 'create', None, reversal_entry.to_dict(),
                f"إنشاء قيد عكسي للقيد {entry.entry_number}", reversed_by
            )
        try:
            if commit:
                db.session.flush()
            else:
                db.session.flush()
        except Exception:
            db.session.rollback()
            raise
        return reversal_entry

    # ── Soft-delete (cancel) — NEVER physical delete ─────────────────────

    @staticmethod
    def delete_entry(entry_id, deleted_by, reason, commit=True):
        """Soft-delete: sets status='cancelled'. Preserves audit trail.

        Financial documents are immutable. Physical deletes are forbidden
        for any entry that has been posted or reversed.
        """
        entry = AdvancedJournalEntryManager._entry_or_404(entry_id)
        if entry.status in ('posted', 'reversed'):
            raise ValueError(
                f'Cannot delete entry in status "{entry.status}". '
                'Use reverse_entry_advanced() for posted entries.'
            )
        if entry.reversed_entry_id:
            raise ValueError("لا يمكن حذف قيد له قيود عكسية مرتبطة")

        old_values = entry.to_dict()
        AdvancedJournalEntryManager._transition(entry, 'cancelled', user_id=deleted_by, reason=reason)
        AdvancedJournalEntryManager._log_audit(
            entry_id, 'cancel', old_values, entry.to_dict(),
            f"إلغاء القيد - السبب: {reason}", deleted_by
        )
        try:
            if commit:
                db.session.flush()
            else:
                db.session.flush()
        except Exception:
            db.session.rollback()
            raise
        return True

    # ── Approve (legacy alias → validate) ────────────────────────────────

    @staticmethod
    def approve_entry(entry_id, approved_by, approval_notes=None):
        """الموافقة على قيد — routes through validate_entry for state-machine compliance."""
        return AdvancedJournalEntryManager.validate_entry(
            entry_id, validated_by=approved_by,
        )
    
    @staticmethod
    def get_entry_history(entry_id, tenant_id=None):
        """الحصول على تاريخ القيد"""
        from utils.gl_tenant import gl_entry_query, active_tenant_id
        tid = tenant_id if tenant_id is not None else active_tenant_id()
        entry = gl_entry_query(tenant_id=tid).filter_by(id=entry_id).first()
        if not entry:
            return []
        return JournalEntryAudit.query.filter_by(
            journal_entry_id=entry_id,
            tenant_id=entry.tenant_id
        ).order_by(JournalEntryAudit.performed_at.desc()).all()
    
    @staticmethod
    def _log_audit(entry_id, action, old_values, new_values, reason, user_id):
        """تسجيل تدقيق"""
        if user_id is None:
            return
        entry = GLJournalEntry.query.get(entry_id)
        tenant_id = entry.tenant_id if entry else None
        audit = JournalEntryAudit(
            journal_entry_id=entry_id,
            tenant_id=tenant_id,
            action=action,
            old_values=str(old_values) if old_values else None,
            new_values=str(new_values) if new_values else None,
            reason=reason,
            performed_by=user_id,
            performed_at=datetime.now(timezone.utc)
        )
        db.session.add(audit)

# إضافة دالة مساعدة لـ GLJournalEntry
def add_helper_methods():
    """إضافة دوال مساعدة لـ GLJournalEntry"""
    
    def to_dict(self):
        """تحويل القيد إلى قاموس"""
        return {
            'id': self.id,
            'entry_number': self.entry_number,
            'entry_date': self.entry_date.isoformat() if self.entry_date else None,
            'description': self.description,
            'entry_type': self.entry_type,
            'status': getattr(self, 'status', 'posted'),
            'total_debit': float(self.total_debit),
            'total_credit': float(self.total_credit),
            'is_posted': self.is_posted,
            'is_reversed': self.is_reversed,
            'validation_errors': getattr(self, 'validation_errors', None),
            'validated_at': self.validated_at.isoformat() if getattr(self, 'validated_at', None) else None,
            'notes': self.notes,
            'lines': [
                {
                    'account_code': line.account.code,
                    'account_name': line.account.full_name,
                    'debit': float(line.debit),
                    'credit': float(line.credit),
                    'description': line.description
                }
                for line in self.lines
            ]
        }
    
    def get_balance_status(self):
        """الحصول على حالة التوازن"""
        difference = abs(self.total_debit - self.total_credit)
        if difference < 0.01:
            return 'balanced'
        elif difference < 10:
            return 'minor_imbalance'
        else:
            return 'major_imbalance'
    
    def can_be_modified(self):
        """فحص إمكانية التعديل — state-machine aware."""
        return getattr(self, 'status', 'posted') in ('draft', 'error')
    
    def can_be_reversed(self):
        """فحص إمكانية العكس"""
        return getattr(self, 'status', 'posted') == 'posted' and not self.is_reversed
    
    def can_be_deleted(self):
        """فحص إمكانية الحذف — soft-delete only for draft/error entries."""
        return getattr(self, 'status', 'posted') in ('draft', 'error') and not self.reversed_entry_id
    
    # إضافة الدوال للكلاس
    GLJournalEntry.to_dict = to_dict
    GLJournalEntry.get_balance_status = get_balance_status
    GLJournalEntry.can_be_modified = can_be_modified
    GLJournalEntry.can_be_reversed = can_be_reversed
    GLJournalEntry.can_be_deleted = can_be_deleted

# استدعاء الدوال المساعدة
add_helper_methods()
