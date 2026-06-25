from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query, unauthenticated_client


def _mock_tenant_store(**overrides):
    store = MagicMock()
    store.id = 1
    store.tenant_id = 1
    store.title = "Demo Store"
    store.store_slug = "demo-store"
    store.is_enabled = True
    store.platform_disabled = False
    store.warehouse_id = 10
    store.min_order_amount = None
    for key, value in overrides.items():
        setattr(store, key, value)
    return store


def _mock_warehouse(wid=10):
    wh = MagicMock()
    wh.id = wid
    wh.name = "Online WH"
    return wh


def _mock_product(pid=5, tenant_id=1):
    product = MagicMock()
    product.id = pid
    product.tenant_id = tenant_id
    product.name = "Widget"
    product.is_active = True
    return product


def _mock_sale(sid=100):
    sale = MagicMock()
    sale.id = sid
    sale.sale_number = "ORD-100"
    sale.status = "pending"
    sale.checkout_payment_method = "cod"
    sale.tenant_id = 1
    return sale


@pytest.fixture
def store_service_mocks():
    store = _mock_tenant_store()
    online_wh = _mock_warehouse(10)
    physical_wh = _mock_warehouse(20)
    physical_wh.id = 20
    sale_query = _chain_query(all=[_mock_sale()])
    product_query = MagicMock()
    product_query.filter_by.return_value.order_by.return_value.all.return_value = [_mock_product()]
    product_query.filter_by.return_value.first.return_value = _mock_product()
    customer_query = MagicMock()
    customer_query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = []
    tenant_store_query = MagicMock()
    tenant_store_query.filter.return_value.first.return_value = None
    patches = [
        patch("routes.store.StoreService.get_tenant_store", return_value=store),
        patch("routes.store.StoreService.ensure_tenant_store", return_value=store),
        patch("routes.store.StoreService.get_online_warehouse", return_value=online_wh),
        patch("routes.store.StoreService.ensure_online_warehouse", return_value=online_wh),
        patch("routes.store.StoreService.count_visible_products", return_value=3),
        patch("routes.store.StoreService.online_stock_map", return_value={5: Decimal("12")}),
        patch("routes.store.StoreService.stores_globally_enabled", return_value=True),
        patch("routes.store.StoreService.get_catalog_products", return_value=([_mock_product()], {5: Decimal("4")})),
        patch("routes.store.StoreService.get_physical_warehouses", return_value=[physical_wh]),
        patch("routes.store.StoreService.validate_slug", side_effect=lambda s: s),
        patch("routes.store.StoreService.ensure_unique_slug", side_effect=lambda s, tenant_id=None: s),
        patch("routes.store.StoreService.normalize_subdomain", side_effect=lambda s: s),
        patch("routes.store.StoreService.ensure_unique_subdomain", side_effect=lambda s, tenant_id=None: s),
        patch("routes.store.StoreOrderService.order_counts", return_value={"pending": 2}),
        patch("routes.store.StoreOrderService.STORE_ORDER_STATUSES", ("pending", "confirmed", "processing", "shipped", "delivered", "cancelled"), create=True),
        patch("routes.store.StoreOrderService.STATUS_LABELS_AR", {"pending": "بانتظار التأكيد", "confirmed": "مؤكد"}, create=True),
        patch("routes.store.StoreOrderService.get_tenant_order", return_value=_mock_sale()),
        patch("routes.store.StoreOrderService.is_fulfilled", return_value=False),
        patch("routes.store.StoreOrderService.validate_stock_for_order", return_value=[]),
        patch("routes.store.StoreOrderService.confirm_order"),
        patch("routes.store.StoreOrderService.cancel_order"),
        patch("routes.store.StoreOrderService.status_label", return_value="قيد الانتظار"),
        patch("routes.store.StoreAnalyticsService.low_stock_products", return_value=[]),
        patch("routes.store.StoreAnalyticsService.order_stats", return_value={"total": 5}),
        patch("routes.store.StoreAnalyticsService.top_products", return_value=[]),
        patch("routes.store.StoreAnalyticsService.daily_orders_chart", return_value=[]),
        patch("routes.store.StoreCouponService.list_for_tenant", return_value=[]),
        patch("routes.store.StoreCouponService.create_coupon"),
        patch("routes.store.StoreCouponService.update_coupon"),
        patch("routes.store.StorePaymentMethodService.list_all", return_value=[]),
        patch("routes.store.StorePaymentMethodService.get_by_code", return_value=MagicMock()),
        patch("routes.store.StockService.transfer_stock"),
        patch("routes.store.Product.query", product_query),
        patch("routes.store.Sale.query", sale_query),
        patch("routes.store.ShopCustomerAccount.query", customer_query),
        patch("routes.store.TenantStore.query", tenant_store_query),
        patch("routes.store.render_template", return_value="ok"),
        patch("routes.store.db.session"),
        patch("routes.store.save_uploaded_file", return_value="uploads/store_logos/logo.png"),
        patch("services.store_notification_service.StoreNotificationService.whatsapp_admin_link", return_value="https://wa.me/"),
        patch("routes.store.LoggingCore.log_audit"),
    ]
    for p in patches:
        p.start()
    yield {"store": store, "online_wh": online_wh, "physical_wh": physical_wh, "sale_query": sale_query}
    for p in reversed(patches):
        p.stop()


@pytest.fixture
def store_client(app_factory, bypass_permission_auth, store_service_mocks):
    from routes.store import store_bp
    app = app_factory(store_bp)
    return app.test_client()


class TestStoreAuth:
    def test_unauthenticated_returns_401(self, store_client):
        with unauthenticated_client(store_client):
            resp = store_client.get("/store/admin")
        assert resp.status_code == 401

    def test_missing_permission_returns_403(self, store_client, mock_user):
        mock_user.has_permission.return_value = False
        with patch("utils.decorators.is_global_owner_user", return_value=False):
            resp = store_client.get("/store/admin")
        assert resp.status_code == 403

    def test_tenant_none_returns_403(self, store_client):
        with patch("routes.store.get_active_tenant_id", return_value=None):
            resp = store_client.get("/store/admin")
        assert resp.status_code == 403


class TestStoreAdminIndex:
    def test_admin_index_renders(self, store_client):
        with patch("routes.store.render_template", return_value="index") as render:
            resp = store_client.get("/store/admin")
        assert resp.status_code == 200
        assert render.called
        assert render.call_args[0][0] == "store/admin_index.html"

    def test_admin_index_without_online_warehouse(self, store_client):
        with patch("routes.store.StoreService.get_online_warehouse", return_value=None), \
             patch("routes.store.render_template", return_value="index") as render:
            resp = store_client.get("/store/admin")
        assert resp.status_code == 200
        kwargs = render.call_args[1]
        assert kwargs["visible_count"] == 0
        assert kwargs["total_units"] == Decimal("0")


class TestStoreAdminSettings:
    def test_settings_get_renders(self, store_client):
        with patch("routes.store.render_template", return_value="settings") as render:
            resp = store_client.get("/store/admin/settings")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "store/admin_settings.html"

    def test_settings_post_success_redirects(self, store_client, store_service_mocks):
        resp = store_client.post("/store/admin/settings", data={
            "title": "My Store",
            "store_slug": "my-store",
        })
        assert resp.status_code in (302, 303)

    def test_settings_post_validation_error_missing_title_when_enabled(self, store_client, store_service_mocks):
        with patch("routes.store.render_template", return_value="settings") as render:
            resp = store_client.post("/store/admin/settings", data={
                "is_enabled": "on",
                "title": "",
                "store_slug": "my-store",
            })
        assert resp.status_code == 200
        assert render.called

    def test_settings_post_platform_disabled_blocks_enable(self, store_client, store_service_mocks):
        store_service_mocks["store"].platform_disabled = True
        resp = store_client.post("/store/admin/settings", data={
            "is_enabled": "on",
            "title": "Enabled Store",
            "store_slug": "enabled-store",
        })
        assert resp.status_code in (302, 303)
        assert store_service_mocks["store"].is_enabled is False

    def test_settings_post_custom_domain_clash(self, store_client):
        clash = MagicMock()
        tenant_store_query = MagicMock()
        tenant_store_query.filter.return_value.first.return_value = clash
        with patch("routes.store.TenantStore.query", tenant_store_query), \
             patch("routes.store.render_template", return_value="settings"):
            resp = store_client.post("/store/admin/settings", data={
                "title": "Store",
                "store_slug": "store",
                "custom_domain": "shop.example.com",
            })
        assert resp.status_code == 200


class TestStoreAdminCatalog:
    def test_catalog_renders(self, store_client):
        with patch("routes.store.render_template", return_value="catalog") as render:
            resp = store_client.get("/store/admin/catalog")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "store/admin_catalog.html"

    def test_catalog_include_zero(self, store_client):
        with patch("routes.store.StoreService.get_catalog_products", return_value=([], {})), \
             patch("routes.store.render_template", return_value="catalog") as render:
            resp = store_client.get("/store/admin/catalog?all=1")
        assert resp.status_code == 200
        assert render.call_args[1]["include_zero"] is True


class TestStoreAdminTransfer:
    def test_transfer_get_renders(self, store_client):
        with patch("routes.store.render_template", return_value="transfer") as render:
            resp = store_client.get("/store/admin/transfer")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "store/admin_transfer.html"

    def test_transfer_post_success_to_online(self, store_client, store_service_mocks):
        with patch("routes.store.StockService.transfer_stock") as transfer:
            resp = store_client.post("/store/admin/transfer", data={
                "direction": "to_online",
                "product_id": "5",
                "source_warehouse_id": "20",
                "quantity": "3",
            })
        transfer.assert_called_once()
        assert resp.status_code in (302, 303)

    def test_transfer_post_validation_error(self, store_client):
        with patch("routes.store.render_template", return_value="transfer"):
            resp = store_client.post("/store/admin/transfer", data={
                "direction": "to_online",
                "product_id": "",
                "quantity": "0",
            })
        assert resp.status_code == 200

    def test_transfer_post_from_online(self, store_client, store_service_mocks):
        with patch("routes.store.StockService.transfer_stock") as transfer:
            resp = store_client.post("/store/admin/transfer", data={
                "direction": "from_online",
                "product_id": "5",
                "source_warehouse_id": "20",
                "quantity": "2",
            })
        transfer.assert_called_once()
        assert resp.status_code in (302, 303)


class TestStoreAdminOrders:
    def test_orders_list_renders(self, store_client):
        with patch("routes.store.render_template", return_value="orders") as render:
            resp = store_client.get("/store/admin/orders")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "store/admin_orders.html"

    def test_orders_with_status_filter(self, store_client, store_service_mocks):
        with patch("routes.store.render_template", return_value="orders"):
            resp = store_client.get("/store/admin/orders?status=pending&page=2")
        assert resp.status_code == 200

    def test_order_detail_renders(self, store_client):
        with patch("routes.store.render_template", return_value="detail") as render:
            resp = store_client.get("/store/admin/orders/100")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "store/admin_order_detail.html"

    def test_order_detail_not_found(self, store_client):
        with patch("routes.store.StoreOrderService.get_tenant_order", return_value=None):
            resp = store_client.get("/store/admin/orders/999")
        assert resp.status_code == 404

    def test_order_confirm_success(self, store_client):
        with patch("routes.store.StoreOrderService.confirm_order") as confirm:
            resp = store_client.post("/store/admin/orders/100/confirm", data={"mark_paid": "on"})
        confirm.assert_called_once()
        assert resp.status_code in (302, 303)

    def test_order_confirm_not_found(self, store_client):
        with patch("routes.store.StoreOrderService.get_tenant_order", return_value=None):
            resp = store_client.post("/store/admin/orders/999/confirm")
        assert resp.status_code == 404

    def test_order_confirm_value_error(self, store_client):
        with patch("routes.store.StoreOrderService.confirm_order", side_effect=ValueError("stock issue")):
            resp = store_client.post("/store/admin/orders/100/confirm")
        assert resp.status_code in (302, 303)

    def test_order_cancel_success(self, store_client):
        with patch("routes.store.StoreOrderService.cancel_order") as cancel:
            resp = store_client.post("/store/admin/orders/100/cancel")
        cancel.assert_called_once()
        assert resp.status_code in (302, 303)

    def test_order_cancel_not_found(self, store_client):
        with patch("routes.store.StoreOrderService.get_tenant_order", return_value=None):
            resp = store_client.post("/store/admin/orders/999/cancel")
        assert resp.status_code == 404


class TestStoreAdminCustomers:
    def test_customers_renders(self, store_client):
        account = MagicMock()
        account.id = 1
        customer_query = MagicMock()
        customer_query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [account]
        with patch("routes.store.ShopCustomerAccount.query", customer_query), \
             patch("routes.store.render_template", return_value="customers") as render:
            resp = store_client.get("/store/admin/customers")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "store/admin_customers.html"


class TestStoreAdminStats:
    def test_stats_renders(self, store_client):
        with patch("routes.store.render_template", return_value="stats") as render:
            resp = store_client.get("/store/admin/stats")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "store/admin_stats.html"


class TestStoreAdminCoupons:
    def test_coupons_get_renders(self, store_client):
        with patch("routes.store.render_template", return_value="coupons") as render:
            resp = store_client.get("/store/admin/coupons")
        assert resp.status_code == 200
        assert render.call_args[0][0] == "store/admin_coupons.html"

    def test_coupons_create_redirects(self, store_client):
        with patch("routes.store.StoreCouponService.create_coupon") as create:
            resp = store_client.post("/store/admin/coupons", data={
                "action": "create",
                "code": "SAVE10",
                "discount_percent": "10",
            })
        create.assert_called_once()
        assert resp.status_code in (302, 303)

    def test_coupons_toggle_redirects(self, store_client):
        with patch("routes.store.StoreCouponService.update_coupon") as update:
            resp = store_client.post("/store/admin/coupons", data={
                "action": "toggle",
                "coupon_id": "7",
                "enabled": "1",
            })
        update.assert_called_once_with(7, 1, {"is_active": True})
        assert resp.status_code in (302, 303)

    def test_coupons_create_value_error(self, store_client):
        with patch("routes.store.StoreCouponService.create_coupon", side_effect=ValueError("bad code")):
            resp = store_client.post("/store/admin/coupons", data={
                "action": "create",
                "code": "",
            })
        assert resp.status_code in (302, 303)
