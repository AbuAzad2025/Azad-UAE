from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def platform_owner_client(client, db_session):
    from models import Role, User

    unique = str(uuid.uuid4())[:8]
    role = db_session.query(Role).filter_by(slug="owner").first()
    created_role = None
    if not role:
        role = Role(name="Owner", slug="owner", is_active=True)
        db_session.add(role)
        db_session.flush()
        created_role = role
    user = User(
        username=f"powner-{unique}",
        email=f"powner-{unique}@example.com",
        full_name="Platform Owner",
        tenant_id=None,
        role_id=role.id,
        is_owner=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=False,
    )
    yield client
    db_session.delete(user)
    if created_role is not None:
        db_session.delete(created_role)
    db_session.commit()


class TestReproPollution:
    def test_dashboard_view_directly(self, app, platform_owner_client):
        from routes.owner_admin import dashboard

        fn = dashboard
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        with app.test_request_context("/super-admin/dashboard"):
            html = fn()
        assert html
