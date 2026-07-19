from flask_babel import gettext
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import TaskStage, Task, ProjectMember, Customer, User
from services.project_service import ProjectService
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id, tenant_query

projects_bp = Blueprint("projects", __name__, url_prefix="/projects")


@projects_bp.route("/")
@login_required
@permission_required("project.view")
def list_projects():
    projects = ProjectService.list_projects(current_user)
    return render_template("projects/list.html", projects=projects)


@projects_bp.route("/create", methods=["GET", "POST"])
@login_required
@permission_required("project.manage")
def create_project():
    if request.method == "POST":
        try:
            ProjectService.create_project(request.form, current_user)
            flash(gettext("تم إنشاء المشروع بنجاح"), "success")
            return redirect(url_for("projects.list_projects"))
        except Exception as e:
            flash(gettext(f"حدث خطأ: {e}"), "danger")
    customers = (
        tenant_query(Customer).filter_by(is_active=True).order_by(Customer.name).all()
    )
    return render_template("projects/task_form.html", customers=customers)


@projects_bp.route("/<int:project_id>")
@login_required
@permission_required("project.view")
def project_detail(project_id):
    try:
        project = ProjectService.get_project(project_id, current_user)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("projects.list_projects"))
    stages = (
        TaskStage.query.filter_by(project_id=project.id)
        .order_by(TaskStage.sequence)
        .all()
    )
    tasks = (
        Task.query.filter_by(project_id=project.id, is_active=True)
        .order_by(Task.sort_order)
        .all()
    )
    tid = get_active_tenant_id(current_user)
    members = ProjectMember.query.filter_by(project_id=project.id).all()
    users = (
        User.query.filter(User.tenant_id == tid, User.is_active)
        .order_by(User.full_name)
        .all()
        if tid
        else []
    )
    return render_template(
        "projects/detail.html",
        project=project,
        stages=stages,
        tasks=tasks,
        members=members,
        users=users,
    )


@projects_bp.route("/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("project.manage")
def edit_project(project_id):
    try:
        project = ProjectService.get_project(project_id, current_user)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("projects.list_projects"))
    if request.method == "POST":
        try:
            ProjectService.update_project(project_id, request.form, current_user)
            flash(gettext("تم تحديث المشروع"), "success")
            return redirect(url_for("projects.project_detail", project_id=project_id))
        except Exception as e:
            flash(gettext(f"حدث خطأ: {e}"), "danger")
    customers = tenant_query(Customer).filter_by(is_active=True).all()
    return render_template(
        "projects/task_form.html", project=project, customers=customers
    )


@projects_bp.route("/<int:project_id>/tasks", methods=["POST"])
@login_required
@permission_required("project.manage")
def add_task(project_id):
    try:
        ProjectService.create_task(project_id, request.form, current_user)
        flash(gettext("تم إنشاء المهمة"), "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("projects.project_detail", project_id=project_id))


@projects_bp.route("/api/move-task", methods=["POST"])
@login_required
@permission_required("project.manage")
def api_move_task():
    data = request.get_json(silent=True) or {}
    try:
        ProjectService.move_task(data["task_id"], data["stage_id"], current_user)
        return jsonify({"success": True})
    except (ValueError, KeyError) as e:
        return jsonify({"success": False, "error": str(e)}), 400


@projects_bp.route("/api/log-timesheet", methods=["POST"])
@login_required
@permission_required("project.manage")
def api_log_timesheet():
    data = request.get_json(silent=True) or {}
    try:
        ts = ProjectService.log_timesheet(data["task_id"], data, current_user)
        return jsonify({"success": True, "id": ts.id, "hours": float(ts.hours)})
    except (ValueError, KeyError) as e:
        return jsonify({"success": False, "error": str(e)}), 400


@projects_bp.route("/<int:project_id>/gantt")
@login_required
@permission_required("project.view")
def api_gantt(project_id):
    try:
        data = ProjectService.get_gantt_data(project_id, current_user)
        return jsonify(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@projects_bp.route("/<int:project_id>/members", methods=["POST"])
@login_required
@permission_required("project.manage")
def add_member(project_id):
    try:
        ProjectService.add_member(
            project_id,
            request.form["user_id"],
            request.form.get("role", "member"),
            current_user,
        )
        flash(gettext("تم إضافة العضو"), "success")
    except (ValueError, KeyError) as e:
        flash(str(e), "danger")
    return redirect(url_for("projects.project_detail", project_id=project_id))
