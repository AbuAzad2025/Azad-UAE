"""
مرجع مركزي موحد للصلاحيات وترتيب الأدوار.
يُستورد من routes/users.py و routes/owner.py بدل تكرار _role_level و _current_user_level.
"""
from utils.constants import ROLE_LEVELS


def role_level_for(slug):
    """ترتيب الدور (أعلى = أكثر صلاحية). يُستخدم لفلترة الأدوار التي يمكن للمستخدم الحالي تعيينها."""
    return ROLE_LEVELS.get(slug, 0)


def role_level_for_user(user):
    """ترتيب المستخدم الحالي حسب دوره."""
    if not user:
        return 0
    if getattr(user, 'is_owner', False):
        return ROLE_LEVELS.get('owner', 100)
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
    return slug == 'super_admin'


def is_global_owner_user(user):
    """
    هل المستخدم مالك أو مطوّر (صلاحيات شاملة)؟
    يُستخدم لـ owner_required و developer access.
    """
    if not user:
        return False
    if getattr(user, 'is_owner', False):
        return True
    role = getattr(user, 'role', None)
    slug = getattr(role, 'slug', None) if role else None
    return slug == 'developer'
