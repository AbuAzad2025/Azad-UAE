from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import Employee, SalaryAdvance, PayrollTransaction, Branch
from services.payroll_service import PayrollService
from datetime import datetime
from utils.decorators import branch_scope_id, permission_required
from utils.branching import should_show_all_branch_columns

payroll_bp = Blueprint('payroll', __name__, url_prefix='/payroll')

@payroll_bp.route('/employees')
@login_required
@permission_required('manage_payroll')
def employees_list():
    query = Employee.query
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None:
        query = query.filter(Employee.branch_id == scoped_branch_id)
    employees = query.order_by(Employee.name).all()
    return render_template(
        'payroll/employees.html',
        employees=employees,
        show_branch_columns=should_show_all_branch_columns(current_user),
    )

@payroll_bp.route('/employees/add', methods=['GET', 'POST'])
@login_required
@permission_required('manage_payroll')
def add_employee():
    scoped_branch_id = branch_scope_id()
    if request.method == 'POST':
        try:
            if scoped_branch_id is not None:
                form_branch_id = request.form.get('branch_id', type=int)
                if form_branch_id != scoped_branch_id:
                    flash('لا يمكنك ربط الموظف إلا بفرعك الحالي.', 'danger')
                    branches = Branch.query.filter_by(id=scoped_branch_id, is_active=True).all()
                    return render_template('payroll/add_employee.html', branches=branches)
            PayrollService.create_employee(request.form)
            flash('تم إضافة الموظف بنجاح', 'success')
            return redirect(url_for('payroll.employees_list'))
        except Exception as e:
            flash(f'حدث خطأ: {e}', 'danger')
            
    branches_query = Branch.query.filter_by(is_active=True)
    if scoped_branch_id is not None:
        branches_query = branches_query.filter(Branch.id == scoped_branch_id)
    branches = branches_query.order_by(Branch.code, Branch.name).all()
    return render_template('payroll/add_employee.html', branches=branches)

@payroll_bp.route('/advances', methods=['GET', 'POST'])
@login_required
@permission_required('manage_payroll')
def advances():
    if request.method == 'POST':
        try:
            PayrollService.create_advance(
                employee_id=int(request.form.get('employee_id')),
                amount=float(request.form.get('amount')),
                description=request.form.get('description'),
                user_id=current_user.id
            )
            flash('تم تسجيل السلفة بنجاح', 'success')
        except Exception as e:
            flash(f'حدث خطأ: {e}', 'danger')
            
    scoped_branch_id = branch_scope_id()
    employees_query = Employee.query.filter_by(is_active=True)
    advances_query = SalaryAdvance.query.join(Employee, SalaryAdvance.employee_id == Employee.id)
    if scoped_branch_id is not None:
        employees_query = employees_query.filter(Employee.branch_id == scoped_branch_id)
        advances_query = advances_query.filter(Employee.branch_id == scoped_branch_id)
    employees = employees_query.order_by(Employee.name).all()
    advances = advances_query.order_by(SalaryAdvance.date.desc()).limit(50).all()
    return render_template('payroll/advances.html', advances=advances, employees=employees)

@payroll_bp.route('/process', methods=['GET', 'POST'])
@login_required
@permission_required('manage_payroll')
def process_payroll():
    scoped_branch_id = branch_scope_id()
    if request.method == 'POST':
        if 'generate_branch' in request.form:
            try:
                branch_id = int(request.form.get('branch_id'))
                if scoped_branch_id is not None and branch_id != scoped_branch_id:
                    raise ValueError('لا يمكنك معالجة رواتب فرع آخر.')
                month = int(request.form.get('month'))
                year = int(request.form.get('year'))
                
                gen, skipped = PayrollService.generate_branch_payroll(branch_id, month, year, current_user.id)
                flash(f'تم توليد الرواتب بنجاح: {gen} موظف، وتم تخطي {skipped} (تمت معالجتهم سابقاً أو نظام مياومة)', 'success')
            except Exception as e:
                flash(f'حدث خطأ: {e}', 'danger')
        else:
            try:
                PayrollService.process_payroll(
                    employee_id=int(request.form.get('employee_id')),
                    month=int(request.form.get('month')),
                    year=int(request.form.get('year')),
                    days_worked=float(request.form.get('days_worked', 0)),
                    allowances=float(request.form.get('allowances', 0)),
                    deductions=float(request.form.get('deductions', 0)),
                    user_id=current_user.id
                )
                flash('تم صرف الراتب بنجاح', 'success')
            except Exception as e:
                flash(f'حدث خطأ: {e}', 'danger')
            
    employees_query = Employee.query.filter_by(is_active=True)
    branches_query = Branch.query.filter_by(is_active=True)
    transactions_query = PayrollTransaction.query
    if scoped_branch_id is not None:
        employees_query = employees_query.filter(Employee.branch_id == scoped_branch_id)
        branches_query = branches_query.filter(Branch.id == scoped_branch_id)
        transactions_query = transactions_query.filter(PayrollTransaction.branch_id == scoped_branch_id)
    employees = employees_query.order_by(Employee.name).all()
    branches = branches_query.order_by(Branch.code, Branch.name).all()
    transactions = transactions_query.order_by(PayrollTransaction.payment_date.desc()).limit(50).all()
    today = datetime.now()
    return render_template('payroll/process.html', transactions=transactions, employees=employees, branches=branches, today=today)

@payroll_bp.route('/slip/<int:id>')
@login_required
@permission_required('manage_payroll')
def salary_slip(id):
    transaction = PayrollTransaction.query.get_or_404(id)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and transaction.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    return render_template('payroll/slip.html', t=transaction)

@payroll_bp.route('/statement/<int:id>')
@login_required
@permission_required('manage_payroll')
def statement(id):
    employee = Employee.query.get_or_404(id)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and employee.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    advances = SalaryAdvance.query.filter_by(employee_id=id).all()
    payments = PayrollTransaction.query.filter_by(employee_id=id).all()
    
    # Combine history (Simplified)
    history = []
    for a in advances:
        history.append({
            'date': a.date,
            'type': 'سلفة',
            'amount': -a.amount,
            'desc': a.description
        })
    for p in payments:
        history.append({
            'date': p.payment_date,
            'type': 'راتب',
            'amount': p.net_salary,
            'desc': f'راتب {p.month}/{p.year}'
        })
        
    history.sort(key=lambda x: x['date'])
    
    return render_template('payroll/statement.html', employee=employee, history=history)
