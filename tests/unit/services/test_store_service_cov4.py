"""Coverage-4 for services.store_service — slug/else/except arcs (real paths)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.store_service import StoreService


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield
        db_session.rollback()


class TestSlugHelpers:
    def test_normalize_empty_returns_store(self):
        assert StoreService.normalize_slug("") == "store"
        assert StoreService.normalize_slug("   ") == "store"
        assert StoreService.normalize_slug(None) == "store"

    def test_normalize_collapses(self):
        assert StoreService.normalize_slug("My  Store!!") == "my-store"

    def test_validate_ok_and_bad(self):
        assert StoreService.validate_slug("My Store") == "my-store"
        # normalize of punctuation-only becomes 'store' which IS valid
        assert StoreService.validate_slug("!!!") == "store"

    def test_subdomain_delegates(self):
        assert StoreService.normalize_subdomain("My Shop") == "my-shop"

    def test_cart_session_key(self):
        assert StoreService.cart_session_key(7) == "shop_cart_7"


class TestLocks:
    def test_platform_locked_arcs(self):
        assert StoreService.is_platform_locked(None) is False
        assert StoreService.is_platform_locked(SimpleNamespace(platform_disabled=True)) is True
        assert StoreService.is_platform_locked(SimpleNamespace(platform_disabled=False)) is False

    def test_effective_enabled_matrix(self):
        assert StoreService.effective_enabled(None) is False
        assert StoreService.effective_enabled(SimpleNamespace(is_enabled=False, platform_disabled=False)) is False
        assert StoreService.effective_enabled(SimpleNamespace(is_enabled=True, platform_disabled=True)) is False
        assert StoreService.effective_enabled(SimpleNamespace(is_enabled=True, platform_disabled=False)) is True

    def test_stores_globally_enabled_exception(self, mocker):
        mocker.patch("services.store_service.SystemSettings.get_current", side_effect=RuntimeError("db down"))
        assert StoreService.stores_globally_enabled() is False

    def test_stores_globally_enabled_true_false(self, mocker):
        mocker.patch(
            "services.store_service.SystemSettings.get_current",
            return_value=SimpleNamespace(enable_ecommerce=True),
        )
        assert StoreService.stores_globally_enabled() is True
        mocker.patch(
            "services.store_service.SystemSettings.get_current",
            return_value=SimpleNamespace(enable_ecommerce=False),
        )
        assert StoreService.stores_globally_enabled() is False


class TestHostAndCart:
    def test_get_store_by_host_empty(self):
        assert StoreService.get_store_by_host("") is None
        assert StoreService.get_store_by_host(None) is None
        assert StoreService.get_store_by_host("   ") is None

    def test_get_store_by_host_localhost_skips_subdomain(self, mocker):
        from models import TenantStore

        mq = MagicMock()
        mq.filter_by.return_value = mq
        mq.first.return_value = None
        mocker.patch.object(TenantStore, "query", new_callable=mocker.PropertyMock, return_value=mq)
        assert StoreService.get_store_by_host("localhost:5000") is None

    def test_get_store_by_host_www_prefix(self, mocker):
        from models import TenantStore

        store = SimpleNamespace(id=1)
        mq = MagicMock()
        mq.filter_by.return_value = mq
        mq.first.return_value = store
        mocker.patch.object(TenantStore, "query", new_callable=mocker.PropertyMock, return_value=mq)
        assert StoreService.get_store_by_host("www.example.com") is store

    def test_get_cart_cleans(self):
        session = {StoreService.cart_session_key(3): {"1": "2", "x": "bad", "2": "-1", "3": 0}}
        assert StoreService.get_cart(session, 3) == {"1": 2.0}

    def test_get_cart_non_dict(self):
        assert StoreService.get_cart({StoreService.cart_session_key(3): "nope"}, 3) == {}

    def test_save_cart_marks_modified(self):
        class _S(dict):
            modified = False

        s = _S()
        StoreService.save_cart(s, 5, {"1": 2})
        assert s[StoreService.cart_session_key(5)] == {"1": 2}
        assert s.modified is True

    def test_online_stock_map_no_warehouse(self, mocker):
        mocker.patch.object(StoreService, "get_online_warehouse", return_value=None)
        assert StoreService.online_stock_map(1) == {}

    def test_catalog_no_warehouse(self, mocker):
        mocker.patch.object(StoreService, "get_online_warehouse", return_value=None)
        products, stock = StoreService.get_catalog_products(1)
        assert products == [] and stock == {}
