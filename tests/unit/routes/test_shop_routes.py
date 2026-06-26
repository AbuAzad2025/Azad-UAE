from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import NotFound


SLUG = "demo-store"
BASE = f"/s/{SLUG}"


def _mock_product(pid=10, tenant_id=1):
    product = MagicMock()
    product.id = pid
    product.tenant_id = tenant_id
    product.is_active = True
    product.has_serial_number = False
    product.regular_price = Decimal("99.00")
    product.image_url = "/img/p.jpg"
    product.category_id = 1
    product.get_display_name.return_value = "Test Product"
    return product


def _mock_account(aid=5, customer_id=20):
    account = MagicMock()
    account.id = aid
    account.customer_id = customer_id
    account.name = "Shop User"
    account.email = "shop@test.com"
    account.phone = "+971500000001"
    account.address = "Dubai Marina"
    return account


def _cart_totals(lines=None):
    if lines is None:
        lines = [{"product_id": 10, "qty": 1, "line_total": Decimal("99")}]
    return {
        "lines": lines,
        "subtotal": Decimal("99"),
        "total": Decimal("99"),
        "tax": Decimal("0"),
        "count": len(lines),
    }


def _catalog_items(product=None):
    product = product or _mock_product()
    return {"items": [{"product": product}], "page": 1, "pages": 1, "total": 1}


class TestShopStoreResolution:
    def test_store_slug_not_found_returns_404(self, shop_client):
        with patch("routes.shop.StoreService.get_store_by_slug", return_value=None):
            resp = shop_client.get(f"/s/unknown-store/")
        assert resp.status_code == 404

    def test_stores_globally_disabled_returns_503(self, shop_client, mock_store):
        with patch("routes.shop.StoreService.stores_globally_enabled", return_value=False):
            resp = shop_client.get(f"{BASE}/")
        assert resp.status_code == 503

    def test_platform_locked_store_returns_503(self, shop_client, mock_store):
        with patch("routes.shop.StoreService.is_platform_locked", return_value=True):
            resp = shop_client.get(f"{BASE}/cart")
        assert resp.status_code == 503

    def test_tenant_disabled_store_returns_503(self, shop_client, mock_store):
        mock_store.is_enabled = False
        with patch("routes.shop.StoreService.get_store_by_slug", return_value=mock_store):
            resp = shop_client.get(f"{BASE}/")
        assert resp.status_code == 503


class TestShopLangAndOffline:
    def test_set_lang_en_redirects(self, shop_client, mock_store):
        with patch("routes.shop.safe_redirect_target", return_value=f"{BASE}/"):
            resp = shop_client.get(f"{BASE}/lang/en", headers={"Referer": f"{BASE}/"})
        assert resp.status_code in (302, 303)

    def test_set_lang_ar_redirects(self, shop_client, mock_store):
        with patch("routes.shop.safe_redirect_target", return_value=f"{BASE}/"):
            resp = shop_client.get(f"{BASE}/lang/ar", headers={"Referer": f"{BASE}/"})
        assert resp.status_code in (302, 303)

    def test_offline_page_renders(self, shop_client):
        with patch("routes.shop.StoreService.get_store_by_slug") as get_store:
            get_store.return_value.is_enabled = True
            resp = shop_client.get(f"{BASE}/offline")
        assert resp.status_code == 200


class TestShopWishlist:
    def test_wishlist_add_requires_login(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.post(
                f"{BASE}/wishlist/add/10",
                json={},
                content_type="application/json",
            )
        assert resp.status_code == 401

    def test_wishlist_add_json_success(self, shop_client):
        account = _mock_account()
        wl_query = MagicMock()
        wl_query.filter_by.return_value.first.return_value = None
        wl_query.filter_by.return_value.count.return_value = 1
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.ShopWishlist.query", wl_query), \
             patch("routes.shop.db.session"):
            resp = shop_client.post(
                f"{BASE}/wishlist/add/10",
                json={},
                content_type="application/json",
            )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_wishlist_add_redirect_when_not_json(self, shop_client):
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.ShopWishlist.query"):
            resp = shop_client.post(f"{BASE}/wishlist/add/10")
        assert resp.status_code in (302, 303)

    def test_wishlist_remove_requires_login(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.post(
                f"{BASE}/wishlist/remove/10",
                json={},
                content_type="application/json",
            )
        assert resp.status_code == 401

    def test_wishlist_remove_json_success(self, shop_client):
        account = _mock_account()
        wl_query = MagicMock()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.ShopWishlist.query", wl_query), \
             patch("routes.shop.db.session"):
            resp = shop_client.post(
                f"{BASE}/wishlist/remove/10",
                json={},
                content_type="application/json",
            )
        assert resp.status_code == 200
        assert resp.get_json()["wishlisted"] is False

    def test_wishlist_view_redirects_when_anonymous(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.get(f"{BASE}/wishlist")
        assert resp.status_code in (302, 303)

    def test_wishlist_view_renders_when_logged_in(self, shop_client):
        account = _mock_account()
        wl_query = MagicMock()
        wl_query.filter_by.return_value.order_by.return_value.all.return_value = []
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.ShopWishlist.query", wl_query):
            resp = shop_client.get(f"{BASE}/wishlist")
        assert resp.status_code == 200


class TestShopAccountAuth:
    def test_account_login_get(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.get(f"{BASE}/account/login")
        assert resp.status_code == 200

    def test_account_login_post_success(self, shop_client):
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None), \
             patch("routes.shop.ShopCustomerAuthService.authenticate", return_value=account), \
             patch("routes.shop.ShopCustomerAuthService.login"), \
             patch("routes.shop.safe_redirect_target", return_value=f"{BASE}/"):
            resp = shop_client.post(f"{BASE}/account/login", data={
                "email": "shop@test.com",
                "password": "secret",
            })
        assert resp.status_code in (302, 303)

    def test_account_login_post_invalid_credentials(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None), \
             patch("routes.shop.ShopCustomerAuthService.authenticate", side_effect=ValueError("bad creds")):
            resp = shop_client.post(f"{BASE}/account/login", data={
                "email": "bad@test.com",
                "password": "wrong",
            })
        assert resp.status_code == 200

    def test_account_login_redirects_when_already_logged_in(self, shop_client):
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.safe_redirect_target", return_value=f"{BASE}/"):
            resp = shop_client.get(f"{BASE}/account/login")
        assert resp.status_code in (302, 303)

    def test_account_register_get(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.get(f"{BASE}/account/register")
        assert resp.status_code == 200

    def test_account_register_post_success(self, shop_client):
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None), \
             patch("routes.shop.ShopCustomerAuthService.register", return_value=account), \
             patch("routes.shop.ShopCustomerAuthService.login"):
            resp = shop_client.post(f"{BASE}/account/register", data={
                "name": "Shop User",
                "email": "shop@test.com",
                "phone": "+971500000001",
                "password": "secret123",
            })
        assert resp.status_code in (302, 303)

    def test_account_register_honeypot_returns_400(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.post(f"{BASE}/account/register", data={
                "name": "Bot",
                "email": "bot@test.com",
                "website": "http://spam.example",
            })
        assert resp.status_code == 400

    def test_account_logout_clears_cart(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.logout") as logout, \
             patch("routes.shop.StoreService.save_cart") as save_cart:
            resp = shop_client.post(f"{BASE}/account/logout")
        logout.assert_called_once()
        save_cart.assert_called_once()
        assert resp.status_code in (302, 303)


class TestShopAccountOrders:
    def test_account_orders_redirects_anonymous(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.get(f"{BASE}/account/orders")
        assert resp.status_code in (302, 303)

    def test_account_orders_lists_orders(self, shop_client):
        account = _mock_account()
        sale = MagicMock()
        sale.id = 100
        pm = MagicMock()
        pm.code = "cod"
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.StoreOrderService.list_for_customer", return_value=[sale]), \
             patch("routes.shop.StorePaymentMethodService.list_all", return_value=[pm]):
            resp = shop_client.get(f"{BASE}/account/orders")
        assert resp.status_code == 200

    def test_account_order_detail_not_found(self, shop_client):
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.StoreOrderService.get_tenant_order", return_value=None):
            resp = shop_client.get(f"{BASE}/account/orders/999")
        assert resp.status_code == 404

    def test_account_order_detail_wrong_customer_404(self, shop_client):
        account = _mock_account(customer_id=20)
        sale = MagicMock()
        sale.customer_id = 99
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.StoreOrderService.get_tenant_order", return_value=sale):
            resp = shop_client.get(f"{BASE}/account/orders/100")
        assert resp.status_code == 404

    def test_account_order_detail_success(self, shop_client):
        account = _mock_account(customer_id=20)
        sale = MagicMock()
        sale.customer_id = 20
        sale.checkout_payment_method = "cod"
        sale.status = "confirmed"
        pm = MagicMock()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.StoreOrderService.get_tenant_order", return_value=sale), \
             patch("routes.shop.StorePaymentMethodService.get_by_code", return_value=pm), \
             patch("routes.shop.StoreOrderService.status_label", return_value="Confirmed"):
            resp = shop_client.get(f"{BASE}/account/orders/100")
        assert resp.status_code == 200


class TestShopCatalogAndSearch:
    def test_catalog_get(self, shop_client):
        cat_query = MagicMock()
        cat_query.filter_by.return_value.order_by.return_value.all.return_value = []
        with patch("routes.shop.StoreService.get_public_catalog", return_value=_catalog_items()), \
             patch("routes.shop.ProductCategory.query", cat_query):
            resp = shop_client.get(f"{BASE}/")
        assert resp.status_code == 200

    def test_catalog_with_utm_params(self, shop_client):
        cat_query = MagicMock()
        cat_query.filter_by.return_value.order_by.return_value.all.return_value = []
        with patch("routes.shop.StoreService.get_public_catalog", return_value=_catalog_items()), \
             patch("routes.shop.ProductCategory.query", cat_query):
            resp = shop_client.get(f"{BASE}/?utm_source=google&utm_campaign=sale")
        assert resp.status_code == 200

    def test_api_search_empty_query(self, shop_client):
        with patch("routes.shop.StoreService.get_public_catalog"):
            resp = shop_client.get(f"{BASE}/api/search?q=a")
        assert resp.status_code == 200
        assert resp.get_json()["results"] == []

    def test_api_search_returns_results(self, shop_client):
        product = _mock_product()
        with patch("routes.shop.StoreService.get_public_catalog", return_value=_catalog_items(product)):
            resp = shop_client.get(f"{BASE}/api/search?q=test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["results"]) == 1
        assert data["results"][0]["id"] == product.id


class TestShopProduct:
    def test_product_detail_success(self, shop_client):
        product = _mock_product()
        pq = MagicMock()
        pq.filter_by.return_value.first_or_404.return_value = product
        rq = MagicMock()
        rq.filter_by.return_value.order_by.return_value.all.return_value = []
        with patch("routes.shop.Product.query", pq), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("5")}), \
             patch("routes.shop.StoreService.get_related_products", return_value=[]), \
             patch("routes.shop.StoreService.get_recently_viewed_products", return_value=[]), \
             patch("routes.shop.StoreService.get_product_variants", return_value=[]), \
             patch("routes.shop.ShopCustomerAuthService.whatsapp_order_url", return_value="https://wa.me/"), \
             patch("routes.shop.ShopReview.query", rq):
            resp = shop_client.get(f"{BASE}/p/10")
        assert resp.status_code == 200

    def test_product_detail_wrong_tenant_404(self, shop_client):
        pq = MagicMock()
        pq.filter_by.return_value.first_or_404.side_effect = NotFound()
        with patch("routes.shop.Product.query", pq):
            resp = shop_client.get(f"{BASE}/p/10")
        assert resp.status_code == 404

    def test_product_detail_out_of_stock_404(self, shop_client):
        product = _mock_product()
        pq = MagicMock()
        pq.filter_by.return_value.first_or_404.return_value = product
        with patch("routes.shop.Product.query", pq), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("0")}):
            resp = shop_client.get(f"{BASE}/p/10")
        assert resp.status_code == 404

    def test_product_reviews_json(self, shop_client):
        review = MagicMock()
        review.id = 1
        review.customer_name = "Ali"
        review.rating = 5
        review.comment = "Great"
        review.created_at = None
        rq = MagicMock()
        rq.filter_by.return_value.order_by.return_value.all.return_value = [review]
        with patch("routes.shop.ShopReview.query", rq):
            resp = shop_client.get(f"{BASE}/p/10/reviews")
        assert resp.status_code == 200
        assert len(resp.get_json()["reviews"]) == 1

    def test_add_review_requires_login(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.post(f"{BASE}/p/10/review/add", data={"rating": "5"})
        assert resp.status_code in (302, 303)

    def test_add_review_invalid_rating(self, shop_client):
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account):
            resp = shop_client.post(f"{BASE}/p/10/review/add", data={"rating": "9"})
        assert resp.status_code in (302, 303)

    def test_add_review_success(self, shop_client):
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.db.session"):
            resp = shop_client.post(f"{BASE}/p/10/review/add", data={"rating": "5", "comment": "Nice"})
        assert resp.status_code in (302, 303)


class TestShopStockAlertAndNewsletter:
    def test_stock_alert_invalid_email(self, shop_client):
        with patch("routes.shop.safe_redirect_target", return_value=f"{BASE}/p/10"):
            resp = shop_client.post(f"{BASE}/stock-alert/10", data={"email": "bad"})
        assert resp.status_code in (302, 303)

    def test_stock_alert_creates_subscription(self, shop_client):
        alert_q = MagicMock()
        alert_q.filter_by.return_value.first.return_value = None
        with patch("models.shop_stock_alert.ShopStockAlert.query", alert_q), \
             patch("routes.shop.db.session"):
            resp = shop_client.post(f"{BASE}/stock-alert/10", data={"email": "a@test.com"})
        assert resp.status_code in (302, 303)

    def test_newsletter_invalid_email(self, shop_client):
        with patch("routes.shop.safe_redirect_target", return_value=f"{BASE}/"):
            resp = shop_client.post(f"{BASE}/newsletter/subscribe", data={"email": ""})
        assert resp.status_code in (302, 303)

    def test_newsletter_subscribe_success(self, shop_client):
        nl_q = MagicMock()
        nl_q.filter_by.return_value.first.return_value = None
        with patch("models.shop_newsletter.ShopNewsletter.query", nl_q), \
             patch("routes.shop.db.session"):
            resp = shop_client.post(f"{BASE}/newsletter/subscribe", data={"email": "sub@test.com"})
        assert resp.status_code in (302, 303)


class TestShopCart:
    def test_cart_view(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()):
            resp = shop_client.get(f"{BASE}/cart")
        assert resp.status_code == 200

    def test_cart_add_success(self, shop_client):
        product = _mock_product()
        pq = MagicMock()
        pq.filter_by.return_value.first.return_value = product
        with patch("routes.shop.Product.query", pq), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("10")}), \
             patch("routes.shop.StoreService.get_cart", return_value={}), \
             patch("routes.shop.StoreService.save_cart"), \
             patch("routes.shop._track_cart_activity"):
            resp = shop_client.post(f"{BASE}/cart/add", data={"product_id": "10", "quantity": "1"})
        assert resp.status_code in (302, 303)

    def test_cart_add_ajax_success(self, shop_client):
        product = _mock_product()
        pq = MagicMock()
        pq.filter_by.return_value.first.return_value = product
        with patch("routes.shop.Product.query", pq), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("10")}), \
             patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.save_cart"), \
             patch("routes.shop._track_cart_activity"):
            resp = shop_client.post(
                f"{BASE}/cart/add",
                data={"product_id": "10", "quantity": "1"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_cart_add_invalid_product(self, shop_client):
        pq = MagicMock()
        pq.filter_by.return_value.first.return_value = None
        with patch("routes.shop.Product.query", pq), \
             patch("routes.shop.safe_redirect_target", return_value=f"{BASE}/"):
            resp = shop_client.post(f"{BASE}/cart/add", data={"product_id": "99", "quantity": "1"})
        assert resp.status_code in (302, 303)

    def test_cart_add_closed_store_503(self, shop_client, mock_store):
        with patch("routes.shop.StoreService.stores_globally_enabled", return_value=False):
            resp = shop_client.post(f"{BASE}/cart/add", data={"product_id": "10"})
        assert resp.status_code == 503

    def test_cart_update(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 2}), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("5")}), \
             patch("routes.shop.StoreService.save_cart"), \
             patch("routes.shop._track_cart_activity"):
            resp = shop_client.post(f"{BASE}/cart/update", data={"qty_10": "1"})
        assert resp.status_code in (302, 303)

    def test_cart_update_ajax(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("5")}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()), \
             patch("routes.shop.StoreService.save_cart"), \
             patch("routes.shop._track_cart_activity"):
            resp = shop_client.post(
                f"{BASE}/cart/update",
                data={"qty_10": "1"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_cart_remove(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.save_cart"), \
             patch("routes.shop._track_cart_activity"):
            resp = shop_client.post(f"{BASE}/cart/remove/10")
        assert resp.status_code in (302, 303)

    def test_cart_remove_ajax(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={}), \
             patch("routes.shop.StoreService.save_cart"), \
             patch("routes.shop._track_cart_activity"):
            resp = shop_client.post(
                f"{BASE}/cart/remove/10",
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code == 200

    def test_cart_count_json(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 2, "11": 1}):
            resp = shop_client.get(f"{BASE}/cart/count")
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 3


class TestShopCheckout:
    def test_checkout_get_empty_cart_redirects(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals(lines=[])):
            resp = shop_client.get(f"{BASE}/checkout")
        assert resp.status_code in (302, 303)

    def test_checkout_get_with_items(self, shop_client):
        pm = MagicMock()
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()), \
             patch("routes.shop.StorePaymentMethodService.list_for_checkout", return_value=[pm]), \
             patch("routes.shop.StorePaymentMethodService.format_checkout_instructions", return_value="Pay COD"):
            resp = shop_client.get(f"{BASE}/checkout")
        assert resp.status_code == 200

    def test_checkout_post_success(self, shop_client):
        sale = MagicMock()
        sale.id = 500
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()), \
             patch("routes.shop.StorePaymentMethodService.list_for_checkout", return_value=[]), \
             patch("routes.shop.StoreCheckoutService.create_web_order", return_value=sale), \
             patch("routes.shop.StoreCheckoutService.make_order_token", return_value="tok-abc"), \
             patch("routes.shop.StoreService.save_cart"):
            resp = shop_client.post(f"{BASE}/checkout", data={
                "customer_name": "Ali",
                "phone": "+971500000001",
                "address": "Dubai",
                "payment_method": "cod",
            })
        assert resp.status_code in (302, 303)

    def test_checkout_post_honeypot_returns_400(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()):
            resp = shop_client.post(f"{BASE}/checkout", data={
                "website": "http://spam.example",
                "address": "Dubai",
            })
        assert resp.status_code == 400

    def test_checkout_post_missing_address_shows_error(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()), \
             patch("routes.shop.StorePaymentMethodService.list_for_checkout", return_value=[]), \
             patch("routes.shop.db.session.rollback"):
            resp = shop_client.post(f"{BASE}/checkout", data={
                "customer_name": "Ali",
                "phone": "+971500000001",
                "address": "",
                "payment_method": "cod",
            })
        assert resp.status_code == 200

    def test_checkout_post_online_payment_redirect(self, shop_client):
        sale = MagicMock()
        sale.id = 501
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()), \
             patch("routes.shop.StoreCheckoutService.create_web_order", return_value=sale), \
             patch("services.store_online_payment_service.StoreOnlinePaymentService.create_payment_for_sale", return_value={
                 "payment_url": "https://pay.example/checkout",
             }), \
             patch("routes.shop.StoreService.save_cart"):
            resp = shop_client.post(f"{BASE}/checkout", data={
                "customer_name": "Ali",
                "phone": "+971500000001",
                "address": "Dubai",
                "payment_method": "online_pay",
            })
        assert resp.status_code in (302, 303)

    def test_checkout_post_online_payment_init_failure(self, shop_client):
        sale = MagicMock()
        sale.id = 502
        sale.notes = ""
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()), \
             patch("routes.shop.StoreCheckoutService.create_web_order", return_value=sale), \
             patch("services.store_online_payment_service.StoreOnlinePaymentService.create_payment_for_sale", side_effect=ValueError("gateway down")), \
             patch("routes.shop.StoreCheckoutService.make_order_token", return_value="tok-fail"), \
             patch("routes.shop.StoreService.save_cart"), \
             patch("routes.shop.db.session.commit"), \
             patch("routes.shop.db.session.rollback"):
            resp = shop_client.post(f"{BASE}/checkout", data={
                "customer_name": "Ali",
                "phone": "+971500000001",
                "address": "Dubai",
                "payment_method": "online_pay",
            })
        assert resp.status_code in (302, 303)


class TestShopStaticPages:
    def test_return_policy_renders(self, shop_client, mock_store):
        mock_store.return_policy.return_value = "30-day returns"
        with patch("routes.shop.StoreService.get_store_by_slug", return_value=mock_store):
            resp = shop_client.get(f"{BASE}/return-policy")
        assert resp.status_code == 200

    def test_return_policy_missing_404(self, shop_client, mock_store):
        mock_store.return_policy.return_value = ""
        with patch("routes.shop.StoreService.get_store_by_slug", return_value=mock_store):
            resp = shop_client.get(f"{BASE}/return-policy")
        assert resp.status_code == 404

    def test_quick_view_renders(self, shop_client):
        product = _mock_product()
        pq = MagicMock()
        pq.filter_by.return_value.first_or_404.return_value = product
        with patch("routes.shop.Product.query", pq), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("3")}), \
             patch("routes.shop.ShopCustomerAuthService.whatsapp_order_url", return_value="https://wa.me/"):
            resp = shop_client.get(f"{BASE}/quick-view/10")
        assert resp.status_code == 200

    def test_sitemap_xml(self, shop_client):
        product = _mock_product()
        with patch("routes.shop.StoreService.is_store_publicly_available", return_value=True), \
             patch("routes.shop.StoreService.get_public_catalog", return_value=_catalog_items(product)):
            resp = shop_client.get(f"{BASE}/sitemap.xml")
        assert resp.status_code == 200
        assert b"urlset" in resp.data

    def test_sitemap_not_public_404(self, shop_client):
        with patch("routes.shop.StoreService.is_store_publicly_available", return_value=False):
            resp = shop_client.get(f"{BASE}/sitemap.xml")
        assert resp.status_code == 404

    def test_robots_txt(self, shop_client):
        resp = shop_client.get(f"{BASE}/robots.txt")
        assert resp.status_code == 200
        assert b"User-agent" in resp.data


class TestShopPasswordReset:
    def test_forgot_password_get(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.get(f"{BASE}/account/forgot-password")
        assert resp.status_code == 200

    def test_forgot_password_post(self, shop_client):
        account = MagicMock()
        account.password_reset_token = "reset-tok"
        with patch("routes.shop.ShopCustomerAuthService.request_password_reset", return_value=account), \
             patch("routes.shop.ShopCustomerAuthService.send_password_reset_email"):
            resp = shop_client.post(f"{BASE}/account/forgot-password", data={"email": "shop@test.com"})
        assert resp.status_code in (302, 303)

    def test_reset_password_get(self, shop_client):
        resp = shop_client.get(f"{BASE}/account/reset-password/some-token")
        assert resp.status_code == 200

    def test_reset_password_post_success(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.reset_password"):
            resp = shop_client.post(f"{BASE}/account/reset-password/some-token", data={
                "password": "newsecret123",
            })
        assert resp.status_code in (302, 303)


class TestShopSavedPayments:
    def test_saved_payments_redirects_anonymous(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.get(f"{BASE}/account/payments")
        assert resp.status_code in (302, 303)

    def test_saved_payments_lists(self, shop_client):
        account = _mock_account()
        pay_q = MagicMock()
        pay_q.filter_by.return_value.all.return_value = []
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("models.shop_saved_payment.ShopSavedPayment.query", pay_q):
            resp = shop_client.get(f"{BASE}/account/payments")
        assert resp.status_code == 200

    def test_save_payment_unauthorized(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.post(f"{BASE}/account/payments/save", data={"method_code": "cod"})
        assert resp.status_code == 401

    def test_save_payment_success(self, shop_client):
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.db.session"):
            resp = shop_client.post(f"{BASE}/account/payments/save", data={
                "method_code": "cod",
                "label": "Cash",
            })
        assert resp.status_code in (302, 303)

    def test_delete_saved_payment_success(self, shop_client):
        account = _mock_account()
        pm = MagicMock()
        pay_q = MagicMock()
        pay_q.filter_by.return_value.first_or_404.return_value = pm
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("models.shop_saved_payment.ShopSavedPayment.query", pay_q), \
             patch("routes.shop.db.session"):
            resp = shop_client.post(f"{BASE}/account/payments/delete/1")
        assert resp.status_code in (302, 303)


class TestShopReorderInvoiceTrack:
    def test_reorder_requires_login(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.post(f"{BASE}/order/reorder/50")
        assert resp.status_code in (302, 303)

    def test_reorder_adds_to_cart(self, shop_client):
        account = _mock_account(customer_id=20)
        sale = MagicMock()
        sale.id = 50
        sale.customer_id = 20
        line = MagicMock()
        line.product_id = 10
        line.quantity = Decimal("2")
        sq = MagicMock()
        sq.filter_by.return_value.first_or_404.return_value = sale
        sl_q = MagicMock()
        sl_q.filter_by.return_value.all.return_value = [line]
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.Sale.query", sq), \
             patch("routes.shop.SaleLine.query", sl_q), \
             patch("routes.shop.StoreService.get_cart", return_value={}), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("5")}), \
             patch("routes.shop.StoreService.save_cart"):
            resp = shop_client.post(f"{BASE}/order/reorder/50")
        assert resp.status_code in (302, 303)

    def test_order_invoice_requires_login(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.get(f"{BASE}/order/50/invoice")
        assert resp.status_code in (302, 303)

    def test_order_invoice_success(self, shop_client):
        account = _mock_account(customer_id=20)
        sale = MagicMock()
        sale.id = 50
        sale.customer_id = 20
        sale.checkout_payment_method = "cod"
        sale.status = "confirmed"
        sq = MagicMock()
        sq.filter_by.return_value.first_or_404.return_value = sale
        pm = MagicMock()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.Sale.query", sq), \
             patch("routes.shop.StorePaymentMethodService.get_by_code", return_value=pm), \
             patch("routes.shop.StoreOrderService.status_label", return_value="Confirmed"):
            resp = shop_client.get(f"{BASE}/order/50/invoice")
        assert resp.status_code == 200

    def test_order_track_empty(self, shop_client):
        with patch("routes.shop.StoreOrderService.status_label", return_value=None):
            resp = shop_client.get(f"{BASE}/track")
        assert resp.status_code == 200

    def test_order_track_found(self, shop_client):
        sale = MagicMock()
        sale.status = "shipped"
        sq = MagicMock()
        sq.filter_by.return_value.first.return_value = sale
        with patch("routes.shop.Sale.query", sq), \
             patch("routes.shop.StoreOrderService.status_label", return_value="Shipped"):
            resp = shop_client.get(f"{BASE}/track?order=ORD-001")
        assert resp.status_code == 200

    def test_order_track_not_found(self, shop_client):
        sq = MagicMock()
        sq.filter_by.return_value.first.return_value = None
        with patch("routes.shop.Sale.query", sq):
            resp = shop_client.get(f"{BASE}/track?order=MISSING")
        assert resp.status_code == 200


class TestShopOrderConfirmation:
    def test_order_confirmation_success(self, shop_client):
        sale = MagicMock()
        sale.id = 600
        sale.checkout_payment_method = "cod"
        sq = MagicMock()
        sq.filter_by.return_value.first_or_404.return_value = sale
        pm = MagicMock()
        with patch("routes.shop.StoreCheckoutService.load_order_token", return_value={
            "sale_id": 600,
            "tenant_id": 1,
        }), \
             patch("routes.shop.Sale.query", sq), \
             patch("routes.shop.StorePaymentMethodService.get_by_code", return_value=pm):
            resp = shop_client.get(f"{BASE}/order/valid-token")
        assert resp.status_code == 200

    def test_order_confirmation_wrong_tenant_404(self, shop_client):
        with patch("routes.shop.StoreCheckoutService.load_order_token", return_value={
            "sale_id": 600,
            "tenant_id": 999,
        }):
            resp = shop_client.get(f"{BASE}/order/wrong-tenant-token")
        assert resp.status_code == 404

    def test_order_confirmation_invalid_token_404(self, shop_client):
        with patch("routes.shop.StoreCheckoutService.load_order_token", return_value=None):
            resp = shop_client.get(f"{BASE}/order/bad-token")
        assert resp.status_code == 404


class TestShopRoutesExtended:
    def test_login_redirect_safe_next(self, shop_client):
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account):
            resp = shop_client.get(f"{BASE}/account/login?next=/s/{SLUG}/cart")
        assert resp.status_code in (302, 303)

    def test_tenant_suspended_returns_503(self, shop_client, mock_store):
        tenant = MagicMock()
        tenant.is_active = True
        tenant.is_suspended = True
        with patch("routes.shop.db.session") as mock_db:
            mock_db.get.return_value = tenant
            resp = shop_client.get(f"{BASE}/")
        assert resp.status_code == 503

    def test_wishlist_remove_non_json_redirect(self, shop_client):
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.db.session"):
            resp = shop_client.post(
                f"{BASE}/wishlist/remove/10",
                headers={"Referer": f"{BASE}/wishlist"},
            )
        assert resp.status_code in (302, 303)

    def test_account_register_closed_store(self, shop_client, mock_store):
        with patch("routes.shop.StoreService.stores_globally_enabled", return_value=False):
            resp = shop_client.get(f"{BASE}/account/register")
        assert resp.status_code == 503

    def test_account_register_already_logged_in(self, shop_client):
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account):
            resp = shop_client.get(f"{BASE}/account/register")
        assert resp.status_code in (302, 303)

    def test_cart_add_zero_qty_ajax(self, shop_client):
        resp = shop_client.post(
            f"{BASE}/cart/add",
            data={"product_id": "", "quantity": "0"},
            headers={"X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_cart_add_zero_qty_redirect(self, shop_client):
        resp = shop_client.post(
            f"{BASE}/cart/add",
            data={"product_id": "", "quantity": "0"},
            headers={"Referer": f"{BASE}/"},
        )
        assert resp.status_code in (302, 303)

    def test_cart_add_serial_product_ajax(self, shop_client):
        product = _mock_product()
        product.has_serial_number = True
        pq = MagicMock()
        pq.filter_by.return_value.first.return_value = product
        with patch("routes.shop.Product.query", pq):
            resp = shop_client.post(
                f"{BASE}/cart/add",
                data={"product_id": "10", "quantity": "1"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code == 400

    def test_cart_add_out_of_stock_ajax(self, shop_client):
        product = _mock_product()
        pq = MagicMock()
        pq.filter_by.return_value.first.return_value = product
        with patch("routes.shop.Product.query", pq), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("0")}):
            resp = shop_client.post(
                f"{BASE}/cart/add",
                data={"product_id": "10", "quantity": "1"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code == 400

    def test_cart_add_tracks_abandoned_cart(self, shop_client):
        product = _mock_product()
        pq = MagicMock()
        pq.filter_by.return_value.first.return_value = product
        account = _mock_account()
        ac_q = MagicMock()
        ac_q.filter_by.return_value.first.return_value = None
        with patch("routes.shop._require_open_store", return_value=None), \
             patch("routes.shop.Product.query", pq), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("5")}), \
             patch("routes.shop.StoreService.get_cart", return_value={}), \
             patch("routes.shop.StoreService.save_cart"), \
             patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("models.shop_abandoned_cart.ShopAbandonedCart.query", ac_q), \
             patch("routes.shop.db.session"):
            resp = shop_client.post(f"{BASE}/cart/add", data={"product_id": "10", "quantity": "1"})
        assert resp.status_code in (302, 303)

    def test_cart_update_closed_store_503(self, shop_client, mock_store):
        with patch("routes.shop.StoreService.stores_globally_enabled", return_value=False):
            resp = shop_client.post(f"{BASE}/cart/update", data={"qty_10": "2"})
        assert resp.status_code == 503

    def test_cart_update_skips_missing_fields(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("5")}), \
             patch("routes.shop.StoreService.save_cart"):
            resp = shop_client.post(f"{BASE}/cart/update", data={})
        assert resp.status_code in (302, 303)

    def test_cart_update_invalid_qty_skipped(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("5")}), \
             patch("routes.shop.StoreService.save_cart"):
            resp = shop_client.post(f"{BASE}/cart/update", data={"qty_10": "bad"})
        assert resp.status_code in (302, 303)

    def test_checkout_no_payment_methods_warning(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()), \
             patch("routes.shop.StorePaymentMethodService.list_for_checkout", return_value=[]):
            resp = shop_client.get(f"{BASE}/checkout")
        assert resp.status_code == 200

    def test_checkout_generic_exception_ar(self, shop_client):
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()), \
             patch("routes.shop.StorePaymentMethodService.list_for_checkout", return_value=[MagicMock()]), \
             patch("routes.shop.StoreCheckoutService.create_web_order", side_effect=RuntimeError("boom")), \
             patch("routes.shop.db.session.rollback"):
            resp = shop_client.post(f"{BASE}/checkout", data={
                "customer_name": "Ali",
                "phone": "+971500000001",
                "address": "Dubai",
            })
        assert resp.status_code == 200

    def test_checkout_online_payment_commit_failure(self, shop_client):
        sale = MagicMock()
        sale.id = 777
        sale.notes = ""
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()), \
             patch("routes.shop.StoreCheckoutService.create_web_order", return_value=sale), \
             patch("services.store_online_payment_service.StoreOnlinePaymentService.create_payment_for_sale", side_effect=ValueError("gateway")), \
             patch("routes.shop.StoreCheckoutService.make_order_token", return_value="tok"), \
             patch("routes.shop.StoreService.save_cart"), \
             patch("routes.shop.db.session.commit", side_effect=RuntimeError("commit fail")), \
             patch("routes.shop.db.session.rollback"):
            resp = shop_client.post(f"{BASE}/checkout", data={
                "customer_name": "Ali",
                "phone": "+971500000001",
                "address": "Dubai",
                "payment_method": "online_pay",
            })
        assert resp.status_code in (302, 303)

    def test_product_detail_closed_store(self, shop_client, mock_store):
        with patch("routes.shop.StoreService.stores_globally_enabled", return_value=False):
            resp = shop_client.get(f"{BASE}/p/10")
        assert resp.status_code == 503

    def test_reorder_wrong_customer_404(self, shop_client):
        account = _mock_account(customer_id=20)
        sale = MagicMock()
        sale.id = 50
        sale.customer_id = 99
        sq = MagicMock()
        sq.filter_by.return_value.first_or_404.return_value = sale
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.Sale.query", sq):
            resp = shop_client.post(f"{BASE}/order/reorder/50")
        assert resp.status_code == 404

    def test_reorder_no_lines_warning(self, shop_client):
        account = _mock_account(customer_id=20)
        sale = MagicMock()
        sale.id = 50
        sale.customer_id = 20
        sq = MagicMock()
        sq.filter_by.return_value.first_or_404.return_value = sale
        sl_q = MagicMock()
        sl_q.filter_by.return_value.all.return_value = []
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.Sale.query", sq), \
             patch("routes.shop.SaleLine.query", sl_q):
            resp = shop_client.post(f"{BASE}/order/reorder/50")
        assert resp.status_code in (302, 303)

    def test_delete_saved_payment_unauthorized_json(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.post(f"{BASE}/account/payments/delete/1")
        assert resp.status_code == 401

    def test_order_invoice_wrong_customer_404(self, shop_client):
        account = _mock_account(customer_id=20)
        sale = MagicMock()
        sale.id = 50
        sale.customer_id = 99
        sq = MagicMock()
        sq.filter_by.return_value.first_or_404.return_value = sale
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account), \
             patch("routes.shop.Sale.query", sq):
            resp = shop_client.get(f"{BASE}/order/50/invoice")
        assert resp.status_code == 404


class TestShopInternalHelpers:
    def test_require_shop_customer_redirects_anonymous(self, shop_client, mock_store):
        from routes.shop import _require_shop_customer
        with shop_client.application.test_request_context(f"{BASE}/cart"):
            result = _require_shop_customer(mock_store)
        assert result is not None

    def test_require_shop_customer_allows_logged_in(self, shop_client, mock_store):
        from routes.shop import _require_shop_customer
        account = _mock_account()
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=account):
            assert _require_shop_customer(mock_store) is None


class TestShopRoutesMoreCoverage:
    def test_wishlist_view_closed_store(self, shop_client, mock_store):
        with patch("routes.shop.StoreService.stores_globally_enabled", return_value=False):
            resp = shop_client.get(f"{BASE}/wishlist")
        assert resp.status_code == 503

    def test_account_login_closed_store(self, shop_client, mock_store):
        with patch("routes.shop.StoreService.stores_globally_enabled", return_value=False):
            resp = shop_client.get(f"{BASE}/account/login")
        assert resp.status_code == 503

    def test_account_register_value_error(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.register", side_effect=ValueError("bad data")):
            resp = shop_client.post(f"{BASE}/account/register", data={
                "name": "X",
                "email": "bad",
                "phone": "05012345678",
                "password": "secret12",
            })
        assert resp.status_code == 200

    def test_account_orders_closed_store(self, shop_client, mock_store):
        with patch("routes.shop.StoreService.stores_globally_enabled", return_value=False):
            resp = shop_client.get(f"{BASE}/account/orders")
        assert resp.status_code == 503

    def test_account_order_detail_closed_store(self, shop_client, mock_store):
        with patch("routes.shop.StoreService.stores_globally_enabled", return_value=False):
            resp = shop_client.get(f"{BASE}/account/orders/10")
        assert resp.status_code == 503

    def test_stock_alert_existing_subscription(self, shop_client):
        existing = MagicMock()
        alert_q = MagicMock()
        alert_q.filter_by.return_value.first.return_value = existing
        with patch("models.shop_stock_alert.ShopStockAlert.query", alert_q):
            resp = shop_client.post(f"{BASE}/stock-alert/10", data={"email": "a@b.com"})
        assert resp.status_code in (302, 303)

    def test_account_order_detail_anonymous_redirect(self, shop_client):
        with patch("routes.shop.ShopCustomerAuthService.get_logged_in_account", return_value=None):
            resp = shop_client.get(f"{BASE}/account/orders/10")
        assert resp.status_code in (302, 303)

    def test_cart_add_out_of_stock_redirect(self, shop_client):
        product = _mock_product()
        pq = MagicMock()
        pq.filter_by.return_value.first.return_value = product
        with patch("routes.shop._require_open_store", return_value=None), \
             patch("routes.shop.Product.query", pq), \
             patch("routes.shop.StoreService.online_stock_map", return_value={10: Decimal("0")}):
            resp = shop_client.post(
                f"{BASE}/cart/add",
                data={"product_id": "10", "quantity": "1"},
                headers={"Referer": f"{BASE}/"},
            )
        assert resp.status_code in (302, 303)

    def test_checkout_closed_store(self, shop_client, mock_store):
        with patch("routes.shop.StoreService.stores_globally_enabled", return_value=False):
            resp = shop_client.get(f"{BASE}/checkout")
        assert resp.status_code == 503

    def test_checkout_min_order_warning(self, shop_client, mock_store):
        mock_store.min_order_amount = Decimal("500")
        with patch("routes.shop.StoreService.get_cart", return_value={"10": 1}), \
             patch("routes.shop.StoreService.cart_totals", return_value=_cart_totals()), \
             patch("routes.shop.StorePaymentMethodService.list_for_checkout", return_value=[MagicMock()]):
            resp = shop_client.get(f"{BASE}/checkout")
        assert resp.status_code == 200
