from datetime import datetime, timezone
from extensions import db
from utils.currency_utils import context_aware_default_currency

class Employee(db.Model):
    __tablename__ = 'employees'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    
    # Employment Details
    employment_type = db.Column(db.String(20), default='salary') # salary (monthly), daily (miyawama)
    contract_type = db.Column(db.String(20), default='limited') # limited, unlimited
    basic_salary = db.Column(db.Numeric(10, 2), default=0) # Monthly salary or Daily rate
    allowances = db.Column(db.Numeric(10, 2), default=0) # Monthly allowances
    currency = db.Column(db.String(3), default=context_aware_default_currency)
    
    # Branch Link
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    
    is_active = db.Column(db.Boolean, default=True, index=True)
    joined_date = db.Column(db.Date, default=datetime.now)
    termination_date = db.Column(db.Date)
    termination_reason = db.Column(db.String(255))
    
    # Leave Accrual
    annual_leave_days = db.Column(db.Integer, default=30) # Annual leave entitlement
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    branch = db.relationship('Branch', backref='employees')
    advances = db.relationship('SalaryAdvance', backref='employee', lazy='dynamic')
    payments = db.relationship('PayrollTransaction', backref='employee', lazy='dynamic')
    leaves = db.relationship('EmployeeLeave', backref='employee', lazy='dynamic')

    def __repr__(self):
        return f'<Employee {self.name}>'
    
    def get_balance(self):
        return 0

class EmployeeLeave(db.Model):
    __tablename__ = 'employee_leaves'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False, index=True)
    
    leave_type = db.Column(db.String(20), default='annual') # annual, sick, unpaid
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    days_taken = db.Column(db.Integer, nullable=False)
    
    status = db.Column(db.String(20), default='approved', index=True) # pending, approved, rejected
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class SalaryAdvance(db.Model):
    __tablename__ = 'salary_advances'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), default=0)  # إجمالي السلفة (للسلف الجزئية)
    deducted_amount = db.Column(db.Numeric(10, 2), default=0)  # المبلغ المخصوم
    remaining_amount = db.Column(db.Numeric(10, 2), default=0)  # المبلغ المتبقي
    date = db.Column(db.Date, default=datetime.now)
    description = db.Column(db.String(255))
    
    status = db.Column(db.String(20), default='approved', index=True) # pending, approved, paid, deducted
    is_deducted = db.Column(db.Boolean, default=False) # True if fully deducted from salary
    fully_deducted_at = db.Column(db.DateTime, nullable=True)  # تاريخ الاكتمال
    
    # Link to GL
    gl_entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'), nullable=True, index=True)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)


class PayrollTransaction(db.Model):
    __tablename__ = 'payroll_transactions'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'employee_id', 'month', 'year', name='uq_payroll_tenant_employee_period'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False, index=True)
    
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
    status = db.Column(db.String(20), default='paid', index=True) # draft, posted, paid
    
    # Link to GL
    gl_entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'), nullable=True, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
