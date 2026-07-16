"""
مرجع مركزي موحد للصلاحيات وترتيب الأدوار.
يُستورد من routes/users.py و routes/owner.py بدل تكرار _role_level و _current_user_level.
"""
from extensions import db
from utils.constants import ROLE_LEVELS
from models.enums import RoleEnum


def role_level_for(slug):
    """ترتيب الدور (أعلى = أكثر صلاحية). يُستخدم لفلترة الأدوار التي يمكن للمستخدم الحالي تعيينها."""
    return ROLE_LEVELS.get(slug, 0)


def role_level_for_user(user):
    """ترتيب المستخدم الحالي حسب دوره."""
    if not user:
        return 0
    if getattr(user, 'is_owner', False):
        return ROLE_LEVELS.get(RoleEnum.OWNER.value, 100)
    role = getattr(user, 'role', None)
    slug = getattr(role, 'slug', None) if role else None
    return role_level_for(slug)


def is_admin_surface_user(user):
    """
    هل المستخدم يصل إلى لوحات الإدارة الحساسة؟
    السياسة: owner و super_admin فقط.
    """
    if not user:
        return False
    if getattr(user, 'is_owner', False):
        return True
    role = getattr(user, 'role', None)
    slug = getattr(role, 'slug', None) if role else None
    return slug == RoleEnum.SUPER_ADMIN.value


def is_global_owner_user(user):
    """
    هل المستخدم مالك منصة أو مطوّر (صلاحيات شاملة)؟
    يُستخدم لـ owner_required و developer access.
    الشرط: is_owner=True بالإضافة إلى tenant_id=NULL (platform owner فعلي).
    """
    if not user:
        return False
    if getattr(user, 'is_owner', False):
        tid = getattr(user, 'tenant_id', None)
        if tid is None:
            return True
    role = getattr(user, 'role', None)
    slug = getattr(role, 'slug', None) if role else None
    return slug == RoleEnum.DEVELOPER.value


def user_may_have_null_tenant(*, is_owner=False, role=None):
    """tenant_id=NULL is allowed only for platform owner or developer role."""
    if is_owner:
        return True
    slug = getattr(role, 'slug', None) if role else None
    return slug == RoleEnum.DEVELOPER.value


def enforce_company_user_tenant(user, *, role=None, is_owner=None):
    """
    Ensure company users have tenant_id. Global owner/developer may stay NULL.
    Raises ValueError when a company role cannot be assigned a tenant.
    """
    role = role or getattr(user, 'role', None)
    is_owner = is_owner if is_owner is not None else getattr(user, 'is_owner', False)
    if user_may_have_null_tenant(is_owner=is_owner, role=role):
        return user
    if getattr(user, 'tenant_id', None):
        return user
    branch_id = getattr(user, 'branch_id', None)
    if branch_id:
        from models import Branch

        branch = db.session.get(Branch, int(branch_id or 0))
        if branch and getattr(branch, 'tenant_id', None):
            user.tenant_id = int(branch.tenant_id or 0)
            return user
    from utils.tenanting import assign_tenant_id

    assign_tenant_id(user)
    if not getattr(user, 'tenant_id', None):
        raise ValueError('يجب ربط مستخدم الشركة بشركة نشطة (tenant_id).')
    return user
