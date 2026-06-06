from datetime import datetime

from decimal import Decimal

from extensions import db

from models import Employee, SalaryAdvance, PayrollTransaction

from services.gl_service import GLService

from services.gl_posting import post_or_fail

from utils.gl_reference_types import GLRef
from utils.field_validators import normalize_phone_optional



class PayrollService:

    @staticmethod
    def _branch_tenant_id(branch_id):
        from models import Branch

        branch = db.session.get(Branch, int(branch_id))
        if not branch:
            raise ValueError('الفرع المحدد غير موجود.')
        tenant_id = getattr(branch, 'tenant_id', None)
        if tenant_id is None:
            raise ValueError('الفرع المحدد غير مرتبط بشركة نشطة.')
        return int(tenant_id)

    @staticmethod
    def _require_employee_tenant_id(employee):
        tenant_id = getattr(employee, 'tenant_id', None)
        if tenant_id is None:
            raise ValueError('الموظف غير مرتبط بشركة — لا يمكن إتمام العملية.')
        return int(tenant_id)

    @staticmethod

    def create_employee(data):

        branch_id = data.get('branch_id')

        if not branch_id:

            raise ValueError('يجب ربط الموظف بفرع محدد.')

        tenant_id = PayrollService._branch_tenant_id(branch_id)

        employee = Employee(

            name=data.get('name'),

            name_ar=data.get('name_ar'),

            phone=normalize_phone_optional(data.get('phone')),

            email=data.get('email'),

            employment_type=data.get('employment_type', 'salary'),

            basic_salary=Decimal(data.get('basic_salary', 0)),

            branch_id=int(branch_id),

            tenant_id=tenant_id,

            joined_date=datetime.strptime(data.get('joined_date'), '%Y-%m-%d') if data.get('joined_date') else datetime.now()

        )

        db.session.add(employee)

        db.session.commit()

        return employee



    @staticmethod

    def create_advance(employee_id, amount, description, user_id):

        employee = Employee.query.get_or_404(employee_id)

        tenant_id = PayrollService._require_employee_tenant_id(employee)

        advance = SalaryAdvance(

            employee_id=employee_id,

            amount=Decimal(amount),

            description=description,

            created_by=user_id,

            status='approved',

            tenant_id=tenant_id,

        )

        db.session.add(advance)

        db.session.flush()

        GLService.ensure_core_accounts(tenant_id=tenant_id)
        cash_account = GLService.get_default_liquidity_account(
            'cash',
            branch_id=employee.branch_id,
            tenant_id=tenant_id,
        )



        gl_entry = post_or_fail(

            [

                {'account': '1160', 'concept_code': 'EMPLOYEE_ADVANCES', 'debit': Decimal(str(amount)), 'credit': 0, 'description': f'Advance - {employee.name}'},

                {'account': cash_account, 'concept_code': 'CASH', 'debit': 0, 'credit': Decimal(str(amount)), 'description': 'Cash Payment'},

            ],

            description=f"Salary Advance for {employee.name}",

            reference_type=GLRef.SALARY_ADVANCE,

            reference_id=advance.id,

            branch_id=employee.branch_id,

            user_id=user_id,

        )

        

        advance.gl_entry_id = gl_entry.id

        db.session.commit()

        return advance



    @staticmethod

    def process_payroll(employee_id, month, year, days_worked, allowances, deductions, user_id):

        employee = Employee.query.get_or_404(employee_id)

        tenant_id = PayrollService._require_employee_tenant_id(employee)

        basic_amount = Decimal(0)

        if employee.employment_type == 'salary':

            basic_amount = employee.basic_salary

        else:

            basic_amount = employee.basic_salary * Decimal(days_worked)

            

        pending_advances = SalaryAdvance.query.filter_by(
            employee_id=employee_id, 
            is_deducted=False, 
            status='approved',
            tenant_id=tenant_id
        ).all()

        

        advances_total = sum(adv.amount for adv in pending_advances)

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

            tenant_id=tenant_id,

            created_by=user_id,

            status='paid'

        )

        db.session.add(transaction)

        db.session.flush()

        

        for adv in pending_advances:

            adv.is_deducted = True

            

        total_expense = basic_amount + Decimal(allowances)

        GLService.ensure_core_accounts(tenant_id=tenant_id)
        cash_account = GLService.get_default_liquidity_account(
            'cash',
            branch_id=employee.branch_id,
            tenant_id=tenant_id,
        )

        lines = [

            {'account': '6100', 'concept_code': 'PAYROLL_EXPENSE', 'debit': Decimal(str(total_expense)), 'credit': 0, 'description': f'Salary {month}/{year} - {employee.name}'},

            {'account': cash_account, 'concept_code': 'CASH', 'debit': 0, 'credit': Decimal(str(net_salary)), 'description': 'Net Salary Payment'},

        ]

        if deductions > 0:

            lines.append({'account': '2140', 'concept_code': 'PAYROLL_PAYABLE', 'debit': 0, 'credit': Decimal(str(deductions)), 'description': 'Salary Deductions'})

        if advances_total > 0:

            lines.append({'account': '1160', 'concept_code': 'EMPLOYEE_ADVANCES', 'debit': 0, 'credit': Decimal(str(advances_total)), 'description': 'Advance Deduction'})



        gl_entry = post_or_fail(

            lines,

            description=f"Payroll {month}/{year} - {employee.name}",

            reference_type=GLRef.PAYROLL,

            reference_id=transaction.id,

            branch_id=employee.branch_id,

            user_id=user_id,

        )

        

        transaction.gl_entry_id = gl_entry.id

        db.session.commit()

        return transaction



    @staticmethod

    def generate_branch_payroll(branch_id, month, year, user_id):
        tenant_id = PayrollService._branch_tenant_id(branch_id)
        employees = Employee.query.filter_by(branch_id=branch_id, tenant_id=tenant_id, is_active=True).all()

        generated_count = 0

        skipped_count = 0

        

        for emp in employees:

            exists = PayrollTransaction.query.filter_by(

                employee_id=emp.id, tenant_id=tenant_id, month=month, year=year

            ).first()

            

            if exists:

                skipped_count += 1

                continue

                

            if emp.employment_type == 'salary':

                PayrollService.process_payroll(

                    employee_id=emp.id,

                    month=month,

                    year=year,

                    days_worked=0,

                    allowances=0,

                    deductions=0,

                    user_id=user_id

                )

                generated_count += 1

            else:

                skipped_count += 1

            

        return generated_count, skipped_count

