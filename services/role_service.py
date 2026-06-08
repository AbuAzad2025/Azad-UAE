from models import Role, Permission, User
from extensions import db
from sqlalchemy.orm import joinedload
from sqlalchemy import func

class RoleService:
    @staticmethod
    def get_roles_permissions_context(tenant_id=None):
        roles = Role.query.filter_by(is_active=True).options(joinedload(Role.permissions)).order_by(Role.name).all()
        permissions = Permission.query.order_by(Permission.category, Permission.name).all()
        
        perm_categories = {}
        for p in permissions:
            perm_categories.setdefault(p.category or 'عام', []).append(p)
            
        role_user_counts = {}
        for r in roles:
            q = User.query.filter_by(role_id=r.id, is_active=True)
            if tenant_id:
                q = q.filter_by(tenant_id=tenant_id)
            role_user_counts[r.id] = q.count()
            
        return {
            'roles': roles,
            'permissions': permissions,
            'perm_categories': perm_categories,
            'role_user_counts': role_user_counts
        }
