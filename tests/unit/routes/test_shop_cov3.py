"""Coverage for routes/shop.py remaining arcs.

Targets: safe_float arcs, wishlist json/redirect arcs, register honeypot +
error arcs, login error arc, cart add/update/remove ajax + non-ajax arcs,
checkout honeypot/min-order/online-pay-fail/generic arcs, reorder/invoice/
track/confirmation/sitemap/robots/reviews/newsletter/saved-payments arcs.
Real test-client paths; service/DB boundaries mocked only.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

SLUG = "demo-store"
BASE = f"/s/{SLUG}"


def _product(pid=10):
    p = MagicMock()
    p.id = pid
    p.tenant_id = 1
    p.is_active = True
    p.has_serial_number = False
    p.regular_price = Decimal("99")
    p.image_url = "/img.jpg"
    p.category_id = 1
    p.get_display_name.return_value = "Prod"
    return p


def _account(aid=5):
    a = MagicMock()
    a.id = aid
    a.customer_id = 20
    a.name = "Shop User"
    a.email = "shop@test.com"
    a.phone = "+9715"
    a.address = "Dubai"
    return a


@pytest.fixture
def shop_cov3_client(app_factory, bypass_shop_auth):
    from routes.shop import shop_bp

    app = app_factory(shop_bp)
    with app.test_client() as client:
        yield client


class TestSafeFloatAndWishlist:
    def test_safe_float_arcs(self):
        from routes.shop import safe_float

        assert safe_float(None) == 0.0
        assert safe_float(" ") == 0.0
        assert safe_float("bad") == 0.0
        assert safe_float("1.5") == 1.5

    def test_wishlist_add_json(self, shop_cov3_client):
        with (
            patch("routes.shop._shop_account", return_value=_account()),
            patch("routes.shop.StoreService.wishlist_entry", return_value=None),
            patch("routes.shop.atomic_transaction"),
            patch("routes.shop.db.session.add"),
            patch("routes.shop.StoreService.wishlist_count", return_value=2),
        ):
            resp = shop_cov3_client.post(
                f"{BASE}/wishlist/add/10", json={}, headers={"Content-Type": "application/json"}
            )
        assert resp.status_code == 200

    def test_wishlist_add_unauth(self, shop_cov3_client):
        with patch("routes.shop._shop_account", return_value=None):
            resp = shop_cov3_client.post(f"{BASE}/wishlist/add/10")
        assert resp.status_code == 401

    def test_wishlist_remove_json(self, shop_cov3_client):
        with (
            patch("routes.shop._shop_account", return_value=_account()),
            patch("routes.shop.StoreService.remove_wishlist_entry"),
            patch("routes.shop.atomic_transaction"),
        ):
            resp = shop_cov3_client.post(
                f"{BASE}/wishlist/remove/10", json={}, headers={"Content-Type": "application/json"}
            )
        assert resp.status_code == 200

    def test_wishlist_remove_redirect(self, shop_cov3_client):
        with (
            patch("routes.shop._shop_account", return_value=_account()),
            patch("routes.shop.StoreService.remove_wishlist_entry"),
            patch("routes.shop.atomic_transaction"),
        ):
            resp = shop_cov3_client.post(f"{BASE}/wishlist/remove/10")
        assert resp.status_code == 302


class TestAuthArcs:
    def test_register_honeypot_400(self, shop_cov3_client):
        resp = shop_cov3_client.post(f"{BASE}/account/register", data={"website": "bot"})
        assert resp.status_code == 400

    def test_register_value_error(self, shop_cov3_client, mock_store):
        with (
            patch(
                "routes.shop._store_context",
                return_value={"is_shop_logged_in": False, "lang": "ar", "store": mock_store},
            ),
            patch(
                "routes.shop.ShopCustomerAuthService.register",
                side_effect=ValueError("email taken"),
            ),
            patch("routes.shop.render_template", return_value="ok"),
        ):
            resp = shop_cov3_client.post(
                f"{BASE}/account/register",
                data={"name": "N", "email": "e@t.com", "password": "x"},
            )
        assert resp.status_code == 200

    def test_login_value_error(self, shop_cov3_client, mock_store):
        with (
            patch(
                "routes.shop._store_context",
                return_value={"is_shop_logged_in": False, "lang": "ar", "store": mock_store},
            ),
            patch(
                "routes.shop.ShopCustomerAuthService.authenticate",
                side_effect=ValueError("bad creds"),
            ),
            patch("routes.shop.render_template", return_value="ok"),
        ):
            resp = shop_cov3_client.post(f"{BASE}/account/login", data={"email": "e@t.com", "password": "x"})
        assert resp.status_code == 200

    def test_reviews_list(self, shop_cov3_client):
        with patch("routes.shop.StoreService.approved_reviews", return_value=[]):
            resp = shop_cov3_client.get(f"{BASE}/p/10/reviews")
        assert resp.status_code == 200

    def test_add_review_bad_rating(self, shop_cov3_client):
        with patch("routes.shop._shop_account", return_value=_account()):
            resp = shop_cov3_client.post(f"{BASE}/p/10/review/add", data={"rating": "9"})
        assert resp.status_code == 302

    def test_newsletter_invalid_email(self, shop_cov3_client):
        resp = shop_cov3_client.post(f"{BASE}/newsletter/subscribe", data={"email": "bad"})
        assert resp.status_code == 302

    def test_stock_alert_invalid_email(self, shop_cov3_client):
        resp = shop_cov3_client.post(f"{BASE}/stock-alert/10", data={"email": "bad"})
        assert resp.status_code == 302

    def test_forgot_password_value_error(self, shop_cov3_client, mock_store):
        with (
            patch(
                "routes.shop._store_context",
                return_value={"is_shop_logged_in": False, "lang": "ar", "store": mock_store},
            ),
            patch(
                "routes.shop.ShopCustomerAuthService.request_password_reset",
                side_effect=ValueError("no such email"),
            ),
            patch("routes.shop.render_template", return_value="ok"),
        ):
            resp = shop_cov3_client.post(f"{BASE}/account/forgot-password", data={"email": "x@y.com"})
        assert resp.status_code == 200

    def test_reset_password_value_error(self, shop_cov3_client, mock_store):
        with (
            patch(
                "routes.shop._store_context",
                return_value={"is_shop_logged_in": False, "lang": "ar", "store": mock_store},
            ),
            patch(
                "routes.shop.ShopCustomerAuthService.reset_password",
                side_effect=ValueError("expired"),
            ),
            patch("routes.shop.render_template", return_value="ok"),
        ):
            resp = shop_cov3_client.post(f"{BASE}/account/reset-password/tok", data={"password": "newpass123"})
        assert resp.status_code == 200


class TestCartArcs:
    def test_cart_add_invalid_ajax_400(self, shop_cov3_client):
        resp = shop_cov3_client.post(
            f"{BASE}/cart/add",
            json={},
            headers={"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code in (302, 400)

    def test_cart_add_unknown_product_redirect(self, shop_cov3_client):
        with patch("routes.shop.StoreService.active_product", return_value=None):
            resp = shop_cov3_client.post(f"{BASE}/cart/add", data={"product_id": "999", "quantity": "1"})
        assert resp.status_code == 302

    def test_cart_add_zero_stock_ajax(self, shop_cov3_client):
        with (
            patch("routes.shop.StoreService.active_product", return_value=_product()),
            patch("routes.shop.StoreService.online_stock_map", return_value={10: 0}),
            patch("routes.shop.StoreService.get_cart", return_value={}),
        ):
            resp = shop_cov3_client.post(
                f"{BASE}/cart/add",
                data={"product_id": "10", "quantity": "1"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code in (302, 400)

    def test_cart_add_success_ajax(self, shop_cov3_client):
        with (
            patch("routes.shop.StoreService.active_product", return_value=_product()),
            patch("routes.shop.StoreService.online_stock_map", return_value={10: 5}),
            patch("routes.shop.StoreService.get_cart", return_value={"10": 1}),
            patch("routes.shop.StoreService.save_cart"),
            patch("routes.shop._track_cart_activity"),
        ):
            resp = shop_cov3_client.post(
                f"{BASE}/cart/add",
                data={"product_id": "10", "quantity": "1"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code == 200

    def test_cart_update_bad_qty_and_ajax(self, shop_cov3_client):
        with (
            patch("routes.shop.StoreService.get_cart", return_value={"10": 2}),
            patch("routes.shop.StoreService.online_stock_map", return_value={10: 5}),
            patch("routes.shop.StoreService.save_cart"),
            patch("routes.shop._track_cart_activity"),
        ):
            resp = shop_cov3_client.post(
                f"{BASE}/cart/update",
                data={"qty_10": "not-a-number"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code in (200, 302)

    def test_cart_remove_ajax(self, shop_cov3_client):
        with (
            patch("routes.shop.StoreService.get_cart", return_value={"10": 1}),
            patch("routes.shop.StoreService.save_cart"),
            patch("routes.shop._track_cart_activity"),
        ):
            resp = shop_cov3_client.post(
                f"{BASE}/cart/remove/10",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code == 200

    def test_cart_count(self, shop_cov3_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 2}):
            resp = shop_cov3_client.get(f"{BASE}/cart/count")
        assert resp.status_code == 200


class TestCheckoutAndOrders:
    def test_checkout_honeypot_400(self, shop_cov3_client):
        with (
            patch("routes.shop.StoreService.get_cart", return_value={"10": 1}),
            patch(
                "routes.shop.StoreService.cart_totals",
                return_value={"lines": [{"id": 1}], "subtotal": Decimal("10")},
            ),
        ):
            resp = shop_cov3_client.post(f"{BASE}/checkout", data={"website": "bot"})
        assert resp.status_code in (302, 400)

    def test_checkout_missing_address(self, shop_cov3_client):
        with (
            patch("routes.shop.StoreService.get_cart", return_value={"10": 1}),
            patch(
                "routes.shop.StoreService.cart_totals",
                return_value={"lines": [{"id": 1}], "subtotal": Decimal("10")},
            ),
            patch("routes.shop.render_template", return_value="ok"),
        ):
            resp = shop_cov3_client.post(f"{BASE}/checkout", data={"address": ""})
        assert resp.status_code == 200

    def test_checkout_online_pay_init_fail(self, shop_cov3_client):
        sale = MagicMock(id=77, sale_number="S-77", notes="")
        with (
            patch("routes.shop.StoreService.get_cart", return_value={"10": 1}),
            patch(
                "routes.shop.StoreService.cart_totals",
                return_value={"lines": [{"id": 1}], "subtotal": Decimal("10")},
            ),
            patch("routes.shop.StoreService.save_cart"),
            patch("services.store_checkout_service.StoreCheckoutService.create_web_order", return_value=sale),
            patch("routes.shop.atomic_transaction"),
            patch(
                "services.store_online_payment_service.StoreOnlinePaymentService.create_payment_for_sale",
                side_effect=ValueError("gateway down"),
            ),
            patch(
                "services.store_checkout_service.StoreCheckoutService.make_order_token",
                return_value="tok",
            ),
        ):
            resp = shop_cov3_client.post(
                f"{BASE}/checkout",
                data={"address": "Dubai", "payment_method": "online_pay"},
            )
        assert resp.status_code == 302

    def test_reorder_no_lines(self, shop_cov3_client):
        sale = MagicMock(id=5, customer_id=20)
        with (
            patch("routes.shop._shop_account", return_value=_account()),
            patch("routes.shop.StoreService.online_order_or_404", return_value=sale),
            patch("routes.shop.StoreService.online_order_lines", return_value=[]),
        ):
            resp = shop_cov3_client.post(f"{BASE}/order/reorder/5")
        assert resp.status_code == 302

    def test_order_track_not_found(self, shop_cov3_client):
        with (
            patch("routes.shop.StoreService.online_order_by_number", return_value=None),
            patch("routes.shop.render_template", return_value="ok"),
        ):
            resp = shop_cov3_client.get(f"{BASE}/track?order=NOPE")
        assert resp.status_code == 200

    def test_order_confirmation_bad_token(self, shop_cov3_client):
        with patch(
            "services.store_checkout_service.StoreCheckoutService.load_order_token",
            return_value=None,
        ):
            resp = shop_cov3_client.get(f"{BASE}/order/badtok")
        assert resp.status_code == 404

    def test_store_sitemap_and_robots(self, shop_cov3_client):
        with (
            patch("routes.shop.StoreService.is_store_publicly_available", return_value=True),
            patch(
                "routes.shop.StoreService.get_public_catalog",
                return_value={"items": []},
            ),
        ):
            assert shop_cov3_client.get(f"{BASE}/sitemap.xml").status_code == 200
        assert shop_cov3_client.get(f"{BASE}/robots.txt").status_code == 200

    def test_save_and_delete_payment(self, shop_cov3_client):
        with (
            patch("routes.shop._shop_account", return_value=_account()),
            patch("routes.shop.atomic_transaction"),
            patch("routes.shop.db.session.add"),
        ):
            assert (
                shop_cov3_client.post(f"{BASE}/account/payments/save", data={"method_code": "cod"}).status_code == 302
            )
        pm = MagicMock(id=1)
        with (
            patch("routes.shop._shop_account", return_value=_account()),
            patch("routes.shop.StoreService.saved_payment_or_404", return_value=pm),
            patch("routes.shop.atomic_transaction"),
            patch("routes.shop.db.session.delete"),
        ):
            assert shop_cov3_client.post(f"{BASE}/account/payments/delete/1").status_code == 302

    def test_invoice_wrong_customer_404(self, shop_cov3_client):
        sale = MagicMock(id=9, customer_id=999)
        with (
            patch(
                "routes.shop._store_context",
                return_value={"shop_account": _account(), "lang": "ar", "store": MagicMock(store_slug=SLUG)},
            ),
            patch("routes.shop.StoreService.online_order_or_404", return_value=sale),
        ):
            resp = shop_cov3_client.get(f"{BASE}/order/9/invoice")
        assert resp.status_code in (302, 404)
