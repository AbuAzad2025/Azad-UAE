"""
نموذج مطابقة البنك - Bank Reconciliation Model
"""

from datetime import datetime, timezone
from extensions import db
from decimal import Decimal


class BankReconciliation(db.Model):
    """
    سجل مطابقة البنك الشهرية
    """
    __tablename__ = 'bank_reconciliations'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'reconciliation_number', name='uq_bank_reconciliations_tenant_number'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    reconciliation_number = db.Column(db.String(50), nullable=False, index=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'), nullable=False, index=True)

    # الفترة
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False, index=True)
    
    # الأرصدة
    opening_balance_per_books = db.Column(db.Numeric(18, 3), default=0)  # رصيد الدفاتر الافتتاحي
    closing_balance_per_books = db.Column(db.Numeric(18, 3), default=0)  # رصيد الدفاتر الختامي
    closing_balance_per_bank = db.Column(db.Numeric(18, 3), default=0)   # رصيد البنك الختامي
    
    # الفروقات
    outstanding_deposits = db.Column(db.Numeric(18, 3), default=0)  # إيداعات معلقة
    outstanding_withdrawals = db.Column(db.Numeric(18, 3), default=0)  # سحوبات معلقة
    bank_charges = db.Column(db.Numeric(18, 3), default=0)  # مصاريف بنكية
    bank_interest = db.Column(db.Numeric(18, 3), default=0)  # فوائد بنكية
    errors_in_books = db.Column(db.Numeric(18, 3), default=0)  # أخطاء في الدفاتر
    errors_in_bank = db.Column(db.Numeric(18, 3), default=0)  # أخطاء في البنك
    
    # الحالة
    status = db.Column(db.String(20), default='draft', index=True)  # draft, completed, approved
    is_balanced = db.Column(db.Boolean, default=False)
    difference = db.Column(db.Numeric(18, 3), default=0)
    
    # الملاحظات
    notes = db.Column(db.Text)
    
    # Meta
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    approved_at = db.Column(db.DateTime)
    
    # Relationships
    tenant = db.relationship('Tenant', backref='bank_reconciliations', foreign_keys=[tenant_id])
    bank_account = db.relationship('GLAccount', foreign_keys=[bank_account_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    items = db.relationship('BankReconciliationItem', back_populates='reconciliation',
                           cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<BankReconciliation {self.reconciliation_number}>'
    
    @property
    def status_ar(self):
        """الحالة بالعربي"""
        statuses = {
            'draft': 'مسودة',
            'completed': 'مكتملة',
            'approved': 'معتمدة'
        }
        return statuses.get(self.status, self.status)
    
    def calculate_reconciliation(self):
        """حساب المطابقة"""
        # الرصيد المعدل حسب الدفاتر
        adjusted_books = (
            self.closing_balance_per_books 
            - self.bank_charges 
            + self.bank_interest 
            - self.errors_in_books
        )
        
        # الرصيد المعدل حسب البنك
        adjusted_bank = (
            self.closing_balance_per_bank 
            + self.outstanding_deposits 
            - self.outstanding_withdrawals 
            - self.errors_in_bank
        )
        
        # الفرق
        self.difference = adjusted_books - adjusted_bank
        self.is_balanced = abs(self.difference) < Decimal('0.01')
        
        return {
            'adjusted_books': float(adjusted_books),
            'adjusted_bank': float(adjusted_bank),
            'difference': float(self.difference),
            'is_balanced': self.is_balanced
        }
    
    def approve(self, user_id):
        """اعتماد المطابقة"""
        if not self.is_balanced:
            raise ValueError('لا يمكن اعتماد مطابقة غير متوازنة')
        
        self.status = 'approved'
        self.approved_by = user_id
        self.approved_at = datetime.now(timezone.utc)


class BankReconciliationItem(db.Model):
    """
    سطور مطابقة البنك - عمليات فردية
    """
    __tablename__ = 'bank_reconciliation_items'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    reconciliation_id = db.Column(db.Integer, db.ForeignKey('bank_reconciliations.id'), nullable=False, index=True)

    # نوع العنصر
    item_type = db.Column(db.String(30), nullable=False)  # outstanding_deposit, outstanding_withdrawal, bank_charge, etc.

    # التفاصيل
    transaction_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(18, 3), nullable=False)

    # الربط
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'), index=True)
    cheque_id = db.Column(db.Integer, db.ForeignKey('cheques.id'), index=True)

    # الحالة
    is_cleared = db.Column(db.Boolean, default=False)
    cleared_date = db.Column(db.Date)

    notes = db.Column(db.Text)

    # Relationships
    tenant = db.relationship('Tenant', backref='bank_reconciliation_items', foreign_keys=[tenant_id])
    reconciliation = db.relationship('BankReconciliation', back_populates='items')
    journal_entry = db.relationship('GLJournalEntry')
    cheque = db.relationship('Cheque')
    
    def __repr__(self):
        return f'<BankReconciliationItem {self.description}>'

    @property
    def item_type_ar(self):
        """نوع العنصر بالعربي"""
        types = {
            'outstanding_deposit': 'إيداع معلق',
            'outstanding_withdrawal': 'سحب معلق',
            'bank_charge': 'مصروف بنكي',
            'bank_interest': 'فائدة بنكية',
            'error_in_books': 'خطأ في الدفاتر',
            'error_in_bank': 'خطأ في البنك',
            'cleared': 'مطابق'
        }
        return types.get(self.item_type, self.item_type)


class BankStatementLine(db.Model):
    """
    سطر كشف حساب بنك مستورد (CSV/OFX).
    Used for auto-matching against GL lines and cheques.
    """
    __tablename__ = 'bank_statement_lines'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)

    # Import metadata
    bank_account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'), nullable=False, index=True)
    statement_date = db.Column(db.Date, nullable=False, index=True)

    # Transaction data
    transaction_date = db.Column(db.Date, nullable=False, index=True)
    reference = db.Column(db.String(120), index=True)
    description = db.Column(db.String(255))
    amount = db.Column(db.Numeric(18, 3), nullable=False)
    currency = db.Column(db.String(3), default='AED')

    # Matching status
    matched = db.Column(db.Boolean, default=False, index=True)
    match_type = db.Column(db.String(30))  # exact, amount_date, fuzzy
    matched_journal_entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'), index=True)
    matched_cheque_id = db.Column(db.Integer, db.ForeignKey('cheques.id'), index=True)
    reconciliation_item_id = db.Column(db.Integer, db.ForeignKey('bank_reconciliation_items.id'), index=True)

    # Raw import data
    raw_data = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    tenant = db.relationship('Tenant', backref='bank_statement_lines', foreign_keys=[tenant_id])
    bank_account = db.relationship('GLAccount', foreign_keys=[bank_account_id])
    matched_journal_entry = db.relationship('GLJournalEntry')
    matched_cheque = db.relationship('Cheque')
    reconciliation_item = db.relationship('BankReconciliationItem')

    def __repr__(self):
        return f'<BankStatementLine {self.reference} {self.amount}>'

