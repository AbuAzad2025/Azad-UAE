"""Cov5: user_service — unscoped lookup + full create arcs."""

from __future__ import annotations


def test_get_scoped_without_tenant(db_session, sample_tenant, sample_user):
    from services.user_service import UserService

    out = UserService.get_scoped_non_owner_or_404(sample_user.id, None)
    assert out.id == sample_user.id


def test_create_user_with_tenant_and_role(db_session, sample_tenant, sample_role):
    from services.user_service import UserService

    u = UserService.create_user(
        "cov5-user",
        "Cov Five",
        email="cov5@example.com",
        tenant_id=sample_tenant.id,
        role_id=sample_role.id,
    )
    db_session.flush()
    assert u.tenant_id == sample_tenant.id
    assert u.role_id == sample_role.id
