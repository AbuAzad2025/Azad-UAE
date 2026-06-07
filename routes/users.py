from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user
from extensions import db
from models import User, Role, Branch
from utils.decorators import admin_required, permission_required
from utils.branching import branch_scope_id_for, role_requires_branch
from utils.helpers import create_audit_log
from utils.auth_helpers import role_level_for, role_level_for_user, enforce_company_user_tenant
from utils.tenanting import get_active_tenant_id
from utils.db_safety import atomic_transaction
from utils.structured_logging import log_mutation
from utils.tenanting import assign_tenant_id
from utils.tenanting import scoped_user_query
from utils.username_policy import validate_username_for_user, tenant_username_prefix, is_platform_reserved
from models.tenant import Tenant

users_bp = Blueprint('users', __name__, url_prefix='/users')


def _available_branches():
    tid = get_active_tenant_id(current_user)
    query = Branch.query.filter_by(is_active=True)
    if tid is not None:
        query = query.filter(Branch.tenant_id == tid)
    scoped_branch_id = branch_scope_id_for(current_user)
    if scoped_branch_id is not None:
        query = query.filter(Branch.id == scoped_branch_id)
    return query.order_by(Branch.code, Branch.name).all()


def _clean_branch_id(raw_value):
    if raw_value in (None, '', 'None'):
        return None
    return int(raw_value)


def _username_example():
    tid = get_active_tenant_id(current_user)
    tenant = Tenant.query.get(int(tid)) if tid else None
    prefix = tenant_username_prefix(tenant) if tenant else 'CODE'
    return f'{prefix}_ahmad'


def _validate_user_branch(role_id, branch_id):
    role = Role.query.get(role_id) if role_id else None
    if not role:
        raise ValueError('⚠️ يرجى اختيار الدور الوظيفي.')

    if role_requires_branch(role):
        if not branch_id:
            raise ValueError('⚠️ يجب ربط هذا المستخدم بفرع محدد.')
        if not any(branch.id == branch_id for branch in _available_branches()):
            raise ValueError('⚠️ الفرع المحدد خارج نطاقك أو غير نشط.')
    return role


def _ensure_user_in_scope(user):
    scoped_branch_id = branch_scope_id_for(current_user)
    if scoped_branch_id is None:
        return user
    if getattr(user, 'branch_id', None) != scoped_branch_id:
        abort(403)
    return user


@users_bp.route('/')
@login_required
@permission_required('manage_users')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '', type=str)

    query = scoped_user_query(exclude_owners=True, active_only=True)
    scoped_branch_id = branch_scope_id_for(current_user)
    if scoped_branch_id is not None:
        query = query.filter(User.branch_id == scoped_branch_id)

    if search:
        search_filter = f'%{search}%'
        query = query.filter(
            db.or_(
                User.username.ilike(search_filter),
                User.email.ilike(search_filter),
                User.full_name.ilike(search_filter)
            )
        )

    pagination = query.order_by(User.username).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    return render_template('users/index.html',
                         users=pagination.items,
                         pagination=pagination)


@users_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permission_required('manage_users')
def create():
    current_level = role_level_for_user(current_user)
    roles = Role.query.filter_by(is_active=True).all()
    roles = [r for r in roles if role_level_for(getattr(r, 'slug', None)) <= current_level]
    branches = _available_branches()
    default_form = {'is_active': '1'}

    if request.method == 'POST':
        try:
            role_id = request.form.get('role_id', type=int)
            if not role_id:
                flash('⚠️ يرجى اختيار الدور الوظيفي.', 'warning')
                form_values = request.form.to_dict()
                form_values['is_active'] = request.form.get('is_active', '1')
                return render_template(
                    'users/create.html',
                    roles=roles,
                    branches=branches,
                    form_data=form_values,
                    username_example=_username_example(),
                )

            is_active = request.form.get('is_active', '1') == '1'
            branch_id = _clean_branch_id(request.form.get('branch_id'))
            _validate_user_branch(role_id, branch_id)

            username = (request.form.get('username') or '').strip()
            if is_platform_reserved(username):
                flash('⚠️ اسم المستخدم محجوز للمنصة (owner / azad).', 'danger')
                form_values = request.form.to_dict()
                form_values['is_active'] = request.form.get('is_active', '1')
                return render_template(
                    'users/create.html',
                    roles=roles,
                    branches=branches,
                    form_data=form_values,
                    username_example=_username_example(),
                )

            tid = get_active_tenant_id(current_user)
            tenant = Tenant.query.get(int(tid)) if tid else None
            uname_err = validate_username_for_user(username, is_owner=False, tenant=tenant)
            if uname_err:
                prefix = tenant_username_prefix(tenant) if tenant else 'CODE'
                flash(f'⚠️ {uname_err}\n💡 مثال: {prefix}_ahmad', 'danger')
                form_values = request.form.to_dict()
                form_values['is_active'] = request.form.get('is_active', '1')
                return render_template(
                    'users/create.html',
                    roles=roles,
                    branches=branches,
                    form_data=form_values,
                    username_example=_username_example(),
                )

            # Check tenant user limit
            try:
                from utils.tenant_limits import check_users_limit, TenantLimitError
                check_users_limit()
            except TenantLimitError as e:
                flash(str(e), 'danger')
                form_values = request.form.to_dict()
                form_values['is_active'] = request.form.get('is_active', '1')
                return render_template(
                    'users/create.html',
                    roles=roles,
                    branches=branches,
                    form_data=form_values,
                    username_example=_username_example(),
                )

            conflict = User.query.filter(User.username.ilike(username)).first()
            if conflict:
                flash('⚠️ اسم المستخدم مستخدم مسبقاً على مستوى النظام.', 'danger')
                form_values = request.form.to_dict()
                form_values['is_active'] = request.form.get('is_active', '1')
                return render_template(
                    'users/create.html',
                    roles=roles,
                    branches=branches,
                    form_data=form_values,
                    username_example=_username_example(),
                )

            from utils.field_validators import normalize_phone_optional

            user = User(
                username=username,
                email=request.form.get('email'),
                full_name=request.form.get('full_name'),
                full_name_ar=request.form.get('full_name_ar'),
                phone=normalize_phone_optional(request.form.get('phone')),
                role_id=role_id,
                branch_id=branch_id,
                is_owner=False,
                is_active=is_active
            )

            password = request.form.get('password')
            user.set_password(password)
            assign_tenant_id(user)

            with atomic_transaction('user_creation'):
                db.session.add(user)
                db.session.flush()

                create_audit_log('create', 'users', user.id)

            log_mutation('create', 'User', user.id, {'username': user.username})
            flash('✅ تم إضافة المستخدم بنجاح!', 'success')
            return redirect(url_for('users.index'))

        except Exception as e:
            db.session.rollback()
            import traceback
            error_details = traceback.format_exc()
            current_app.logger.error(f'User creation error: {error_details}')
            flash(ErrorMessages.create_failed('user'), 'danger')
            form_values = request.form.to_dict()
            form_values['is_active'] = request.form.get('is_active', '1')
            return render_template(
                    'users/create.html',
                    roles=roles,
                    branches=branches,
                    form_data=form_values,
                    username_example=_username_example(),
                )

    return render_template(
        'users/create.html',
        roles=roles,
        branches=branches,
        form_data=default_form,
        username_example=_username_example(),
    )


@users_bp.route('/<int:id>')
@login_required
@permission_required('manage_users')
def view(id):
    tid = get_active_tenant_id(current_user)
    user_query = User.query.filter_by(id=id, is_owner=False)
    if tid is not None:
        user_query = user_query.filter(User.tenant_id == tid)
    user = user_query.first_or_404()
    _ensure_user_in_scope(user)
    return render_template('users/view.html', user=user)


@users_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):
    tid = get_active_tenant_id(current_user)
    user_query = User.query.filter_by(id=id, is_owner=False)
    if tid is not None:
        user_query = user_query.filter(User.tenant_id == tid)
    user = user_query.first_or_404()
    _ensure_user_in_scope(user)

    current_level = role_level_for_user(current_user)
    roles = Role.query.filter_by(is_active=True).all()
    roles = [r for r in roles if role_level_for(getattr(r, 'slug', None)) <= current_level]
    branches = _available_branches()

    if request.method == 'POST':
        try:
            user.email = request.form.get('email')
            user.full_name = request.form.get('full_name')
            user.full_name_ar = request.form.get('full_name_ar')
            from utils.field_validators import normalize_phone_optional

            user.phone = normalize_phone_optional(request.form.get('phone'))
            role_id = request.form.get('role_id', type=int)
            branch_id = _clean_branch_id(request.form.get('branch_id'))
            role = _validate_user_branch(role_id, branch_id)
            user.role_id = role_id
            user.branch_id = branch_id
            enforce_company_user_tenant(user, role=role, is_owner=False)

            new_password = request.form.get('new_password')
            if new_password:
                user.set_password(new_password)

            user.is_active = request.form.get('is_active') == '1'

            create_audit_log('update', 'users', user.id)

            db.session.commit()
            flash('✅ تم تحديث بيانات المستخدم بنجاح!', 'success')
            return redirect(url_for('users.index'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating user {id}: {e}")
            flash(ErrorMessages.update_failed('user'), 'danger')
            return render_template('users/edit.html', user=user, roles=roles, branches=branches)

    return render_template('users/edit.html', user=user, roles=roles, branches=branches)


@users_bp.route('/<int:id>/toggle-active', methods=['POST'])
@login_required
@admin_required
def toggle_active(id):
    tid = get_active_tenant_id(current_user)
    user_query = User.query.filter_by(id=id, is_owner=False)
    if tid is not None:
        user_query = user_query.filter(User.tenant_id == tid)
    user = user_query.first_or_404()
    _ensure_user_in_scope(user)

    user.is_active = not user.is_active
    db.session.commit()

    status = 'تفعيل' if user.is_active else 'تعطيل'
    status_msg = 'تفعيل' if user.is_active else 'إلغاء تفعيل'
    flash(f'✅ تم {status_msg} المستخدم "{user.username}" بنجاح!', 'success')

    create_audit_log('toggle_active', 'users', user.id)

    return redirect(url_for('users.index'))


@users_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('manage_users')
def delete(id):
    # Ensure target is NOT owner (double check, though filter handles it)
    tid = get_active_tenant_id(current_user)
    user_query = User.query.filter_by(id=id, is_owner=False)
    if tid is not None:
        user_query = user_query.filter(User.tenant_id == tid)
    user = user_query.first_or_404()
    _ensure_user_in_scope(user)

    if user.id == current_user.id:
        flash('⚠️ لا يمكنك حذف حسابك الخاص.\n💡 اطلب من مدير آخر حذف حسابك إذا لزم الأمر.', 'danger')
        return redirect(url_for('users.index'))

    try:
        from models import Sale, AuditLog
        sales_query = Sale.query.filter_by(seller_id=id)
        if tid is not None:
            sales_query = sales_query.filter(Sale.tenant_id == tid)
        sales_count = sales_query.count()

        if sales_count > 0:
            user.is_active = False
            db.session.commit()
            flash(f'⚠️ تم إلغاء تفعيل المستخدم "{user.username}" (لديه {sales_count} عملية مسجلة).\n💡 لا يمكن حذفه نهائياً للحفاظ على السجلات.', 'warning')
            create_audit_log('deactivate', 'users', id)
        else:
            username = user.username
            db.session.delete(user)
            db.session.commit()
            flash(f'✅ تم حذف المستخدم "{username}" نهائياً!', 'success')
            create_audit_log('delete', 'users', id)

        return redirect(url_for('users.index'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting user {id}: {e}")
        flash(ErrorMessages.delete_failed('user'), 'danger')
        return redirect(url_for('users.index'))
