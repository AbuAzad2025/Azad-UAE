from models import User, Tenant, Role, Permission
from utils.tenanting import scoped_user_query
from sqlalchemy.orm import joinedload


class UserService:
    @staticmethod
    def get_users_list_context(tenant_id=None):
        query = (
            scoped_user_query(exclude_owners=True)
            .options(
                joinedload(User.role),
                joinedload(User.branch),
            )
            .order_by(User.created_at.desc())
        )
        users = query.all()

        tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name_ar).all()

        base = scoped_user_query(exclude_owners=True)
        stats = {
            "total": base.count(),
            "active": base.filter_by(is_active=True).count(),
            "inactive": base.filter_by(is_active=False).count(),
            "owners": User.query.filter_by(is_owner=True).count(),
            "admins": base.join(Role).filter(Role.slug == "super_admin").count(),
            "managers": base.join(Role).filter(Role.slug == "manager").count(),
            "sellers": base.join(Role).filter(Role.slug == "seller").count(),
        }

        return {
            "users": users,
            "stats": stats,
            "tenants": tenants,
            "active_tenant_id": tenant_id,
        }
