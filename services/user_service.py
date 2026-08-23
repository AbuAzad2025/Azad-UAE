from sqlalchemy.orm import joinedload

from extensions import db
from models import Role, Tenant, User
from utils.tenanting import scoped_user_query


class UserService:
    @staticmethod
    def available_branches(user):
        """Active branches visible to the user (tenant + branch scope)."""
        from models import Branch
        from utils.branching import branch_scope_id_for
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id(user)
        query = Branch.query.filter_by(is_active=True)
        if tid is not None:
            query = query.filter(Branch.tenant_id == tid)
        scoped_branch_id = branch_scope_id_for(user)
        if scoped_branch_id is not None:
            query = query.filter(Branch.id == scoped_branch_id)
        return query.order_by(Branch.code, Branch.name).all()

    @staticmethod
    def get_tenant(tenant_id):
        return db.session.get(Tenant, int(tenant_id)) if tenant_id else None

    @staticmethod
    def get_role(role_id):
        return db.session.get(Role, role_id) if role_id else None

    @staticmethod
    def roles_visible_to_level(max_level):
        """Active roles whose level does not exceed the given level."""
        from utils.auth_helpers import role_level_for

        roles = Role.query.filter_by(is_active=True).all()
        return [r for r in roles if role_level_for(getattr(r, "slug", None)) <= max_level]

    @staticmethod
    def find_username_conflict(username):
        """System-wide username conflict lookup (case-insensitive)."""
        return User.query.filter(User.username.ilike(username)).first()

    @staticmethod
    def get_scoped_non_owner_or_404(record_id, user):
        """Non-owner user by id within the active tenant; 404 when absent."""
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id(user)
        user_query = User.query.filter_by(id=record_id, is_owner=False)
        if tid is not None:
            user_query = user_query.filter(User.tenant_id == tid)
        return user_query.first_or_404()

    @staticmethod
    def count_sales_for_seller(seller_id, tenant_id) -> int:
        from models import Sale

        sales_query = Sale.query.filter_by(seller_id=seller_id)
        if tenant_id is not None:
            sales_query = sales_query.filter(Sale.tenant_id == tenant_id)
        return sales_query.count()

    @staticmethod
    def create_user(
        username: str,
        full_name: str,
        email: str = "",
        phone: str = "",
        tenant_id: int | None = None,
        role_id: int | None = None,
    ):
        """Create a new user. Returns the created user (not yet committed)."""
        user = User(username=username, full_name=full_name, email=email, phone=phone, is_active=True)
        if tenant_id is not None:
            user.tenant_id = tenant_id
        if role_id is not None:
            user.role_id = role_id
        user.set_password("password123")
        db.session.add(user)
        return user

    @staticmethod
    def get_users_list_context(tenant_id=None):
        """Get users list with stats and tenants for the users management page."""
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
