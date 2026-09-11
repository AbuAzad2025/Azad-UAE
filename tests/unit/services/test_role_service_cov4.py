"""Cov4: role_service — context with/without tenant + empty-category arcs."""

from __future__ import annotations

from services.role_service import RoleService


def test_context_without_tenant(db_session, sample_tenant):
    ctx = RoleService.get_roles_permissions_context()
    assert set(ctx) == {"roles", "permissions", "perm_categories", "role_user_counts"}
    assert isinstance(ctx["roles"], list)
    assert isinstance(ctx["permissions"], list)
    assert all(isinstance(v, int) for v in ctx["role_user_counts"].values())


def test_context_with_tenant_scopes_counts(db_session, sample_tenant, sample_user):
    ctx = RoleService.get_roles_permissions_context(tenant_id=sample_tenant.id)
    assert ctx["role_user_counts"].get(sample_user.role_id, 0) >= 1
    ctx2 = RoleService.get_roles_permissions_context(tenant_id=-999)
    assert all(v == 0 for v in ctx2["role_user_counts"].values())


def test_perm_categories_groups_uncategorized(db_session):
    from models import Permission

    p = Permission.query.first()
    if p is not None:
        p.category = None
        db_session.flush()
    ctx = RoleService.get_roles_permissions_context()
    assert sum(len(v) for v in ctx["perm_categories"].values()) == len(ctx["permissions"])
