from datetime import datetime, timezone
from extensions import db


class GLAccount(db.Model):
    __tablename__ = 'gl_accounts'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'code', name='uq_gl_accounts_tenant_code'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    code = db.Column(db.String(20), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)  # English name
    name_ar = db.Column(db.String(200))  # Arabic name
    parent_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'))
    type = db.Column(db.String(20), nullable=False, index=True)  # asset, liability, equity, revenue, expense
    currency = db.Column(db.String(3), default='AED', nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_header = db.Column(db.Boolean, default=False)  # حساب رئيسي (لا يقبل قيود مباشرة)
    level = db.Column(db.Integer, default=0)  # مستوى الحساب في الشجرة
    description = db.Column(db.Text)  # وصف الحساب
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))

    parent = db.relationship('GLAccount', remote_side=[id], backref='children')
    tenant = db.relationship('Tenant', backref='gl_accounts', foreign_keys=[tenant_id])

    def __repr__(self):
        return f'<GLAccount {self.code} {self.name}>'
    
    @property
    def full_name(self):
        """الاسم الكامل مع الكود"""
        return f"{self.code} - {self.name_ar or self.name}"
    
    @property
    def type_ar(self):
        """نوع الحساب بالعربي"""
        types = {
            'asset': 'أصول',
            'liability': 'خصوم',
            'equity': 'حقوق ملكية',
            'revenue': 'إيرادات',
            'expense': 'مصروفات'
        }
        return types.get(self.type, self.type)
    
    def get_balance(self):
        """حساب رصيد الحساب بالعملة المحلية (AED)"""
        from sqlalchemy import func
        from models import GLJournalLine
        
        balance_sum = db.session.query(func.sum(GLJournalLine.amount_aed)).filter_by(account_id=self.id).scalar() or 0
        
        if self.type in ['asset', 'expense']:
            return balance_sum
        else:  # liability, equity, revenue
            return -balance_sum
    
    def get_children_recursive(self):
        """الحصول على جميع الحسابات الفرعية بشكل متكرر"""
        result = []
        for child in self.children:
            result.append(child)
            result.extend(child.get_children_recursive())
        return result


class GLJournalEntry(db.Model):
    __tablename__ = 'gl_journal_entries'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'entry_number', name='uq_gl_journal_entries_tenant_number'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    entry_number = db.Column(db.String(50), nullable=False, index=True)
    entry_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    description = db.Column(db.String(255))
    reference_type = db.Column(db.String(50))  # sale, purchase, payment, expense, manual, adjustment, closing, reversing
    reference_id = db.Column(db.Integer)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True) # New Branch ID
    entry_type = db.Column(db.String(30), default='manual')  # manual, auto, adjustment, closing, reversing
    currency = db.Column(db.String(3), default='AED', nullable=False)
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    total_debit = db.Column(db.Numeric(18, 3), default=0)
    total_credit = db.Column(db.Numeric(18, 3), default=0)
    is_posted = db.Column(db.Boolean, default=True)  # هل تم ترحيل القيد
    is_reversed = db.Column(db.Boolean, default=False)  # هل تم عكس القيد
    reversed_entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'))  # القيد المعكوس
    notes = db.Column(db.Text)  # ملاحظات إضافية
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))

    lines = db.relationship('GLJournalLine', back_populates='entry', lazy='dynamic', cascade='all, delete-orphan')
    reversed_entry = db.relationship('GLJournalEntry', remote_side=[id], foreign_keys=[reversed_entry_id])
    user = db.relationship('User', foreign_keys=[created_by])
    branch = db.relationship('Branch', backref='journal_entries', foreign_keys=[branch_id])
    tenant = db.relationship('Tenant', backref='journal_entries', foreign_keys=[tenant_id])

    def __repr__(self):
        return f'<GLEntry {self.entry_number}>'
    
    def is_balanced(self):
        """Check if entry is balanced"""
        return self.total_debit == self.total_credit
    
    @property
    def entry_type_ar(self):
        """نوع القيد بالعربي"""
        types = {
            'manual': 'قيد يدوي',
            'auto': 'قيد تلقائي',
            'adjustment': 'قيد تسوية',
            'closing': 'قيد إقفال',
            'reversing': 'قيد عكسي'
        }
        return types.get(self.entry_type, self.entry_type)
    
    def reverse_entry(self, description=None):
        """عكس القيد (إنشاء قيد معاكس)"""
        if self.is_reversed:
            raise ValueError('هذا القيد تم عكسه مسبقاً')
        
        from utils.helpers import generate_number
        
        from services import gl_helpers
        reversed_entry = GLJournalEntry(
            tenant_id=self.tenant_id,
            entry_number=gl_helpers.next_entry_number(self.tenant_id),
            entry_date=datetime.now(timezone.utc),
            description=description or f'عكس قيد: {self.description}',
            reference_type=self.reference_type,
            reference_id=self.reference_id,
            branch_id=self.branch_id,
            entry_type='reversing',
            currency=self.currency,
            exchange_rate=self.exchange_rate,
            total_debit=self.total_credit,
            total_credit=self.total_debit,
            reversed_entry_id=self.id,
            created_by=self.created_by,
        )
        db.session.add(reversed_entry)
        db.session.flush()
        
        # عكس السطور
        for line in self.lines:
            reversed_line = GLJournalLine(
                tenant_id=self.tenant_id,
                entry_id=reversed_entry.id,
                account_id=line.account_id,
                description=line.description,
                debit=line.credit,  # عكس
                credit=line.debit,  # عكس
                amount_aed=-line.amount_aed  # عكس
            )
            db.session.add(reversed_line)
        
        # تحديث القيد الأصلي
        self.is_reversed = True
        
        db.session.flush()
        return reversed_entry


class GLPeriod(db.Model):
    """Accounting period lock — prevents posting into closed months."""
    __tablename__ = 'gl_periods'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'year', 'month', name='uq_gl_periods_tenant_ym'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    is_closed = db.Column(db.Boolean, default=False, nullable=False)
    closed_at = db.Column(db.DateTime)
    closed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    tenant = db.relationship('Tenant', backref='gl_periods', foreign_keys=[tenant_id])


class GLJournalLine(db.Model):
    __tablename__ = 'gl_journal_lines'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'), nullable=False, index=True)
    description = db.Column(db.String(255))
    debit = db.Column(db.Numeric(18, 3), default=0)
    credit = db.Column(db.Numeric(18, 3), default=0)
    amount_aed = db.Column(db.Numeric(18, 3), default=0)
    
    # مركز التكلفة (اختياري)
    cost_center_id = db.Column(db.Integer, db.ForeignKey('cost_centers.id'))

    entry = db.relationship('GLJournalEntry', back_populates='lines')
    account = db.relationship('GLAccount')
    cost_center = db.relationship('CostCenter')
    tenant = db.relationship('Tenant', backref='journal_lines', foreign_keys=[tenant_id])

    def __repr__(self):
        return f'<GLLine acc={self.account_id} d={self.debit} c={self.credit}>'


