"""
خدمة مطابقة البنك - Bank Reconciliation Service
"""

from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_
from extensions import db
from models import (
    BankReconciliation, BankReconciliationItem, 
    GLAccount, GLJournalEntry, GLJournalLine,
    Cheque
)
from utils.helpers import generate_number
from utils.gl_reference_types import GLRef


class BankReconciliationService:
    
    @staticmethod
    def create_reconciliation(bank_account_id, period_start, period_end, 
                            closing_balance_per_bank, created_by=None):
        """
        إنشاء مطابقة بنك جديدة
        """
        from flask_login import current_user
        
        bank_account = GLAccount.query.get_or_404(bank_account_id)
        
        # حساب رصيد الدفاتر
        from services.gl_service import GLService
        statement = GLService.get_account_statement(
            bank_account_id, 
            date_from=None, 
            date_to=period_end
        )
        
        closing_balance_per_books = Decimal(str(statement['closing_balance']))
        opening_balance = Decimal(str(statement['opening_balance']))
        
        # إنشاء المطابقة
        reconciliation_number = generate_number('BR', BankReconciliation, 'reconciliation_number')
        
        reconciliation = BankReconciliation(
            reconciliation_number=reconciliation_number,
            bank_account_id=bank_account_id,
            period_start=period_start,
            period_end=period_end,
            opening_balance_per_books=opening_balance,
            closing_balance_per_books=closing_balance_per_books,
            closing_balance_per_bank=closing_balance_per_bank,
            created_by=created_by or (current_user.id if current_user.is_authenticated else None)
        )
        
        db.session.add(reconciliation)
        db.session.flush()
        
        # جلب العمليات المعلقة تلقائياً
        BankReconciliationService._auto_populate_items(reconciliation)
        
        # حساب المطابقة
        reconciliation.calculate_reconciliation()
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return reconciliation
    
    @staticmethod
    def _auto_populate_items(reconciliation):
        """
        ملء العناصر تلقائياً (شيكات معلقة، عمليات غير مطابقة)
        """
        # 1. الشيكات الواردة المعلقة (pending, deposited)
        outstanding_cheques_in = Cheque.query.filter(
            Cheque.cheque_type == 'incoming',
            Cheque.status.in_(['pending', 'deposited']),
            Cheque.is_active == True,
            Cheque.due_date <= reconciliation.period_end
        ).all()
        
        for cheque in outstanding_cheques_in:
            item = BankReconciliationItem(
                reconciliation_id=reconciliation.id,
                item_type='outstanding_deposit',
                transaction_date=cheque.issue_date,
                description=f'شيك وارد رقم {cheque.cheque_bank_number} - {cheque.drawer_name or ""}',
                amount=cheque.amount_aed,
                cheque_id=cheque.id
            )
            db.session.add(item)
            reconciliation.outstanding_deposits += cheque.amount_aed
        
        # 2. الشيكات الصادرة المعلقة
        outstanding_cheques_out = Cheque.query.filter(
            Cheque.cheque_type == 'outgoing',
            Cheque.status.in_(['pending', 'deposited']),
            Cheque.is_active == True,
            Cheque.due_date <= reconciliation.period_end
        ).all()
        
        for cheque in outstanding_cheques_out:
            item = BankReconciliationItem(
                reconciliation_id=reconciliation.id,
                item_type='outstanding_withdrawal',
                transaction_date=cheque.issue_date,
                description=f'شيك صادر رقم {cheque.cheque_bank_number} - {cheque.payee_name or ""}',
                amount=cheque.amount_aed,
                cheque_id=cheque.id
            )
            db.session.add(item)
            reconciliation.outstanding_withdrawals += cheque.amount_aed
    
    @staticmethod
    def add_bank_charge(reconciliation_id, amount, description, transaction_date=None):
        """
        إضافة مصروف بنكي
        """
        reconciliation = BankReconciliation.query.get_or_404(reconciliation_id)
        
        if reconciliation.status != 'draft':
            raise ValueError('لا يمكن تعديل مطابقة معتمدة')
        
        item = BankReconciliationItem(
            reconciliation_id=reconciliation_id,
            item_type='bank_charge',
            transaction_date=transaction_date or reconciliation.period_end,
            description=description,
            amount=abs(Decimal(str(amount)))
        )
        db.session.add(item)
        
        reconciliation.bank_charges += abs(Decimal(str(amount)))
        reconciliation.calculate_reconciliation()
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return item
    
    @staticmethod
    def add_bank_interest(reconciliation_id, amount, description, transaction_date=None):
        """
        إضافة فائدة بنكية
        """
        reconciliation = BankReconciliation.query.get_or_404(reconciliation_id)
        
        if reconciliation.status != 'draft':
            raise ValueError('لا يمكن تعديل مطابقة معتمدة')
        
        item = BankReconciliationItem(
            reconciliation_id=reconciliation_id,
            item_type='bank_interest',
            transaction_date=transaction_date or reconciliation.period_end,
            description=description,
            amount=abs(Decimal(str(amount)))
        )
        db.session.add(item)
        
        reconciliation.bank_interest += abs(Decimal(str(amount)))
        reconciliation.calculate_reconciliation()
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return item
    
    @staticmethod
    def complete_reconciliation(reconciliation_id):
        """
        إكمال المطابقة وإنشاء القيود التسوية
        """
        reconciliation = BankReconciliation.query.get_or_404(reconciliation_id)
        
        if reconciliation.status != 'draft':
            raise ValueError('المطابقة معتمدة مسبقاً')
        
        # التحقق من التوازن
        result = reconciliation.calculate_reconciliation()
        
        if not result['is_balanced']:
            raise ValueError(f'المطابقة غير متوازنة - الفرق: {result["difference"]}')
        
        # إنشاء قيود التسوية
        from services.gl_service import GLService
        
        lines = []
        
        # مصاريف بنكية
        if reconciliation.bank_charges > 0:
            lines.append({
                'account': '6950',  # مصاريف بنكية
                'concept_code': 'BANK_FEES',
                'debit': reconciliation.bank_charges,
                'credit': 0,
                'description': 'مصاريف بنكية'
            })
            lines.append({
                'account': str(reconciliation.bank_account.code),  # البنك
                'concept_code': 'BANK',
                'debit': 0,
                'credit': reconciliation.bank_charges,
                'description': 'مصاريف بنكية'
            })
        
        # فوائد بنكية
        if reconciliation.bank_interest > 0:
            lines.append({
                'account': str(reconciliation.bank_account.code),  # البنك
                'concept_code': 'BANK',
                'debit': reconciliation.bank_interest,
                'credit': 0,
                'description': 'فوائد بنكية'
            })
            lines.append({
                'account': '4500',  # إيرادات أخرى
                'concept_code': 'BANK_INTEREST_INCOME',
                'debit': 0,
                'credit': reconciliation.bank_interest,
                'description': 'فوائد بنكية'
            })
        
        if lines:
            from services.gl_posting import post_or_fail
            post_or_fail(
                lines=lines,
                description=f'قيد تسوية بنك - {reconciliation.reconciliation_number}',
                reference_type=GLRef.BANK_RECONCILIATION,
                reference_id=reconciliation.id,
                branch_id=getattr(reconciliation, 'branch_id', None),
                tenant_id=getattr(reconciliation.bank_account, 'tenant_id', None),
            )
        
        # تحديث الحالة
        reconciliation.status = 'completed'
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        return reconciliation
    
    @staticmethod
    def get_reconciliation_summary(bank_account_id, period_start, period_end):
        """
        ملخص المطابقة قبل الإنشاء
        """
        from services.gl_service import GLService
        
        statement = GLService.get_account_statement(
            bank_account_id,
            date_from=period_start,
            date_to=period_end
        )
        
        # الشيكات المعلقة
        outstanding_cheques_in = Cheque.query.filter(
            Cheque.cheque_type == 'incoming',
            Cheque.status.in_(['pending', 'deposited']),
            Cheque.is_active == True,
            Cheque.due_date.between(period_start, period_end)
        ).all()
        
        outstanding_cheques_out = Cheque.query.filter(
            Cheque.cheque_type == 'outgoing',
            Cheque.status.in_(['pending', 'deposited']),
            Cheque.is_active == True,
            Cheque.due_date.between(period_start, period_end)
        ).all()
        
        outstanding_deposits = sum(c.amount_aed for c in outstanding_cheques_in)
        outstanding_withdrawals = sum(c.amount_aed for c in outstanding_cheques_out)
        
        return {
            'closing_balance_per_books': statement['closing_balance'],
            'outstanding_deposits_count': len(outstanding_cheques_in),
            'outstanding_deposits_amount': float(outstanding_deposits),
            'outstanding_withdrawals_count': len(outstanding_cheques_out),
            'outstanding_withdrawals_amount': float(outstanding_withdrawals),
            'outstanding_cheques_in': outstanding_cheques_in,
            'outstanding_cheques_out': outstanding_cheques_out
        }

