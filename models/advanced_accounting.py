from datetime import datetime, timezone
from extensions import db
from decimal import Decimal

class CustomsTax(db.Model):
    """نموذج الجمارك والضرائب"""
    __tablename__ = 'customs_taxes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    name_ar = db.Column(db.String(200), nullable=False)
    tax_type = db.Column(db.String(50), nullable=False)  # customs, vat, excise, income, corporate
    rate = db.Column(db.Numeric(5, 4), nullable=False)  # نسبة الضريبة (0.05 = 5%)
    is_percentage = db.Column(db.Boolean, default=True)
    fixed_amount = db.Column(db.Numeric(18, 3), default=0)  # مبلغ ثابت
    gl_account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    effective_from = db.Column(db.Date, nullable=False)
    effective_to = db.Column(db.Date)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    gl_account = db.relationship('GLAccount')
    
    def __repr__(self):
        return f'<CustomsTax {self.name_ar} - {self.rate}%>'
    
    @property
    def tax_type_ar(self):
        types = {
            'customs': 'جمارك',
            'vat': 'ضريبة القيمة المضافة',
            'excise': 'ضريبة استهلاك',
            'income': 'ضريبة دخل',
            'corporate': 'ضريبة الشركات'
        }
        return types.get(self.tax_type, self.tax_type)

class AdvancedExpense(db.Model):
    """نموذج المصروفات المتقدمة"""
    __tablename__ = 'advanced_expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    expense_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    expense_date = db.Column(db.Date, nullable=False, index=True)
    description = db.Column(db.String(255), nullable=False)
    description_ar = db.Column(db.String(255), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    amount = db.Column(db.Numeric(18, 3), nullable=False)
    currency = db.Column(db.String(3), default='AED', nullable=False)
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    amount_aed = db.Column(db.Numeric(18, 3), nullable=False)
    
    # معلومات الضرائب
    taxable_amount = db.Column(db.Numeric(18, 3), default=0)
    tax_amount = db.Column(db.Numeric(18, 3), default=0)
    tax_rate = db.Column(db.Numeric(5, 4), default=0)
    tax_exempt = db.Column(db.Boolean, default=False)
    
    # معلومات الجمارك
    customs_amount = db.Column(db.Numeric(18, 3), default=0)
    customs_rate = db.Column(db.Numeric(5, 4), default=0)
    customs_exempt = db.Column(db.Boolean, default=False)
    
    # معلومات الدفع
    payment_method = db.Column(db.String(50))  # cash, bank_transfer, cheque, credit_card
    payment_status = db.Column(db.String(50), default='pending')  # pending, paid, partial, overdue
    paid_amount = db.Column(db.Numeric(18, 3), default=0)
    due_date = db.Column(db.Date)
    
    # معلومات الموافقة
    requires_approval = db.Column(db.Boolean, default=False)
    approval_status = db.Column(db.String(50), default='pending')  # pending, approved, rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    approval_notes = db.Column(db.Text)
    
    # معلومات المرفقات
    attachment_count = db.Column(db.Integer, default=0)
    has_receipt = db.Column(db.Boolean, default=False)
    receipt_number = db.Column(db.String(100))
    
    # معلومات النظام
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True) # New Branch ID
    gl_journal_entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'))
    is_reversed = db.Column(db.Boolean, default=False)
    reversed_at = db.Column(db.DateTime)
    reversed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reversal_reason = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # العلاقات
    category = db.relationship('ExpenseCategory')
    supplier = db.relationship('Supplier')
    branch = db.relationship('Branch', backref='expenses', foreign_keys=[branch_id])
    created_user = db.relationship('User', foreign_keys=[created_by])
    approved_user = db.relationship('User', foreign_keys=[approved_by])
    reversed_user = db.relationship('User', foreign_keys=[reversed_by])
    gl_journal_entry = db.relationship('GLJournalEntry')
    
    def __repr__(self):
        return f'<AdvancedExpense {self.expense_number} - {self.description_ar}>'
    
    @property
    def payment_method_ar(self):
        methods = {
            'cash': 'نقداً',
            'bank_transfer': 'تحويل بنكي',
            'cheque': 'شيك',
            'credit_card': 'بطاقة ائتمان'
        }
        return methods.get(self.payment_method, self.payment_method)
    
    @property
    def payment_status_ar(self):
        statuses = {
            'pending': 'معلق',
            'paid': 'مدفوع',
            'partial': 'مدفوع جزئياً',
            'overdue': 'متأخر'
        }
        return statuses.get(self.payment_status, self.payment_status)
    
    @property
    def approval_status_ar(self):
        statuses = {
            'pending': 'في انتظار الموافقة',
            'approved': 'موافق عليه',
            'rejected': 'مرفوض'
        }
        return statuses.get(self.approval_status, self.approval_status)
    
    def calculate_taxes(self):
        """حساب الضرائب والجمارك"""
        if self.tax_exempt:
            self.tax_amount = 0
        else:
            self.tax_amount = self.taxable_amount * self.tax_rate
        
        if self.customs_exempt:
            self.customs_amount = 0
        else:
            self.customs_amount = self.amount_aed * self.customs_rate
    
    def get_total_amount(self):
        """الحصول على المبلغ الإجمالي مع الضرائب"""
        return self.amount_aed + self.tax_amount + self.customs_amount
    
    def reverse_expense(self, reason, reversed_by_user):
        """عكس المصروف"""
        if self.is_reversed:
            raise ValueError("المصروف معكوس مسبقاً")
        
        self.is_reversed = True
        self.reversed_at = datetime.now(timezone.utc)
        self.reversed_by = reversed_by_user.id
        self.reversal_reason = reason
        
        # إنشاء قيد عكسي
        from services.gl_service import GLService
        
        lines = [{
            'account_code': self.category.gl_account.code,
            'debit': 0,
            'credit': self.amount_aed,
            'description': f'عكس مصروف {self.description_ar}'
        }, {
            'account_code': '1110',  # صندوق
            'debit': self.amount_aed,
            'credit': 0,
            'description': f'استرداد مصروف {self.expense_number}'
        }]
        
        GLService.create_manual_entry(
            description=f'عكس مصروف {self.expense_number}',
            lines=lines,
            entry_date=datetime.now().date(),
            created_by=reversed_by_user.id,
            branch_id=self.branch_id,
            notes=f'سبب العكس: {reason}'
        )

class TaxCalculationRule(db.Model):
    """قواعد حساب الضرائب"""
    __tablename__ = 'tax_calculation_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    name_ar = db.Column(db.String(200), nullable=False)
    rule_type = db.Column(db.String(50), nullable=False)  # expense, income, purchase, sale
    condition_field = db.Column(db.String(100))  # الحقل المراد فحصه
    condition_operator = db.Column(db.String(20))  # =, >, <, >=, <=, LIKE
    condition_value = db.Column(db.String(255))  # القيمة المطلوبة
    tax_id = db.Column(db.Integer, db.ForeignKey('customs_taxes.id'), nullable=False)
    priority = db.Column(db.Integer, default=0)  # أولوية التطبيق
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    tax = db.relationship('CustomsTax')
    
    def __repr__(self):
        return f'<TaxCalculationRule {self.name_ar}>'
    
    def matches(self, expense):
        """فحص إذا كانت القاعدة تنطبق على المصروف"""
        if not self.is_active:
            return False
        
        # تطبيق القاعدة حسب النوع
        if self.rule_type == 'expense':
            return self._check_expense_condition(expense)
        
        return False
    
    def _check_expense_condition(self, expense):
        """فحص شروط المصروف"""
        if self.condition_field == 'category_id':
            return str(expense.category_id) == self.condition_value
        elif self.condition_field == 'amount':
            amount = float(expense.amount_aed)
            value = float(self.condition_value)
            
            if self.condition_operator == '>':
                return amount > value
            elif self.condition_operator == '<':
                return amount < value
            elif self.condition_operator == '>=':
                return amount >= value
            elif self.condition_operator == '<=':
                return amount <= value
            elif self.condition_operator == '=':
                return amount == value
        
        return False
