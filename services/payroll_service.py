from datetime import datetime
from decimal import Decimal
from extensions import db
from models import Employee, SalaryAdvance, PayrollTransaction, GLJournalEntry, GLAccount
from services.gl_service import GLService

class PayrollService:
    
    @staticmethod
    def create_employee(data):
        branch_id = data.get('branch_id')
        if not branch_id:
            raise ValueError('يجب ربط الموظف بفرع محدد.')

        employee = Employee(
            name=data.get('name'),
            name_ar=data.get('name_ar'),
            phone=data.get('phone'),
            email=data.get('email'),
            employment_type=data.get('employment_type', 'salary'),
            basic_salary=Decimal(data.get('basic_salary', 0)),
            branch_id=int(branch_id),
            joined_date=datetime.strptime(data.get('joined_date'), '%Y-%m-%d') if data.get('joined_date') else datetime.now()
        )
        db.session.add(employee)
        db.session.commit()
        return employee

    @staticmethod
    def create_advance(employee_id, amount, description, user_id):
        employee = Employee.query.get_or_404(employee_id)
        
        advance = SalaryAdvance(
            employee_id=employee_id,
            amount=Decimal(amount),
            description=description,
            created_by=user_id,
            status='approved'
        )
        db.session.add(advance)
        db.session.flush()
        
        # GL Entry for Advance
        # Dr. Employee Advances (Asset/Receivable)
        # Cr. Cash
        
        # Ensure 'Employee Advances' account exists (1160)
        adv_account = GLAccount.query.filter_by(code='1160').first()
        if not adv_account:
            # Create if missing (simplified)
            parent = GLAccount.query.filter_by(code='1100').first() # Current Assets
            adv_account = GLAccount(code='1160', name='Employee Advances', name_ar='سلف الموظفين', type='asset', parent_id=parent.id if parent else None)
            db.session.add(adv_account)
            db.session.flush()
            
        cash_account = GLAccount.query.filter_by(code='1110').first() # Cash
        
        gl_entry = GLService.create_journal_entry(
            date=datetime.now(),
            description=f"Salary Advance for {employee.name}",
            lines=[
                {'account_code': adv_account.code, 'debit': Decimal(str(amount)), 'credit': 0, 'description': f'Advance - {employee.name}'},
                {'account_code': cash_account.code, 'debit': 0, 'credit': Decimal(str(amount)), 'description': 'Cash Payment'}
            ],
            user_id=user_id,
            branch_id=employee.branch_id,
            reference_type='salary_advance',
            reference_id=advance.id
        )
        
        advance.gl_entry_id = gl_entry.id
        db.session.commit()
        return advance

    @staticmethod
    def process_payroll(employee_id, month, year, days_worked, allowances, deductions, user_id):
        employee = Employee.query.get_or_404(employee_id)
        
        # Calculate Basic
        basic_amount = Decimal(0)
        if employee.employment_type == 'salary':
            basic_amount = employee.basic_salary
        else: # daily
            basic_amount = employee.basic_salary * Decimal(days_worked)
            
        # Check Advances
        pending_advances = SalaryAdvance.query.filter_by(
            employee_id=employee_id, 
            is_deducted=False, 
            status='approved'
        ).all()
        
        advances_total = sum(adv.amount for adv in pending_advances)
        
        # Net Salary
        net_salary = basic_amount + Decimal(allowances) - Decimal(deductions) - advances_total
        
        transaction = PayrollTransaction(
            employee_id=employee_id,
            month=month,
            year=year,
            basic_amount=basic_amount,
            days_worked=days_worked if employee.employment_type == 'daily' else 0,
            allowances=Decimal(allowances),
            deductions=Decimal(deductions),
            advances_deducted=advances_total,
            net_salary=net_salary,
            branch_id=employee.branch_id,
            created_by=user_id,
            status='paid'
        )
        db.session.add(transaction)
        db.session.flush()
        
        # Mark advances as deducted
        for adv in pending_advances:
            adv.is_deducted = True
            
        # GL Entry for Payroll
        # Dr. Salaries Expense (6100) -> Total (Basic + Allowances)
        # Cr. Employee Advances (1160) -> Advances Deducted
        # Cr. Cash (1110) -> Net Salary
        
        total_expense = basic_amount + Decimal(allowances)
        
        lines = [
            {'account_code': '6100', 'debit': Decimal(str(total_expense)), 'credit': 0, 'description': f'Salary {month}/{year} - {employee.name}'},
            {'account_code': '1110', 'debit': 0, 'credit': Decimal(str(net_salary)), 'description': 'Net Salary Payment'}
        ]

        if deductions > 0:
             # Assuming a generic deductions account or placeholder, but since specific account is unknown, 
             # we ensure credits balance with debits. Usually deductions go to a liability account.
             # For this fix, we will add a placeholder line for deductions to balance the entry.
             lines.append({'account_code': '2140', 'debit': 0, 'credit': Decimal(str(deductions)), 'description': 'Salary Deductions'})
        
        if advances_total > 0:
            lines.append({'account_code': '1160', 'debit': 0, 'credit': Decimal(str(advances_total)), 'description': 'Advance Deduction'})
            
        gl_entry = GLService.create_journal_entry(
            date=datetime.now(),
            description=f"Payroll {month}/{year} - {employee.name}",
            lines=lines,
            user_id=user_id,
            branch_id=employee.branch_id,
            reference_type='payroll',
            reference_id=transaction.id
        )
        
        transaction.gl_entry_id = gl_entry.id
        
        db.session.commit()
        return transaction

    @staticmethod
    def generate_branch_payroll(branch_id, month, year, user_id):
        employees = Employee.query.filter_by(branch_id=branch_id, is_active=True).all()
        generated_count = 0
        skipped_count = 0
        
        for emp in employees:
            # Check if already processed
            exists = PayrollTransaction.query.filter_by(
                employee_id=emp.id, month=month, year=year
            ).first()
            
            if exists:
                skipped_count += 1
                continue
                
            if emp.employment_type == 'salary':
                # Process automatically for fixed salary
                PayrollService.process_payroll(
                    employee_id=emp.id,
                    month=month,
                    year=year,
                    days_worked=0, # Not used for salary
                    allowances=0,
                    deductions=0,
                    user_id=user_id
                )
                generated_count += 1
            else:
                # Daily employees are skipped in auto-generation
                skipped_count += 1
            
        return generated_count, skipped_count
