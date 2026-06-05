from datetime import datetime, timezone
import sqlalchemy as sa
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
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    type = db.Column(db.String(20), nullable=False, index=True)  # asset, liability, equity, revenue, expense
    currency = db.Column(db.String(3), default='AED', nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_header = db.Column(db.Boolean, default=False)  # حساب رئيسي (لا يقبل قيود مباشرة)
    level = db.Column(db.Integer, default=0)  # مستوى الحساب في الشجرة
    description = db.Column(db.Text)  # وصف الحساب
    liquidity_kind = db.Column(db.String(20), nullable=True, index=True)  # cash, bank, card, gateway, in_transit
    is_default_liquidity = db.Column(db.Boolean, default=False, nullable=False)
    bank_name = db.Column(db.String(200), nullable=True)
    bank_account_number = db.Column(db.String(100), nullable=True)
    bank_iban = db.Column(db.String(50), nullable=True)
    bank_swift_code = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))

    parent = db.relationship('GLAccount', remote_side=[id], backref='children')
    branch = db.relationship('Branch', foreign_keys=[branch_id])
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

        if self.is_header:
            return sum((child.get_balance() for child in self.children if child.is_active), 0)
        
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

    lines = db.relationship('GLJournalLine', back_populates='entry', lazy='dynamic')
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
                amount=-(line.amount or 0),  # عكس المبلغ الأصلي
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
    entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id', ondelete='RESTRICT'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'), nullable=False, index=True)
    description = db.Column(db.String(255))
    debit = db.Column(db.Numeric(18, 3), default=0)
    credit = db.Column(db.Numeric(18, 3), default=0)
    amount = db.Column(db.Numeric(18, 3), nullable=True)  # original currency net amount
    amount_aed = db.Column(db.Numeric(18, 3), default=0)
    
    # Alias for unified currency handling
    @property
    def base_amount(self):
        return self.amount_aed
    
    @base_amount.setter
    def base_amount(self, value):
        self.amount_aed = value
    
    # مركز التكلفة (اختياري)
    cost_center_id = db.Column(db.Integer, db.ForeignKey('cost_centers.id'), index=True)

    entry = db.relationship('GLJournalEntry', back_populates='lines')
    account = db.relationship('GLAccount')
    cost_center = db.relationship('CostCenter')
    tenant = db.relationship('Tenant', backref='journal_lines', foreign_keys=[tenant_id])

    def __repr__(self):
        return f'<GLLine acc={self.account_id} d={self.debit} c={self.credit}>'


# ---------------------------------------------------------------------------
# Phase 1E – GL Concept Registry & Dynamic Mapping Foundation
# ---------------------------------------------------------------------------

# Approved standard concepts from the master blueprint.
GL_CONCEPT_AR = 'AR'
GL_CONCEPT_AP = 'AP'
GL_CONCEPT_CASH = 'CASH'
GL_CONCEPT_BANK = 'BANK'
GL_CONCEPT_INVENTORY_ASSET = 'INVENTORY_ASSET'
GL_CONCEPT_COGS = 'COGS'
GL_CONCEPT_COGS_REVERSAL = 'COGS_REVERSAL'
GL_CONCEPT_SALES_REVENUE = 'SALES_REVENUE'
GL_CONCEPT_SALES_RETURNS = 'SALES_RETURNS'
GL_CONCEPT_SALES_DISCOUNT = 'SALES_DISCOUNT'
GL_CONCEPT_VAT_INPUT = 'VAT_INPUT'
GL_CONCEPT_VAT_OUTPUT = 'VAT_OUTPUT'
GL_CONCEPT_FX_GAIN = 'FX_GAIN'
GL_CONCEPT_FX_LOSS = 'FX_LOSS'
GL_CONCEPT_CHEQUES_UNDER_COLLECTION = 'CHEQUES_UNDER_COLLECTION'
GL_CONCEPT_INVENTORY_ADJUSTMENT_GAIN = 'INVENTORY_ADJUSTMENT_GAIN'
GL_CONCEPT_INVENTORY_ADJUSTMENT_LOSS = 'INVENTORY_ADJUSTMENT_LOSS'
GL_CONCEPT_FREIGHT_IN = 'FREIGHT_IN'
GL_CONCEPT_CUSTOMS_DUTY = 'CUSTOMS_DUTY'
GL_CONCEPT_DEFERRED_CHEQUES_PAYABLE = 'DEFERRED_CHEQUES_PAYABLE'
GL_CONCEPT_PARTNER_CURRENT_ACCOUNT = 'PARTNER_CURRENT_ACCOUNT'
GL_CONCEPT_MERCHANT_CURRENT_ACCOUNT = 'MERCHANT_CURRENT_ACCOUNT'
GL_CONCEPT_SHIPPING_REVENUE = 'SHIPPING_REVENUE'
GL_CONCEPT_MISC_EXPENSE = 'MISC_EXPENSE'
GL_CONCEPT_COMMISSION_EXPENSE = 'COMMISSION_EXPENSE'
GL_CONCEPT_EMPLOYEE_ADVANCES = 'EMPLOYEE_ADVANCES'
GL_CONCEPT_PAYROLL_EXPENSE = 'PAYROLL_EXPENSE'
GL_CONCEPT_PAYROLL_PAYABLE = 'PAYROLL_PAYABLE'
GL_CONCEPT_BANK_FEES = 'BANK_FEES'
GL_CONCEPT_BANK_INTEREST_INCOME = 'BANK_INTEREST_INCOME'
GL_CONCEPT_DONATION_REVENUE = 'DONATION_REVENUE'
GL_CONCEPT_FIXED_ASSET_ASSET = 'FIXED_ASSET_ASSET'
GL_CONCEPT_DEPRECIATION_EXPENSE = 'DEPRECIATION_EXPENSE'
GL_CONCEPT_ACCUMULATED_DEPRECIATION = 'ACCUMULATED_DEPRECIATION'
GL_CONCEPT_FIXED_ASSET_GAIN = 'FIXED_ASSET_GAIN'
GL_CONCEPT_FIXED_ASSET_LOSS = 'FIXED_ASSET_LOSS'

GL_CONCEPT_CODES = (
    GL_CONCEPT_AR,
    GL_CONCEPT_AP,
    GL_CONCEPT_CASH,
    GL_CONCEPT_BANK,
    GL_CONCEPT_INVENTORY_ASSET,
    GL_CONCEPT_COGS,
    GL_CONCEPT_COGS_REVERSAL,
    GL_CONCEPT_SALES_REVENUE,
    GL_CONCEPT_SALES_RETURNS,
    GL_CONCEPT_SALES_DISCOUNT,
    GL_CONCEPT_VAT_INPUT,
    GL_CONCEPT_VAT_OUTPUT,
    GL_CONCEPT_FX_GAIN,
    GL_CONCEPT_FX_LOSS,
    GL_CONCEPT_CHEQUES_UNDER_COLLECTION,
    GL_CONCEPT_INVENTORY_ADJUSTMENT_GAIN,
    GL_CONCEPT_INVENTORY_ADJUSTMENT_LOSS,
    GL_CONCEPT_FREIGHT_IN,
    GL_CONCEPT_CUSTOMS_DUTY,
    GL_CONCEPT_DEFERRED_CHEQUES_PAYABLE,
    GL_CONCEPT_PARTNER_CURRENT_ACCOUNT,
    GL_CONCEPT_MERCHANT_CURRENT_ACCOUNT,
    GL_CONCEPT_SHIPPING_REVENUE,
    GL_CONCEPT_MISC_EXPENSE,
    GL_CONCEPT_COMMISSION_EXPENSE,
    GL_CONCEPT_EMPLOYEE_ADVANCES,
    GL_CONCEPT_PAYROLL_EXPENSE,
    GL_CONCEPT_PAYROLL_PAYABLE,
    GL_CONCEPT_BANK_FEES,
    GL_CONCEPT_BANK_INTEREST_INCOME,
    GL_CONCEPT_DONATION_REVENUE,
    GL_CONCEPT_FIXED_ASSET_ASSET,
    GL_CONCEPT_DEPRECIATION_EXPENSE,
    GL_CONCEPT_ACCUMULATED_DEPRECIATION,
    GL_CONCEPT_FIXED_ASSET_GAIN,
    GL_CONCEPT_FIXED_ASSET_LOSS,
)

# legacy_code is informational in Phase 1E. No mappings are seeded here.
GL_CONCEPT_REGISTRY = {
    GL_CONCEPT_AR: {'meaning': 'Accounts Receivable', 'legacy_code': '1130', 'required': True},
    GL_CONCEPT_AP: {'meaning': 'Accounts Payable', 'legacy_code': '2110', 'required': True},
    GL_CONCEPT_CASH: {'meaning': 'Cash', 'legacy_code': None, 'required': True},
    GL_CONCEPT_BANK: {'meaning': 'Bank', 'legacy_code': '1120', 'required': True},
    GL_CONCEPT_INVENTORY_ASSET: {'meaning': 'Inventory Asset', 'legacy_code': '1140', 'required': True},
    GL_CONCEPT_COGS: {'meaning': 'Cost of Goods Sold', 'legacy_code': '5100', 'required': True},
    GL_CONCEPT_COGS_REVERSAL: {'meaning': 'Cost of Goods Sold Reversal', 'legacy_code': None, 'required': False},
    GL_CONCEPT_SALES_REVENUE: {'meaning': 'Sales Revenue', 'legacy_code': '4100', 'required': True},
    GL_CONCEPT_SALES_RETURNS: {'meaning': 'Sales Returns', 'legacy_code': None, 'required': False},
    GL_CONCEPT_SALES_DISCOUNT: {'meaning': 'Sales Discount', 'legacy_code': None, 'required': False},
    GL_CONCEPT_VAT_INPUT: {'meaning': 'VAT Input', 'legacy_code': None, 'required': True},
    GL_CONCEPT_VAT_OUTPUT: {'meaning': 'VAT Output', 'legacy_code': '2130', 'required': True},
    GL_CONCEPT_FX_GAIN: {'meaning': 'Foreign Exchange Gain', 'legacy_code': None, 'required': False},
    GL_CONCEPT_FX_LOSS: {'meaning': 'Foreign Exchange Loss', 'legacy_code': None, 'required': False},
    GL_CONCEPT_CHEQUES_UNDER_COLLECTION: {'meaning': 'Cheques Under Collection', 'legacy_code': '1150', 'required': False},
    GL_CONCEPT_INVENTORY_ADJUSTMENT_GAIN: {'meaning': 'Inventory Adjustment Gain', 'legacy_code': None, 'required': False},
    GL_CONCEPT_INVENTORY_ADJUSTMENT_LOSS: {'meaning': 'Inventory Adjustment Loss', 'legacy_code': None, 'required': False},
    GL_CONCEPT_FREIGHT_IN: {'meaning': 'Freight In', 'legacy_code': None, 'required': False},
    GL_CONCEPT_CUSTOMS_DUTY: {'meaning': 'Customs Duty', 'legacy_code': None, 'required': False},
    GL_CONCEPT_DEFERRED_CHEQUES_PAYABLE: {'meaning': 'Deferred Cheques Payable', 'legacy_code': '2120', 'required': False, 'normal_balance': 'credit'},
    GL_CONCEPT_PARTNER_CURRENT_ACCOUNT: {'meaning': 'Partner Current Account', 'legacy_code': '3350', 'required': False},
    GL_CONCEPT_MERCHANT_CURRENT_ACCOUNT: {'meaning': 'Merchant Current Account', 'legacy_code': '2115', 'required': False},
    GL_CONCEPT_SHIPPING_REVENUE: {'meaning': 'Shipping Revenue', 'legacy_code': '4300', 'required': False, 'normal_balance': 'credit'},
    GL_CONCEPT_MISC_EXPENSE: {'meaning': 'Miscellaneous Expense', 'legacy_code': '6990', 'required': False, 'normal_balance': 'debit'},
    GL_CONCEPT_COMMISSION_EXPENSE: {'meaning': 'Commission Expense', 'legacy_code': '6150', 'required': False, 'normal_balance': 'debit'},
    GL_CONCEPT_EMPLOYEE_ADVANCES: {'meaning': 'Employee Advances', 'legacy_code': '1160', 'required': False},
    GL_CONCEPT_PAYROLL_EXPENSE: {'meaning': 'Payroll Expense', 'legacy_code': '6100', 'required': False, 'normal_balance': 'debit'},
    GL_CONCEPT_PAYROLL_PAYABLE: {'meaning': 'Payroll Payable', 'legacy_code': '2140', 'required': False, 'normal_balance': 'credit'},
    GL_CONCEPT_BANK_FEES: {'meaning': 'Bank Fees', 'legacy_code': '6950', 'required': False, 'normal_balance': 'debit'},
    GL_CONCEPT_BANK_INTEREST_INCOME: {'meaning': 'Bank Interest Income', 'legacy_code': '4500', 'required': False, 'normal_balance': 'credit'},
    GL_CONCEPT_DONATION_REVENUE: {'meaning': 'Donation Revenue', 'legacy_code': '4200', 'required': False, 'normal_balance': 'credit'},
    GL_CONCEPT_FIXED_ASSET_ASSET: {'meaning': 'Fixed Asset Asset', 'legacy_code': '1240', 'required': False},
    GL_CONCEPT_DEPRECIATION_EXPENSE: {'meaning': 'Depreciation Expense', 'legacy_code': '6180', 'required': False, 'normal_balance': 'debit'},
    GL_CONCEPT_ACCUMULATED_DEPRECIATION: {'meaning': 'Accumulated Depreciation', 'legacy_code': '1290', 'required': False, 'normal_balance': 'credit'},
    GL_CONCEPT_FIXED_ASSET_GAIN: {'meaning': 'Fixed Asset Disposal Gain', 'legacy_code': '4500', 'required': False, 'normal_balance': 'credit'},
    GL_CONCEPT_FIXED_ASSET_LOSS: {'meaning': 'Fixed Asset Disposal Loss', 'legacy_code': '6990', 'required': False, 'normal_balance': 'debit'},
}

VALID_GL_CONCEPT_CODES = frozenset(GL_CONCEPT_CODES)
REQUIRED_GL_CONCEPTS = frozenset(
    code for code, meta in GL_CONCEPT_REGISTRY.items() if meta['required']
)

_GL_CONCEPT_CODE_CHECK = "concept_code IN ({})".format(
    ", ".join(f"'{code}'" for code in GL_CONCEPT_CODES)
)


class GLAccountMapping(db.Model):
    """
    Maps a standard GL concept to a tenant's chart-of-accounts entry.

    Phase 1E foundation — the table is additive and inert until the feature
    flag ``ENABLE_DYNAMIC_GL_MAPPING`` is enabled.  Legacy hardcoded lookups
    remain the active code path while the flag is off.

    Unique constraint logic:
      • (tenant_id, concept_code) with branch_id IS NULL → tenant-level default.
      • (tenant_id, concept_code, branch_id) when branch_id IS NOT NULL → branch override.
    """
    __tablename__ = 'gl_account_mappings'
    __table_args__ = (
        db.CheckConstraint(
            _GL_CONCEPT_CODE_CHECK,
            name='ck_gl_account_mappings_concept_code',
        ),
        db.Index(
            'ix_gl_account_mappings_tenant_concept_active',
            'tenant_id', 'concept_code', 'is_active',
        ),
        db.Index(
            'uq_gl_account_mappings_tenant_concept_default',
            'tenant_id', 'concept_code',
            unique=True,
            postgresql_where=sa.text('branch_id IS NULL'),
            sqlite_where=sa.text('branch_id IS NULL'),
        ),
        db.Index(
            'uq_gl_account_mappings_tenant_concept_branch',
            'tenant_id', 'concept_code', 'branch_id',
            unique=True,
            postgresql_where=sa.text('branch_id IS NOT NULL'),
            sqlite_where=sa.text('branch_id IS NOT NULL'),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey('tenants.id', ondelete='RESTRICT'),
        nullable=False,
        index=True,
    )
    concept_code = db.Column(db.String(50), nullable=False, index=True)
    gl_account_id = db.Column(
        db.Integer,
        db.ForeignKey('gl_accounts.id', ondelete='RESTRICT'),
        nullable=False,
        index=True,
    )
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey('branches.id', ondelete='RESTRICT'),
        nullable=True,
        index=True,
    )
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    tenant = db.relationship('Tenant', backref='gl_account_mappings', foreign_keys=[tenant_id])
    gl_account = db.relationship('GLAccount', backref='concept_mappings', foreign_keys=[gl_account_id])
    branch = db.relationship('Branch', backref='gl_account_mappings', foreign_keys=[branch_id])

    def __repr__(self):
        branch_tag = f' branch={self.branch_id}' if self.branch_id else ''
        return f'<GLAccountMapping tenant={self.tenant_id} {self.concept_code}→acc={self.gl_account_id}{branch_tag}>'

    @classmethod
    def validate_concept_code(cls, concept_code):
        """Raise ValueError if the concept_code is not in the approved registry."""
        if concept_code not in VALID_GL_CONCEPT_CODES:
            raise ValueError(
                f"Unknown GL concept code '{concept_code}'. "
                f"Valid codes: {sorted(VALID_GL_CONCEPT_CODES)}"
            )
