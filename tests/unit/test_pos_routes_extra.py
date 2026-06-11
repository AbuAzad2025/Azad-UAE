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
        tenant = Tenant(name="POS Extra Tenant", name_ar="Test POS Extra", slug="pos-test-tenant-extra", country="AE")
        db.session.add(tenant)
        db.session.commit()
        role = Role(name="POS Owner Extra", slug="pos_owner_extra", is_active=True)
        db.session.add(role)
        db.session.commit()
        user = User(
            username="pos_test_owner_extra", email="posextra@test.com", full_name="POS Test Owner Extra",
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


class TestPosEnableGuardExtra:
    def test_pos_no_global_setting_allows_access(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            MockSettings.query.order_by.return_value.first.return_value = None
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.search_pos_products", return_value=([], {}, [])):
                        resp = client.get("/pos/api/products?q=test")
                        assert resp.status_code == 200

    def test_pos_no_tenant_id_allows_access(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.get_active_tenant_id", return_value=None):
                with patch("routes.pos.search_pos_products", return_value=([], {}, [])):
                    resp = client.get("/pos/api/products?q=test")
                    assert resp.status_code == 200

    def test_pos_tenant_not_found_allows_access(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                MockTenant.query.get.return_value = None
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.search_pos_products", return_value=([], {}, [])):
                        resp = client.get("/pos/api/products?q=test")
                        assert resp.status_code == 200


class TestPosApiProductLookupExtra:
    def test_api_product_lookup_out_of_stock(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    product = MagicMock()
                    product.id = 1
                    product.name = "Item"
                    product.is_active = True
                    with patch("routes.pos.lookup_pos_product_exact", return_value=(product, {1: 0})):
                        payload = {"id": 1, "name": "Item", "is_out_of_stock": True}
                        with patch("routes.pos.serialize_pos_product", return_value=payload):
                            resp = client.get("/pos/api/product?code=123")
                            assert resp.status_code == 200
                            data = json.loads(resp.data)
                            assert data["warning"] == "لا يوجد مخزون في المستودع المحدد."


class TestPosApiCustomersExtra:
    def test_api_customers_empty_results(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.tenant_query") as mock_query:
                        base = mock_query.return_value.filter_by.return_value.filter.return_value
                        chain = base.order_by.return_value.limit.return_value
                        chain.all.return_value = []
                        resp = client.get("/pos/api/customers?q=zzz")
                        assert resp.status_code == 200
                        data = json.loads(resp.data)
                        assert data == []


class TestPosApiWalkinExtra:
    def test_api_walkin_error_returns_400(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.get_pos_walkin_customer", side_effect=ValueError("missing")):
                        resp = client.get("/pos/api/walkin-customer")
                        assert resp.status_code == 400
                        data = json.loads(resp.data)
                        assert data["success"] is False


class TestPosApiCheckoutExtra:
    def test_checkout_quick_customer_flag(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.get_active_session") as mock_session:
                        mock_session.return_value = MagicMock()
                        customer = MagicMock()
                        customer.id = 1
                        customer.name = "Walkin"
                        with patch("routes.pos.get_pos_walkin_customer", return_value=customer):
                            product = MagicMock()
                            product.id = 1
                            product.is_active = True
                            with patch("routes.pos.tenant_get", return_value=product):
                                sale = MagicMock()
                                sale.id = 300
                                sale.sale_number = "S-2024-004"
                                sale.grand_total = 75
                                with patch("routes.pos.SaleService.create_sale", return_value=sale):
                                    with patch("routes.pos.log_mutation"):
                                        with patch("routes.pos.db"):
                                            resp = client.post(
                                                "/pos/api/checkout",
                                                json={
                                                    "lines": [{"product_id": 1, "quantity": 1, "discount_percent": 0}],
                                                    "quick_customer": True,
                                                    "payment_method": "cash",
                                                    "paid_amount": 75,
                                                },
                                                headers={"Content-Type": "application/json"},
                                            )
                                            assert resp.status_code == 200
                                            data = json.loads(resp.data)
                                            assert data["success"] is True

    def test_checkout_invalid_customer_id(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.tenant_get", return_value=None):
                        resp = client.post(
                            "/pos/api/checkout",
                            json={
                                "lines": [{"product_id": 1, "quantity": 1, "discount_percent": 0}],
                                "customer_id": 999,
                            },
                            headers={"Content-Type": "application/json"},
                        )
                        assert resp.status_code == 400
                        data = json.loads(resp.data)
                        assert data["success"] is False

    def test_checkout_inactive_customer(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    customer = MagicMock()
                    customer.is_active = False
                    with patch("routes.pos.tenant_get", return_value=customer):
                        resp = client.post(
                            "/pos/api/checkout",
                            json={
                                "lines": [{"product_id": 1, "quantity": 1, "discount_percent": 0}],
                                "customer_id": 1,
                            },
                            headers={"Content-Type": "application/json"},
                        )
                        assert resp.status_code == 400
                        data = json.loads(resp.data)
                        assert data["success"] is False

    def test_checkout_invalid_warehouse(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    customer = MagicMock()
                    with patch("routes.pos.get_pos_walkin_customer", return_value=customer):
                        with patch("routes.pos.ensure_warehouse_access", side_effect=ValueError("denied")):
                            resp = client.post(
                                "/pos/api/checkout",
                                json={
                                    "lines": [{"product_id": 1, "quantity": 1, "discount_percent": 0}],
                                    "warehouse_id": 99,
                                    "payment_method": "cash",
                                    "paid_amount": 10,
                                },
                                headers={"Content-Type": "application/json"},
                            )
                            assert resp.status_code == 400
                            data = json.loads(resp.data)
                            assert data["success"] is False

    def test_checkout_invalid_merge_lines(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.merge_checkout_lines", side_effect=ValueError("bad")):
                        resp = client.post(
                            "/pos/api/checkout",
                            json={
                                "lines": [{"product_id": 1, "quantity": 1, "discount_percent": 0}],
                            },
                            headers={"Content-Type": "application/json"},
                        )
                        assert resp.status_code == 400
                        data = json.loads(resp.data)
                        assert data["success"] is False

    def test_checkout_paid_without_payment_method(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    customer = MagicMock()
                    with patch("routes.pos.get_pos_walkin_customer", return_value=customer):
                        product = MagicMock()
                        product.id = 1
                        product.is_active = True
                        with patch("routes.pos.tenant_get", return_value=product):
                            resp = client.post(
                                "/pos/api/checkout",
                                json={
                                    "lines": [
                                        {"product_id": 1, "quantity": 1, "discount_percent": 0, "unit_price": 50}
                                    ],
                                    "paid_amount": 50,
                                },
                                headers={"Content-Type": "application/json"},
                            )
                            assert resp.status_code == 400
                            data = json.loads(resp.data)
                            assert data["success"] is False

    def test_checkout_inactive_product(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    customer = MagicMock()
                    with patch("routes.pos.get_pos_walkin_customer", return_value=customer):
                        product = MagicMock()
                        product.id = 1
                        product.is_active = False
                        with patch("routes.pos.tenant_get", return_value=product):
                            resp = client.post(
                                "/pos/api/checkout",
                                json={
                                    "lines": [{"product_id": 1, "quantity": 1, "discount_percent": 0}],
                                },
                                headers={"Content-Type": "application/json"},
                            )
                            assert resp.status_code == 400
                            data = json.loads(resp.data)
                            assert data["success"] is False

    def test_checkout_qa_marker(self, app, client, pos_owner):
        with client.session_transaction() as sess:
            sess["_user_id"] = str(pos_owner.id)
            sess["_fresh"] = True
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    customer = MagicMock()
                    customer.id = 1
                    customer.name = "Walkin"
                    with patch("routes.pos.get_pos_walkin_customer", return_value=customer):
                        product = MagicMock()
                        product.id = 1
                        product.is_active = True
                        with patch("routes.pos.tenant_get", return_value=product):
                            sale = MagicMock()
                            sale.id = 400
                            sale.sale_number = "S-QA-001"
                            sale.grand_total = 20
                            with patch("routes.pos.SaleService.create_sale", return_value=sale) as mock_create:
                                with patch("routes.pos.log_mutation"):
                                    with patch("routes.pos.db"):
                                        resp = client.post(
                                            "/pos/api/checkout",
                                            json={
                                                "lines": [{"product_id": 1, "quantity": 1, "discount_percent": 0}],
                                                "qa_marker": True,
                                                "notes": "test note",
                                            },
                                            headers={"Content-Type": "application/json"},
                                        )
                                        assert resp.status_code == 200
                                        call_kwargs = mock_create.call_args.kwargs
                                        assert "POS-QA" in (call_kwargs.get("notes") or "")
