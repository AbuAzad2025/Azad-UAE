from datetime import datetime, timezone
from decimal import Decimal
import sqlalchemy as sa
from extensions import db
from utils.currency_utils import context_aware_default_currency
from utils.gl_services import gl_next_entry_number

class GLAccount(db.Model):
    __tablename__ = 'gl_accounts'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'code', name='uq_gl_accounts_tenant_code'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    code = db.Column(db.String(20), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)  # English name
    name_ar = db.Column(db.String(200))  # Arabic name
    parent_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'), index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    type = db.Column(db.String(20), nullable=False, index=True)  # asset, liability, equity, revenue, expense
    sub_type = db.Column(db.String(50), nullable=True, index=True)  # receivable, payable, cash, bank, inventory, fixed_asset, etc.
    is_reconcile = db.Column(db.Boolean, default=False, nullable=False)  # هل الحساب قابل للتسوية
    currency = db.Column(db.String(3), default=context_aware_default_currency, nullable=False)  # TODO: use Config.DEFAULT_CURRENCY
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_header = db.Column(db.Boolean, default=False)  # حساب رئيسي (لا يقبل قيود مباشرة)
    level = db.Column(db.Integer, default=0)  # مستوى الحساب في الشجرة
    description = db.Column(db.Text)
    industry_code = db.Column(db.String(50), nullable=True, index=True)
    module_code = db.Column(db.String(50), nullable=True, index=True)
    liquidity_kind = db.Column(db.String(20), nullable=True, index=True)
    is_default_liquidity = db.Column(db.Boolean, default=False, nullable=False)
    bank_name = db.Column(db.String(200), nullable=True)
    bank_account_number = db.Column(db.String(100), nullable=True)
    bank_iban = db.Column(db.String(50), nullable=True)
    bank_swift_code = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
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

    @property
    def sub_type_ar(self):
        """النوع الفرعي بالعربي"""
        sub_types = {
            'receivable': 'ذمم مدينة',
            'payable': 'ذمم دائنة',
            'cash': 'نقدية',
            'bank': 'بنك',
            'inventory': 'مخزون',
            'fixed_asset': 'أصل ثابت',
            'current_liability': 'خصم متداول',
            'non_current_liability': 'خصم غير متداول',
            'equity_share': 'حقوق ملكية',
            'retained_earnings': 'أرباح مرحلة',
            'revenue_operating': 'إيرادات تشغيلية',
            'revenue_non_operating': 'إيرادات غير تشغيلية',
            'cogs': 'تكلفة بضاعة',
            'expense_operating': 'مصروف تشغيلي',
            'expense_non_operating': 'مصروف غير تشغيلي',
            'tax': 'ضريبة',
            'depreciation': 'إهلاك',
            'vat': 'ضريبة قيمة مضافة',
        }
        return sub_types.get(self.sub_type, self.sub_type or '')
    
    def get_balance(self, start_date=None, end_date=None, as_of_date=None,
                    _depth=0, _visited=None):
        from sqlalchemy import func
        from models import GLJournalLine
        from decimal import Decimal

        if _depth > 10:
            raise RecursionError("Max depth 10 exceeded")
        if _visited is None:
            _visited = set()
        if id(self) in _visited:
            raise ValueError("Circular reference detected")
        _visited.add(id(self))

        if self.is_header:
            return sum(
                (child.get_balance(start_date=start_date, end_date=end_date,
                                   as_of_date=as_of_date,
                                   _depth=_depth + 1, _visited=_visited)
                 for child in self.children if child.is_active),
                Decimal('0'),
            )

        # --- Leaf account: single optimized SQL query ---
        end = end_date or as_of_date

        q = db.session.query(
            func.coalesce(func.sum(GLJournalLine.debit - GLJournalLine.credit), Decimal('0'))
        ).join(
            GLJournalLine.entry
        ).filter(
            GLJournalLine.account_id == self.id,
            GLJournalEntry.status == 'posted',
            GLJournalEntry.tenant_id == self.tenant_id,
        )

        if start_date is not None:
            q = q.filter(GLJournalEntry.entry_date >= start_date)
        if end is not None:
            q = q.filter(GLJournalEntry.entry_date <= end)

        balance = q.scalar()

        if self.type in ('liability', 'equity', 'revenue'):
            balance = -balance

        return balance
    
    def get_children_recursive(self, max_depth=10, _depth=0, _visited=None):
        if _depth > max_depth:
            raise RecursionError(f"Max depth {max_depth} exceeded")
        if _visited is None:
            _visited = set()
        if id(self) in _visited:
            raise ValueError("Circular reference detected")
        _visited.add(id(self))
        result = []
        for child in self.children:
            result.append(child)
            result.extend(child.get_children_recursive(max_depth=max_depth, _depth=_depth+1, _visited=_visited))
        return result

class GLJournalEntry(db.Model):
    __tablename__ = 'gl_journal_entries'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'entry_number', name='uq_gl_journal_entries_tenant_number'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    entry_number = db.Column(db.String(50), nullable=False, index=True)
    entry_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    description = db.Column(db.String(255))
    reference_type = db.Column(db.String(50))  # sale, purchase, payment, expense, manual, adjustment, closing, reversing
    reference_id = db.Column(db.Integer)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True) # New Branch ID
    entry_type = db.Column(db.String(30), default='manual')  # manual, auto, adjustment, closing, reversing
    currency = db.Column(db.String(3), default=context_aware_default_currency, nullable=False)  # TODO: use Config.DEFAULT_CURRENCY
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    total_debit = db.Column(db.Numeric(18, 3), default=0)
    total_credit = db.Column(db.Numeric(18, 3), default=0)
    is_posted = db.Column(db.Boolean, default=True)  # DEPRECATED: use status column
    is_reversed = db.Column(db.Boolean, default=False)  # هل تم عكس القيد
    # ── State Machine ──────────────────────────────────────────────────────
    # Draft → Validated → Posted   (happy path)
    # Draft → Error                (validation failure)
    # Any   → Reversed             (reversal creates a new reversing entry)
    # Any   → Cancelled            (soft-delete, never physical delete)
    status = db.Column(db.String(20), default='draft', nullable=False, index=True)
    # 'draft': editable, not yet validated (default for new entries)
    # 'validated': balanced & CoA valid, ready for posting
    # 'error': validation failed — see validation_errors
    # 'posted': posted to GL (requires validation first)
    # 'reversed': original entry that was reversed
    # 'cancelled': soft-deleted entry (audit trail preserved)
    validation_errors = db.Column(db.Text)  # JSON list of validation failures
    validated_at = db.Column(db.DateTime)
    validated_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    reversed_entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'), index=True)  # القيد المعكوس
    notes = db.Column(db.Text)  # ملاحظات إضافية
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
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
        
        reversed_entry = GLJournalEntry(
            tenant_id=self.tenant_id,
            entry_number=gl_next_entry_number(self.tenant_id),
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
                amount_aed=-line.amount_aed,  # عكس
                # الأبعاد المالية (متوارثة من السطر الأصلي)
                branch_id=line.branch_id,
                warehouse_id=line.warehouse_id,
                cost_center_id=line.cost_center_id,
                profit_center_id=line.profit_center_id,
                partner_id=line.partner_id,
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
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    is_closed = db.Column(db.Boolean, default=False, nullable=False)
    closed_at = db.Column(db.DateTime)
    closed_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    tenant = db.relationship('Tenant', backref='gl_periods', foreign_keys=[tenant_id])

class GLJournalLine(db.Model):
    __tablename__ = 'gl_journal_lines'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
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
    
    # الأبعاد المالية (Financial Dimensions)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True, index=True)
    cost_center_id = db.Column(db.Integer, db.ForeignKey('cost_centers.id'), nullable=True, index=True)
    profit_center_id = db.Column(db.Integer, db.ForeignKey('profit_centers.id'), nullable=True, index=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), nullable=True, index=True)

    entry = db.relationship('GLJournalEntry', back_populates='lines')
    account = db.relationship('GLAccount')
    cost_center = db.relationship('CostCenter')
    branch = db.relationship('Branch', foreign_keys=[branch_id])
    warehouse = db.relationship('Warehouse', foreign_keys=[warehouse_id])
    profit_center = db.relationship('ProfitCenter', foreign_keys=[profit_center_id])
    partner = db.relationship('Partner', foreign_keys=[partner_id])
    tenant = db.relationship('Tenant', backref='journal_lines', foreign_keys=[tenant_id])

    def __repr__(self):
        return f'<GLLine acc={self.account_id} d={self.debit} c={self.credit}>'

from models._constants import (
    GL_CONCEPT_REGISTRY,
    GL_CONCEPT_CODES,
    VALID_GL_CONCEPT_CODES,
    REQUIRED_GL_CONCEPTS,
    _GL_CONCEPT_CODE_CHECK,
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
        db.ForeignKey('tenants.id', ondelete='CASCADE'),
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
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

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


@sa.event.listens_for(GLJournalEntry, 'before_insert')
@sa.event.listens_for(GLJournalEntry, 'before_update')
def _validate_journal_entry(mapper, connection, target):
    # 1. Balance check
    diff = abs((target.total_debit or Decimal('0')) - (target.total_credit or Decimal('0')))
    if diff > Decimal('0.001'):
        from services.gl_posting import UnbalancedJournalEntryError
        raise UnbalancedJournalEntryError(
            f'Journal entry {target.entry_number or "(new)"} is not balanced: '
            f'debit={target.total_debit} credit={target.total_credit}'
        )
    # 2. Keep is_posted in sync with status (deprecated field used by reports)
    if target.status in ('posted', 'reversed'):
        target.is_posted = True
    elif target.status in ('draft', 'validated', 'error', 'cancelled'):
        target.is_posted = False
    if target.status == 'reversed':
        target.is_reversed = True
