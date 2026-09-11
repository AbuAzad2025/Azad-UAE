"""Coverage for routes/store.py remaining arcs.

Targets: _tenant_id 403 arc, admin_settings platform-disabled/title/
domain-clash/logo/value/generic arcs, transfer direction/validation arcs,
order confirm/cancel value/generic arcs, coupon create/toggle/error arcs,
order-detail 404 arc. Real test-client paths; service boundaries mocked.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import _chain_query


def _store(**over):
    s = MagicMock()
    s.id = 1
    s.tenant_id = 1
    s.title = "Demo Store"
    s.store_slug = "demo-store"
    s.is_enabled = True
    s.platform_disabled = over.get("platform_disabled", False)
    s.warehouse_id = 10
    s.min_order_amount = None
    s.display_currency = None
    for k, v in over.items():
        setattr(s, k, v)
    return s


def _wh(wid=10):
    w = MagicMock()
    w.id = wid
    w.name = "Online WH"
    return w


def _product(pid=5):
    p = MagicMock()
    p.id = pid
    p.tenant_id = 1
    p.name = "Widget"
    p.is_active = True
    return p


def _sale(sid=100, status="pending"):
    s = MagicMock()
    s.id = sid
    s.sale_number = "ORD-100"
    s.status = status
    s.checkout_payment_method = "cod"
    s.tenant_id = 1
    return s


@pytest.fixture
def store_cov3_client(app_factory, bypass_permission_auth):
    from routes.store import store_bp

    app = app_factory(store_bp)
    return app.test_client()


def _base(stack, **kw):
    store = kw.get("store", _store())
    online = kw.get("online", _wh(10))
    stack.enter_context(patch("routes.store._tenant_id", return_value=1))
    stack.enter_context(patch("routes.store.StoreService.get_tenant_store", return_value=store))
    stack.enter_context(patch("routes.store.StoreService.ensure_tenant_store", return_value=store))
    stack.enter_context(patch("routes.store.StoreService.get_online_warehouse", return_value=online))
    stack.enter_context(patch("routes.store.StoreService.ensure_online_warehouse", return_value=online))
    stack.enter_context(patch("routes.store.StoreService.count_visible_products", return_value=1))
    stack.enter_context(patch("routes.store.StoreService.online_stock_map", return_value={}))
    stack.enter_context(patch("routes.store.StoreService.stores_globally_enabled", return_value=True))
    stack.enter_context(
        patch("routes.store.StoreService.get_catalog_products", return_value=([_product()], {5: Decimal("1")}))
    )
    stack.enter_context(patch("routes.store.StoreService.get_physical_warehouses", return_value=[_wh(20)]))
    stack.enter_context(patch("routes.store.StoreService.list_active_products", return_value=[_product()]))
    stack.enter_context(patch("routes.store.StoreService.get_transfer_product", return_value=_product()))
    stack.enter_context(
        patch("routes.store.StoreService.online_orders_query", return_value=_chain_query(all=[_sale()]))
    )
    stack.enter_context(patch("routes.store.StoreOrderService.get_tenant_order", return_value=kw.get("sale", _sale())))
    stack.enter_context(patch("routes.store.StoreOrderService.order_counts", return_value={"pending": 1}))
    stack.enter_context(patch("routes.store.StoreOrderService.is_fulfilled", return_value=True))
    stack.enter_context(patch("routes.store.StoreOrderService.status_label", return_value="Pending"))
    stack.enter_context(patch("routes.store.StoreOrderService.validate_stock_for_order", return_value=[]))
    stack.enter_context(patch("routes.store.StorePaymentMethodService.list_all", return_value=[]))
    stack.enter_context(patch("routes.store.StorePaymentMethodService.get_by_code", return_value=MagicMock()))
    stack.enter_context(patch("routes.store.StoreAnalyticsService.order_stats", return_value={}))
    stack.enter_context(patch("routes.store.StoreAnalyticsService.low_stock_products", return_value=[]))
    stack.enter_context(patch("routes.store.StoreAnalyticsService.top_products", return_value=[]))
    stack.enter_context(patch("routes.store.StoreAnalyticsService.daily_orders_chart", return_value={}))
    stack.enter_context(patch("routes.store.StoreCouponService.list_for_tenant", return_value=[]))
    stack.enter_context(patch("routes.store.StoreService.list_customer_accounts", return_value=[]))
    stack.enter_context(
        patch("services.azad_platform_fee_service.AzadPlatformFeeService.get_accrued_summary", return_value=[])
    )
    stack.enter_context(
        patch(
            "services.azad_platform_fee_service.AzadPlatformFeeService.get_settlement_report",
            return_value={"items": []},
        )
    )
    stack.enter_context(patch("routes.store.render_template", return_value="ok"))
    stack.enter_context(patch("routes.store.atomic_transaction"))
    stack.enter_context(patch("routes.store.LoggingCore.log_audit"))
    return store


class TestTenantGuard:
    def test_tenant_none_403(self, store_cov3_client):
        from routes import store as store_mod

        with patch.object(store_mod, "get_active_tenant_id", return_value=None):
            resp = store_cov3_client.get("/store/admin")
        assert resp.status_code == 403


class TestAdminSettings:
    def test_platform_disabled_blocks_enable(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            store = _base(stack, store=_store(platform_disabled=True))
            stack.enter_context(patch("routes.store.StoreService.validate_slug", return_value="demo-store"))
            stack.enter_context(patch("routes.store.StoreService.ensure_unique_slug", return_value="demo-store"))
            resp = store_cov3_client.post("/store/admin/settings", data={"is_enabled": "on", "title": "T"})
        assert resp.status_code == 302
        assert store.is_enabled is False

    def test_enable_without_title_warns(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("routes.store.StoreService.validate_slug", return_value="s"))
            stack.enter_context(patch("routes.store.StoreService.ensure_unique_slug", return_value="s"))
            resp = store_cov3_client.post("/store/admin/settings", data={"is_enabled": "on", "title": ""})
        assert resp.status_code == 200

    def test_custom_domain_clash_warns(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("routes.store.StoreService.validate_slug", return_value="s"))
            stack.enter_context(patch("routes.store.StoreService.ensure_unique_slug", return_value="s"))
            stack.enter_context(patch("routes.store.StoreService.find_custom_domain_clash", return_value=MagicMock()))
            resp = store_cov3_client.post(
                "/store/admin/settings", data={"title": "T", "custom_domain": "shop.example.com"}
            )
        assert resp.status_code == 200

    def test_logo_upload_path(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("routes.store.StoreService.validate_slug", return_value="s"))
            stack.enter_context(patch("routes.store.StoreService.ensure_unique_slug", return_value="s"))
            stack.enter_context(patch("routes.store.save_uploaded_file", return_value="uploads/logo.png"))
            import io

            resp = store_cov3_client.post(
                "/store/admin/settings",
                data={"title": "T", "logo": (io.BytesIO(b"img"), "logo.png")},
                content_type="multipart/form-data",
            )
        assert resp.status_code in (200, 302)

    def test_generic_exception(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("routes.store.StoreService.validate_slug", side_effect=RuntimeError("down")))
            resp = store_cov3_client.post("/store/admin/settings", data={"title": "T"})
        assert resp.status_code == 200


class TestTransferAndOrders:
    def test_transfer_missing_product_warns(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack)
            resp = store_cov3_client.post("/store/admin/transfer", data={"direction": "to_online", "quantity": "0"})
        assert resp.status_code == 200

    def test_transfer_bad_source_warns(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack)
            resp = store_cov3_client.post(
                "/store/admin/transfer",
                data={"direction": "to_online", "product_id": "5", "quantity": "2"},
            )
        assert resp.status_code == 200

    def test_transfer_from_online_success(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("services.stock_service.StockService.transfer_stock"))
            resp = store_cov3_client.post(
                "/store/admin/transfer",
                data={"direction": "from_online", "product_id": "5", "quantity": "2", "source_warehouse_id": "10"},
            )
        assert resp.status_code in (200, 302)

    def test_transfer_generic_exception(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(
                patch(
                    "services.stock_service.StockService.transfer_stock",
                    side_effect=RuntimeError("down"),
                )
            )
            resp = store_cov3_client.post(
                "/store/admin/transfer",
                data={"direction": "to_online", "product_id": "5", "quantity": "1", "source_warehouse_id": "20"},
            )
        assert resp.status_code == 200

    def test_order_detail_404(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack, sale=None)
            resp = store_cov3_client.get("/store/admin/orders/9999")
        assert resp.status_code == 404

    def test_order_confirm_value_and_generic(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(
                patch(
                    "services.store_order_service.StoreOrderService.confirm_order",
                    side_effect=ValueError("no stock"),
                )
            )
            assert store_cov3_client.post("/store/admin/orders/100/confirm").status_code == 302
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(
                patch(
                    "services.store_order_service.StoreOrderService.confirm_order",
                    side_effect=RuntimeError("down"),
                )
            )
            assert store_cov3_client.post("/store/admin/orders/100/confirm").status_code == 302

    def test_order_cancel_value_and_generic(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(
                patch(
                    "services.store_order_service.StoreOrderService.cancel_order",
                    side_effect=ValueError("locked"),
                )
            )
            assert store_cov3_client.post("/store/admin/orders/100/cancel").status_code == 302
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(
                patch(
                    "services.store_order_service.StoreOrderService.cancel_order",
                    side_effect=RuntimeError("down"),
                )
            )
            assert store_cov3_client.post("/store/admin/orders/100/cancel").status_code == 302

    def test_coupon_create_toggle_errors(self, store_cov3_client):
        from contextlib import ExitStack

        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("services.store_coupon_service.StoreCouponService.create_coupon"))
            assert (
                store_cov3_client.post("/store/admin/coupons", data={"action": "create", "code": "X"}).status_code
                == 302
            )
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("services.store_coupon_service.StoreCouponService.update_coupon"))
            assert (
                store_cov3_client.post(
                    "/store/admin/coupons", data={"action": "toggle", "coupon_id": "1", "enabled": "1"}
                ).status_code
                == 302
            )
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(
                patch(
                    "services.store_coupon_service.StoreCouponService.create_coupon",
                    side_effect=ValueError("bad"),
                )
            )
            assert store_cov3_client.post("/store/admin/coupons", data={"action": "create"}).status_code == 302
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(
                patch(
                    "services.store_coupon_service.StoreCouponService.create_coupon",
                    side_effect=RuntimeError("down"),
                )
            )
            assert store_cov3_client.post("/store/admin/coupons", data={"action": "create"}).status_code == 302
