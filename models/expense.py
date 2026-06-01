from datetime import datetime, timezone
from extensions import db


class ExpenseCategory(db.Model):
    __tablename__ = 'expense_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    name_ar = db.Column(db.String(100))
    gl_account_code = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    expenses = db.relationship('Expense', back_populates='category', lazy='dynamic')
    tenant = db.relationship('Tenant', backref='expense_categories', foreign_keys=[tenant_id])
    
    def __repr__(self):
        return f'<ExpenseCategory {self.name}>'


class Expense(db.Model):
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    expense_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=False, index=True)
    
    description = db.Column(db.String(255), nullable=False)
    description_ar = db.Column(db.String(255))
    
    amount = db.Column(db.Numeric(15, 3), nullable=False)
    currency = db.Column(db.String(3), default='AED', nullable=False)
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False)
    
    expense_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    payment_method = db.Column(db.String(20), nullable=False)
    reference_number = db.Column(db.String(100))
    
    cheque_number = db.Column(db.String(50))
    cheque_date = db.Column(db.Date)
    bank_name = db.Column(db.String(100))
    
    supplier_name = db.Column(db.String(200))
    
    notes = db.Column(db.Text)
    
    status = db.Column(db.String(20), default='confirmed', index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Branch Support
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    is_reversed = db.Column(db.Boolean, default=False, index=True)
    
    category = db.relationship('ExpenseCategory', back_populates='expenses')
    tenant = db.relationship('Tenant', backref='expenses', foreign_keys=[tenant_id])
    user = db.relationship('User', foreign_keys=[user_id])
    branch = db.relationship('Branch', backref='simple_expenses', foreign_keys=[branch_id])
    
    def __repr__(self):
        return f'<Expense {self.expense_number}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'expense_number': self.expense_number,
            'category': self.category.name if self.category else None,
            'description': self.description,
            'amount': float(self.amount),
            'currency': self.currency,
            'amount_aed': float(self.amount_aed),
            'expense_date': self.expense_date.isoformat(),
            'payment_method': self.payment_method,
            'status': self.status,
        }

