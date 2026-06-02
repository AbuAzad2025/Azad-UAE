from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

from utils.branching import branch_scope_id_for, report_branch_scope_id_for
from utils.auth_helpers import is_admin_surface_user, is_global_owner_user


def branch_scope_id():
    """يرجع branch_id لأي مستخدم غير عالمي لتطبيق عزل البيانات حسب الفرع."""
    return branch_scope_id_for(current_user)


def report_branch_scope_id():
    """نطاق الفرع في التقارير — المستخدم العالمي يبدأ من فرعه الافتراضي."""
    return report_branch_scope_id_for(current_user)


def permission_required(permission_code):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('الرجاء تسجيل الدخول أولاً', 'warning')
                return redirect(url_for('auth.login'))
            
            if is_global_owner_user(current_user):
                return f(*args, **kwargs)

            if not current_user.has_permission(permission_code):
                flash('ليس لديك صلاحية للوصول لهذه الصفحة', 'danger')
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def any_permission_required(*permission_codes):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('الرجاء تسجيل الدخول أولاً', 'warning')
                return redirect(url_for('auth.login'))

            allowed = any(current_user.has_permission(code) for code in permission_codes if code)
            if not allowed:
                flash('ليس لديك صلاحية للوصول لهذه الصفحة', 'danger')
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """لوحات الإدارة الحساسة: owner و super_admin فقط."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('الرجاء تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        if not is_admin_surface_user(current_user):
            flash('هذه الصفحة للإدارة فقط', 'danger')
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def seller_or_above(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('الرجاء تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))

        from utils.constants import ROLE_LEVELS
        user_slug = getattr(getattr(current_user, 'role', None), 'slug', None)
        user_level = ROLE_LEVELS.get(user_slug, 0)
        if user_level < ROLE_LEVELS.get('seller', 10):
            flash('ليس لديك صلاحية للوصول لهذه الصفحة', 'danger')
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def super_admin_required(f):
    """مطابق لـ admin_required: owner و super_admin فقط."""
    return admin_required(f)


def owner_required(f):
    """لوحة المالك: owner أو developer فقط."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(404)
        
        if not is_global_owner_user(current_user):
            abort(404)
        
        return f(*args, **kwargs)
    return decorated_function


def platform_owner_required(f):
    """Platform routes — same gate as owner_required (owner / developer)."""
    return owner_required(f)


def company_admin_required(f):
    """Tenant company admin surface — super_admin or manager with active tenant."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('الرجاء تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))

        if is_global_owner_user(current_user):
            abort(404)

        from utils.tenanting import get_active_tenant_id

        slug = getattr(getattr(current_user, 'role', None), 'slug', None)
        if slug not in ('super_admin', 'manager') and not current_user.is_super_admin():
            abort(403)
        if not get_active_tenant_id(current_user):
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def owner_or_company_admin(f):
    """Platform owner/developer or tenant super_admin/manager."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('الرجاء تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))

        if is_global_owner_user(current_user):
            return f(*args, **kwargs)

        from utils.tenanting import get_active_tenant_id

        slug = getattr(getattr(current_user, 'role', None), 'slug', None)
        if slug in ('super_admin', 'manager') or current_user.is_super_admin():
            if get_active_tenant_id(current_user):
                return f(*args, **kwargs)
        abort(403)

    return decorated_function

def branch_manager_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(404)
        
        # Super Admin or Owner or Branch Manager
        if not (current_user.is_owner or 
                current_user.is_super_admin() or 
                (getattr(current_user, 'role', None) and getattr(current_user.role, 'slug', None) == 'branch_manager')):
            flash('هذه الصفحة لمدراء الفروع فقط', 'danger')
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function

def accountant_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(404)
        
        # Super Admin or Owner or Accountant or Branch Manager
        if not (current_user.is_owner or 
                current_user.is_super_admin() or 
                (getattr(current_user, 'role', None) and getattr(current_user.role, 'slug', None) in ['accountant', 'branch_manager'])):
            flash('هذه الصفحة للمحاسبين فقط', 'danger')
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function

