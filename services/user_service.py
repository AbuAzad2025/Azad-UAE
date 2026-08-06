from models import User, Tenant, Role
from utils.tenanting import scoped_user_query
from sqlalchemy.orm import joinedload


class UserService:
    @staticmethod
    def create_user(username: str, full_name: str, email: str = "", phone: str = "", tenant_id: int | None = None, role_id: int | None = None):
        """Create a new user. Returns the created user (not yet committed)."""
        from models import User

        user = User(username=username, full_name=full_name, email=email, phone=phone, is_active=True)
        if tenant_id is not None:
            user.tenant_id = tenant_id
        if role_id is not None:
            user.role_id = role_id
        user.set_password("password123")
        db.session.add(user)
        return user
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
