from sqlalchemy import func, or_

from extensions import db
from models import Branch, Tenant, User
from models.tenant_store import TenantStore

_SORT_MAP = {
    "name": lambda: [Tenant.name.asc(), Tenant.id.asc()],
    "slug": lambda: [Tenant.slug.asc(), Tenant.id.asc()],
    "plan": lambda: [Tenant.subscription_plan.asc(), Tenant.id.asc()],
    "status": lambda: [Tenant.is_active.desc(), Tenant.is_suspended.asc(), Tenant.id.asc()],
    "created_at": lambda: [Tenant.created_at.desc(), Tenant.id.asc()],
}


class TenantService:
    @staticmethod
    def get_tenants_list_context(*, sort: str = "created_at", order: str = "desc", search: str = ""):
        builder = _SORT_MAP.get(sort or "created_at", _SORT_MAP["created_at"])
        ordering = builder()
        if (order or "").lower() == "asc":
            # map the default-None values to ascending
            new = []
            for col in ordering:
                if hasattr(col, "modifier"):
                    new.append(col)
                else:
                    try:
                        new.append(col.asc())
                    except Exception:
                        new.append(col)
            ordering = new

        query = Tenant.query
        if search:
            like = f"%{search.lower()}%"
            # Defensive: column may not exist in older schemas -> fall back to id match
            try:
                query = query.filter(
                    or_(
                        func.lower(getattr(Tenant, "name", "")).like(like),
                        func.lower(getattr(Tenant, "name_ar", "")).like(like),
                        func.lower(getattr(Tenant, "name_en", "")).like(like),
                        func.lower(getattr(Tenant, "slug", "")).like(like),
                    )
                )
            except Exception:
                query = query.filter(Tenant.id == int(search) if search.isdigit() else (Tenant.id == -1))

        tenants = query.order_by(*ordering).all()
        tenant_ids = [t.id for t in tenants]

        user_counts = dict(
            db.session.query(User.tenant_id, func.count(User.id))
            .filter(User.tenant_id.in_(tenant_ids))
            .group_by(User.tenant_id)
            .all()
        ) if tenant_ids else {}
        branch_counts = dict(
            db.session.query(Branch.tenant_id, func.count(Branch.id))
            .filter(Branch.tenant_id.in_(tenant_ids))
            .group_by(Branch.tenant_id)
            .all()
        ) if tenant_ids else {}
        store_counts = dict(
            db.session.query(TenantStore.tenant_id, func.count(TenantStore.id))
            .filter(TenantStore.tenant_id.in_(tenant_ids))
            .group_by(TenantStore.tenant_id)
            .all()
        ) if tenant_ids else {}

        return {
            "tenants": tenants,
            "user_counts": user_counts,
            "branch_counts": branch_counts,
            "store_counts": store_counts,
        }
