from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Campaign, WarrantyClaim, Shipment
from utils.decorators import permission_required
from utils.tenanting import get_active_tenant_id
from services.logging_core import LoggingCore
from utils.db_safety import atomic_transaction

uinv_bp = Blueprint('unified_inventory', __name__, url_prefix='/uinv')


@uinv_bp.route('/campaigns')
@login_required
@permission_required('manage_products')
def campaigns_index():
    tid = get_active_tenant_id(current_user)
    if tid:
        campaigns = Campaign.query.filter_by(tenant_id=tid, is_active=True).order_by(Campaign.created_at.desc()).all()
    else:
        campaigns = []
    return render_template('unified_inventory/campaigns.html', campaigns=campaigns)


@uinv_bp.route('/campaigns', methods=['POST'])
@login_required
@permission_required('manage_products')
def campaigns_create():
    tid = get_active_tenant_id(current_user)
    if not tid:
        flash('No active tenant.', 'warning')
        return redirect(url_for('unified_inventory.campaigns_index'))
    try:
        c = Campaign(
            tenant_id=tid,
            name=request.form.get('name'),
            campaign_type=request.form.get('campaign_type', 'percentage'),
            coupon_code=request.form.get('coupon_code'),
            discount_value=float(request.form.get('discount_value', 0)),
            min_order_amount=float(request.form.get('min_order_amount', 0)),
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True,
        )
        with atomic_transaction('campaign_create'):
            db.session.add(c)
            LoggingCore.log_audit('create', 'campaigns', c.id)
        flash('Campaign created.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('unified_inventory.campaigns_index'))


@uinv_bp.route('/warranty')
@login_required
@permission_required('manage_products')
def warranty_index():
    tid = get_active_tenant_id(current_user)
    if tid:
        claims = WarrantyClaim.query.filter_by(tenant_id=tid).order_by(WarrantyClaim.claim_date.desc()).all()
    else:
        claims = []
    return render_template('unified_inventory/warranty.html', claims=claims)


@uinv_bp.route('/warranty', methods=['POST'])
@login_required
@permission_required('manage_products')
def warranty_create():
    tid = get_active_tenant_id(current_user)
    if not tid:
        flash('No active tenant.', 'warning')
        return redirect(url_for('unified_inventory.warranty_index'))
    try:
        claim = WarrantyClaim(
            tenant_id=tid,
            sale_id=int(request.form.get('sale_id')),
            sale_line_id=int(request.form.get('sale_line_id') or 0) or None,
            product_id=int(request.form.get('product_id')),
            claim_type=request.form.get('claim_type', 'repair'),
            description=request.form.get('description'),
            status='open',
        )
        with atomic_transaction('warranty_claim_create'):
            db.session.add(claim)
            LoggingCore.log_audit('create', 'warranty_claims', claim.id)
        flash('Warranty claim created.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('unified_inventory.warranty_index'))


@uinv_bp.route('/shipments')
@login_required
@permission_required('manage_warehouse')
def shipments_index():
    tid = get_active_tenant_id(current_user)
    if tid:
        shipments = Shipment.query.filter_by(tenant_id=tid).order_by(Shipment.created_at.desc()).all()
    else:
        shipments = []
    return render_template('unified_inventory/shipments.html', shipments=shipments)


@uinv_bp.route('/shipments', methods=['POST'])
@login_required
@permission_required('manage_warehouse')
def shipments_create():
    tid = get_active_tenant_id(current_user)
    if not tid:
        flash('No active tenant.', 'warning')
        return redirect(url_for('unified_inventory.shipments_index'))
    try:
        s = Shipment(
            tenant_id=tid,
            carrier_name=request.form.get('carrier_name'),
            tracking_number=request.form.get('tracking_number'),
            source_type='sale',
            source_id=int(request.form.get('source_id')),
            shipping_cost=float(request.form.get('shipping_cost', 0)),
            customs_duty=float(request.form.get('customs_duty', 0)),
            insurance=float(request.form.get('insurance', 0)),
            status='pending',
        )
        with atomic_transaction('shipment_create'):
            db.session.add(s)
            LoggingCore.log_audit('create', 'shipments', s.id)
        flash('Shipment created.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('unified_inventory.shipments_index'))
