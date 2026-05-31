from datetime import datetime, timezone
from extensions import db
from decimal import Decimal
from sqlalchemy import event
from models.gl import GLJournalEntry, GLJournalLine

class JournalEntryAudit(db.Model):
    """سجل تدقيق القيود المحاسبية"""
    __tablename__ = 'journal_entry_audits'
    
    id = db.Column(db.Integer, primary_key=True)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # create, update, reverse, delete, approve
    old_values = db.Column(db.Text)  # JSON للقيم القديمة
    new_values = db.Column(db.Text)  # JSON للقيم الجديدة
    reason = db.Column(db.Text)
    performed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    performed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    
    journal_entry = db.relationship('GLJournalEntry')
    user = db.relationship('User')
    
    def __repr__(self):
        return f'<JournalEntryAudit {self.action} - {self.journal_entry_id}>'

class AdvancedJournalEntryManager:
    """مدير القيود المحاسبية المتقدم"""

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
    def create_entry_with_validation(description, lines, entry_date=None, notes=None, created_by=None, **kwargs):
        """إنشاء قيد مع التحقق المتقدم"""
        from services.gl_service import GLService
        
        # التحقق من التوازن
        total_debit = sum(line.get('debit', 0) for line in lines)
        total_credit = sum(line.get('credit', 0) for line in lines)
        
        if abs(total_debit - total_credit) > 0.01:
            raise ValueError(f"القيد غير متوازن: المدين {total_debit} ≠ الدائن {total_credit}")
        
        # التحقق من الحسابات الرئيسية
        for line in lines:
            account_code = line.get('account_code')
            if account_code:
                from models.gl import GLAccount
                from utils.gl_tenant import get_gl_account_by_code, active_tenant_id
                account = get_gl_account_by_code(account_code, tenant_id=kwargs.get('tenant_id') or active_tenant_id())
                if account and account.is_header:
                    raise ValueError(f"لا يمكن القيد على الحساب الرئيسي: {account.full_name}")
        
        # إنشاء القيد
        entry = GLService.create_manual_entry(
            description=description,
            lines=lines,
            entry_date=entry_date,
            notes=notes,
            created_by=created_by,
            branch_id=kwargs.get('branch_id'), # Pass branch_id
            **kwargs
        )
        
        # تسجيل التدقيق
        AdvancedJournalEntryManager._log_audit(
            entry.id, 'create', None, entry.to_dict(), 
            f"إنشاء قيد جديد: {description}", created_by
        )
        
        return entry
    
    @staticmethod
    def update_entry(entry_id, updates, updated_by, reason=None):
        """تحديث قيد محاسبي"""
        entry = AdvancedJournalEntryManager._entry_or_404(entry_id)
        
        if entry.is_posted:
            raise ValueError("لا يمكن تعديل قيد مرحل")
        
        if entry.is_reversed:
            raise ValueError("لا يمكن تعديل قيد معكوس")
        
        # حفظ القيم القديمة
        old_values = entry.to_dict()
        
        # تطبيق التحديثات
        for field, value in updates.items():
            if hasattr(entry, field):
                setattr(entry, field, value)
        
        # التحقق من التوازن إذا تم تحديث السطور
        if 'lines' in updates:
            total_debit = sum(line.get('debit', 0) for line in updates['lines'])
            total_credit = sum(line.get('credit', 0) for line in updates['lines'])
            
            if abs(total_debit - total_credit) > 0.01:
                raise ValueError(f"القيد غير متوازن بعد التحديث: المدين {total_debit} ≠ الدائن {total_credit}")
        
        entry.updated_at = datetime.now(timezone.utc)
        
        # تسجيل التدقيق
        AdvancedJournalEntryManager._log_audit(
            entry_id, 'update', old_values, entry.to_dict(),
            reason or "تحديث القيد", updated_by
        )
        
        db.session.commit()
        return entry
    
    @staticmethod
    def reverse_entry_advanced(entry_id, reversed_by, reason, create_reversal_entry=True):
        """عكس قيد محاسبي متقدم"""
        entry = AdvancedJournalEntryManager._entry_or_404(entry_id)
        
        if entry.is_reversed:
            raise ValueError("القيد معكوس مسبقاً")
        
        if not entry.is_posted:
            raise ValueError("لا يمكن عكس قيد غير مرحل")
        
        # حفظ القيم القديمة
        old_values = entry.to_dict()
        
        # إنشاء قيد عكسي إذا طُلب
        reversal_entry = None
        if create_reversal_entry:
            reversal_lines = []
            for line in entry.lines:
                reversal_lines.append({
                    'account_code': line.account.code,
                    'debit': line.credit,  # عكس الاتجاه
                    'credit': line.debit,  # عكس الاتجاه
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
            
            # ربط القيود
            entry.is_reversed = True
            entry.reversed_entry_id = reversal_entry.id
            reversal_entry.reversed_entry_id = entry.id
        
        # تسجيل التدقيق
        AdvancedJournalEntryManager._log_audit(
            entry_id, 'reverse', old_values, entry.to_dict(),
            f"عكس القيد - السبب: {reason}", reversed_by
        )
        
        if reversal_entry:
            AdvancedJournalEntryManager._log_audit(
                reversal_entry.id, 'create', None, reversal_entry.to_dict(),
                f"إنشاء قيد عكسي للقيد {entry.entry_number}", reversed_by
            )
        
        db.session.commit()
        return reversal_entry
    
    @staticmethod
    def delete_entry(entry_id, deleted_by, reason):
        """حذف قيد محاسبي"""
        entry = AdvancedJournalEntryManager._entry_or_404(entry_id)
        
        if entry.is_posted:
            raise ValueError("لا يمكن حذف قيد مرحل - استخدم العكس بدلاً من ذلك")
        
        if entry.is_reversed:
            raise ValueError("لا يمكن حذف قيد معكوس")
        
        # التحقق من وجود قيود مرتبطة
        if entry.reversed_entry_id:
            raise ValueError("لا يمكن حذف قيد له قيود عكسية مرتبطة")
        
        # حفظ القيم القديمة
        old_values = entry.to_dict()
        
        # حذف السطور أولاً
        GLJournalLine.query.filter_by(entry_id=entry_id).delete()
        
        # حذف القيد
        db.session.delete(entry)
        
        # تسجيل التدقيق
        AdvancedJournalEntryManager._log_audit(
            entry_id, 'delete', old_values, None,
            f"حذف القيد - السبب: {reason}", deleted_by
        )
        
        db.session.commit()
        return True
    
    @staticmethod
    def approve_entry(entry_id, approved_by, approval_notes=None):
        """الموافقة على قيد محاسبي"""
        entry = AdvancedJournalEntryManager._entry_or_404(entry_id)
        
        if entry.is_posted:
            raise ValueError("القيد مرحل مسبقاً")
        
        # التحقق من التوازن مرة أخرى
        total_debit = sum(line.debit for line in entry.lines)
        total_credit = sum(line.credit for line in entry.lines)
        
        if abs(total_debit - total_credit) > 0.01:
            raise ValueError(f"القيد غير متوازن: المدين {total_debit} ≠ الدائن {total_credit}")
        
        # الموافقة
        entry.is_posted = True
        entry.updated_at = datetime.now(timezone.utc)
        
        # تسجيل التدقيق
        AdvancedJournalEntryManager._log_audit(
            entry_id, 'approve', entry.to_dict(), entry.to_dict(),
            f"الموافقة على القيد - ملاحظات: {approval_notes or 'لا توجد'}",
            approved_by
        )
        
        db.session.commit()
        return entry
    
    @staticmethod
    def get_entry_history(entry_id):
        """الحصول على تاريخ القيد"""
        return JournalEntryAudit.query.filter_by(journal_entry_id=entry_id)\
            .order_by(JournalEntryAudit.performed_at.desc()).all()
    
    @staticmethod
    def _log_audit(entry_id, action, old_values, new_values, reason, user_id):
        """تسجيل تدقيق"""
        audit = JournalEntryAudit(
            journal_entry_id=entry_id,
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
            'total_debit': float(self.total_debit),
            'total_credit': float(self.total_credit),
            'is_posted': self.is_posted,
            'is_reversed': self.is_reversed,
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
        """فحص إمكانية التعديل"""
        return not self.is_posted and not self.is_reversed
    
    def can_be_reversed(self):
        """فحص إمكانية العكس"""
        return self.is_posted and not self.is_reversed
    
    def can_be_deleted(self):
        """فحص إمكانية الحذف"""
        return not self.is_posted and not self.is_reversed and not self.reversed_entry_id
    
    # إضافة الدوال للكلاس
    GLJournalEntry.to_dict = to_dict
    GLJournalEntry.get_balance_status = get_balance_status
    GLJournalEntry.can_be_modified = can_be_modified
    GLJournalEntry.can_be_reversed = can_be_reversed
    GLJournalEntry.can_be_deleted = can_be_deleted

# استدعاء الدوال المساعدة
add_helper_methods()
