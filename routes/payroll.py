from datetime import UTC, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext
from flask_login import current_user, login_required

from extensions import db
from models import Branch, Employee
from services.payroll_service import PayrollService
from utils.branching import should_show_all_branch_columns
from utils.db_safety import atomic_transaction
from utils.decorators import branch_scope_id, permission_required
from utils.feature_guards import install_feature_gate
from utils.tenanting import get_active_tenant_id

payroll_bp = Blueprint("payroll", __name__, url_prefix="/payroll")
install_feature_gate(payroll_bp, "payroll")


def _assert_employee_scope(employee, scoped_branch_id, tid):
    if not employee:
        raise ValueError(gettext("الموظف غير موجود."))
    if tid is not None and int(employee.tenant_id) != int(tid):
        raise ValueError(gettext("الموظف لا ينتمي إلى شركتك النشطة."))
    if scoped_branch_id is not None and employee.branch_id != scoped_branch_id:
        raise ValueError(gettext("لا يمكنك التعامل مع موظف من فرع آخر."))


def _assert_branch_scope(branch_id, scoped_branch_id, tid):
    branch = db.session.get(Branch, int(branch_id))
    if not branch:
        raise ValueError(gettext("الفرع المحدد غير موجود."))
    if tid is not None and int(branch.tenant_id) != int(tid):
        raise ValueError(gettext("الفرع لا ينتمي إلى شركتك النشطة."))
    if scoped_branch_id is not None and int(branch_id) != int(scoped_branch_id):
        raise ValueError(gettext("لا يمكنك معالجة رواتب فرع آخر."))


@payroll_bp.route("/employees")
@login_required
@permission_required("manage_payroll")
def employees_list():
    tid = get_active_tenant_id(current_user)
    scoped_branch_id = branch_scope_id()
    employees = PayrollService.list_employees(tid, scoped_branch_id)
    return render_template(
        "payroll/employees.html",
        employees=employees,
        show_branch_columns=should_show_all_branch_columns(current_user),
    )


@payroll_bp.route("/employees/add", methods=["GET", "POST"])
@login_required
@permission_required("manage_payroll")
def add_employee():
    scoped_branch_id = branch_scope_id()
    if request.method == "POST":
        try:
            if not request.form.get("name"):
                raise ValueError(gettext("اسم الموظف مطلوب."))
            if scoped_branch_id is not None:
                form_branch_id = request.form.get("branch_id", type=int)
                if form_branch_id != scoped_branch_id:
                    flash(gettext("لا يمكنك ربط الموظف إلا بفرعك الحالي."), "danger")
                    tid = get_active_tenant_id(current_user)
                    branches = PayrollService.list_branches_at_scope(tid, scoped_branch_id)
                    return render_template("payroll/add_employee.html", branches=branches)
            with atomic_transaction("payroll_add_employee"):
                PayrollService.create_employee(request.form)
            flash(gettext("تم إضافة الموظف بنجاح"), "success")
            return redirect(url_for("payroll.employees_list"))
        except Exception as e:
            flash(gettext(f"حدث خطأ: {e}"), "danger")

    tid = get_active_tenant_id(current_user)
    branches = PayrollService.list_branch_options(tid, scoped_branch_id)
    return render_template("payroll/add_employee.html", branches=branches)


@payroll_bp.route("/advances", methods=["GET", "POST"])
@login_required
@permission_required("manage_payroll")
def advances():
    if request.method == "POST":
        try:
            scoped_branch_id = branch_scope_id()
            tid = get_active_tenant_id(current_user)
            employee_id_str = request.form.get("employee_id")
            if not employee_id_str:
                raise ValueError(gettext("معرف الموظف مطلوب."))
            employee_id = int(employee_id_str)
            amount_str = request.form.get("amount")
            if not amount_str:
                raise ValueError(gettext("المبلغ مطلوب."))
            amount = float(amount_str)
            employee = db.session.get(Employee, employee_id)
            _assert_employee_scope(employee, scoped_branch_id, tid)
            with atomic_transaction("payroll_create_advance"):
                PayrollService.create_advance(
                    employee_id=employee_id,
                    amount=amount,
                    description=request.form.get("description"),
                    user_id=current_user.id,
                    actor_user=current_user,
                )
            flash(gettext("تم تسجيل السلفة بنجاح"), "success")
        except ValueError as e:
            flash(gettext(f"خطأ في البيانات: {e}"), "danger")
        except Exception as e:
            flash(gettext(f"حدث خطأ: {e}"), "danger")

    scoped_branch_id = branch_scope_id()
    tid = get_active_tenant_id(current_user)
    employees, advance_list = PayrollService.advance_page_data(tid, scoped_branch_id)
    return render_template("payroll/advances.html", advances=advance_list, employees=employees)


@payroll_bp.route("/process", methods=["GET", "POST"])
@login_required
@permission_required("manage_payroll")
def process_payroll():
    scoped_branch_id = branch_scope_id()
    if request.method == "POST":
        if "generate_branch" in request.form:
            try:
                branch_id_str = request.form.get("branch_id")
                if not branch_id_str:
                    raise ValueError(gettext("معرف الفرع مطلوب."))
                branch_id = int(branch_id_str)
                tid = get_active_tenant_id(current_user)
                _assert_branch_scope(branch_id, scoped_branch_id, tid)
                month_str = request.form.get("month")
                year_str = request.form.get("year")
                if not month_str or not year_str:
                    raise ValueError(gettext("الشهر والسنة مطلوبان."))
                month = int(month_str)
                year = int(year_str)
                with atomic_transaction("payroll_generate_branch"):
                    gen, skipped = PayrollService.generate_branch_payroll(branch_id, month, year, current_user.id)
                flash(
                    gettext(
                        f"تم توليد الرواتب بنجاح: {gen} موظف، وتم تخطي {skipped} (تمت معالجتهم سابقاً أو نظام مياومة)"
                    ),
                    "success",
                )
            except ValueError as e:
                flash(gettext(f"خطأ في البيانات: {e}"), "danger")
            except Exception as e:
                flash(gettext(f"حدث خطأ: {e}"), "danger")
        else:
            try:
                employee_id_str = request.form.get("employee_id")
                if not employee_id_str:
                    raise ValueError(gettext("معرف الموظف مطلوب."))
                employee_id = int(employee_id_str)
                tid = get_active_tenant_id(current_user)
                employee = db.session.get(Employee, employee_id)
                _assert_employee_scope(employee, scoped_branch_id, tid)
                with atomic_transaction("payroll_process"):
                    PayrollService.process_payroll(
                        employee_id=employee_id,
                        month=int(request.form.get("month") or 0),
                        year=int(request.form.get("year") or 0),
                        days_worked=float(request.form.get("days_worked", 0)),
                        allowances=float(request.form.get("allowances", 0)),
                        deductions=float(request.form.get("deductions", 0)),
                        user_id=current_user.id,
                        actor_user=current_user,
                    )
                flash(gettext("تم صرف الراتب بنجاح"), "success")
            except ValueError as e:
                flash(gettext(f"خطأ في البيانات: {e}"), "danger")
            except Exception as e:
                flash(gettext(f"حدث خطأ: {e}"), "danger")

    tid = get_active_tenant_id(current_user)
    employees, branches, transactions = PayrollService.process_page_data(tid, scoped_branch_id)
    today = datetime.now()
    return render_template(
        "payroll/process.html",
        transactions=transactions,
        employees=employees,
        branches=branches,
        today=today,
    )


@payroll_bp.route("/slip/<int:id>")
@login_required
@permission_required("manage_payroll")
def salary_slip(**kwargs):
    record_id = kwargs.pop("id")
    tid = get_active_tenant_id(current_user)
    transaction = PayrollService.get_transaction_or_404(record_id, tid)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and transaction.branch_id != scoped_branch_id:
        return render_template("errors/403.html"), 403

    from services.print_service import PrintService

    ctx = PrintService._get_tenant_context(transaction.tenant_id or tid)
    ctx.update(PrintService._user_context())
    ctx["printed_at"] = datetime.now(UTC)
    return render_template("payroll/slip.html", slip=transaction, **ctx)


@payroll_bp.route("/statement/<int:id>")
@login_required
@permission_required("manage_payroll")
def statement(**kwargs):
    record_id = kwargs.pop("id")
    tid = get_active_tenant_id(current_user)
    employee = PayrollService.get_employee_or_404(record_id, tid)
    scoped_branch_id = branch_scope_id()
    if scoped_branch_id is not None and employee.branch_id != scoped_branch_id:
        return render_template("errors/403.html"), 403
    advance_list, payments = PayrollService.employee_statement_records(record_id, tid)

    history = []
    for a in advance_list:
        history.append(
            {
                "date": a.date,
                "type": gettext("سلفة"),
                "amount": -a.amount,
                "desc": a.description,
            }
        )
        # عند خصم (جزء من) السلفة من راتب لاحق، يظهر الراتب في الكشف
        # بصافيه المخصوم أصلًا — فنضيف قيد سداد موجبًا بالمبلغ المخصوم
        # وإلا احتُسبت السلفة مرتين (سلفة سالبة + راتب منقوص).
        deducted = float(a.deducted_amount or 0)
        if deducted > 0:
            deducted_on = a.fully_deducted_at.date() if a.fully_deducted_at else a.date
            history.append(
                {
                    "date": deducted_on,
                    "type": gettext("سداد سلفة"),
                    "amount": deducted,
                    "desc": gettext("خصم السلفة من الراتب"),
                }
            )
    for p in payments:
        history.append(
            {
                "date": p.payment_date,
                "type": gettext("راتب"),
                "amount": p.net_salary,
                "desc": gettext(f"راتب {p.month}/{p.year}"),
            }
        )

    history.sort(key=lambda x: x["date"])

    return render_template("payroll/statement.html", employee=employee, history=history)
