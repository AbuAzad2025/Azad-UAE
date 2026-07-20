"""Unit tests for routes/owner_admin.py — /super-admin landlord interface.

The owner_required guard runs for real (anonymous and tenant admins get 404,
the real platform owner gets in). Provisioning is mocked at the service
boundary; the dashboard renders against the real test database.
"""

from __future__ import annotations

import uuid

import pytest

from services.saas_provisioning_service import SaaSProvisioningError


@pytest.fixture
def platform_owner_client(client, db_session):
    """Real platform owner (is_owner + tenant_id=None) via real login."""
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


@pytest.fixture
def sample_package(db_session):
    from models.package import Package

    unique = str(uuid.uuid4())[:8]
    package = Package(
        name_ar="باقة",
        name_en=f"Pkg {unique}",
        slug=f"pkg-{unique}",
        price=50.0,
        is_active=True,
    )
    db_session.add(package)
    db_session.commit()
    yield package
    db_session.delete(package)
    db_session.commit()


class TestOwnerGuardContract:
    def test_anonymous_gets_404(self, client):
        assert client.get("/super-admin/").status_code == 404

    def test_tenant_admin_gets_404(self, auth_client):
        assert auth_client.get("/super-admin/").status_code == 404

    def test_index_redirects_owner_to_dashboard(self, platform_owner_client):
        resp = platform_owner_client.get("/super-admin/")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/super-admin/dashboard")


class TestDashboard:
    def test_dashboard_renders_with_real_db(self, platform_owner_client):
        resp = platform_owner_client.get("/super-admin/dashboard")
        assert resp.status_code == 200

    def test_activate_form_carries_csrf_token(self, platform_owner_client):
        """Production has WTF_CSRF_ENABLED=True — the manual override form
        must ship a csrf_token input or every submit is rejected with 400."""
        resp = platform_owner_client.get("/super-admin/dashboard")
        html = resp.get_data(as_text=True)
        form_start = html.index('action="/super-admin/activate-subscription"')
        form_end = html.index("</form>", form_start)
        assert 'name="csrf_token"' in html[form_start:form_end]


class TestActivateSubscription:
    _URL = "/super-admin/activate-subscription"

    def test_missing_fields_redirects_without_provisioning(self, platform_owner_client, mocker):
        provision = mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package"
        )
        resp = platform_owner_client.post(self._URL, data={})
        assert resp.status_code == 302
        provision.assert_not_called()

    def test_invalid_duration_rejected(self, platform_owner_client, sample_tenant, sample_package, mocker):
        provision = mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package"
        )
        resp = platform_owner_client.post(
            self._URL,
            data={
                "tenant_id": sample_tenant.id,
                "package_id": sample_package.id,
                "duration_type": "hourly",
            },
        )
        assert resp.status_code == 302
        provision.assert_not_called()

    def test_missing_tenant_rejected(self, platform_owner_client, sample_package, mocker):
        provision = mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package"
        )
        resp = platform_owner_client.post(
            self._URL,
            data={"tenant_id": "999999999", "package_id": sample_package.id},
        )
        assert resp.status_code == 302
        provision.assert_not_called()

    def test_missing_package_rejected(self, platform_owner_client, sample_tenant, mocker):
        provision = mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package"
        )
        resp = platform_owner_client.post(
            self._URL,
            data={"tenant_id": sample_tenant.id, "package_id": "999999999"},
        )
        assert resp.status_code == 302
        provision.assert_not_called()

    def test_valid_activation_calls_provisioning(self, platform_owner_client, sample_tenant, sample_package, mocker):
        provision = mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package",
            return_value={"tenant_id": sample_tenant.id},
        )
        resp = platform_owner_client.post(
            self._URL,
            data={
                "tenant_id": sample_tenant.id,
                "package_id": sample_package.id,
                "duration_type": "monthly",
            },
        )
        assert resp.status_code == 302
        provision.assert_called_once_with(
            tenant_id=sample_tenant.id,
            package_id=sample_package.id,
            duration_type="monthly",
        )

    def test_yearly_duration_normalized_to_annual(self, platform_owner_client, sample_tenant, sample_package, mocker):
        provision = mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package",
            return_value={"tenant_id": sample_tenant.id},
        )
        resp = platform_owner_client.post(
            self._URL,
            data={
                "tenant_id": sample_tenant.id,
                "package_id": sample_package.id,
                "duration_type": "yearly",
            },
        )
        assert resp.status_code == 302
        assert provision.call_args.kwargs["duration_type"] == "annual"

    def test_provisioning_error_flashes_and_redirects(
        self, platform_owner_client, sample_tenant, sample_package, mocker
    ):
        mocker.patch(
            "services.saas_provisioning_service.SaaSProvisioningService.activate_purchased_package",
            side_effect=SaaSProvisioningError("Package inactive"),
        )
        resp = platform_owner_client.post(
            self._URL,
            data={
                "tenant_id": sample_tenant.id,
                "package_id": sample_package.id,
            },
        )
        assert resp.status_code == 302
        with platform_owner_client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert any(category == "danger" for category, _ in flashes)
