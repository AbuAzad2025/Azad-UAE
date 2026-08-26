from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext
from flask_login import current_user, login_required

from models import LeaveRequest, LeaveType
from services.hr_service import HRService, LeaveBalanceService, OvertimeService
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id, tenant_get_or_404, tenant_query

hr_bp = Blueprint("hr", __name__, url_prefix="/hr")


@hr_bp.route("/attendance")
@login_required
@permission_required("hr.view")
def attendance():
    filters = {}
    if request.args.get("user_id"):
        filters["user_id"] = request.args["user_id"]
    if request.args.get("date_from"):
        filters["date_from"] = request.args["date_from"]
    if request.args.get("date_to"):
        filters["date_to"] = request.args["date_to"]
    records = HRService.report_attendance(filters, current_user)
    tid = get_active_tenant_id(current_user)
    departments = HRService.list_departments(current_user)
    users = HRService.list_active_users(tid)
    return render_template(
        "hr/attendance.html",
        records=records,
        departments=departments,
        users=users,
    )


@hr_bp.route("/attendance/clock-in", methods=["POST"])
@login_required
@permission_required("hr.view")
def clock_in():
    try:
        branch_id = request.form.get("branch_id")
        att = HRService.clock_in(current_user, branch_id)
        flash(
            gettext(f"تم تسجيل الحضور الساعة {att.check_in.strftime('%H:%M')}"),
            "success",
        )
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("hr.attendance"))


@hr_bp.route("/attendance/clock-out", methods=["POST"])
@login_required
@permission_required("hr.view")
def clock_out():
    try:
        att = HRService.clock_out(current_user)
        flash(gettext(f"تم تسجيل الانصراف. عدد ساعات العمل: {att.work_hours}"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("hr.attendance"))


@hr_bp.route("/leaves")
@login_required
@permission_required("hr.view")
def leaves_list():
    filters = {k: v for k, v in request.args.items() if v}
    leaves = HRService.list_leaves(filters, current_user)
    tid = get_active_tenant_id(current_user)
    leave_types = tenant_query(LeaveType).filter_by(is_active=True).all() if tid else []
    users = HRService.list_active_users(tid)
    return render_template(
        "hr/leave_list.html",
        leaves=leaves,
        leave_types=leave_types,
        users=users,
    )


@hr_bp.route("/leaves/request", methods=["GET", "POST"])
@login_required
@permission_required("hr.view")
def request_leave():
    if request.method == "POST":
        try:
            HRService.request_leave(request.form, current_user)
            flash(gettext("تم تقديم طلب الإجازة"), "success")
            return redirect(url_for("hr.leaves_list"))
        except Exception as e:
            flash(gettext(f"حدث خطأ: {e}"), "danger")
    leave_types = tenant_query(LeaveType).filter_by(is_active=True).all() if get_active_tenant_id(current_user) else []
    return render_template("hr/leave_form.html", leave_types=leave_types)


@hr_bp.route("/leaves/<int:leave_id>/approve", methods=["POST"])
@login_required
@permission_required("hr.manage")
def approve_leave(leave_id):
    tenant_get_or_404(LeaveRequest, leave_id)
    try:
        HRService.approve_leave(leave_id, current_user)
        flash(gettext("تم الموافقة على طلب الإجازة"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("hr.leaves_list"))


@hr_bp.route("/leaves/<int:leave_id>/refuse", methods=["POST"])
@login_required
@permission_required("hr.manage")
def refuse_leave(leave_id):
    tenant_get_or_404(LeaveRequest, leave_id)
    reason = request.form.get("rejected_reason", "")
    try:
        HRService.refuse_leave(leave_id, current_user, reason)
        flash(gettext("تم رفض طلب الإجازة"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("hr.leaves_list"))


@hr_bp.route("/departments")
@login_required
@permission_required("hr.view")
def departments_list():
    departments = HRService.list_departments(current_user)
    return render_template("hr/attendance.html", departments=departments, tab="departments")


@hr_bp.route("/departments/create", methods=["POST"])
@login_required
@permission_required("hr.manage")
def create_department():
    try:
        HRService.create_department(request.form, current_user)
        flash(gettext("تم إنشاء القسم"), "success")
    except (ValueError, KeyError) as e:
        flash(str(e), "danger")
    return redirect(url_for("hr.departments_list"))


@hr_bp.route("/contracts/create", methods=["POST"])
@login_required
@permission_required("hr.manage")
def create_contract():
    try:
        HRService.create_contract(request.form, current_user)
        flash(gettext("تم إنشاء العقد"), "success")
    except (ValueError, KeyError) as e:
        flash(str(e), "danger")
    return redirect(url_for("hr.departments_list"))


# ---------------------------------------------------------------------------
# Leave Balance Ledger
# ---------------------------------------------------------------------------
@hr_bp.route("/leave-ledger")
@login_required
@permission_required("hr:leave_manage")
def leave_ledger():
    tid = get_active_tenant_id(current_user)
    year = request.args.get("year", date.today().year, type=int)
    user_id = request.args.get("user_id", type=int)
    balances = LeaveBalanceService.list_balances(user_id, year, tid) if user_id else []
    users = HRService.list_active_users(tid)
    leave_types = tenant_query(LeaveType).filter_by(is_active=True).all() if tid else []
    return render_template(
        "hr/leave_ledger.html",
        balances=balances,
        users=users,
        leave_types=leave_types,
        selected_year=year,
        selected_user_id=user_id,
    )


@hr_bp.route("/leave-ledger/accrue", methods=["POST"])
@login_required
@permission_required("hr:leave_manage")
def accrue_leave():
    year = request.args.get("year", date.today().year, type=int)
    user_id = request.form.get("user_id", type=int)
    try:
        user_id = int(request.form["user_id"])
        leave_type_id = int(request.form["leave_type_id"])
        days = request.form.get("days", "1")
        year = int(request.args.get("year", date.today().year))
        tid = get_active_tenant_id(current_user)
        LeaveBalanceService.accrue_leave(user_id, leave_type_id, year, float(days), tid)
        flash(gettext("تم احتساب أيام الإجازة"), "success")
    except (ValueError, KeyError) as e:
        flash(str(e), "danger")
    if user_id is not None:
        return redirect(url_for("hr.leave_ledger", user_id=user_id, year=year))
    return redirect(url_for("hr.leave_ledger", year=year))


@hr_bp.route("/leave-ledger/carry-forward", methods=["POST"])
@login_required
@permission_required("hr:leave_manage")
def carry_forward_leave():
    try:
        user_id = int(request.form["user_id"])
        leave_type_id = int(request.form["leave_type_id"])
        from_year = int(request.form["from_year"])
        tid = get_active_tenant_id(current_user)
        LeaveBalanceService.carry_forward_leave(user_id, leave_type_id, from_year, tid)
        flash(gettext("تم تحويل الرصيد إلى السنة الجديدة"), "success")
    except (ValueError, KeyError) as e:
        flash(str(e), "danger")
    return redirect(url_for("hr.leave_ledger"))


# ---------------------------------------------------------------------------
# Overtime Management
# ---------------------------------------------------------------------------
@hr_bp.route("/overtime")
@login_required
@permission_required("hr:manage")
def overtime_list():
    filters = {k: v for k, v in request.args.items() if v}
    entries = OvertimeService.list_entries(current_user, filters)
    tid = get_active_tenant_id(current_user)
    users = HRService.list_active_users(tid)
    return render_template("hr/overtime.html", entries=entries, users=users)


@hr_bp.route("/overtime/create", methods=["POST"])
@login_required
@permission_required("hr:manage")
def create_overtime():
    try:
        data = {
            "user_id": request.form["user_id"],
            "branch_id": request.form.get("branch_id"),
            "overtime_date": request.form["overtime_date"],
            "hours": request.form["hours"],
            "rate_multiplier": request.form.get("rate_multiplier", "1.0"),
            "overtime_type": request.form.get("overtime_type", "standard"),
            "notes": request.form.get("notes"),
        }
        OvertimeService.create_entry(data, current_user)
        flash(gettext("تم إنشاء سجل العمل الإضافي"), "success")
    except (ValueError, KeyError) as e:
        flash(str(e), "danger")
    return redirect(url_for("hr.overtime_list"))


@hr_bp.route("/overtime/<int:entry_id>/approve", methods=["POST"])
@login_required
@permission_required("hr:manage")
def approve_overtime(entry_id):
    from models import OvertimeEntry

    entry = tenant_get_or_404(OvertimeEntry, entry_id)
    try:
        OvertimeService.approve_entry(entry, current_user)
        flash(gettext("تمت الموافقة على العمل الإضافي"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("hr.overtime_list"))


@hr_bp.route("/overtime/<int:entry_id>/reject", methods=["POST"])
@login_required
@permission_required("hr:manage")
def reject_overtime(entry_id):
    from models import OvertimeEntry

    entry = tenant_get_or_404(OvertimeEntry, entry_id)
    reason = request.form.get("reason", "")
    try:
        OvertimeService.reject_entry(entry, current_user, reason)
        flash(gettext("تم رفض العمل الإضافي"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("hr.overtime_list"))
