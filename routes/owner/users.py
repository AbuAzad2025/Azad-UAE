"""User management and roles/permissions routes for the owner blueprint."""

from routes.owner import (
    render_template, request, jsonify, flash, redirect, url_for, current_app, abort,
    login_required, current_user, func, desc, db, limiter,
    User, Branch, Tenant, Role, Sale, Payment, AuditLog,
    owner_required,
    role_level_for, role_level_for_user, is_global_owner_user,
    user_may_have_null_tenant, enforce_company_user_tenant,
    get_active_tenant_id, InputSanitizer,
)
from services.logging_core import LoggingCore
from routes.owner import owner_bp
from routes.owner.shared import _invalidate_owner_changes

import logging

logger = logging.getLogger(__name__)

@owner_bp.route('/users-list')
@owner_required
def users_list():
    """قائمة المستخدمين — platform: all or filtered by active tenant."""
    from services.user_service import UserService
    from utils.tenanting import get_active_tenant_id
    tid = get_active_tenant_id(current_user)
    context = UserService.get_users_list_context(tenant_id=tid)
    return render_template(
        'owner/users_list.html',
        users=context['users'],
        stats=context['stats'],
        active_tenant_id=context['active_tenant_id'],
        tenants=context['tenants'],
    )

@owner_bp.route('/users/create', methods=['GET', 'POST'])
@owner_required
@limiter.limit("5 per minute", methods=['POST'])
def create_user():
    """إضافة مستخدم جديد"""
    from models import Role
    from werkzeug.security import generate_password_hash
    from utils.password_validator import PasswordValidator

    from utils.tenanting import get_active_tenant_id
    from utils.auth_helpers import is_global_owner_user, user_may_have_null_tenant

    current_level = role_level_for_user(current_user)
    roles = Role.query.filter_by(is_active=True).all()
    roles = [r for r in roles if role_level_for(getattr(r, 'slug', None)) <= current_level]
    roles = [r for r in roles if getattr(r, 'slug', None) not in ('owner', 'developer')]
    tid = get_active_tenant_id(current_user)
    branches = Branch.query.filter_by(is_active=True)
    if tid:
        branches = branches.filter_by(tenant_id=tid)
    branches = branches.order_by(Branch.code, Branch.name).all()
    tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name_ar).all()
    default_form = {'is_active': 'on'}
    preselect_tenant_id = request.args.get('tenant_id', type=int)

    if request.method == 'POST':
        def _form_values():
            values = request.form.to_dict()
            values['is_owner'] = 'on' if request.form.get('is_owner') == 'on' else 'off'
            values['is_active'] = 'on' if request.form.get('is_active') == 'on' else 'off'
            return values

        try:
            from utils.sanitizer import InputSanitizer

            from utils.field_validators import FieldValidationError, normalize_user_email_required

            username = str(InputSanitizer.sanitize_text(request.form.get('username', ''), max_length=20)).strip()
            try:
                email = normalize_user_email_required(request.form.get('email'))
            except FieldValidationError as exc:
                flash(str(exc), 'error')
                return render_template('owner/create_user.html', roles=roles, branches=branches, tenants=tenants, show_tenant_picker=True, form_data=_form_values())
            password = request.form.get('password', '').strip()  # لا نعدل password
            full_name = InputSanitizer.sanitize_text(request.form.get('full_name', ''), max_length=100)
            role_id = request.form.get('role_id', type=int)
            requested_is_owner = request.form.get('is_owner') == 'on'
            is_owner = requested_is_owner if current_user.is_owner else False
            is_active = request.form.get('is_active') == 'on'
            branch_id = request.form.get('branch_id', type=int) or None

            # التحقق من البيانات
            if not username or not password:
                from utils.error_messages import ErrorMessages
                flash(ErrorMessages.user_required_fields(), 'error')
                return render_template('owner/create_user.html', roles=roles, branches=branches, tenants=tenants, show_tenant_picker=True, form_data=_form_values())

            if not role_id:
                flash('⚠️ يرجى اختيار الدور الوظيفي.', 'warning')
                return render_template('owner/create_user.html', roles=roles, branches=branches, tenants=tenants, show_tenant_picker=True, form_data=_form_values())

            # التحقق من قوة كلمة المرور
            is_valid, errors = PasswordValidator.validate(password)
            if not is_valid:
                from utils.error_messages import ErrorMessages
                flash(ErrorMessages.weak_password(errors), 'danger')
                return render_template('owner/create_user.html', roles=roles, branches=branches, tenants=tenants, show_tenant_picker=True, form_data=_form_values())

            # التحقق من عدم وجود المستخدم في نفس التينانت
            target_tenant_id = request.form.get('tenant_id', type=int) or tid
            existing = User.query.filter_by(username=username, tenant_id=target_tenant_id).first()
            if existing:
                from utils.error_messages import ErrorMessages
                flash(ErrorMessages.user_exists(username), 'error')
                return render_template('owner/create_user.html', roles=roles, branches=branches, tenants=tenants, show_tenant_picker=True, form_data=_form_values())

            role = db.session.get(Role, role_id)
            if role_requires_branch(role, is_owner=is_owner) and not branch_id:
                flash('⚠️ يجب ربط هذا المستخدم بفرع محدد.', 'warning')
                return render_template('owner/create_user.html', roles=roles, branches=branches, tenants=tenants, show_tenant_picker=True, form_data=_form_values())
            if role_level_for(getattr(role, 'slug', None)) > current_level:
                flash('⚠️ لا يمكنك تعيين دور أعلى من دورك.', 'danger')
                return render_template('owner/create_user.html', roles=roles, branches=branches, tenants=tenants, show_tenant_picker=True, form_data=_form_values())

            from utils.auth_helpers import enforce_company_user_tenant

            # إنشاء المستخدم
            form_tenant_id = request.form.get('tenant_id', type=int)
            if is_global_owner_user(current_user):
                if role and user_may_have_null_tenant(is_owner=is_owner, role=role):
                    user_tenant_id = None
                else:
                    user_tenant_id = form_tenant_id or get_active_tenant_id(current_user)
            else:
                user_tenant_id = get_active_tenant_id(current_user)

            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                full_name=full_name,
                role_id=role_id,
                branch_id=branch_id,
                tenant_id=user_tenant_id,
                is_owner=is_owner,
                is_active=is_active
            )
            enforce_company_user_tenant(user, role=role, is_owner=is_owner)

            db.session.add(user)
            db.session.commit()
            _invalidate_owner_changes()
            flash(f'تم إضافة المستخدم {username} بنجاح', 'success')
            return redirect(url_for('owner.users_list'))

        except Exception as e:
            db.session.rollback()
            from utils.error_messages import ErrorMessages
            flash(ErrorMessages.user_update_failed(str(e)), 'error')
            return render_template(
                'owner/create_user.html',
                roles=roles,
                branches=branches,
                tenants=tenants,
                form_data=_form_values(),
            )

    if preselect_tenant_id:
        default_form['tenant_id'] = str(preselect_tenant_id)
    return render_template(
        'owner/create_user.html',
        roles=roles,
        branches=branches,
        tenants=tenants,
        form_data=default_form,
        show_tenant_picker=True,
    )

@owner_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@owner_required
@limiter.limit("10 per minute", methods=['POST'])
def edit_user(user_id):
    """تعديل مستخدم"""
    from models import Role
    from werkzeug.security import generate_password_hash

    user = User.query.get_or_404(user_id)
    current_level = role_level_for_user(current_user)
    roles = Role.query.filter_by(is_active=True).all()
    roles = [r for r in roles if role_level_for(getattr(r, 'slug', None)) <= current_level]
    tid = get_active_tenant_id(current_user)
    branches = Branch.query.filter_by(is_active=True)
    if tid:
        branches = branches.filter_by(tenant_id=tid)
    branches = branches.order_by(Branch.code, Branch.name).all()

    if request.method == 'POST':
        try:
            role_id = request.form.get('role_id', type=int)
            requested_is_owner = request.form.get('is_owner') == 'on'
            is_owner = requested_is_owner if current_user.is_owner else user.is_owner
            branch_id = request.form.get('branch_id', type=int) or None
            role = db.session.get(Role, role_id)
            if role_requires_branch(role, is_owner=is_owner) and not branch_id:
                flash('⚠️ يجب ربط هذا المستخدم بفرع محدد.', 'warning')
                return render_template('owner/edit_user.html', user=user, roles=roles, branches=branches)
            if role_level_for(getattr(role, 'slug', None)) > current_level:
                flash('⚠️ لا يمكنك تعيين دور أعلى من دورك.', 'danger')
                return render_template('owner/edit_user.html', user=user, roles=roles, branches=branches)

            from utils.sanitizer import InputSanitizer
            from utils.field_validators import FieldValidationError, normalize_user_email_required

            user.username = str(InputSanitizer.sanitize_text(request.form.get('username', ''), max_length=20)).strip()
            try:
                user.email = normalize_user_email_required(request.form.get('email'))
            except FieldValidationError as exc:
                flash(str(exc), 'error')
                return render_template('owner/edit_user.html', user=user, roles=roles, branches=branches)
            user.full_name = request.form.get('full_name', '').strip()
            user.role_id = role_id
            user.branch_id = branch_id
            user.is_owner = is_owner
            user.is_active = request.form.get('is_active') == 'on'
            from utils.auth_helpers import enforce_company_user_tenant

            enforce_company_user_tenant(user, role=role, is_owner=is_owner)

            # تغيير كلمة المرور إن وجدت
            new_password = request.form.get('new_password', '').strip()
            if new_password:
                user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')

            user.updated_by = current_user.id

            db.session.commit()
            _invalidate_owner_changes()
            flash(f'تم تحديث المستخدم {user.username} بنجاح', 'success')
            return redirect(url_for('owner.users_list'))

        except Exception as e:
            db.session.rollback()
            flash(f'خطأ في تحديث المستخدم: {str(e)}', 'error')

    return render_template('owner/edit_user.html', user=user, roles=roles, branches=branches)

@owner_bp.route('/users/<int:user_id>/profile')
@owner_required
def user_profile(user_id):
    """الملف الشخصي للمستخدم — مع نشاطات AuditLog حقيقية."""
    user = User.query.get_or_404(user_id)
    tid = get_active_tenant_id(current_user)

    from models import Sale, Payment

    # Sale/Payment stats scoped by tenant for security
    sale_q = Sale.query.filter_by(seller_id=user_id, tenant_id=tid) if tid else Sale.query.filter_by(seller_id=user_id)
    payment_q = Payment.query.filter_by(user_id=user_id, tenant_id=tid) if tid else Payment.query.filter_by(user_id=user_id)

    stats = {
        'sales_count': sale_q.count(),
        'sales_total': db.session.query(func.sum(Sale.amount_aed)).filter(Sale.status == 'confirmed', Sale.seller_id == user_id, Sale.tenant_id == tid).scalar() or 0 if tid else db.session.query(func.sum(Sale.amount_aed)).filter_by(status='confirmed', seller_id=user_id).scalar() or 0,
        'payments_count': payment_q.count(),
        'payments_total': db.session.query(func.sum(Payment.amount_aed)).filter_by(user_id=user_id, tenant_id=tid).scalar() or 0 if tid else db.session.query(func.sum(Payment.amount_aed)).filter_by(user_id=user_id).scalar() or 0,
        'audits_count': AuditLog.query.filter_by(user_id=user_id, tenant_id=tid).count() if tid else AuditLog.query.filter_by(user_id=user_id).count(),
    }

    # آخر النشاطات
    recent_sales = sale_q.order_by(Sale.sale_date.desc()).limit(5).all()
    recent_audits = AuditLog.query.filter_by(user_id=user_id)
    if tid:
        recent_audits = recent_audits.filter_by(tenant_id=tid)
    recent_audits = recent_audits.order_by(AuditLog.created_at.desc()).limit(10).all()

    return render_template('owner/user_profile.html',
                         user=user,
                         stats=stats,
                         recent_sales=recent_sales,
                         recent_audits=recent_audits)

@owner_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@owner_required
def delete_user(user_id):
    """حذف مستخدم"""
    user = User.query.get_or_404(user_id)

    # لا يمكن حذف المالك
    from utils.error_messages import ErrorMessages

    if user.is_owner:
        flash(ErrorMessages.user_delete_owner(), 'error')
        return redirect(url_for('owner.users_list'))

    # لا يمكن حذف نفسك
    if user.id == current_user.id:
        flash(ErrorMessages.user_delete_self(), 'error')
        return redirect(url_for('owner.users_list'))

    try:
        # Soft delete - تعطيل بدلاً من الحذف
        user.is_active = False
        user.updated_by = current_user.id
        db.session.commit()
        _invalidate_owner_changes()
        flash(f'تم تعطيل المستخدم {user.username}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطأ في حذف المستخدم: {str(e)}', 'error')

    return redirect(url_for('owner.users_list'))

@owner_bp.route('/roles-permissions')
@owner_required
def roles_permissions():
    """صفحة الأدوار والصلاحيات — بيانات حقيقية من قاعدة البيانات."""
    from services.role_service import RoleService
    tid = get_active_tenant_id(current_user)
    context = RoleService.get_roles_permissions_context(tenant_id=tid)
    return render_template(
        'owner/roles_permissions.html',
        roles=context['roles'],
        permissions=context['permissions'],
        perm_categories=context['perm_categories'],
        role_user_counts=context['role_user_counts'],
    )

