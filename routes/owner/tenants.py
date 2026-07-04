"""Tenant management routes for the owner blueprint."""

from routes.owner import (
    render_template, request, jsonify, flash, redirect, url_for, current_app, abort,
    login_required, current_user, func, desc, db,
    Tenant, User, SystemSettings,
    owner_required, get_active_tenant_id, get_system_default_currency,
    get_tenant_ai_level, set_tenant_ai_level,
)
from services.logging_core import LoggingCore
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Import the shared owner_bp blueprint and helpers from the package
from routes.owner import owner_bp
from routes.owner.shared import _invalidate_owner_changes, _owner_branch_scope, _audit_owner_db_action

@owner_bp.route('/tenant-stores')
@owner_required
def tenant_stores():
    """التحكم الهرمي بمتاجر التينانتس — قفل/فك قفل من مالك المنصة."""
    from models.tenant_store import TenantStore
    from models.tenant import Tenant
    from services.store_service import StoreService

    stores = (
        db.session.query(TenantStore, Tenant)
        .join(Tenant, Tenant.id == TenantStore.tenant_id)
        .order_by(Tenant.name.asc())
        .all()
    )
    rows = []
    for store, tenant in stores:
        rows.append({
            'store': store,
            'tenant': tenant,
            'is_enabled': store.is_enabled,
            'platform_disabled': store.platform_disabled,
            'public_available': StoreService.is_store_publicly_available(store),
        })
    return render_template(
        'owner/tenant_stores.html',
        rows=rows,
        global_enabled=StoreService.stores_globally_enabled(),
    )

@owner_bp.route('/tenant-ai')
@owner_required
def tenant_ai():
    """Platform-level per-tenant AI visibility toggle."""
    tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name.asc()).all()
    tenant_ai_levels = {int(t.id): get_tenant_ai_level(int(t.id), default='execute') for t in tenants}
    return render_template('owner/tenant_ai.html', tenants=tenants, tenant_ai_levels=tenant_ai_levels)

@owner_bp.route('/tenant-ai/<int:tenant_id>/toggle', methods=['POST'])
@owner_required
def tenant_ai_toggle(tenant_id):
    tenant = db.session.get(Tenant, int(tenant_id))
    if not tenant:
        flash('التينانت غير موجود.', 'warning')
        return redirect(url_for('owner.tenant_ai'))

    enabled = request.form.get('enable_ai') == '1'
    ai_access_level = (request.form.get('ai_access_level') or get_tenant_ai_level(int(tenant.id), default='execute')).strip().lower()
    if ai_access_level not in ('basic', 'advanced', 'execute'):
        ai_access_level = 'execute'
    try:
        tenant.enable_ai = enabled
        ai_access_level = set_tenant_ai_level(int(tenant.id), ai_access_level)
        db.session.commit()
        LoggingCore.log_audit(
            'platform_tenant_ai_enable' if enabled else 'platform_tenant_ai_disable',
            'tenants',
            tenant.id,
            {'tenant_name': tenant.name, 'enabled': enabled, 'ai_access_level': ai_access_level},
        )
        _invalidate_owner_changes()
        flash(
            f"تم {'تفعيل' if enabled else 'إيقاف'} المساعد الذكي للتينانت: {tenant.name_ar or tenant.name}",
            'success',
        )
    except Exception as exc:
        db.session.rollback()
        flash(f'تعذر تحديث إعداد AI: {exc}', 'danger')
    return redirect(url_for('owner.tenant_ai'))

@owner_bp.route('/tenant-stores/<int:store_id>/platform-toggle', methods=['POST'])
@owner_required
def tenant_store_platform_toggle(store_id):
    """قفل (force-OFF) أو فك قفل متجر تينانت من مالك المنصة."""
    from models.tenant_store import TenantStore
    from services.store_service import StoreService

    store = db.session.get(TenantStore, int(store_id))
    if not store:
        flash('المتجر غير موجود.', 'warning')
        return redirect(url_for('owner.tenant_stores'))

    disabled = request.form.get('platform_disabled') == '1'
    try:
        StoreService.set_platform_disabled(store, disabled)
        LoggingCore.log_audit(
            'platform_store_lock' if disabled else 'platform_store_unlock',
            'tenant_stores',
            store.id,
        )
        _invalidate_owner_changes()
        flash(
            'تم تعطيل المتجر من مستوى المنصة. لا يستطيع مالك التينانت تفعيله.' if disabled
            else 'تم فك القفل. أصبح التحكم بيد مالك التينانت.',
            'success',
        )
    except Exception as exc:
        db.session.rollback()
        flash(f'تعذر تحديث حالة المتجر: {exc}', 'danger')
    return redirect(url_for('owner.tenant_stores'))

@owner_bp.route('/tenants')
@owner_required
def tenants_list():
    from services.tenant_service import TenantService
    context = TenantService.get_tenants_list_context()
    return render_template(
        'owner/tenants_list.html',
        tenants=context['tenants'],
        user_counts=context['user_counts'],
        branch_counts=context['branch_counts'],
        store_counts=context['store_counts'],
    )

@owner_bp.route('/tenants/create', methods=['GET', 'POST'])
@owner_required
def tenant_create():
    """Create a new tenant from the owner panel."""
    if request.method == 'POST':
        try:
            name_ar = request.form.get('name_ar', '').strip()
            name_en = request.form.get('name_en', '').strip() or name_ar
            slug = request.form.get('slug', '').strip()
            if not name_ar or not slug:
                flash('الاسم العربي والـ Slug مطلوبان.', 'danger')
                return redirect(url_for('owner.tenant_create'))
            default_currency = request.form.get('default_currency', '').strip().upper()
            if not default_currency:
                flash('يجب اختيار العملة الافتراضية للتينانت.', 'danger')
                return redirect(url_for('owner.tenant_create'))
            if Tenant.query.filter_by(slug=slug).first():
                flash('الـ Slug مستخدم مسبقاً.', 'danger')
                return redirect(url_for('owner.tenant_create'))
            tenant = Tenant(
                name=name_ar,
                name_ar=name_ar,
                name_en=name_en,
                slug=slug,
                business_type=request.form.get('business_type', 'general').strip(),
                phone_1=request.form.get('phone_1', '').strip() or None,
                phone_2=request.form.get('phone_2', '').strip() or None,
                email=request.form.get('email', '').strip() or None,
                address_ar=request.form.get('address_ar', '').strip() or None,
                default_currency=default_currency,
                max_users=int(request.form.get('max_users', 5)),
                max_products=int(request.form.get('max_products', 1000)),
                max_customers=int(request.form.get('max_customers', 500)),
                max_suppliers=int(request.form.get('max_suppliers', 200)),
                max_branches=int(request.form.get('max_branches', 3)),
                max_warehouses=int(request.form.get('max_warehouses', 2)),
                max_invoices_per_month=int(request.form.get('max_invoices_per_month', 1000)),
                max_sales_per_month=int(request.form.get('max_sales_per_month', 5000)),
                data_retention_days=int(request.form.get('data_retention_days', 365)),
                enable_pos=request.form.get('enable_pos') == 'on',
                enable_payroll=request.form.get('enable_payroll') == 'on',
                enable_cheques=request.form.get('enable_cheques') == 'on',
                enable_expenses=request.form.get('enable_expenses') == 'on',
                enable_store=request.form.get('enable_store') == 'on',
                allow_data_export=request.form.get('allow_data_export') == 'on',
                allow_custom_integrations=request.form.get('allow_custom_integrations') == 'on',
                is_active=True,
                is_suspended=False,
            )
            db.session.add(tenant)
            db.session.commit()
            from services.gl_service import GLService
            from utils.db_safety import atomic_transaction
            with atomic_transaction('tenant_gl_setup'):
                GLService.ensure_core_accounts(tenant_id=tenant.id, cleanup_extra=False)
                # Explicitly ensure GL concept -> account mappings exist.
                # This guarantees that OPENING_BALANCE_EQUITY->3130 (and all
                # other required mappings) are persisted immediately, preventing
                # failures when products are later created with opening balances.
                GLService.ensure_gl_mappings(tenant_id=tenant.id)
            _invalidate_owner_changes()
            _audit_owner_db_action('tenant_create', {'tenant_id': tenant.id, 'slug': slug})
            flash(f'تم إنشاء التينانت "{tenant.name_ar}" بنجاح.', 'success')
            return redirect(url_for('owner.tenants_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في إنشاء التينانت: {str(e)}', 'danger')
    return render_template('owner/tenant_create.html')

@owner_bp.route('/tenants/<int:tenant_id>/suspend', methods=['POST'])
@owner_required
def tenant_suspend(tenant_id):
    """Suspend a tenant (soft-disable all operations)."""
    tenant = Tenant.query.get_or_404(tenant_id)
    reason = request.form.get('reason', '').strip()

    # Protect default tenant (id==1) from suspension
    if tenant.id == 1:
        flash('⚠️ لا يمكن تعليق التينانت الرئيسي.', 'danger')
        return redirect(url_for('owner.tenants_list'))

    tenant.is_active = False
    tenant.is_suspended = True
    tenant.suspension_reason = reason or 'Suspended by owner'
    tenant.updated_at = datetime.now(timezone.utc)

    db.session.commit()
    _invalidate_owner_changes()
    _audit_owner_db_action('tenant_suspend', {'tenant_id': tenant_id, 'reason': reason})
    flash(f'تم تعليق التينانت "{tenant.name_ar or tenant.name}" بنجاح.', 'success')
    return redirect(url_for('owner.tenants_list'))

@owner_bp.route('/tenants/<int:tenant_id>/activate', methods=['POST'])
@owner_required
def tenant_activate(tenant_id):
    """Re-activate a suspended tenant."""
    tenant = Tenant.query.get_or_404(tenant_id)

    tenant.is_active = True
    tenant.is_suspended = False
    tenant.suspension_reason = None
    tenant.updated_at = datetime.now(timezone.utc)

    db.session.commit()
    _invalidate_owner_changes()
    _audit_owner_db_action('tenant_activate', {'tenant_id': tenant_id})
    flash(f'تم تفعيل التينانت "{tenant.name_ar or tenant.name}" بنجاح.', 'success')
    return redirect(url_for('owner.tenants_list'))

@owner_bp.route('/tenants/<int:tenant_id>/edit', methods=['GET', 'POST'])
@owner_required
def tenant_edit(tenant_id):
    """Edit tenant core settings."""
    tenant = Tenant.query.get_or_404(tenant_id)

    if request.method == 'POST':
        try:
            tenant.name = request.form.get('name_ar', tenant.name).strip()
            tenant.name_ar = request.form.get('name_ar', tenant.name_ar).strip()
            tenant.name_en = request.form.get('name_en', tenant.name_en).strip()
            tenant.slug = request.form.get('slug', tenant.slug).strip()
            tenant.business_type = request.form.get('business_type', tenant.business_type).strip()
            tenant.phone_1 = request.form.get('phone_1', tenant.phone_1).strip() or None
            tenant.phone_2 = request.form.get('phone_2', tenant.phone_2).strip() or None
            tenant.email = request.form.get('email', tenant.email).strip() or None
            tenant.address_ar = request.form.get('address_ar', tenant.address_ar).strip() or None
            tenant.default_currency = request.form.get('default_currency', tenant.default_currency).strip() or get_system_default_currency()
            tenant.max_users = int(request.form.get('max_users', tenant.max_users or 5))
            tenant.max_products = int(request.form.get('max_products', tenant.max_products or 1000))
            tenant.max_customers = int(request.form.get('max_customers', tenant.max_customers or 500))
            tenant.max_suppliers = int(request.form.get('max_suppliers', tenant.max_suppliers or 200))
            tenant.max_branches = int(request.form.get('max_branches', tenant.max_branches or 3))
            tenant.max_warehouses = int(request.form.get('max_warehouses', tenant.max_warehouses or 2))
            tenant.max_invoices_per_month = int(request.form.get('max_invoices_per_month', tenant.max_invoices_per_month or 1000))
            tenant.max_sales_per_month = int(request.form.get('max_sales_per_month', tenant.max_sales_per_month or 5000))
            tenant.data_retention_days = int(request.form.get('data_retention_days', tenant.data_retention_days or 365))
            tenant.enable_pos = request.form.get('enable_pos') == 'on'
            tenant.enable_payroll = request.form.get('enable_payroll') == 'on'
            tenant.enable_cheques = request.form.get('enable_cheques') == 'on'
            tenant.enable_expenses = request.form.get('enable_expenses') == 'on'
            tenant.enable_store = request.form.get('enable_store') == 'on'
            tenant.allow_data_export = request.form.get('allow_data_export') == 'on'
            tenant.allow_custom_integrations = request.form.get('allow_custom_integrations') == 'on'
            tenant.prices_include_vat = request.form.get('prices_include_vat') == 'on'
            tenant.updated_at = datetime.now(timezone.utc)

            db.session.commit()
            _invalidate_owner_changes()
            _audit_owner_db_action('tenant_edit', {'tenant_id': tenant_id})
            flash(f'تم تحديث بيانات التينانت "{tenant.name_ar}" بنجاح.', 'success')
            return redirect(url_for('owner.tenants_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في تحديث التينانت: {str(e)}', 'danger')

    return render_template('owner/tenant_edit.html', tenant=tenant)

@owner_bp.route('/tenants/<int:tenant_id>/delete', methods=['POST'])
@owner_required
def tenant_delete(tenant_id):
    """Soft-delete a tenant (mark as inactive, do not purge)."""
    tenant = Tenant.query.get_or_404(tenant_id)

    # Protect default tenant (id==1) from deletion
    if tenant.id == 1:
        flash('⚠️ لا يمكن حذف التينانت الرئيسي.', 'danger')
        return redirect(url_for('owner.tenants_list'))

    # Check for active users
    active_users = User.query.filter_by(tenant_id=tenant_id, is_active=True).count()
    if active_users > 0:
        flash(f'⚠️ التينانت يحتوي على {active_users} مستخدمين نشطين. قم بتعطيلهم أولاً أو قم بالتعليق.', 'warning')
        return redirect(url_for('owner.tenants_list'))

    tenant.is_active = False
    tenant.is_suspended = True
    tenant.suspension_reason = 'Deleted by owner'
    tenant.updated_at = datetime.now(timezone.utc)

    db.session.commit()
    _invalidate_owner_changes()
    _audit_owner_db_action('tenant_soft_delete', {'tenant_id': tenant_id})
    flash(f'تم حذف التينانت "{tenant.name_ar or tenant.name}" بنجاح.', 'success')
    return redirect(url_for('owner.tenants_list'))

@owner_bp.route('/api/tenant/<int:tenant_id>/toggle-status', methods=['POST'])
@owner_required
def api_tenant_toggle_status(tenant_id):
    """AJAX endpoint to toggle tenant active/suspended status from super admin dashboard."""
    if not request.is_json:
        return jsonify({'success': False, 'error': 'JSON required'}), 400
    try:
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found'}), 404
        if tenant.id == 1:
            return jsonify({'success': False, 'error': 'لا يمكن تعطيل التينانت الرئيسي'}), 400
        tenant.is_active = not tenant.is_active
        tenant.is_suspended = not tenant.is_active
        if not tenant.is_active:
            tenant.suspension_reason = 'Disabled via API'
        else:
            tenant.suspension_reason = None
        tenant.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        _invalidate_owner_changes()
        _audit_owner_db_action('api_tenant_toggle_status', {
            'tenant_id': tenant_id, 'is_active': tenant.is_active
        })
        status_label = 'مفعل' if tenant.is_active else 'معطل'
        return jsonify({
            'success': True,
            'is_active': tenant.is_active,
            'message': f'تم {status_label} التينانت "{tenant.name_ar or tenant.name}" بنجاح',
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@owner_bp.route('/api/tenant/<int:tenant_id>/update-package', methods=['POST'])
@owner_required
def api_tenant_update_package(tenant_id):
    """AJAX endpoint to update tenant package limits from super admin dashboard."""
    if not request.is_json:
        return jsonify({'success': False, 'error': 'JSON required'}), 400
    try:
        data = request.get_json()
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            return jsonify({'success': False, 'error': 'Tenant not found'}), 404
        field = data.get('field')
        value = data.get('value')
        allowed_fields = [
            'max_users', 'max_products', 'max_customers', 'max_suppliers',
            'max_branches', 'max_warehouses', 'max_invoices_per_month', 'max_sales_per_month',
        ]
        if field not in allowed_fields:
            return jsonify({'success': False, 'error': f'Unknown field: {field}'}), 400
        try:
            setattr(tenant, field, int(value))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid integer value'}), 400
        tenant.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        _invalidate_owner_changes()
        _audit_owner_db_action('api_tenant_update_package', {
            'tenant_id': tenant_id, 'field': field, 'value': value
        })
        return jsonify({
            'success': True,
            'message': f'تم تحديث {field} إلى {value}',
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500