from decimal import Decimal

from flask import has_request_context, session
from flask_login import current_user
from sqlalchemy import func

from extensions import db
from utils.tenanting import get_active_tenant_id, apply_tenant_scope


GLOBAL_ROLE_SLUGS = {"developer", "super_admin"}
ACTIVE_BRANCH_SESSION_KEY = "active_branch_id"
ACTIVE_BRANCH_MODE_SESSION_KEY = "active_branch_mode"


def _resolve_user(user=None):
    if user is not None:
        return user
    try:
        candidate = current_user._get_current_object()
    except Exception:
        return None
    return candidate if getattr(candidate, "is_authenticated", False) else None


def is_global_user(user=None):
    user = _resolve_user(user)
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_owner", False):
        return True

    role = getattr(user, "role", None)
    role_slug = getattr(role, "slug", None)
    if role_slug in GLOBAL_ROLE_SLUGS:
        return True

    is_super_admin = getattr(user, "is_super_admin", None)
    if callable(is_super_admin) and is_super_admin():
        return True

    return False


def branch_scope_id_for(user=None):
    user = _resolve_user(user)
    if not user or not getattr(user, "is_authenticated", False):
        return None
    selected_branch_id = get_active_branch_id(user)
    if is_global_user(user):
        return selected_branch_id
    return selected_branch_id or getattr(user, "branch_id", None)


def report_branch_scope_id_for(user=None):
    """
    Branch scope for reports: global non-owner users default to home branch
    instead of all branches within the tenant.
    """
    user = _resolve_user(user)
    selected = branch_scope_id_for(user)
    if selected is not None:
        return selected
    if is_global_user(user) and not getattr(user, "is_owner", False):
        home_branch_id = getattr(user, "branch_id", None)
        if home_branch_id:
            return int(home_branch_id)
    return None


def role_requires_branch(role=None, *, is_owner=False):
    if is_owner:
        return False
    role_slug = getattr(role, "slug", None)
    return role_slug not in GLOBAL_ROLE_SLUGS


def get_accessible_branches_query(user=None):
    from models import Branch
    query = Branch.query.filter_by(is_active=True)
    user = _resolve_user(user)
    if not user or not getattr(user, "is_authenticated", False):
        return query
    tenant_id = get_active_tenant_id(user)
    if tenant_id is not None:
        query = query.filter(Branch.tenant_id == tenant_id)
    if is_global_user(user):
        return query
    branch_id = getattr(user, "branch_id", None)
    if branch_id is None:
        return query.filter(Branch.id < 0)
    return query.filter(Branch.id == branch_id)


def get_accessible_branches(user=None):
    from models import Branch
    return get_accessible_branches_query(user).order_by(Branch.is_main.desc(), Branch.code, Branch.name).all()


def user_can_access_branch(branch_id, user=None):
    from models import Branch
    if branch_id in (None, "", "all"):
        return is_global_user(user)
    try:
        branch_id = int(branch_id)
    except (TypeError, ValueError):
        return False
    return db.session.query(
        get_accessible_branches_query(user).filter(Branch.id == branch_id).exists()
    ).scalar()


def get_main_branch():
    from models import Branch
    tenant_id = get_active_tenant_id(current_user)
    query = Branch.query.filter_by(is_active=True, is_main=True)
    if tenant_id is not None:
        query = query.filter(Branch.tenant_id == tenant_id)
    return query.order_by(Branch.id.asc()).first()


def get_active_branch_mode():
    if not has_request_context():
        return "single"
    return session.get(ACTIVE_BRANCH_MODE_SESSION_KEY, "single")


def should_show_all_branch_columns(user=None):
    """
    Return True when the current user is global (owner/super admin/developer)
    and currently browsing in "all branches" mode.
    """
    user = _resolve_user(user)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not is_global_user(user):
        return False
    return get_active_branch_mode() == "all"


def get_active_branch_id(user=None):
    user = _resolve_user(user)
    if not user or not getattr(user, "is_authenticated", False):
        return None

    session_branch_id = session.get(ACTIVE_BRANCH_SESSION_KEY) if has_request_context() else None
    session_mode = get_active_branch_mode()

    if is_global_user(user):
        if session_mode == "all":
            return None
        if session_branch_id and user_can_access_branch(session_branch_id, user):
            return int(session_branch_id)
        return None

    user_branch_id = getattr(user, "branch_id", None)
    if user_branch_id and session_branch_id and int(session_branch_id) == int(user_branch_id):
        return int(user_branch_id)
    return int(user_branch_id) if user_branch_id else None


def get_active_branch(user=None):
    from models import Branch
    branch_id = get_active_branch_id(user)
    if not branch_id:
        return None
    return db.session.get(Branch, int(branch_id))


def set_active_branch(branch_id=None, *, user=None, allow_all=False):
    if not has_request_context():
        return
    user = _resolve_user(user)
    if allow_all and (branch_id in (None, "", "all")) and is_global_user(user):
        session[ACTIVE_BRANCH_SESSION_KEY] = None
        session[ACTIVE_BRANCH_MODE_SESSION_KEY] = "all"
        return

    if not branch_id:
        if is_global_user(user):
            session[ACTIVE_BRANCH_SESSION_KEY] = None
            session[ACTIVE_BRANCH_MODE_SESSION_KEY] = "all" if allow_all else "single"
            return
        branch_id = getattr(user, "branch_id", None)

    if not user_can_access_branch(branch_id, user):
        raise ValueError("الفرع المحدد غير مسموح لهذا المستخدم.")

    session[ACTIVE_BRANCH_SESSION_KEY] = int(branch_id)
    session[ACTIVE_BRANCH_MODE_SESSION_KEY] = "single"


def clear_active_branch():
    if not has_request_context():
        return
    session.pop(ACTIVE_BRANCH_SESSION_KEY, None)
    session.pop(ACTIVE_BRANCH_MODE_SESSION_KEY, None)


def get_accessible_warehouses_query(user=None):
    from models import Warehouse
    query = Warehouse.query.filter_by(is_active=True)
    tenant_id = get_active_tenant_id(user)
    if tenant_id is not None:
        query = query.filter(Warehouse.tenant_id == tenant_id)
    branch_id = branch_scope_id_for(user)
    if branch_id is not None:
        query = query.filter(Warehouse.branch_id == branch_id)
    return query


def get_accessible_warehouses(user=None):
    from models import Warehouse
    return get_accessible_warehouses_query(user).order_by(
        Warehouse.is_main.desc(),
        Warehouse.name,
    ).all()


def get_accessible_warehouse_ids(user=None):
    return [warehouse.id for warehouse in get_accessible_warehouses(user)]


def get_branch_stock_map(product_ids=None, warehouse_ids=None):
    from models import StockMovement
    warehouse_ids = list(warehouse_ids or [])
    if not warehouse_ids:
        return {}

    query = db.session.query(
        StockMovement.product_id,
        func.coalesce(func.sum(StockMovement.quantity), 0).label("qty"),
    ).filter(StockMovement.warehouse_id.in_(warehouse_ids))

    if product_ids:
        query = query.filter(StockMovement.product_id.in_(product_ids))

    return {
        product_id: qty or Decimal("0")
        for product_id, qty in query.group_by(StockMovement.product_id).all()
    }


def get_product_stock(product_id, *, warehouse_id=None, warehouse_ids=None, user=None):
    if warehouse_id is not None:
        warehouse_ids = [warehouse_id]
    elif warehouse_ids is None:
        warehouse_ids = get_accessible_warehouse_ids(user)

    stock_map = get_branch_stock_map(product_ids=[product_id], warehouse_ids=warehouse_ids)
    return stock_map.get(product_id, Decimal("0"))


def get_visible_products_query(user=None):
    from models import Product, StockMovement
    query = apply_tenant_scope(
        Product.query.filter(Product.is_active == True),
        Product,
        user,
    )
    warehouse_ids = get_accessible_warehouse_ids(user)
    if branch_scope_id_for(user) is None:
        return query
    if not warehouse_ids:
        return query.filter(Product.id < 0)
    subq = db.session.query(Product.id).join(
        Product.stock_movements
    ).filter(
        StockMovement.warehouse_id.in_(warehouse_ids)
    ).distinct().subquery()
    return query.filter(Product.id.in_(db.session.query(subq.c.id)))


def user_can_access_warehouse(warehouse_id, user=None):
    from models import Warehouse
    if warehouse_id is None:
        return False
    query = get_accessible_warehouses_query(user).filter(Warehouse.id == warehouse_id)
    return db.session.query(query.exists()).scalar()


def ensure_warehouse_access(warehouse_id, user=None):
    from models import Warehouse
    if not warehouse_id:
        raise ValueError("⚠️ يجب اختيار مستودع صالح.")

    warehouse = get_accessible_warehouses_query(user).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise ValueError("⚠️ المستودع المحدد خارج نطاق الفرع أو غير نشط.")
    return warehouse


branch_scope_id = branch_scope_id_for
