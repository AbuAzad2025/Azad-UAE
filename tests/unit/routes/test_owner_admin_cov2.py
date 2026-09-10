"""Coverage boost for routes/owner_admin.py.

Targets: lines 133-135 (generic exception during subscription activation).
Real response path via test client with real platform-owner login; only the
provisioning service (external boundary) is mocked.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def platform_owner_cov2_client(client, db_session):
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
        username=f"powner-cov2-{unique}",
        email=f"powner-cov2-{unique}@example.com",
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


@pytest.fixture
def sample_package_cov2(db_session):
    from models.package import Package

    unique = str(uuid.uuid4())[:8]
    package = Package(
        name_ar="باقة",
        name_en=f"Pkg cov2 {unique}",
        slug=f"pkg-cov2-{unique}",
        price=50.0,
        is_active=True,
    )
    db_session.add(package)
    db_session.commit()
    yield package
    db_session.delete(package)
    db_session.commit()


class TestActivateSubscriptionUnexpectedError:
    """Lines 133-135: generic Exception -> danger flash + redirect."""

    def test_generic_exception_flashes_and_redirects(
        self, platform_owner_cov2_client, sample_tenant, sample_package_cov2, mocker
    ):
        mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package",
            side_effect=RuntimeError("db down"),
        )
        resp = platform_owner_cov2_client.post(
            "/super-admin/activate-subscription",
            data={
                "tenant_id": sample_tenant.id,
                "package_id": sample_package_cov2.id,
                "duration_type": "monthly",
            },
        )
        assert resp.status_code == 302
        with platform_owner_cov2_client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert any(category == "danger" for category, _ in flashes)
