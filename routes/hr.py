from flask_babel import gettext
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import LeaveRequest, LeaveType, User
from services.hr_service import HRService
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
    users = User.query.filter(User.tenant_id == tid, User.is_active).order_by(User.full_name).all() if tid else []
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
    users = User.query.filter(User.tenant_id == tid, User.is_active).order_by(User.full_name).all() if tid else []
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
