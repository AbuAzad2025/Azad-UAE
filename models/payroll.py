from datetime import datetime, timezone
from extensions import db

class Employee(db.Model):
    __tablename__ = 'employees'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    
    # Employment Details
    employment_type = db.Column(db.String(20), default='salary') # salary (monthly), daily (miyawama)
    basic_salary = db.Column(db.Numeric(10, 2), default=0) # Monthly salary or Daily rate
    currency = db.Column(db.String(3), default='AED')
    
    # Branch Link
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    joined_date = db.Column(db.Date, default=datetime.now)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    branch = db.relationship('Branch', backref='employees')
    advances = db.relationship('SalaryAdvance', backref='employee', lazy='dynamic')
    payments = db.relationship('PayrollTransaction', backref='employee', lazy='dynamic')

    def __repr__(self):
        return f'<Employee {self.name}>'
    
    def get_balance(self):
        """
        Calculate employee balance (Net Payable)
        This is a simplified view. Usually, payroll is calculated period-based.
        But for 'Account Statement', we might want to track Advances vs Repayments.
        """
        # Logic can be expanded based on requirements
        return 0


class SalaryAdvance(db.Model):
    __tablename__ = 'salary_advances'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    date = db.Column(db.Date, default=datetime.now)
    description = db.Column(db.String(255))
    
    status = db.Column(db.String(20), default='approved') # pending, approved, paid, deducted
    is_deducted = db.Column(db.Boolean, default=False) # True if deducted from next salary
    
    # Link to GL
    gl_entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))


class PayrollTransaction(db.Model):
    __tablename__ = 'payroll_transactions'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    
    # Period
    month = db.Column(db.Integer) # 1-12
    year = db.Column(db.Integer)
    
    # Breakdown
    basic_amount = db.Column(db.Numeric(10, 2), default=0) # Base Salary or Days * Rate
    days_worked = db.Column(db.Numeric(5, 2), default=0) # For daily workers
    
    allowances = db.Column(db.Numeric(10, 2), default=0)
    deductions = db.Column(db.Numeric(10, 2), default=0)
    advances_deducted = db.Column(db.Numeric(10, 2), default=0)
    
    net_salary = db.Column(db.Numeric(10, 2), nullable=False)
    
    payment_date = db.Column(db.Date, default=datetime.now)
    status = db.Column(db.String(20), default='paid') # draft, posted, paid
    
    # Link to GL
    gl_entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'), nullable=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
