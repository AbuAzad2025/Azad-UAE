from datetime import datetime, timezone
from extensions import db
from decimal import Decimal
from models.cheque import Cheque
from models.gl import GLAccount, GLJournalEntry, GLJournalLine
from utils.gl_reference_types import GLRef
from utils.gl_tenant import scope_journal_entries, get_gl_account_by_code, active_tenant_id

class ChequeAccountingIntegration:
    """تكامل الشيكات مع النظام المحاسبي"""

    @staticmethod
    def _scoped_entries(cheque, reference_type=None, **filters):
        from utils.gl_reference_types import ref_variants
        q = scope_journal_entries(GLJournalEntry.query, tenant_id=cheque.tenant_id)
        if reference_type is not None:
            q = q.filter(GLJournalEntry.reference_type.in_(ref_variants(reference_type)))
        for key, val in filters.items():
            q = q.filter_by(**{key: val})
        return q
    # حسابات الشيكات الافتراضية
    CHEQUE_ACCOUNTS = {
        'incoming_under_collection': '1150',  # شيكات تحت التحصيل
        'outgoing_deferred': '2120',          # شيكات مؤجلة الدفع
        'bank_account': '1120',               # حساب البنك
        'cash_account': '1110',               # صندوق
        'accounts_receivable': '1130',        # الذمم المدينة
        'accounts_payable': '2110',           # الذمم الدائنة
        'exchange_gain': '4400',              # أرباح فرق العملة
        'exchange_loss': '6900',              # خسائر فرق العملة
    }
    
    @staticmethod
    def receive_cheque(cheque_id, received_by=None):
        """تسجيل استلام شيك وارد - يفوض إلى Cheque.receive_cheque()"""
        cheque = Cheque.query.get_or_404(cheque_id)
        if cheque.cheque_type != 'incoming':
            raise ValueError("هذا الشيك ليس شيك وارد")
        if cheque.status != 'pending':
            raise ValueError("الشيك ليس في حالة معلق")
        try:
            entry = cheque.receive_cheque()
            db.session.commit()
            return entry
        except Exception as e:
            db.session.rollback()
            raise Exception(f"فشل في تسجيل استلام الشيك: {str(e)}")
    
    @staticmethod
    def issue_cheque(cheque_id, issued_by=None):
        """تسجيل إصدار شيك صادر - يفوض إلى Cheque.issue_cheque()"""
        cheque = Cheque.query.get_or_404(cheque_id)
        if cheque.cheque_type != 'outgoing':
            raise ValueError("هذا الشيك ليس شيك صادر")
        if cheque.status != 'pending':
            raise ValueError("الشيك ليس في حالة معلق")
        try:
            cheque.issue_cheque()
            db.session.commit()
            entry = ChequeAccountingIntegration._scoped_entries(
                cheque, reference_type=GLRef.CHEQUE_ISSUE, reference_id=cheque.id
            ).order_by(GLJournalEntry.id.desc()).first()
            return entry
        except Exception as e:
            db.session.rollback()
            raise Exception(f"فشل في تسجيل إصدار الشيك: {str(e)}")
    
    @staticmethod
    def clear_cheque(cheque_id, cleared_by=None, bank_charges=0, exchange_gain_loss=0):
        """تسجيل صرف شيك - يفوض إلى Cheque.clear_cheque()"""
        cheque = Cheque.query.get_or_404(cheque_id)
        if cheque.status not in ['pending', 'under_collection', 'deposited']:
            raise ValueError("الشيك ليس في حالة يمكن صرفه")
        try:
            # تمرير فرق العملة اليدوي إن وُجد (bank_charges غير مدعوم في Cheque حالياً)
            exchange_rate = None
            if exchange_gain_loss and cheque.currency != 'AED' and cheque.amount:
                from decimal import Decimal as D
                amt_aed = cheque.amount_aed or D('0')
                target_aed = amt_aed + D(str(exchange_gain_loss))
                exchange_rate = target_aed / cheque.amount
            cheque.clear_cheque(clearance_date=None, clearance_exchange_rate=exchange_rate)
            db.session.commit()
            # إرجاع القيد الأخير المرتبط (Cheque لا يُرجع القيد)
            entry = ChequeAccountingIntegration._scoped_entries(
                cheque, reference_type=GLRef.CHEQUE_CLEAR, reference_id=cheque.id
            ).order_by(GLJournalEntry.id.desc()).first()
            if entry is None:
                # القيد قد لا يُنشأ إذا فشل _create_clearing_journal_entry
                class _DummyEntry:
                    entry_number = '—'
                return _DummyEntry()
            return entry
        except Exception as e:
            db.session.rollback()
            raise Exception(f"فشل في تسجيل صرف الشيك: {str(e)}")
    
    @staticmethod
    def bounce_cheque(cheque_id, bounced_by=None, bounce_reason=None):
        """تسجيل ارتداد شيك - يفوض إلى Cheque.bounce_cheque()"""
        cheque = Cheque.query.get_or_404(cheque_id)
        if cheque.status not in ['pending', 'under_collection', 'deposited']:
            raise ValueError("الشيك ليس في حالة يمكن ارتداده")
        try:
            cheque.bounce_cheque(reason=bounce_reason or 'غير محدد')
            db.session.commit()
            # إرجاع القيد المرتبط
            entry = ChequeAccountingIntegration._scoped_entries(
                cheque, reference_type=GLRef.CHEQUE_BOUNCE, reference_id=cheque.id
            ).order_by(GLJournalEntry.id.desc()).first()
            return entry
        except Exception as e:
            db.session.rollback()
            raise Exception(f"فشل في تسجيل ارتداد الشيك: {str(e)}")
    
    @staticmethod
    def get_cheque_accounting_summary(cheque_id):
        """الحصول على ملخص محاسبي للشيك"""
        cheque = Cheque.query.get_or_404(cheque_id)
        
        summary = {
            'cheque_info': {
                'id': cheque.id,
                'number': cheque.cheque_bank_number,
                'type': cheque.type_ar,
                'amount': float(cheque.amount_aed or 0),
                'status': cheque.status_ar,
                'date': (cheque.issue_date or cheque.due_date).isoformat() if (cheque.issue_date or cheque.due_date) else None
            },
            'journal_entries': [],
            'account_impact': []
        }
        
        # جمع القيود المحاسبية المرتبطة (بالاستعلام عن reference_type/reference_id)
        ref_types = [
            (GLRef.CHEQUE_RECEIVE, 'receive'),
            (GLRef.CHEQUE_ISSUE, 'issue'),
            (GLRef.CHEQUE_CLEAR, 'clear'),
            (GLRef.CHEQUE_BOUNCE, 'bounce'),
        ]
        for ref_type, entry_type in ref_types:
            entries = ChequeAccountingIntegration._scoped_entries(
                cheque, reference_type=ref_type, reference_id=cheque.id
            ).order_by(GLJournalEntry.id.asc()).all()
            for entry in entries:
                summary['journal_entries'].append({
                    'type': entry_type,
                    'entry_number': entry.entry_number,
                    'date': entry.entry_date.isoformat() if hasattr(entry.entry_date, 'isoformat') else str(entry.entry_date),
                    'description': entry.description or ''
                })
        
        # حساب التأثير على الحسابات
        accounts_affected = set()
        tid = cheque.tenant_id or active_tenant_id()
        for entry_info in summary['journal_entries']:
            entry = scope_journal_entries(
                GLJournalEntry.query.filter_by(entry_number=entry_info['entry_number']),
                tenant_id=tid,
            ).first()
            if entry:
                for line in entry.lines:
                    accounts_affected.add(line.account.code)
        
        for account_code in accounts_affected:
            account = get_gl_account_by_code(account_code, tenant_id=tid)
            if account:
                summary['account_impact'].append({
                    'code': account.code,
                    'name': account.full_name,
                    'balance': float(account.get_balance())
                })
        
        return summary
