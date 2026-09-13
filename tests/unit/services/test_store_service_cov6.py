"""Cov6: store_service — route-facing scoped fetchers (tail query helpers)."""

from __future__ import annotations

from unittest.mock import MagicMock

from models import Product, ProductCategory, Sale
from models.sale import SaleLine
from models.shop_abandoned_cart import ShopAbandonedCart
from models.shop_customer_account import ShopCustomerAccount
from models.shop_newsletter import ShopNewsletter
from models.shop_review import ShopReview
from models.shop_saved_payment import ShopSavedPayment
from models.shop_stock_alert import ShopStockAlert
from models.shop_wishlist import ShopWishlist


def test_list_active_products(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    mocker.patch.object(Product, "query").filter_by.return_value.order_by.return_value.all.return_value = [row]
    out = StoreService.list_active_products(sample_tenant.id)
    assert out == [row]


def test_list_customer_accounts(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    query = mocker.patch.object(ShopCustomerAccount, "query")
    query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
    out = StoreService.list_customer_accounts(sample_tenant.id)
    assert out == [row]


def test_save_abandoned_cart_snapshot_create(mocker, db_session, sample_tenant):
    from services.store_service import StoreService

    query = mocker.patch.object(ShopAbandonedCart, "query")
    query.filter_by.return_value.first.return_value = None
    add = mocker.patch("services.store_service.db.session.add")
    flush = mocker.patch("services.store_service.db.session.flush")
    StoreService.save_abandoned_cart_snapshot(sample_tenant.id, 7, "buyer@test.com", "{}")
    add.assert_called_once()
    flush.assert_called_once()


def test_wishlist_entry(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    mocker.patch.object(ShopWishlist, "query").filter_by.return_value.first.return_value = row
    out = StoreService.wishlist_entry(sample_tenant.id, 7, 3)
    assert out == row


def test_wishlist_count(mocker, sample_tenant):
    from services.store_service import StoreService

    mocker.patch.object(ShopWishlist, "query").filter_by.return_value.count.return_value = 2
    out = StoreService.wishlist_count(sample_tenant.id, 7)
    assert out == 2


def test_remove_wishlist_entry(mocker, sample_tenant):
    from services.store_service import StoreService

    query = mocker.patch.object(ShopWishlist, "query")
    StoreService.remove_wishlist_entry(sample_tenant.id, 7, 3)
    query.filter_by.return_value.delete.assert_called_once()


def test_wishlist_items(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    query = mocker.patch.object(ShopWishlist, "query")
    query.filter_by.return_value.order_by.return_value.all.return_value = [row]
    out = StoreService.wishlist_items(sample_tenant.id, 7)
    assert out == [row]


def test_active_categories(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    query = mocker.patch.object(ProductCategory, "query")
    query.filter_by.return_value.order_by.return_value.all.return_value = [row]
    out = StoreService.active_categories(sample_tenant.id)
    assert out == [row]


def test_active_product_or_404(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    query = mocker.patch.object(Product, "query")
    query.filter_by.return_value.first_or_404.return_value = row
    out = StoreService.active_product_or_404(sample_tenant.id, 3)
    assert out == row


def test_active_product(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    query = mocker.patch.object(Product, "query")
    query.filter_by.return_value.first.return_value = row
    out = StoreService.active_product(sample_tenant.id, 3)
    assert out == row


def test_approved_reviews(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    query = mocker.patch.object(ShopReview, "query")
    query.filter_by.return_value.order_by.return_value.all.return_value = [row]
    out = StoreService.approved_reviews(sample_tenant.id, 3)
    assert out == [row]


def test_stock_alert_subscriber(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    mocker.patch.object(ShopStockAlert, "query").filter_by.return_value.first.return_value = row
    out = StoreService.stock_alert_subscriber(sample_tenant.id, 3, "a@b.c")
    assert out == row


def test_newsletter_subscriber(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    mocker.patch.object(ShopNewsletter, "query").filter_by.return_value.first.return_value = row
    out = StoreService.newsletter_subscriber(sample_tenant.id, "a@b.c")
    assert out == row


def test_saved_payment_methods(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    mocker.patch.object(ShopSavedPayment, "query").filter_by.return_value.all.return_value = [row]
    out = StoreService.saved_payment_methods(sample_tenant.id, 7)
    assert out == [row]


def test_saved_payment_or_404(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    query = mocker.patch.object(ShopSavedPayment, "query")
    query.filter_by.return_value.first_or_404.return_value = row
    out = StoreService.saved_payment_or_404(sample_tenant.id, 7, 9)
    assert out == row


def test_online_order_or_404(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    query = mocker.patch.object(Sale, "query")
    query.filter_by.return_value.first_or_404.return_value = row
    out = StoreService.online_order_or_404(sample_tenant.id, 3)
    assert out == row


def test_online_order_lines(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    query = mocker.patch.object(SaleLine, "query")
    query.filter_by.return_value.all.return_value = [row]
    out = StoreService.online_order_lines(sample_tenant.id, 3)
    assert out == [row]


def test_online_order_by_number(mocker, sample_tenant):
    from services.store_service import StoreService

    row = MagicMock()
    query = mocker.patch.object(Sale, "query")
    query.filter_by.return_value.first.return_value = row
    out = StoreService.online_order_by_number(sample_tenant.id, "ORD-1")
    assert out == row
