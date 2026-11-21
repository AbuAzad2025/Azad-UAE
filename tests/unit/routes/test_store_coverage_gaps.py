"""Coverage for the remaining arcs of ``routes/store.py``.

Targets (see the combined-coverage report):
  * admin_index fee-status loop (76-77)
  * admin_settings decimal validation / domain / logo branches
    (139-140, 142, 164-165, 167, 182->184, 193->196)
  * admin_prices (246-328)
  * admin_transfer invalid-source branches (367, 374)
  * admin_coupons toggle-invalid coupon arc (574->559, 577-578)
  * whatsapp_checkout (612-713)
  * approve / cancel provisional orders (721-739, 747-759)
  * storefront helpers (779-782, 787-797, 817-827, 832-837)
  * public catalog / product / cart / checkout / reports
    (844-861, 875-886, 901-912, 924-942, 949-961, 973-1068, 1083-1090)

Service boundaries are mocked at the route boundary; only the HTTP layer is
under test. Auth / feature-gate / limiter are handled by the shared fixtures.
"""

from __future__ import annotations

from contextlib import ExitStack
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
    s.platform_disabled = False
    s.warehouse_id = 10
    s.min_order_amount = None
    s.display_currency = None
    s.brand_color_primary = "#1B7A4E"
    s.brand_color_secondary = "#CE1126"
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
    p.category_id = 3
    p.regular_price = Decimal("20")
    return p


def _sale(sid=100, status="pending"):
    s = MagicMock()
    s.id = sid
    s.sale_number = "ORD-100"
    s.status = status
    s.checkout_payment_method = "cod"
    s.tenant_id = 1
    return s


def _provisional(pid=1, status="pending"):
    p = MagicMock()
    p.id = pid
    p.status = status
    p.provisional_number = "PROV-1"
    return p


@pytest.fixture
def sc_client(app_factory, bypass_permission_auth):
    from routes.store import store_bp

    app = app_factory(store_bp)
    return app.test_client()


def _base(stack, **kw):
    """Enter the full set of route-boundary mocks; return the useful mocks."""
    store = kw.get("store", _store())
    online = kw.get("online", _wh(10))
    physical = kw.get("physical", [_wh(20)])
    sale = kw.get("sale", _sale())
    prov = kw.get("provisional", _provisional())
    product = kw.get("product", _product())

    stack.enter_context(patch("routes.store.get_active_tenant_id", return_value=kw.get("tenant_id", 1)))
    stack.enter_context(patch("routes.store.StoreService.get_tenant_store", return_value=store))
    stack.enter_context(patch("routes.store.StoreService.ensure_tenant_store", return_value=store))
    stack.enter_context(patch("routes.store.StoreService.get_online_warehouse", return_value=online))
    stack.enter_context(patch("routes.store.StoreService.ensure_online_warehouse", return_value=online))
    stack.enter_context(patch("routes.store.StoreService.count_visible_products", return_value=1))
    stack.enter_context(patch("routes.store.StoreService.online_stock_map", return_value={}))
    stack.enter_context(patch("routes.store.StoreService.stores_globally_enabled", return_value=True))
    stack.enter_context(patch("routes.store.StoreService.get_catalog_products", return_value=([product], {})))
    stack.enter_context(patch("routes.store.StoreService.get_physical_warehouses", return_value=physical))
    stack.enter_context(patch("routes.store.StoreService.list_active_products", return_value=[product]))
    stack.enter_context(patch("routes.store.StoreService.get_transfer_product", return_value=product))
    stack.enter_context(patch("routes.store.StoreService.online_orders_query", return_value=_chain_query(all=[sale])))
    stack.enter_context(patch("routes.store.StoreService.list_customer_accounts", return_value=[]))
    stack.enter_context(patch("routes.store.StoreService.find_custom_domain_clash", return_value=None))
    stack.enter_context(patch("routes.store.StoreService.validate_slug", side_effect=lambda s: s))
    stack.enter_context(patch("routes.store.StoreService.ensure_unique_slug", side_effect=lambda s, tenant_id=None: s))
    stack.enter_context(patch("routes.store.StoreService.normalize_subdomain", side_effect=lambda s: s))
    stack.enter_context(
        patch("routes.store.StoreService.ensure_unique_subdomain", side_effect=lambda s, tenant_id=None: s)
    )
    stack.enter_context(patch("routes.store.StoreService.get_store_by_host", return_value=kw.get("host_store", store)))
    stack.enter_context(patch("routes.store.StoreService.get_store_by_slug", return_value=kw.get("slug_store", store)))
    stack.enter_context(
        patch("routes.store.StoreService.is_store_publicly_available", return_value=kw.get("public_available", True))
    )
    stack.enter_context(
        patch(
            "routes.store.StoreService.get_public_catalog",
            return_value={"items": [], "total": 0, "pages": 1, "page": 1},
        )
    )
    stack.enter_context(patch("routes.store.StoreService.active_categories", return_value=[]))
    stack.enter_context(patch("routes.store.StoreService.get_cart", return_value=kw.get("cart", {})))
    stack.enter_context(patch("routes.store.StoreService.save_cart"))
    stack.enter_context(
        patch(
            "routes.store.StoreService.cart_totals",
            return_value={"lines": [], "subtotal": Decimal("0"), "total": Decimal("0"), "tax": Decimal("0")},
        )
    )
    stack.enter_context(patch("routes.store.StoreService.active_product_or_404", return_value=product))
    stack.enter_context(patch("routes.store.StoreService.get_related_products", return_value=[]))
    stack.enter_context(patch("routes.store.StoreService.approved_reviews", return_value=[]))

    stack.enter_context(patch("routes.store.StoreOrderService.order_counts", return_value={"pending": 2}))
    stack.enter_context(patch("routes.store.StoreOrderService.get_tenant_order", return_value=sale))
    stack.enter_context(patch("routes.store.StoreOrderService.is_fulfilled", return_value=False))
    stack.enter_context(patch("routes.store.StoreOrderService.validate_stock_for_order", return_value=[]))
    stack.enter_context(patch("routes.store.StoreOrderService.confirm_order"))
    stack.enter_context(patch("routes.store.StoreOrderService.cancel_order"))
    stack.enter_context(patch("routes.store.StoreOrderService.status_label", return_value="Pending"))
    stack.enter_context(patch("routes.store.StoreOrderService._latest_stored_rate", return_value=kw.get("rate")))
    stack.enter_context(patch("routes.store.StoreOrderService.convert_provisional_to_sale", return_value=_sale(101)))

    stack.enter_context(patch("routes.store.StoreAnalyticsService.order_stats", return_value={}))
    stack.enter_context(patch("routes.store.StoreAnalyticsService.top_products", return_value=[]))
    stack.enter_context(patch("routes.store.StoreAnalyticsService.daily_orders_chart", return_value=[]))
    stack.enter_context(patch("routes.store.StoreAnalyticsService.low_stock_products", return_value=[]))

    stack.enter_context(patch("routes.store.StoreCouponService.list_for_tenant", return_value=[]))
    stack.enter_context(patch("routes.store.StoreCouponService.create_coupon"))
    stack.enter_context(patch("routes.store.StoreCouponService.update_coupon"))

    stack.enter_context(patch("routes.store.StorePaymentMethodService.list_all", return_value=[]))
    stack.enter_context(patch("routes.store.StorePaymentMethodService.get_by_code", return_value=MagicMock()))

    stack.enter_context(patch("routes.store.StockService.transfer_stock"))

    stack.enter_context(
        patch(
            "routes.store.AzadPlatformFeeService.get_accrued_summary",
            return_value=[{"total_fee_aed": Decimal("5")}],
        )
    )
    stack.enter_context(patch("routes.store.AzadPlatformFeeService.get_settlement_report", return_value={"items": []}))

    stack.enter_context(patch("routes.store.StorePricingService._base_currency", return_value="AED"))
    stack.enter_context(patch("routes.store.StorePricingService.resolve_store_price", return_value=Decimal("10")))
    stack.enter_context(patch("routes.store.StorePricingService.resolve_display_currency", return_value="AED"))
    stack.enter_context(patch("routes.store.StorePricingService.resolve_display_price", return_value=Decimal("10")))
    stack.enter_context(patch("routes.store.StorePricingService.convert_amount", return_value=Decimal("10")))

    stack.enter_context(patch("routes.store.StoreWhatsAppService.generate_provisional_number", return_value="PROV-1"))
    stack.enter_context(patch("routes.store.StoreWhatsAppService.build_message", return_value="message"))
    stack.enter_context(
        patch("routes.store.StoreWhatsAppService.whatsapp_url", return_value="https://wa.me/971501234567")
    )
    stack.enter_context(patch("routes.store.StoreWhatsAppService.send_message", return_value=True))

    stack.enter_context(patch("routes.store.convert_and_quantize_aed", return_value=Decimal("10")))
    stack.enter_context(patch("routes.store.get_branch_stock_map", return_value={}))
    stack.enter_context(patch("routes.store.save_uploaded_file", return_value="uploads/logo.png"))
    stack.enter_context(patch("routes.store.LoggingCore.log_audit"))
    stack.enter_context(
        patch(
            "services.store_notification_service.StoreNotificationService.whatsapp_admin_link",
            return_value="https://wa.me/",
        )
    )
    render = stack.enter_context(patch("routes.store.render_template", return_value="ok"))
    stack.enter_context(patch("routes.store.atomic_transaction"))
    db_session = stack.enter_context(patch("extensions.db.session"))
    tenant = MagicMock()
    tenant.id = 1
    tenant.tenant_id = 1
    tenant.is_active = True
    tenant.is_suspended = False
    tenant.brand_color_primary = "#1B7A4E"
    tenant.brand_color_secondary = "#CE1126"
    db_session.get.return_value = tenant

    product_q = _chain_query(first=product, all=[product])
    stack.enter_context(patch("routes.store.Product.query", product_q))

    prov_cls = MagicMock()
    prov_cls.STATUS_PENDING = "pending"
    prov_cls.STATUS_CANCELLED = "cancelled"
    prov_cls.query.filter_by.return_value.first_or_404.return_value = prov
    stack.enter_context(patch("routes.store.StoreProvisionalOrder", prov_cls))

    return {
        "store": store,
        "online": online,
        "product": product,
        "sale": sale,
        "provisional": prov,
        "product_query": product_q,
        "prov_cls": prov_cls,
        "render": render,
        "db_session": db_session,
        "tenant": tenant,
    }


# ─── admin_index fee-status loop ────────────────────────────────────────────


class TestAdminIndexFeeLoop:
    def test_fee_status_counts(self, sc_client):
        fees = [
            MagicMock(status="accrued"),
            MagicMock(status="accrued"),
            MagicMock(status="settled"),
            MagicMock(status="paid"),
            MagicMock(status="other"),
        ]
        with ExitStack() as stack:
            ctx = _base(stack)
            stack.enter_context(
                patch("routes.store.AzadPlatformFeeService.get_settlement_report", return_value={"items": fees})
            )
            resp = sc_client.get("/store/admin")
        assert resp.status_code == 200
        assert ctx["render"].call_args[1]["fee_status_counts"] == {"accrued": 2, "settled": 1, "paid": 1}


# ─── admin_settings validation branches ─────────────────────────────────────


class TestAdminSettingsGaps:
    def test_invalid_min_order_amount(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post(
                "/store/admin/settings",
                data={"title": "T", "min_order_amount": "abc"},
            )
        assert resp.status_code == 200

    def test_negative_min_order_amount(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post(
                "/store/admin/settings",
                data={"title": "T", "min_order_amount": "-1"},
            )
        assert resp.status_code == 200

    def test_invalid_low_stock_threshold(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post(
                "/store/admin/settings",
                data={"title": "T", "low_stock_threshold": "abc"},
            )
        assert resp.status_code == 200

    def test_negative_low_stock_threshold(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post(
                "/store/admin/settings",
                data={"title": "T", "low_stock_threshold": "-2"},
            )
        assert resp.status_code == 200

    def test_custom_domain_without_clash(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post(
                "/store/admin/settings",
                data={"title": "T", "custom_domain": "SHOP.Example.com"},
            )
        assert resp.status_code in (302, 303)

    def test_logo_upload_rejected_by_saver(self, sc_client):
        import io

        with ExitStack() as stack:
            ctx = _base(stack)
            stack.enter_context(patch("routes.store.save_uploaded_file", return_value=None))
            resp = sc_client.post(
                "/store/admin/settings",
                data={"title": "T", "logo": (io.BytesIO(b"img"), "logo.bad")},
                content_type="multipart/form-data",
            )
        assert resp.status_code in (302, 303)
        assert ctx["store"].logo_path != "uploads/logo.png"


# ─── admin_prices ────────────────────────────────────────────────────────────


def _price_model(existing=None):
    spp = MagicMock()
    spp.query.filter_by.return_value.first.return_value = existing
    spp.query.filter_by.return_value.all.return_value = [existing] if existing is not None else []
    spp.query.filter_by.return_value.update.return_value = 1
    return spp


class TestAdminPrices:
    def test_get_renders(self, sc_client):
        with ExitStack() as stack:
            ctx = _base(stack)
            stack.enter_context(patch("models.store_product_price.StoreProductPrice", _price_model()))
            resp = sc_client.get("/store/admin/prices")
        assert resp.status_code == 200
        assert ctx["render"].call_args[0][0] == "store/admin_prices.html"

    def test_post_missing_fields(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("models.store_product_price.StoreProductPrice", _price_model()))
            resp = sc_client.post(
                "/store/admin/prices",
                data={"product_id": "0", "currency_code": "", "price": ""},
            )
        assert resp.status_code in (302, 303)

    def test_post_product_not_found(self, sc_client):
        with ExitStack() as stack:
            ctx = _base(stack)
            ctx["product_query"].filter_by.return_value.first.return_value = None
            stack.enter_context(patch("models.store_product_price.StoreProductPrice", _price_model()))
            resp = sc_client.post(
                "/store/admin/prices",
                data={"product_id": "5", "currency_code": "USD", "price": "10"},
            )
        assert resp.status_code in (302, 303)

    def test_post_non_numeric_price(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("models.store_product_price.StoreProductPrice", _price_model()))
            resp = sc_client.post(
                "/store/admin/prices",
                data={"product_id": "5", "currency_code": "USD", "price": "abc"},
            )
        assert resp.status_code in (302, 303)

    def test_post_non_finite_price(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("models.store_product_price.StoreProductPrice", _price_model()))
            resp = sc_client.post(
                "/store/admin/prices",
                data={"product_id": "5", "currency_code": "USD", "price": "NaN"},
            )
        assert resp.status_code in (302, 303)

    def test_post_negative_price(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("models.store_product_price.StoreProductPrice", _price_model()))
            resp = sc_client.post(
                "/store/admin/prices",
                data={"product_id": "5", "currency_code": "USD", "price": "-1"},
            )
        assert resp.status_code in (302, 303)

    def test_post_updates_existing_default(self, sc_client):
        existing = MagicMock()
        with ExitStack() as stack:
            ctx = _base(stack)
            spp = _price_model(existing)
            stack.enter_context(patch("models.store_product_price.StoreProductPrice", spp))
            resp = sc_client.post(
                "/store/admin/prices",
                data={
                    "product_id": "5",
                    "currency_code": "usd",
                    "price": "12.5",
                    "is_default": "on",
                    "is_active": "on",
                },
            )
        assert resp.status_code in (302, 303)
        assert spp.query.filter_by.return_value.update.called
        assert existing.source == "manual"
        assert ctx["store"].tenant_id == 1

    def test_post_creates_new_price(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            spp = _price_model()
            spp.query.filter_by.return_value.first.return_value = None
            stack.enter_context(patch("models.store_product_price.StoreProductPrice", spp))
            resp = sc_client.post(
                "/store/admin/prices",
                data={"product_id": "5", "currency_code": "AED", "price": "7", "is_active": "on"},
            )
        assert resp.status_code in (302, 303)
        assert spp.called

    def test_post_generic_exception(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            spp = _price_model()
            spp.query.filter_by.return_value.update.side_effect = RuntimeError("db down")
            stack.enter_context(patch("models.store_product_price.StoreProductPrice", spp))
            resp = sc_client.post(
                "/store/admin/prices",
                data={"product_id": "5", "currency_code": "USD", "price": "7", "is_default": "on"},
            )
        assert resp.status_code in (302, 303)


# ─── admin_transfer invalid sources ──────────────────────────────────────────


class TestAdminTransferSources:
    def test_to_online_invalid_source(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post(
                "/store/admin/transfer",
                data={
                    "direction": "to_online",
                    "product_id": "5",
                    "source_warehouse_id": "999",
                    "quantity": "2",
                },
            )
        assert resp.status_code == 200

    def test_from_online_invalid_source(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post(
                "/store/admin/transfer",
                data={
                    "direction": "from_online",
                    "product_id": "5",
                    "source_warehouse_id": "999",
                    "quantity": "2",
                },
            )
        assert resp.status_code == 200


# ─── admin_coupons toggle exception arc ──────────────────────────────────────


class TestAdminCouponsToggleException:
    def test_toggle_invalid_coupon_id(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post("/store/admin/coupons", data={"action": "toggle", "coupon_id": "abc"})
        assert resp.status_code in (302, 303)

    def test_unknown_action_skips_both_branches(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post("/store/admin/coupons", data={"action": "unknown"})
        assert resp.status_code in (302, 303)


class TestAdminOrderDetailFulfilled:
    def test_fulfilled_order_skips_stock_validation(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("routes.store.StoreOrderService.is_fulfilled", return_value=True))
            resp = sc_client.get("/store/admin/orders/100")
        assert resp.status_code == 200


# ─── whatsapp_checkout ───────────────────────────────────────────────────────


class TestWhatsappCheckout:
    def test_no_online_warehouse(self, sc_client):
        with ExitStack() as stack:
            _base(stack, online=None)
            resp = sc_client.post(
                "/store/checkout", json={"customer_phone": "+971501234567", "cart": [{"product_id": 5}]}
            )
        assert resp.status_code in (302, 303)

    def test_no_phone(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post("/store/checkout", json={"cart": [{"product_id": 5}]})
        assert resp.status_code in (302, 303)

    def test_empty_cart(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post("/store/checkout", json={"customer_phone": "+971501234567"})
        assert resp.status_code in (302, 303)

    def test_no_valid_lines(self, sc_client):
        with ExitStack() as stack:
            ctx = _base(stack)
            ctx["product_query"].filter_by.return_value.first.return_value = None
            resp = sc_client.post(
                "/store/checkout",
                json={"customer_phone": "+971501234567", "cart": [{"product_id": 999}]},
            )
        assert resp.status_code in (302, 303)

    def test_success_with_stored_rate(self, sc_client):
        with ExitStack() as stack:
            _base(stack, rate=Decimal("3.7"))
            resp = sc_client.post(
                "/store/checkout",
                json={
                    "customer_name": "John",
                    "customer_phone": "+971501234567",
                    "customer_email": "john@example.com",
                    "currency_code": "usd",
                    "cart": [{"product_id": 5, "quantity": 2}],
                },
            )
        assert resp.status_code == 302
        assert resp.headers["Location"].startswith("https://wa.me/")

    def test_success_without_stored_rate(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post(
                "/store/checkout",
                json={
                    "customer_phone": "+971501234567",
                    "currency_code": "AED",
                    "cart": [{"product_id": 5, "quantity": 1}],
                },
            )
        assert resp.status_code == 302

    def test_skips_invalid_item_and_uses_regular_price(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(patch("routes.store.StorePricingService.resolve_store_price", return_value=None))
            resp = sc_client.post(
                "/store/checkout",
                json={
                    "customer_phone": "+971501234567",
                    "cart": [
                        {"product_id": 0, "quantity": 1},
                        {"product_id": 5, "quantity": 1},
                    ],
                },
            )
        assert resp.status_code == 302


# ─── provisional order approve / cancel ──────────────────────────────────────


class TestProvisionalOrders:
    def test_approve_non_pending(self, sc_client):
        with ExitStack() as stack:
            _base(stack, provisional=_provisional(status="confirmed"))
            resp = sc_client.post("/store/admin/provisional/1/approve")
        assert resp.status_code in (302, 303)

    def test_approve_success(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post("/store/admin/provisional/1/approve")
        assert resp.status_code in (302, 303)

    def test_approve_value_error(self, sc_client):
        # A refused conversion flashes guidance and returns to the order list;
        # there is no sale to open a detail page for.
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(
                patch(
                    "routes.store.StoreOrderService.convert_provisional_to_sale",
                    side_effect=ValueError("no stock"),
                )
            )
            resp = sc_client.post("/store/admin/provisional/1/approve")
        assert resp.status_code in (302, 303)

    def test_approve_generic_error(self, sc_client):
        # Same recovery path for an unexpected service failure.
        with ExitStack() as stack:
            _base(stack)
            stack.enter_context(
                patch(
                    "routes.store.StoreOrderService.convert_provisional_to_sale",
                    side_effect=RuntimeError("down"),
                )
            )
            resp = sc_client.post("/store/admin/provisional/1/approve")
        assert resp.status_code in (302, 303)

    def test_cancel_non_pending(self, sc_client):
        with ExitStack() as stack:
            _base(stack, provisional=_provisional(status="converted"))
            resp = sc_client.post("/store/admin/provisional/1/cancel")
        assert resp.status_code in (302, 303)

    def test_cancel_success(self, sc_client):
        prov = _provisional()
        with ExitStack() as stack:
            ctx = _base(stack, provisional=prov)
            resp = sc_client.post("/store/admin/provisional/1/cancel")
        assert resp.status_code in (302, 303)
        assert prov.status == "cancelled"
        assert ctx["prov_cls"].query.filter_by.return_value.first_or_404.called


# ─── storefront helpers ──────────────────────────────────────────────────────


class TestStorefrontHelpers:
    def test_safe_hex_color_valid_and_invalid(self, sc_client):
        from routes.store import _safe_hex_color

        assert _safe_hex_color("#1B7A4E", "fallback") == "#1B7A4E"
        assert _safe_hex_color("#12345678", "fallback") == "#12345678"
        assert _safe_hex_color("not-a-color", "fallback") == "fallback"
        assert _safe_hex_color(None, "fallback") == "fallback"

    def test_parse_int(self, sc_client):
        from routes.store import _parse_int

        assert _parse_int(None) is None
        assert _parse_int("  ") is None
        assert _parse_int("42") == 42
        assert _parse_int("abc", 7) == 7

    def test_storefront_context_success(self, sc_client):
        from routes.store import _storefront_context

        with ExitStack() as stack:
            ctx = _base(stack)
            stack.enter_context(patch("utils.shop_i18n.shop_lang", return_value="ar"))
            stack.enter_context(patch("utils.shop_i18n.t", side_effect=lambda k, lang=None: k))
            with sc_client.application.test_request_context("/store/"):
                result = _storefront_context(ctx["store"])
        assert result["lang"] == "ar"
        assert result["is_rtl"] is True
        assert result["cart_count"] == 0
        assert result["theme_primary"] == "#1B7A4E"

    def test_storefront_context_bad_cart(self, sc_client):
        from routes.store import _storefront_context

        with ExitStack() as stack:
            ctx = _base(stack, cart={"x": "not-a-number"})
            stack.enter_context(patch("utils.shop_i18n.shop_lang", return_value="en"))
            stack.enter_context(patch("utils.shop_i18n.t", side_effect=lambda k, lang=None: k))
            with sc_client.application.test_request_context("/store/"):
                result = _storefront_context(ctx["store"])
        assert result["cart_count"] == 0
        assert result["is_rtl"] is False


# ─── public storefront routes ────────────────────────────────────────────────


class TestPublicStorefront:
    def test_catalog_by_host(self, sc_client):
        with ExitStack() as stack:
            ctx = _base(stack)
            resp = sc_client.get("/store/")
        assert resp.status_code == 200
        assert ctx["render"].call_args[0][0] == "store/public_catalog.html"

    def test_catalog_by_slug(self, sc_client):
        with ExitStack() as stack:
            _base(stack, host_store=None)
            resp = sc_client.get("/store/?store=demo-store")
        assert resp.status_code == 200

    def test_catalog_no_store_404(self, sc_client):
        with ExitStack() as stack:
            _base(stack, host_store=None, slug_store=None)
            resp = sc_client.get("/store/?store=missing")
        assert resp.status_code == 404

    def test_catalog_no_host_no_slug_404(self, sc_client):
        with ExitStack() as stack:
            _base(stack, host_store=None)
            resp = sc_client.get("/store/")
        assert resp.status_code == 404

    def test_catalog_store_unavailable_403(self, sc_client):
        with ExitStack() as stack:
            _base(stack, public_available=False)
            resp = sc_client.get("/store/")
        assert resp.status_code == 403

    def test_product_detail(self, sc_client):
        # store_currency comes from the spread context only; passing it twice
        # used to break every product page with a duplicate-keyword TypeError.
        with ExitStack() as stack:
            ctx = _base(stack)
            resp = sc_client.get("/store/product/5")
        assert resp.status_code == 200
        assert ctx["render"].call_args.kwargs["store_currency"] == "AED"

    def test_cart(self, sc_client):
        with ExitStack() as stack:
            ctx = _base(stack)
            resp = sc_client.get("/store/cart")
        assert resp.status_code == 200
        assert ctx["render"].call_args[0][0] == "store/public_cart.html"

    def test_cart_add_invalid_quantity(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post("/store/cart/add", json={"product_id": 5, "quantity": 0})
        assert resp.status_code == 400

    def test_cart_add_product_not_found(self, sc_client):
        with ExitStack() as stack:
            ctx = _base(stack)
            ctx["product_query"].filter_by.return_value.first.return_value = None
            resp = sc_client.post("/store/cart/add", json={"product_id": 999})
        assert resp.status_code == 404

    def test_cart_add_success(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post("/store/cart/add", json={"product_id": 5, "quantity": 2})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_cart_remove_invalid(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post("/store/cart/remove", json={"product_id": 0})
        assert resp.status_code == 400

    def test_cart_remove_success(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post("/store/cart/remove", json={"product_id": 5})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


# ─── public_checkout ─────────────────────────────────────────────────────────


class TestPublicCheckout:
    def test_invalid_phone(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post("/store/public-checkout", json={"customer_phone": "123"})
        assert resp.status_code == 400

    def test_empty_cart(self, sc_client):
        with ExitStack() as stack:
            _base(stack)
            resp = sc_client.post("/store/public-checkout", json={"customer_phone": "+971501234567"})
        assert resp.status_code == 400

    def test_no_valid_lines(self, sc_client):
        with ExitStack() as stack:
            ctx = _base(stack, cart={"999": 1})
            ctx["product_query"].filter_by.return_value.first.return_value = None
            resp = sc_client.post("/store/public-checkout", json={"customer_phone": "+971501234567"})
        assert resp.status_code == 400

    def test_success(self, sc_client):
        with ExitStack() as stack:
            _base(stack, cart={"5": 2}, rate=Decimal("3.7"))
            resp = sc_client.post(
                "/store/public-checkout",
                json={
                    "customer_name": "John",
                    "customer_phone": "+971501234567",
                    "customer_email": "john@example.com",
                    "currency_code": "USD",
                },
            )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["provisional_number"] == "PROV-1"
        assert body["whatsapp_sent"] is True

    def test_success_without_stored_rate(self, sc_client):
        with ExitStack() as stack:
            _base(stack, cart={"5": 2})
            resp = sc_client.post(
                "/store/public-checkout",
                json={"customer_phone": "+971501234567", "currency_code": "USD"},
            )
        assert resp.status_code == 200

    def test_success_fractional_qty_and_regular_price(self, sc_client):
        with ExitStack() as stack:
            _base(stack, cart={"5": 1.5})
            stack.enter_context(patch("routes.store.StorePricingService.resolve_store_price", return_value=None))
            resp = sc_client.post(
                "/store/public-checkout",
                json={"customer_phone": "+971501234567"},
            )
        assert resp.status_code == 200


# ─── public_reports ──────────────────────────────────────────────────────────


class TestPublicReports:
    def test_reports_renders(self, sc_client):
        with ExitStack() as stack:
            ctx = _base(stack)
            resp = sc_client.get("/store/reports")
        assert resp.status_code == 200
        assert ctx["render"].call_args[0][0] == "store/store_reports.html"
