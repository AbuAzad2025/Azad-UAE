import json
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def _clear_login_cache(app):
    from flask import g
    g.pop("_login_user", None)


@pytest.fixture(scope="module")
def pos_owner(app):
    with app.app_context():
        from models import Tenant, Role, User
        from extensions import db
        tenant = Tenant(name="POS Align Tenant", name_ar="Align", slug="pos-align-tenant", country="AE")
        db.session.add(tenant)
        db.session.commit()
        role = Role(name="POS Align Owner", slug="pos_align_owner", is_active=True)
        db.session.add(role)
        db.session.commit()
        user = User(
            username="pos_align_owner", email="align@test.com", full_name="POS Align Owner",
            tenant_id=tenant.id, role_id=role.id, is_active=True, is_owner=True,
        )
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()
        return user


def _login_owner(client, pos_owner):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(pos_owner.id)
        sess["_fresh"] = True


class TestPosHtmlDisabledPage:
    def test_pos_index_html_disabled_system(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = False
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    resp = client.get("/pos/")
                    assert resp.status_code == 403
                    assert b"<html" in resp.data
                    assert b"alert-warning" in resp.data

    def test_pos_index_html_disabled_tenant(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = False
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    resp = client.get("/pos/")
                    assert resp.status_code == 403
                    assert b"<html" in resp.data
                    assert b"alert-warning" in resp.data


class TestPosApiStillJson:
    def test_api_products_json_disabled(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = False
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant"):
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    resp = client.get("/pos/api/products?q=test")
                    assert resp.status_code == 403
                    data = json.loads(resp.data)
                    assert data["success"] is False

    def test_api_checkout_json_disabled(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = False
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant"):
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    resp = client.post("/pos/api/checkout", json={"lines": []})
                    assert resp.status_code == 403
                    data = json.loads(resp.data)
                    assert data["success"] is False


