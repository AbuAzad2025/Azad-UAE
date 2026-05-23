from flask import session


ACTIVE_TENANT_SESSION_KEY = "active_tenant_id"


def is_global_tenant_user(user):
    if not user:
        return False
    if getattr(user, "is_owner", False):
        return True
    role = getattr(user, "role", None)
    slug = getattr(role, "slug", None) if role else None
    return slug in {"super_admin", "developer"}


def get_active_tenant_id(user=None):
    if user and not is_global_tenant_user(user):
        tid = getattr(user, "tenant_id", None)
        return int(tid) if tid else None

    tid = session.get(ACTIVE_TENANT_SESSION_KEY)
    if tid:
        try:
            return int(tid)
        except Exception:
            return None

    if user:
        tid2 = getattr(user, "tenant_id", None)
        return int(tid2) if tid2 else None

    return None


def set_active_tenant(tenant_id):
    if tenant_id is None or tenant_id == "":
        session.pop(ACTIVE_TENANT_SESSION_KEY, None)
        return
    session[ACTIVE_TENANT_SESSION_KEY] = int(tenant_id)


def clear_active_tenant():
    session.pop(ACTIVE_TENANT_SESSION_KEY, None)

