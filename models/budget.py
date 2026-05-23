"""
نموذج الموازنة التخطيطية - Budget Model
"""

from datetime import datetime, timezone
from extensions import db
from decimal import Decimal


class Budget(db.Model):
    """
    الموازنة السنوية/الشهرية
    """
    __tablename__ = 'budgets'
    
    id = db.Column(db.Integer, primary_key=True)
    budget_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name_ar = db.Column(db.String(200), nullable=False)
    name_en = db.Column(db.String(200))
    
    # الفترة
    fiscal_year = db.Column(db.Integer, nullable=False, index=True)  # 2025, 2026
    period_type = db.Column(db.String(20), default='annual')  # annual, quarterly, monthly
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    
    # الإجماليات
    total_budgeted = db.Column(db.Numeric(18, 3), default=0)
    total_actual = db.Column(db.Numeric(18, 3), default=0)
    total_variance = db.Column(db.Numeric(18, 3), default=0)
    variance_percentage = db.Column(db.Numeric(5, 2), default=0)
    
    # الحالة
    status = db.Column(db.String(20), default='draft', index=True)  # draft, active, closed
    
    notes = db.Column(db.Text)
    
    # Meta
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True) # New Branch ID
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    approved_at = db.Column(db.DateTime)
    
    # Relationships
    lines = db.relationship('BudgetLine', back_populates='budget', cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    branch = db.relationship('Branch', backref='budgets', foreign_keys=[branch_id])
    
    def __repr__(self):
        return f'<Budget {self.budget_number} - {self.fiscal_year}>'
    
    @property
    def status_ar(self):
        """الحالة بالعربي"""
        statuses = {
            'draft': 'مسودة',
            'active': 'نشطة',
            'closed': 'مغلقة'
        }
        return statuses.get(self.status, self.status)
    
    @property
    def period_type_ar(self):
        """نوع الفترة بالعربي"""
        types = {
            'annual': 'سنوية',
            'quarterly': 'ربع سنوية',
            'monthly': 'شهرية'
        }
        return types.get(self.period_type, self.period_type)
    
    def update_actuals(self):
        """تحديث الأرقام الفعلية من دفتر الأستاذ"""
        from sqlalchemy import func
        from models import GLJournalLine, GLJournalEntry
        
        total_actual = Decimal('0')
        total_variance = Decimal('0')
        
        for line in self.lines:
            # حساب المبلغ الفعلي
            debit_sum = db.session.query(func.sum(GLJournalLine.debit)).filter(
                GLJournalLine.account_id == line.account_id
            ).join(GLJournalEntry).filter(
                func.date(GLJournalEntry.entry_date).between(self.period_start, self.period_end)
            ).scalar() or Decimal('0')
            
            credit_sum = db.session.query(func.sum(GLJournalLine.credit)).filter(
                GLJournalLine.account_id == line.account_id
            ).join(GLJournalEntry).filter(
                func.date(GLJournalEntry.entry_date).between(self.period_start, self.period_end)
            ).scalar() or Decimal('0')
            
            # حساب الفعلي حسب نوع الحساب
            if line.account.type in ['asset', 'expense']:
                line.actual_amount = debit_sum - credit_sum
            else:  # liability, equity, revenue
                line.actual_amount = credit_sum - debit_sum
            
            # حساب الانحراف
            line.variance = line.actual_amount - line.budgeted_amount
            
            if line.budgeted_amount != 0:
                line.variance_percentage = (line.variance / line.budgeted_amount) * 100
            else:
                line.variance_percentage = 0
            
            total_actual += line.actual_amount
            total_variance += line.variance
        
        # تحديث الإجماليات
        self.total_actual = total_actual
        self.total_variance = total_variance
        
        if self.total_budgeted != 0:
            self.variance_percentage = (self.total_variance / self.total_budgeted) * 100
        
        db.session.commit()
    
    def activate(self):
        """تفعيل الموازنة"""
        if self.status != 'draft':
            raise ValueError('الموازنة نشطة مسبقاً')
        
        self.status = 'active'
        db.session.commit()
    
    def close(self):
        """إغلاق الموازنة"""
        if self.status != 'active':
            raise ValueError('يجب أن تكون الموازنة نشطة لإغلاقها')
        
        # تحديث الأرقام الفعلية قبل الإغلاق
        self.update_actuals()
        
        self.status = 'closed'
        db.session.commit()


class BudgetLine(db.Model):
    """
    سطور الموازنة - حساب واحد
    """
    __tablename__ = 'budget_lines'
    
    id = db.Column(db.Integer, primary_key=True)
    budget_id = db.Column(db.Integer, db.ForeignKey('budgets.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'), nullable=False)
    
    # المبالغ المخططة
    budgeted_amount = db.Column(db.Numeric(18, 3), nullable=False)
    
    # المبالغ الفعلية (محسوبة)
    actual_amount = db.Column(db.Numeric(18, 3), default=0)
    
    # الانحراف
    variance = db.Column(db.Numeric(18, 3), default=0)
    variance_percentage = db.Column(db.Numeric(8, 2), default=0)
    
    notes = db.Column(db.Text)
    
    # Relationships
    budget = db.relationship('Budget', back_populates='lines')
    account = db.relationship('GLAccount')
    
    def __repr__(self):
        return f'<BudgetLine {self.account.code} - {self.budgeted_amount}>'
    
    @property
    def variance_status(self):
        """حالة الانحراف"""
        if abs(self.variance_percentage) < 5:
            return 'good'  # ضمن الحدود
        elif abs(self.variance_percentage) < 15:
            return 'warning'  # تحذير
        else:
            return 'danger'  # خطر
    
    @property
    def variance_status_ar(self):
        """حالة الانحراف بالعربي"""
        statuses = {
            'good': 'ممتاز',
            'warning': 'يحتاج متابعة',
            'danger': 'انحراف كبير'
        }
        return statuses.get(self.variance_status, '-')

