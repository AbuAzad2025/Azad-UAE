from flask_babel import gettext
from sqlalchemy.orm import joinedload

from extensions import db
from models import Permission, Role, User


class RoleService:
    @staticmethod
    def get_roles_permissions_context(tenant_id=None):
        from models import Tenant
        from utils.constants import PERMISSION_FEATURE_MAP

        roles = Role.query.filter_by(is_active=True).options(joinedload(Role.permissions)).order_by(Role.name).all()
        all_permissions = Permission.query.order_by(Permission.category, Permission.name).all()

        tenant = None
        if tenant_id:
            tenant = db.session.get(Tenant, int(tenant_id))

        def _feature_enabled(code: str) -> bool:
            feature = PERMISSION_FEATURE_MAP.get(code)
            if feature is None or tenant is None:
                return True
            return bool(getattr(tenant, feature, True))

        # A tenant only sees the permissions its enabled features grant:
        # a tenant without the maintenance module never sees a maintenance
        # role, and the same applies to every other gated feature. The
        # feature gate on the blueprint is the second line of defence; this
        # is the first.
        permissions = [p for p in all_permissions if _feature_enabled(p.code)]

        perm_categories: dict[str, list[Permission]] = {}
        for p in permissions:
            perm_categories.setdefault(p.category or gettext("عام"), []).append(p)

        role_user_counts = {}
        for r in roles:
            q = User.query.filter_by(role_id=r.id, is_active=True)
            if tenant_id:
                q = q.filter_by(tenant_id=tenant_id)
            role_user_counts[r.id] = q.count()

        return {
            "roles": roles,
            "permissions": permissions,
            "perm_categories": perm_categories,
            "role_user_counts": role_user_counts,
        }
