from extensions import db
from models import Tenant, User, Branch
from models.tenant_store import TenantStore
from sqlalchemy import func


class TenantService:
    @staticmethod
    def get_tenants_list_context():
        tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
        tenant_ids = [t.id for t in tenants]

        user_counts = dict(
            db.session.query(User.tenant_id, func.count(User.id))
            .filter(User.tenant_id.in_(tenant_ids))
            .group_by(User.tenant_id)
            .all()
        )
        branch_counts = dict(
            db.session.query(Branch.tenant_id, func.count(Branch.id))
            .filter(Branch.tenant_id.in_(tenant_ids))
            .group_by(Branch.tenant_id)
            .all()
        )
        store_counts = dict(
            db.session.query(TenantStore.tenant_id, func.count(TenantStore.id))
            .filter(TenantStore.tenant_id.in_(tenant_ids))
            .group_by(TenantStore.tenant_id)
            .all()
        )
        return {
            "tenants": tenants,
            "user_counts": user_counts,
            "branch_counts": branch_counts,
            "store_counts": store_counts,
        }
