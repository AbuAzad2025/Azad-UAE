"""
Chunk 2 — routes/owner.py 3 write-heavy JSON API endpoints:
  1. POST /owner/api/update-tenant-settings          (@company_admin_required)
  2. POST /owner/api/tenant/<id>/toggle-status       (@owner_required)
  3. POST /owner/api/tenant/<id>/update-package      (@owner_required)
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from tests.unit.routes.test_owner_routes import _owner_route_patches


@pytest.fixture
def owner_client(app_factory, bypass_owner_auth):
    with _owner_route_patches():
        from routes.owner import owner_bp

        app = app_factory(
            owner_bp,
            {"SQLALCHEMY_DATABASE_URI": "postgresql://user:pass@localhost/testdb"},
        )
        yield app.test_client()


@pytest.fixture
def company_admin_client(app_factory, bypass_company_admin_auth):
    with _owner_route_patches():
        from routes.owner import owner_bp

        app = app_factory(
            owner_bp,
            {"SQLALCHEMY_DATABASE_URI": "postgresql://user:pass@localhost/testdb"},
        )
        yield app.test_client()


@pytest.fixture
def mock_settings_db(mocker):
    mock = MagicMock()
    mocker.patch("routes.owner.settings.db", mock)
    return mock


@pytest.fixture
def mock_tenants_db(mocker):
    mock = MagicMock()
    mocker.patch("routes.owner.tenants.db", mock)
    return mock


class TestApiUpdateTenantSettings:
    """POST /owner/api/update-tenant-settings — brand/theme settings per tenant."""

    def test_missing_json_returns_400(self, company_admin_client):
        resp = company_admin_client.post(
            "/owner/api/update-tenant-settings",
            data={},
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 400
        assert resp.json["error"] == "JSON required"

    def test_unknown_field_returns_400(self, company_admin_client, mocker, mock_settings_db):
        mocker.patch("routes.owner.settings.Tenant")
        mock_settings_db.session.get.return_value = MagicMock(id=1)
        resp = company_admin_client.post(
            "/owner/api/update-tenant-settings",
            json={"field": "bogus", "value": "x"},
        )
        assert resp.status_code == 400
        assert "Unknown" in resp.json["error"]

    def test_invalid_tax_rate_returns_400(
        self,
        company_admin_client,
        mocker,
        mock_settings_db,
    ):
        mocker.patch("routes.owner.settings.Tenant")
        mock_settings_db.session.get.return_value = MagicMock(id=1)
        resp = company_admin_client.post(
            "/owner/api/update-tenant-settings",
            json={"field": "default_tax_rate", "value": "not-a-number"},
        )
        assert resp.status_code == 400
        assert "Invalid tax rate" in resp.json["error"]

    def test_tenant_not_found_returns_404(
        self,
        company_admin_client,
        mocker,
        mock_settings_db,
    ):
        mocker.patch("routes.owner.settings.Tenant")
        mock_settings_db.session.get.return_value = None
        resp = company_admin_client.post(
            "/owner/api/update-tenant-settings",
            json={"field": "default_tax_rate", "value": "10"},
        )
        assert resp.status_code == 404
        assert resp.json["error"] == "Tenant not found"

    def test_success_default_tax_rate(
        self,
        company_admin_client,
        mocker,
        mock_settings_db,
    ):
        mocker.patch("routes.owner.settings.Tenant")
        inst = MagicMock()
        mock_settings_db.session.get.return_value = inst
        mocker.patch("routes.owner.settings._invalidate_owner_changes")
        mocker.patch("routes.owner.settings._audit_owner_db_action")

        resp = company_admin_client.post(
            "/owner/api/update-tenant-settings",
            json={"field": "default_tax_rate", "value": "10"},
        )
        assert resp.status_code == 200
        assert resp.json["success"] is True
        assert inst.default_tax_rate == Decimal("10")

    def test_success_prices_include_vat(
        self,
        company_admin_client,
        mocker,
        mock_settings_db,
    ):
        mocker.patch("routes.owner.settings.Tenant")
        inst = MagicMock()
        mock_settings_db.session.get.return_value = inst
        mocker.patch("routes.owner.settings._invalidate_owner_changes")
        mocker.patch("routes.owner.settings._audit_owner_db_action")

        resp = company_admin_client.post(
            "/owner/api/update-tenant-settings",
            json={"field": "prices_include_vat", "value": True},
        )
        assert resp.status_code == 200
        assert inst.prices_include_vat is True

    def test_success_logo_url(
        self,
        company_admin_client,
        mocker,
        mock_settings_db,
    ):
        mocker.patch("routes.owner.settings.Tenant")
        inst = MagicMock()
        mock_settings_db.session.get.return_value = inst
        mocker.patch("routes.owner.settings._invalidate_owner_changes")
        mocker.patch("routes.owner.settings._audit_owner_db_action")

        resp = company_admin_client.post(
            "/owner/api/update-tenant-settings",
            json={"field": "logo_url", "value": "https://example.com/logo.png"},
        )
        assert resp.status_code == 200
        assert inst.logo_url == "https://example.com/logo.png"

    def test_exception_path_returns_500(
        self,
        company_admin_client,
        mocker,
        mock_settings_db,
    ):
        mocker.patch("routes.owner.settings.Tenant")
        mock_settings_db.session.get.side_effect = RuntimeError("DB exploded")
        mocker.patch("routes.owner.settings._invalidate_owner_changes")
        mocker.patch("routes.owner.settings._audit_owner_db_action")

        resp = company_admin_client.post(
            "/owner/api/update-tenant-settings",
            json={"field": "default_tax_rate", "value": "10"},
        )
        assert resp.status_code == 500
        assert resp.json["success"] is False

    # ------------------------------------------------------------------
    # Edge: field is None or empty
    # ------------------------------------------------------------------

    def test_none_field_returns_400(
        self,
        company_admin_client,
        mocker,
        mock_settings_db,
    ):
        mocker.patch("routes.owner.settings.Tenant")
        mock_settings_db.session.get.return_value = MagicMock(id=1)
        resp = company_admin_client.post(
            "/owner/api/update-tenant-settings",
            json={"value": "x"},
        )
        assert resp.status_code == 400
        assert "Unknown" in resp.json["error"]

    def test_none_value_defaults_to_none_string_for_logo(
        self,
        company_admin_client,
        mocker,
        mock_settings_db,
    ):
        mocker.patch("routes.owner.settings.Tenant")
        inst = MagicMock()
        mock_settings_db.session.get.return_value = inst
        mocker.patch("routes.owner.settings._invalidate_owner_changes")
        mocker.patch("routes.owner.settings._audit_owner_db_action")

        resp = company_admin_client.post(
            "/owner/api/update-tenant-settings",
            json={"field": "logo_url"},
        )
        assert resp.status_code == 200
        assert inst.logo_url == "None"  # str(None).strip()


class TestApiTenantToggleStatus:
    """POST /owner/api/tenant/<id>/toggle-status — activate/deactivate tenant."""

    def test_missing_json_returns_400(self, owner_client):
        resp = owner_client.post(
            "/owner/api/tenant/2/toggle-status",
            data={},
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 400
        assert resp.json["error"] == "JSON required"

    def test_tenant_not_found_returns_404(
        self,
        owner_client,
        mocker,
        mock_tenants_db,
    ):
        mocker.patch("routes.owner.tenants.Tenant")
        mock_tenants_db.session.get.return_value = None

        resp = owner_client.post(
            "/owner/api/tenant/999/toggle-status",
            json={},
        )
        assert resp.status_code == 404
        assert resp.json["error"] == "Tenant not found"

    def test_master_tenant_cannot_be_toggled(
        self,
        owner_client,
        mocker,
        mock_tenants_db,
    ):
        mocker.patch("routes.owner.tenants.Tenant")
        inst = MagicMock()
        inst.id = 1
        mock_tenants_db.session.get.return_value = inst

        resp = owner_client.post(
            "/owner/api/tenant/1/toggle-status",
            json={},
        )
        assert resp.status_code == 400
        assert "لا يمكن تعطيل" in resp.json["error"]

    def test_success_toggle_active_to_inactive(
        self,
        owner_client,
        mocker,
        mock_tenants_db,
    ):
        mocker.patch("routes.owner.tenants.Tenant")
        inst = MagicMock()
        inst.id = 2
        inst.is_active = True
        inst.name_ar = "شركة اختبار"
        inst.name = "Test Co"
        mock_tenants_db.session.get.return_value = inst
        mocker.patch("routes.owner.tenants._invalidate_owner_changes")
        mocker.patch("routes.owner.tenants._audit_owner_db_action")

        resp = owner_client.post(
            "/owner/api/tenant/2/toggle-status",
            json={},
        )
        assert resp.status_code == 200
        assert resp.json["success"] is True
        assert resp.json["is_active"] is False
        assert inst.is_active is False
        assert inst.is_suspended is True
        assert inst.suspension_reason == "Disabled via API"

    def test_success_toggle_inactive_to_active(
        self,
        owner_client,
        mocker,
        mock_tenants_db,
    ):
        mocker.patch("routes.owner.tenants.Tenant")
        inst = MagicMock()
        inst.id = 2
        inst.is_active = False
        inst.name_ar = "شركة اختبار"
        inst.name = "Test Co"
        mock_tenants_db.session.get.return_value = inst
        mocker.patch("routes.owner.tenants._invalidate_owner_changes")
        mocker.patch("routes.owner.tenants._audit_owner_db_action")

        resp = owner_client.post(
            "/owner/api/tenant/2/toggle-status",
            json={},
        )
        assert resp.status_code == 200
        assert resp.json["success"] is True
        assert resp.json["is_active"] is True
        assert inst.is_active is True
        assert inst.is_suspended is False
        assert inst.suspension_reason is None

    def test_exception_path_returns_500(
        self,
        owner_client,
        mocker,
        mock_tenants_db,
    ):
        mocker.patch("routes.owner.tenants.Tenant")
        mock_tenants_db.session.get.side_effect = RuntimeError("DB exploded")
        mocker.patch("routes.owner.tenants._invalidate_owner_changes")
        mocker.patch("routes.owner.tenants._audit_owner_db_action")

        resp = owner_client.post(
            "/owner/api/tenant/2/toggle-status",
            json={},
        )
        assert resp.status_code == 500
        assert resp.json["success"] is False


class TestApiTenantUpdatePackage:
    """POST /owner/api/tenant/<id>/update-package — upgrade/downgrade package."""

    allowed = [
        "max_users",
        "max_products",
        "max_customers",
        "max_suppliers",
        "max_branches",
        "max_warehouses",
        "max_invoices_per_month",
        "max_sales_per_month",
    ]

    def test_missing_json_returns_400(self, owner_client):
        resp = owner_client.post(
            "/owner/api/tenant/2/update-package",
            data={},
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 400
        assert resp.json["error"] == "JSON required"

    def test_tenant_not_found_returns_404(
        self,
        owner_client,
        mocker,
        mock_tenants_db,
    ):
        mocker.patch("routes.owner.tenants.Tenant")
        mock_tenants_db.session.get.return_value = None

        resp = owner_client.post(
            "/owner/api/tenant/999/update-package",
            json={},
        )
        assert resp.status_code == 404
        assert resp.json["error"] == "Tenant not found"

    def test_unknown_field_returns_400(
        self,
        owner_client,
        mocker,
        mock_tenants_db,
    ):
        mocker.patch("routes.owner.tenants.Tenant")
        mock_tenants_db.session.get.return_value = MagicMock(id=2)

        resp = owner_client.post(
            "/owner/api/tenant/2/update-package",
            json={"field": "bogus", "value": "10"},
        )
        assert resp.status_code == 400
        assert "Unknown" in resp.json["error"]

    def test_invalid_value_returns_400(
        self,
        owner_client,
        mocker,
        mock_tenants_db,
    ):
        mocker.patch("routes.owner.tenants.Tenant")
        mock_tenants_db.session.get.return_value = MagicMock(id=2)

        resp = owner_client.post(
            "/owner/api/tenant/2/update-package",
            json={"field": "max_users", "value": "not-a-number"},
        )
        assert resp.status_code == 400
        assert "Invalid integer" in resp.json["error"]

    def test_none_field_returns_400(
        self,
        owner_client,
        mocker,
        mock_tenants_db,
    ):
        mocker.patch("routes.owner.tenants.Tenant")
        mock_tenants_db.session.get.return_value = MagicMock(id=2)

        resp = owner_client.post(
            "/owner/api/tenant/2/update-package",
            json={"value": "10"},
        )
        assert resp.status_code == 400
        assert "Unknown" in resp.json["error"]

    def test_success_each_allowed_field(
        self,
        owner_client,
        mocker,
        mock_tenants_db,
    ):
        mocker.patch("routes.owner.tenants.Tenant")
        inst = MagicMock()
        mock_tenants_db.session.get.return_value = inst
        mocker.patch("routes.owner.tenants._invalidate_owner_changes")
        mocker.patch("routes.owner.tenants._audit_owner_db_action")

        for idx, field in enumerate(self.allowed, start=1):
            value = idx * 10
            resp = owner_client.post(
                "/owner/api/tenant/2/update-package",
                json={"field": field, "value": str(value)},
            )
            assert resp.status_code == 200
            assert resp.json["success"] is True
            assert getattr(inst, field) == value

    def test_exception_path_returns_500(
        self,
        owner_client,
        mocker,
        mock_tenants_db,
    ):
        mocker.patch("routes.owner.tenants.Tenant")
        mock_tenants_db.session.get.side_effect = RuntimeError("DB exploded")
        mocker.patch("routes.owner.tenants._invalidate_owner_changes")
        mocker.patch("routes.owner.tenants._audit_owner_db_action")

        resp = owner_client.post(
            "/owner/api/tenant/2/update-package",
            json={"field": "max_users", "value": "10"},
        )
        assert resp.status_code == 500
        assert resp.json["success"] is False
