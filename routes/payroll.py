from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import Employee, SalaryAdvance, PayrollTransaction, Branch
from services.payroll_service import PayrollService
from datetime import datetime
from utils.decorators import branch_scope_id, permission_required
from utils.branching import should_show_all_branch_columns
from utils.tenanting import get_active_tenant_id
from utils.db_safety import atomic_transaction

payroll_bp = Blueprint('payroll', __name__, url_prefix='/payroll')


def _assert_employee_scope(employee, scoped_branch_id, tid):
    if not employee:
        raise ValueError('الموظف غير موجود.')
    if tid is not None and int(employee.tenant_id) != int(tid):
        raise ValueError('الموظف لا ينتمي إلى شركتك النشطة.')
    if scoped_branch_id is not None and employee.branch_id != scoped_branch_id:
        raise ValueError('لا يمكنك التعامل مع موظف من فرع آخر.')


def _assert_branch_scope(branch_id, scoped_branch_id, tid):
    branch = db.session.get(Branch, int(branch_id))
    if not branch:
        raise ValueError('الفرع المحدد غير موجود.')
    if tid is not None and int(branch.tenant_id) != int(tid):
        raise ValueError('الفرع لا ينتمي إلى شركتك النشطة.')
    if scoped_branch_id is not None and int(branch_id) != int(scoped_branch_id):
        raise ValueError('لا يمكنك معالجة رواتب فرع آخر.')


@payroll_bp.route('/employees')
@login_required
@permission_required('manage_payroll')
def employees_list():
    tid = get_active_tenant_id(current_user)
    query = Employee.query
    if tid is not None:
        query = query.filter(Employee.tenant_id == tid)
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
            if not request.form.get('name'):
                raise ValueError('اسم الموظف مطلوب.')
            if scoped_branch_id is not None:
                form_branch_id = request.form.get('branch_id', type=int)
                if form_branch_id != scoped_branch_id:
                    flash('لا يمكنك ربط الموظف إلا بفرعك الحالي.', 'danger')
                    tid = get_active_tenant_id(current_user)
                    branches = Branch.query.filter_by(id=scoped_branch_id, is_active=True)
                    if tid is not None:
                        branches = branches.filter(Branch.tenant_id == tid)
                    branches = branches.all()
                    return render_template('payroll/add_employee.html', branches=branches)
            with atomic_transaction('payroll_add_employee'):
                PayrollService.create_employee(request.form)
            flash('تم إضافة الموظف بنجاح', 'success')
            return redirect(url_for('payroll.employees_list'))
        except Exception as e:
            flash(f'حدث خطأ: {e}', 'danger')

    tid = get_active_tenant_id(current_user)
    branches_query = Branch.query.filter_by(is_active=True)
    if tid is not None:
        branches_query = branches_query.filter(Branch.tenant_id == tid)
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
            scoped_branch_id = branch_scope_id()
            tid = get_active_tenant_id(current_user)
            employee_id_str = request.form.get('employee_id')
            if not employee_id_str:
                raise ValueError('معرف الموظف مطلوب.')
            employee_id = int(employee_id_str)
            amount_str = request.form.get('amount')
            if not amount_str:
                raise ValueError('المبلغ مطلوب.')
            amount = float(amount_str)
            employee = db.session.get(Employee, employee_id)
            _assert_employee_scope(employee, scoped_branch_id, tid)
            with atomic_transaction('payroll_create_advance'):
                PayrollService.create_advance(
                    employee_id=employee_id,
                    amount=amount,
                    description=request.form.get('description'),
                    user_id=current_user.id,
                    actor_user=current_user
                )
            flash('تم تسجيل السلفة بنجاح', 'success')
        except ValueError as e:
            flash(f'خطأ في البيانات: {e}', 'danger')
        except Exception as e:
            flash(f'حدث خطأ: {e}', 'danger')

    scoped_branch_id = branch_scope_id()
    tid = get_active_tenant_id(current_user)
    employees_query = Employee.query.filter_by(is_active=True)
    advances_query = SalaryAdvance.query.join(Employee, SalaryAdvance.employee_id == Employee.id)
    if tid is not None:
        employees_query = employees_query.filter(Employee.tenant_id == tid)
        advances_query = advances_query.filter(Employee.tenant_id == tid)
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
                branch_id_str = request.form.get('branch_id')
                if not branch_id_str:
                    raise ValueError('معرف الفرع مطلوب.')
                branch_id = int(branch_id_str)
                tid = get_active_tenant_id(current_user)
                _assert_branch_scope(branch_id, scoped_branch_id, tid)
                month_str = request.form.get('month')
                year_str = request.form.get('year')
                if not month_str or not year_str:
                    raise ValueError('الشهر والسنة مطلوبان.')
                month = int(month_str)
                year = int(year_str)
                with atomic_transaction('payroll_generate_branch'):
                    gen, skipped = PayrollService.generate_branch_payroll(branch_id, month, year, current_user.id)
                flash(f'تم توليد الرواتب بنجاح: {gen} موظف، وتم تخطي {skipped} (تمت معالجتهم سابقاً أو نظام مياومة)', 'success')
            except ValueError as e:
                flash(f'خطأ في البيانات: {e}', 'danger')
            except Exception as e:
                flash(f'حدث خطأ: {e}', 'danger')
        else:
            try:
                employee_id_str = request.form.get('employee_id')
                if not employee_id_str:
                    raise ValueError('معرف الموظف مطلوب.')
                employee_id = int(employee_id_str)
                tid = get_active_tenant_id(current_user)
                employee = db.session.get(Employee, employee_id)
                _assert_employee_scope(employee, scoped_branch_id, tid)
                with atomic_transaction('payroll_process'):
                    PayrollService.process_payroll(
                        employee_id=employee_id,
                        month=int(request.form.get('month')),
                        year=int(request.form.get('year')),
                        days_worked=float(request.form.get('days_worked', 0)),
                        allowances=float(request.form.get('allowances', 0)),
                        deductions=float(request.form.get('deductions', 0)),
                        user_id=current_user.id,
                        actor_user=current_user
                    )
                flash('تم صرف الراتب بنجاح', 'success')
            except ValueError as e:
                flash(f'خطأ في البيانات: {e}', 'danger')
            except Exception as e:
                flash(f'حدث خطأ: {e}', 'danger')

    tid = get_active_tenant_id(current_user)
    employees_query = Employee.query.filter_by(is_active=True)
    branches_query = Branch.query.filter_by(is_active=True)
    transactions_query = PayrollTransaction.query
    if tid is not None:
        employees_query = employees_query.filter(Employee.tenant_id == tid)
        branches_query = branches_query.filter(Branch.tenant_id == tid)
        transactions_query = transactions_query.filter(PayrollTransaction.tenant_id == tid)
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
def salary_slip(id):  # noqa: A002
    tid = get_active_tenant_id(current_user)
    transaction_query = PayrollTransaction.query.filter_by(id=id)
    if tid is not None:
        transaction_query = transaction_query.filter(PayrollTransaction.tenant_id == tid)
    transaction = transaction_query.first_or_404()
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and transaction.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    return render_template('payroll/slip.html', slip=transaction)


@payroll_bp.route('/statement/<int:id>')
@login_required
@permission_required('manage_payroll')
def statement(id):  # noqa: A002
    tid = get_active_tenant_id(current_user)
    employee_query = Employee.query.filter_by(id=id)
    if tid is not None:
        employee_query = employee_query.filter(Employee.tenant_id == tid)
    employee = employee_query.first_or_404()
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and employee.branch_id != scoped_branch_id:
        return render_template('errors/403.html'), 403
    advances = SalaryAdvance.query.filter_by(employee_id=id)
    payments = PayrollTransaction.query.filter_by(employee_id=id)
    if tid is not None:
        advances = advances.filter(SalaryAdvance.tenant_id == tid)
        payments = payments.filter(PayrollTransaction.tenant_id == tid)
    advances = advances.all()
    payments = payments.all()

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
