from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_babel import gettext
from flask_login import current_user, login_required

from services.crm_lead_service import CRMLeadService
from utils.api_response import error_response, success_response
from utils.db_safety import atomic_transaction
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id

crm_bp = Blueprint("crm", __name__, url_prefix="/crm")


@crm_bp.route("/pipeline")
@login_required
@permission_required("crm.view")
def pipeline():
    tid = get_active_tenant_id(current_user)
    stages = CRMLeadService.tenant_stages(tid)
    leads = CRMLeadService.search_leads({}, current_user)
    teams = CRMLeadService.teams_for_tenant(tid)
    users = CRMLeadService.tenant_users_ordered(tid)
    return render_template(
        "crm/pipeline.html",
        stages=stages,
        leads=leads,
        teams=teams,
        users=users,
    )


@crm_bp.route("/leads")
@login_required
@permission_required("crm.view")
def leads_list():
    leads = CRMLeadService.search_leads(dict(request.args), current_user)
    tid = get_active_tenant_id(current_user)
    stages = CRMLeadService.tenant_stages(tid)
    return render_template(
        "crm/leads_list.html",
        leads=leads,
        stages=stages,
    )


@crm_bp.route("/leads/create", methods=["GET", "POST"])
@login_required
@permission_required("crm.manage")
def create_lead():
    if request.method == "POST":
        try:
            with atomic_transaction("crm_create_lead"):
                CRMLeadService.create_lead(request.form, current_user)
            flash(gettext("تم إنشاء العميل المتوقع بنجاح"), "success")
            return redirect(url_for("crm.leads_list"))
        except Exception as e:
            flash(gettext(f"حدث خطأ: {e}"), "danger")
    tid = get_active_tenant_id(current_user)
    stages = CRMLeadService.tenant_stages(tid)
    customers = CRMLeadService.tenant_customers(tid)
    users = CRMLeadService.tenant_users_ordered(tid) if tid else []
    teams = CRMLeadService.tenant_teams(tid)
    return render_template(
        "crm/lead_form.html",
        stages=stages,
        customers=customers,
        users=users,
        teams=teams,
    )


@crm_bp.route("/leads/<int:lead_id>")
@login_required
@permission_required("crm.view")
def lead_detail(lead_id):
    try:
        lead = CRMLeadService.get_lead(lead_id, current_user)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("crm.leads_list"))
    tid = get_active_tenant_id(current_user)
    stages = CRMLeadService.tenant_stages(tid)
    users = CRMLeadService.tenant_users(tid)
    return render_template("crm/lead_form.html", lead=lead, stages=stages, users=users, view=True)


@crm_bp.route("/leads/<int:lead_id>/edit", methods=["GET", "POST"])
@login_required
@permission_required("crm.manage")
def edit_lead(lead_id):
    try:
        lead = CRMLeadService.get_lead(lead_id, current_user)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("crm.leads_list"))
    if request.method == "POST":
        try:
            with atomic_transaction("crm_update_lead"):
                CRMLeadService.update_lead(lead_id, request.form, current_user)
            flash(gettext("تم تحديث العميل المتوقع بنجاح"), "success")
            return redirect(url_for("crm.leads_list"))
        except Exception as e:
            flash(gettext(f"حدث خطأ: {e}"), "danger")
    tid = get_active_tenant_id(current_user)
    stages = CRMLeadService.tenant_stages(tid)
    customers = CRMLeadService.tenant_customers(tid)
    users = CRMLeadService.tenant_users(tid)
    teams = CRMLeadService.tenant_teams(tid)
    return render_template(
        "crm/lead_form.html",
        lead=lead,
        stages=stages,
        customers=customers,
        users=users,
        teams=teams,
    )


@crm_bp.route("/api/move-stage", methods=["POST"])
@login_required
@permission_required("crm.manage")
def api_move_stage():
    data = request.get_json(silent=True) or {}
    try:
        with atomic_transaction("crm_move_stage"):
            CRMLeadService.move_stage(data["lead_id"], data["stage_id"], current_user)
        return success_response()
    except (ValueError, KeyError) as e:
        return error_response(message=str(e), status_code=400)


@crm_bp.route("/api/stats")
@login_required
@permission_required("crm.view")
def api_stats():
    stats = CRMLeadService.get_pipeline_stats(current_user)
    return success_response(data=stats)


@crm_bp.route("/api/activities", methods=["POST"])
@login_required
@permission_required("crm.manage")
def api_add_activity():
    data = request.get_json(silent=True) or {}
    try:
        with atomic_transaction("crm_add_activity"):
            CRMLeadService.add_activity(data["lead_id"], data, current_user)
        return success_response()
    except (ValueError, KeyError) as e:
        return error_response(message=str(e), status_code=400)
