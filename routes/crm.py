from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import CRMStage, CRMTeam, Customer, User
from services.crm_lead_service import CRMLeadService
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id

crm_bp = Blueprint('crm', __name__, url_prefix='/crm')


def _tenant_stages(tid):
    q = CRMStage.query.filter(CRMStage.is_active == True)
    if tid is not None:
        q = q.filter(CRMStage.tenant_id == tid)
    return q.order_by(CRMStage.sequence).all()


def _tenant_teams(tid):
    q = CRMTeam.query.filter(CRMTeam.is_active == True)
    if tid is not None:
        q = q.filter(CRMTeam.tenant_id == tid)
    return q.all()


def _tenant_customers(tid):
    q = Customer.query.filter(Customer.is_active == True)
    if tid is not None:
        q = q.filter(Customer.tenant_id == tid)
    return q.order_by(Customer.name).all()


@crm_bp.route('/pipeline')
@login_required
@permission_required('crm.view')
def pipeline():
    tid = get_active_tenant_id(current_user)
    stages = _tenant_stages(tid)
    leads = CRMLeadService.search_leads({}, current_user)
    teams = CRMTeam.query.filter_by(tenant_id=tid).all() if tid else []
    users = User.query.filter(User.tenant_id == tid, User.is_active == True).order_by(User.full_name).all()
    return render_template(
        'crm/pipeline.html',
        stages=stages,
        leads=leads,
        teams=teams,
        users=users,
    )


@crm_bp.route('/leads')
@login_required
@permission_required('crm.view')
def leads_list():
    leads = CRMLeadService.search_leads(dict(request.args), current_user)
    tid = get_active_tenant_id(current_user)
    stages = _tenant_stages(tid)
    return render_template(
        'crm/leads_list.html',
        leads=leads,
        stages=stages,
    )


@crm_bp.route('/leads/create', methods=['GET', 'POST'])
@login_required
@permission_required('crm.manage')
def create_lead():
    if request.method == 'POST':
        try:
            CRMLeadService.create_lead(request.form, current_user)
            flash('تم إنشاء العميل المتوقع بنجاح', 'success')
            return redirect(url_for('crm.leads_list'))
        except Exception as e:
            flash(f'حدث خطأ: {e}', 'danger')
    tid = get_active_tenant_id(current_user)
    stages = _tenant_stages(tid)
    customers = _tenant_customers(tid)
    users = User.query.filter(User.tenant_id == tid, User.is_active == True).order_by(User.full_name).all() if tid else []
    teams = _tenant_teams(tid)
    return render_template(
        'crm/lead_form.html',
        stages=stages,
        customers=customers,
        users=users,
        teams=teams,
    )


@crm_bp.route('/leads/<int:lead_id>')
@login_required
@permission_required('crm.view')
def lead_detail(lead_id):
    try:
        lead = CRMLeadService.get_lead(lead_id, current_user)
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('crm.leads_list'))
    tid = get_active_tenant_id(current_user)
    stages = _tenant_stages(tid)
    users = User.query.filter(User.tenant_id == tid, User.is_active == True).all() if tid else []
    return render_template('crm/lead_form.html', lead=lead, stages=stages, users=users, view=True)


@crm_bp.route('/leads/<int:lead_id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('crm.manage')
def edit_lead(lead_id):
    try:
        lead = CRMLeadService.get_lead(lead_id, current_user)
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('crm.leads_list'))
    if request.method == 'POST':
        try:
            CRMLeadService.update_lead(lead_id, request.form, current_user)
            flash('تم تحديث العميل المتوقع بنجاح', 'success')
            return redirect(url_for('crm.leads_list'))
        except Exception as e:
            flash(f'حدث خطأ: {e}', 'danger')
    tid = get_active_tenant_id(current_user)
    stages = _tenant_stages(tid)
    customers = _tenant_customers(tid)
    users = User.query.filter(User.tenant_id == tid, User.is_active == True).all() if tid else []
    teams = _tenant_teams(tid)
    return render_template(
        'crm/lead_form.html',
        lead=lead,
        stages=stages,
        customers=customers,
        users=users,
        teams=teams,
    )


@crm_bp.route('/api/move-stage', methods=['POST'])
@login_required
@permission_required('crm.manage')
def api_move_stage():
    data = request.get_json(silent=True) or {}
    try:
        CRMLeadService.move_stage(data['lead_id'], data['stage_id'], current_user)
        return jsonify({'success': True})
    except (ValueError, KeyError) as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/api/stats')
@login_required
@permission_required('crm.view')
def api_stats():
    stats = CRMLeadService.get_pipeline_stats(current_user)
    return jsonify(stats)


@crm_bp.route('/api/activities', methods=['POST'])
@login_required
@permission_required('crm.manage')
def api_add_activity():
    data = request.get_json(silent=True) or {}
    try:
        CRMLeadService.add_activity(data['lead_id'], data, current_user)
        return jsonify({'success': True})
    except (ValueError, KeyError) as e:
        return jsonify({'success': False, 'error': str(e)}), 400
