"""Tests for routes/assets.py — 10 distinct endpoints (GET/POST)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound

from tests.unit.routes.conftest import unauthenticated_client


def _mock_asset(**kwargs):
    asset = MagicMock()
    asset.id = kwargs.get("id", 1)
    asset.tenant_id = kwargs.get("tenant_id", 1)
    asset.asset_number = kwargs.get("asset_number", "FA-0001")
    asset.name_ar = kwargs.get("name_ar", "أصل اختبار")
    asset.status = kwargs.get("status", "active")
    asset.accumulated_depreciation = kwargs.get("accumulated_depreciation", Decimal("0"))
    asset.book_value = kwargs.get("book_value", Decimal("1000"))
    asset.depreciation_schedules = kwargs.get("depreciation_schedules", [])
    return asset


@pytest.fixture
def assets_client(app_factory, bypass_permission_auth):
    from routes.assets import assets_bp

    app = app_factory(assets_bp)
    return app.test_client()


@pytest.fixture
def assets_mocks():
    asset = _mock_asset()
    patches = [
        patch("routes.assets.AssetService.list_assets", return_value=[asset]),
        patch("routes.assets.AssetService.get_asset_summary", return_value={"total": 1, "active": 1}),
        patch("routes.assets.AssetService.create_asset", return_value=asset),
        patch("routes.assets.AssetService.update_asset", return_value=asset),
        patch("routes.assets.AssetService.post_manual_depreciation", return_value=MagicMock()),
        patch("routes.assets.AssetService.dispose_asset", return_value=asset),
        patch("routes.assets.AssetService.get_depreciation_schedule", return_value=[]),
        patch("routes.assets.tenant_get_or_404", return_value=asset),
        patch("routes.assets.render_template", return_value="ok"),
    ]
    for p in patches:
        p.start()
    yield {"asset": asset}
    for p in reversed(patches):
        p.stop()


class TestAssetsAuth:
    def test_index_requires_login(self, assets_client):
        with unauthenticated_client(assets_client):
            resp = assets_client.get("/assets/")
        assert resp.status_code == 401

    def test_index_forbidden_without_permission(self, assets_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = assets_client.get("/assets/")
        assert resp.status_code == 403

    def test_create_forbidden(self, assets_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = assets_client.get("/assets/create")
        assert resp.status_code == 403

    def test_detail_forbidden(self, assets_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = assets_client.get("/assets/1")
        assert resp.status_code == 403

    def test_depreciate_forbidden(self, assets_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = assets_client.post("/assets/1/depreciate")
        assert resp.status_code == 403


class TestAssetsIndex:
    def test_index_happy(self, assets_client, assets_mocks):
        resp = assets_client.get("/assets/")
        assert resp.status_code == 200

    def test_index_with_filters(self, assets_client, assets_mocks):
        with patch("routes.assets.AssetService.list_assets", return_value=[]) as mock_list:
            resp = assets_client.get("/assets/?status=active&category=equipment")
        assert resp.status_code == 200
        mock_list.assert_called_once()

    def test_index_tenant_isolation_uses_scoped_assets(self, assets_client, assets_mocks):
        with patch("routes.assets.AssetService.list_assets", return_value=[]) as m:
            assets_client.get("/assets/")
            # tenant isolation is via service; ensure service called
            assert m.called


class TestAssetsCreate:
    def test_create_get_happy(self, assets_client, assets_mocks):
        resp = assets_client.get("/assets/create")
        assert resp.status_code == 200

    def test_create_post_success_redirect(self, assets_client, assets_mocks):
        asset = assets_mocks["asset"]
        with patch("routes.assets.AssetService.create_asset", return_value=asset) as mock_create:
            resp = assets_client.post(
                "/assets/create", data={"name_ar": "أصل جديد", "asset_account_id": "1"}, follow_redirects=False
            )
        assert resp.status_code == 302
        assert "/assets/1" in resp.location
        mock_create.assert_called_once()

    def test_create_post_validation_error_stays_200(self, assets_client, assets_mocks):
        with patch("routes.assets.AssetService.create_asset", side_effect=ValueError("invalid purchase_price")):
            resp = assets_client.post("/assets/create", data={"name_ar": "bad"})
        assert resp.status_code == 200

    def test_create_post_key_error_stays_200(self, assets_client, assets_mocks):
        with patch("routes.assets.AssetService.create_asset", side_effect=KeyError("name_ar")):
            resp = assets_client.post("/assets/create", data={})
        assert resp.status_code == 200


class TestAssetsDetail:
    def test_detail_happy(self, assets_client, assets_mocks):
        resp = assets_client.get("/assets/1")
        assert resp.status_code == 200

    def test_detail_404_tenant_isolation(self, assets_client, assets_mocks):
        with patch("routes.assets.tenant_get_or_404", side_effect=NotFound()):
            resp = assets_client.get("/assets/999")
        assert resp.status_code == 404


class TestAssetsEdit:
    def test_edit_get_happy(self, assets_client, assets_mocks):
        resp = assets_client.get("/assets/1/edit")
        assert resp.status_code == 200

    def test_edit_post_success_redirect(self, assets_client, assets_mocks):
        resp = assets_client.post("/assets/1/edit", data={"name_ar": "محدث"}, follow_redirects=False)
        assert resp.status_code == 302
        assert "/assets/1" in resp.location

    def test_edit_post_validation_error_stays_200(self, assets_client, assets_mocks):
        with patch("routes.assets.AssetService.update_asset", side_effect=ValueError("لا يمكن تعديل أصل غير نشط.")):
            resp = assets_client.post("/assets/1/edit", data={"name_ar": "x"})
        assert resp.status_code == 200

    def test_edit_404(self, assets_client, assets_mocks):
        with patch("routes.assets.tenant_get_or_404", side_effect=NotFound()):
            resp = assets_client.get("/assets/999/edit")
        assert resp.status_code == 404


class TestAssetsDepreciate:
    def test_depreciate_happy(self, assets_client, assets_mocks):
        resp = assets_client.post("/assets/1/depreciate", follow_redirects=False)
        assert resp.status_code == 302
        assert "/assets/1" in resp.location

    def test_depreciate_validation_error_stays_redirect(self, assets_client, assets_mocks):
        with patch("routes.assets.AssetService.post_manual_depreciation", side_effect=ValueError("الأصل غير نشط.")):
            resp = assets_client.post("/assets/1/depreciate", follow_redirects=False)
        assert resp.status_code == 302

    def test_depreciate_404(self, assets_client, assets_mocks):
        with patch("routes.assets.tenant_get_or_404", side_effect=NotFound()):
            resp = assets_client.post("/assets/1/depreciate")
        assert resp.status_code == 404


class TestAssetsDispose:
    def test_dispose_get_happy(self, assets_client, assets_mocks):
        resp = assets_client.get("/assets/1/dispose")
        assert resp.status_code == 200

    def test_dispose_post_success_redirect(self, assets_client, assets_mocks):
        resp = assets_client.post(
            "/assets/1/dispose",
            data={"disposal_date": "2026-08-01", "disposal_price": "500"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/assets/1" in resp.location

    def test_dispose_post_without_date_uses_today(self, assets_client, assets_mocks):
        resp = assets_client.post("/assets/1/dispose", data={"disposal_price": "0"}, follow_redirects=False)
        assert resp.status_code == 302

    def test_dispose_post_validation_error_stays_200(self, assets_client, assets_mocks):
        with patch("routes.assets.AssetService.dispose_asset", side_effect=ValueError("تم التخلص من الأصل مسبقاً")):
            resp = assets_client.post("/assets/1/dispose", data={"disposal_price": "0"})
        assert resp.status_code == 200

    def test_dispose_404(self, assets_client, assets_mocks):
        with patch("routes.assets.tenant_get_or_404", side_effect=NotFound()):
            resp = assets_client.get("/assets/999/dispose")
        assert resp.status_code == 404


class TestAssetsDepreciationSchedule:
    def test_depreciation_schedule_happy(self, assets_client, assets_mocks):
        resp = assets_client.get("/assets/depreciation-schedule")
        assert resp.status_code == 200

    def test_depreciation_schedule_forbidden(self, assets_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = assets_client.get("/assets/depreciation-schedule")
        assert resp.status_code == 403
