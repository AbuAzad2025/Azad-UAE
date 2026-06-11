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
        tenant = Tenant(name="POS Test Tenant", name_ar="Test POS", slug="pos-test-tenant", country="AE")
        db.session.add(tenant)
        db.session.commit()
        role = Role(name="POS Owner", slug="pos_owner", is_active=True)
        db.session.add(role)
        db.session.commit()
        user = User(username="pos_test_owner", email="pos@test.com", full_name="POS Test Owner", tenant_id=tenant.id, role_id=role.id, is_active=True, is_owner=True)
        user.set_password("testpass")
        db.session.add(user)
        db.session.commit()
        return user

def _login_owner(client, pos_owner):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(pos_owner.id)
        sess["_fresh"] = True

class TestPosEnableGuard:
    def test_pos_disabled_globally_returns_403(self, app, client, pos_owner):
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
    def test_pos_disabled_for_tenant_returns_403(self, app, client, pos_owner):
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
                    resp = client.get("/pos/api/products?q=test")
                    assert resp.status_code == 403
                    data = json.loads(resp.data)
                    assert data["success"] is False
    def test_pos_enabled_allows_access(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.search_pos_products", return_value=([], {}, [])):
                        resp = client.get("/pos/api/products?q=test")
                        assert resp.status_code == 200
                        data = json.loads(resp.data)
                        assert isinstance(data, list)

class TestPosIndex:
    def test_pos_index_requires_login(self, client):
        resp = client.get("/pos/", follow_redirects=False)
        assert resp.status_code in (302, 401, 403)
    def test_pos_index_loads_for_authenticated_user(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.get_accessible_warehouses", return_value=[]):
                        resp = client.get("/pos/")
                        assert resp.status_code == 200
                        assert b"POS" in resp.data or b"\xd9\x86\xd9\x82\xd8\xb7\xd8\xa9 \xd8\xa7\xd9\x84\xd8\xa8\xd9\x8a\xd8\xb9" in resp.data

class TestPosApiProducts:
    def test_api_products_requires_auth(self, client):
        resp = client.get("/pos/api/products?q=test")
        assert resp.status_code in (302, 401, 403)
    def test_api_products_returns_list(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.search_pos_products", return_value=([], {}, [])):
                        resp = client.get("/pos/api/products?q=test")
                        assert resp.status_code == 200
                        data = json.loads(resp.data)
                        assert isinstance(data, list)
    def test_api_products_with_results(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
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
                    product.name = "Test"
                    product.sku = "SKU1"
                    product.barcode = "123"
                    product.regular_price = 10
                    product.unit = "pc"
                    product.is_active = True
                    with patch("routes.pos.search_pos_products", return_value=([product], {1: 5}, [1])):
                        with patch("routes.pos.serialize_pos_product", return_value={"id": 1, "name": "Test"}):
                            resp = client.get("/pos/api/products?q=test")
                            assert resp.status_code == 200
                            data = json.loads(resp.data)
                            assert len(data) == 1
                            assert data[0]["id"] == 1

class TestPosApiProductLookup:
    def test_api_product_lookup_requires_auth(self, client):
        resp = client.get("/pos/api/product?code=123")
        assert resp.status_code in (302, 401, 403)
    def test_api_product_lookup_missing_code(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    resp = client.get("/pos/api/product")
                    assert resp.status_code == 400
                    data = json.loads(resp.data)
                    assert data["success"] is False
    def test_api_product_lookup_not_found(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.lookup_pos_product_exact", return_value=(None, {})):
                        resp = client.get("/pos/api/product?code=999")
                        assert resp.status_code == 404
                        data = json.loads(resp.data)
                        assert data["success"] is False
    def test_api_product_lookup_found(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
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
                    with patch("routes.pos.lookup_pos_product_exact", return_value=(product, {1: 10})):
                        with patch("routes.pos.serialize_pos_product", return_value={"id": 1, "name": "Item", "is_out_of_stock": False}):
                            resp = client.get("/pos/api/product?code=123")
                            assert resp.status_code == 200
                            data = json.loads(resp.data)
                            assert data["success"] is True
                            assert data["id"] == 1
    def test_api_product_lookup_inactive_warning(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
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
                    product.is_active = False
                    with patch("routes.pos.lookup_pos_product_exact", return_value=(product, {1: 10})):
                        with patch("routes.pos.serialize_pos_product", return_value={"id": 1, "name": "Item", "is_out_of_stock": False}):
                            resp = client.get("/pos/api/product?code=123")
                            assert resp.status_code == 200
                            data = json.loads(resp.data)
                            assert "warning" in data

class TestPosApiCustomers:
    def test_api_customers_requires_auth(self, client):
        resp = client.get("/pos/api/customers?q=test")
        assert resp.status_code in (302, 401, 403)
    def test_api_customers_returns_list(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
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
                        customer = MagicMock()
                        customer.id = 1
                        customer.name = "Ali"
                        customer.phone = "0501234567"
                        customer.customer_type = "regular"
                        mock_query.return_value.filter_by.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [customer]
                        resp = client.get("/pos/api/customers?q=ali")
                        assert resp.status_code == 200
                        data = json.loads(resp.data)
                        assert isinstance(data, list)
                        assert len(data) == 1
                        assert data[0]["name"] == "Ali"

class TestPosApiWalkin:
    def test_api_walkin_requires_auth(self, client):
        resp = client.get("/pos/api/walkin-customer")
        assert resp.status_code in (302, 401, 403)
    def test_api_walkin_returns_customer(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    with patch("routes.pos.get_pos_walkin_customer") as mock_walkin:
                        customer = MagicMock()
                        customer.id = 99
                        customer.name = "Walkin POS"
                        customer.customer_type = "regular"
                        mock_walkin.return_value = customer
                        resp = client.get("/pos/api/walkin-customer")
                        assert resp.status_code == 200
                        data = json.loads(resp.data)
                        assert data["success"] is True
                        assert data["id"] == 99
                        assert data["is_walkin"] is True

class TestPosApiCheckout:
    def test_api_checkout_requires_auth(self, client):
        resp = client.post("/pos/api/checkout", json={})
        assert resp.status_code in (302, 401, 403)
    def test_api_checkout_rejects_non_json(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
        with patch("routes.pos.SystemSettings") as MockSettings:
            setting = MagicMock()
            setting.enable_pos = True
            MockSettings.query.order_by.return_value.first.return_value = setting
            with patch("routes.pos.Tenant") as MockTenant:
                tenant = MagicMock()
                tenant.enable_pos = True
                MockTenant.query.get.return_value = tenant
                with patch("routes.pos.get_active_tenant_id", return_value=1):
                    resp = client.post("/pos/api/checkout", data="not-json")
                    assert resp.status_code == 415
                    data = json.loads(resp.data)
                    assert data["success"] is False
    def test_api_checkout_rejects_empty_cart(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
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
                        resp = client.post(
                            "/pos/api/checkout",
                            json={"lines": []},
                            headers={"Content-Type": "application/json"},
                        )
                        assert resp.status_code == 400
                        data = json.loads(resp.data)
                        assert data["success"] is False
    def test_api_checkout_success(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
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
                        customer.name = "Test Customer"
                        with patch("routes.pos.get_pos_walkin_customer", return_value=customer):
                            product = MagicMock()
                            product.id = 1
                            product.is_active = True
                            with patch("routes.pos.tenant_get", return_value=product):
                                sale = MagicMock()
                                sale.id = 100
                                sale.sale_number = "S-2024-001"
                                sale.grand_total = 100
                                with patch("routes.pos.SaleService.create_sale", return_value=sale):
                                    with patch("routes.pos.log_mutation"):
                                            with patch("routes.pos.db"):
                                                resp = client.post(
                                                    "/pos/api/checkout",
                                                    json={
                                                        "lines": [{"product_id": 1, "quantity": 2, "discount_percent": 0, "unit_price": 50}],
                                                        "payment_method": "cash",
                                                        "paid_amount": 100,
                                                    },
                                                    headers={"Content-Type": "application/json"},
                                                )
                                                assert resp.status_code == 200
                                                data = json.loads(resp.data)
                                                assert data["success"] is True
                                                assert data["sale_id"] == 100
                                                assert data["sale_number"] == "S-2024-001"
    def test_api_checkout_with_invalid_product(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
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
                        with patch("routes.pos.get_pos_walkin_customer", return_value=customer):
                            with patch("routes.pos.tenant_get", return_value=None):
                                resp = client.post(
                                    "/pos/api/checkout",
                                    json={
                                        "lines": [{"product_id": 999, "quantity": 1, "discount_percent": 0}],
                                    },
                                    headers={"Content-Type": "application/json"},
                                )
                                assert resp.status_code == 400
                                data = json.loads(resp.data)
                                assert data["success"] is False
    def test_api_checkout_rejects_invalid_discount(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
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
                        with patch("routes.pos.get_pos_walkin_customer", return_value=customer):
                            resp = client.post(
                                "/pos/api/checkout",
                                json={
                                    "lines": [{"product_id": 1, "quantity": 1, "discount_percent": 150}],
                                },
                                headers={"Content-Type": "application/json"},
                            )
                            assert resp.status_code == 400
                            data = json.loads(resp.data)
                            assert data["success"] is False
    def test_api_checkout_without_payment_method(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
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
                        customer.name = "Test"
                        with patch("routes.pos.get_pos_walkin_customer", return_value=customer):
                            product = MagicMock()
                            product.id = 1
                            product.is_active = True
                            with patch("routes.pos.tenant_get", return_value=product):
                                with patch("routes.pos.SaleService.create_sale") as mock_create:
                                    sale = MagicMock()
                                    sale.id = 101
                                    sale.sale_number = "S-2024-002"
                                    sale.grand_total = 0
                                    mock_create.return_value = sale
                                    with patch("routes.pos.log_mutation"):
                                        with patch("routes.pos.db"):
                                            resp = client.post(
                                                "/pos/api/checkout",
                                                json={
                                                    "lines": [{"product_id": 1, "quantity": 1, "discount_percent": 0}],
                                                    "paid_amount": 0,
                                                },
                                                headers={"Content-Type": "application/json"},
                                            )
                                            assert resp.status_code == 200
                                            data = json.loads(resp.data)
                                            assert data["success"] is True

class TestPosApiCheckoutPrint:
    def test_checkout_print_flag_opens_print(self, app, client, pos_owner):
        _login_owner(client, pos_owner)
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
                        customer.name = "Test"
                        with patch("routes.pos.get_pos_walkin_customer", return_value=customer):
                            product = MagicMock()
                            product.id = 1
                            product.is_active = True
                            with patch("routes.pos.tenant_get", return_value=product):
                                sale = MagicMock()
                                sale.id = 200
                                sale.sale_number = "S-2024-003"
                                sale.grand_total = 50
                                with patch("routes.pos.SaleService.create_sale", return_value=sale):
                                    with patch("routes.pos.log_mutation"):
                                        with patch("routes.pos.db"):
                                            resp = client.post(
                                                "/pos/api/checkout",
                                                json={
                                                    "lines": [{"product_id": 1, "quantity": 1, "discount_percent": 0, "unit_price": 50}],
                                                    "payment_method": "cash",
                                                    "paid_amount": 50,
                                                    "auto_print": True,
                                                },
                                                headers={"Content-Type": "application/json"},
                                            )
                                            assert resp.status_code == 200
                                            data = json.loads(resp.data)
                                            assert data["success"] is True
