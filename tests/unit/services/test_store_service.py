from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from extensions import db
from models import Product, Tenant, TenantStore, Warehouse
from services.store_service import StoreService


class TestSlugHelpers:
    def test_normalize_slug(self):
        assert StoreService.normalize_slug('  Hello World!  ') == 'hello-world'

    def test_validate_slug_rejects_invalid(self, mocker):
        mocker.patch.object(StoreService, 'normalize_slug', return_value='bad_slug')
        with pytest.raises(ValueError, match='رابط'):
            StoreService.validate_slug('bad_slug')

    def test_ensure_unique_slug(self, db_session, tenant_store):
        slug = StoreService.ensure_unique_slug(tenant_store.store_slug)
        assert slug != tenant_store.store_slug
        assert StoreService.normalize_slug(slug).startswith('store')

    def test_normalize_subdomain_alias(self):
        assert StoreService.normalize_subdomain('My Shop') == 'my-shop'


class TestWarehouseBootstrap:
    def test_get_online_warehouse_none(self, sample_tenant):
        assert StoreService.get_online_warehouse(sample_tenant.id) is None

    def test_ensure_online_warehouse_creates(self, db_session, sample_tenant, sample_branch):
        wh = StoreService.ensure_online_warehouse(sample_tenant.id)
        assert wh.is_online is True
        assert wh.tenant_id == sample_tenant.id
        again = StoreService.ensure_online_warehouse(sample_tenant.id)
        assert again.id == wh.id

    def test_ensure_online_warehouse_missing_tenant(self):
        with pytest.raises(ValueError, match='الشركة'):
            StoreService.ensure_online_warehouse(999999999)

    def test_assert_single_online_warehouse_raises(self, online_warehouse, sample_tenant):
        with pytest.raises(ValueError, match='أونلاين'):
            StoreService.assert_single_online_warehouse(sample_tenant.id)


class TestTenantStoreBootstrap:
    def test_ensure_tenant_store_creates(self, db_session, sample_tenant):
        store = StoreService.ensure_tenant_store(sample_tenant.id)
        assert store.tenant_id == sample_tenant.id
        assert store.warehouse_id is not None

    def test_ensure_tenant_store_backfills_warehouse(self, mocker, sample_tenant):
        store = MagicMock(warehouse_id=None, tenant_id=sample_tenant.id)
        mocker.patch.object(StoreService, 'get_tenant_store', return_value=None)
        mocker.patch('services.store_service.TenantStore.query').filter_by.return_value.first.return_value = store
        wh = MagicMock(id=77)
        mocker.patch.object(StoreService, 'ensure_online_warehouse', return_value=wh)
        updated = StoreService.ensure_tenant_store(sample_tenant.id)
        assert updated.warehouse_id == 77

    def test_get_store_by_slug(self, tenant_store):
        found = StoreService.get_store_by_slug(tenant_store.store_slug.upper())
        assert found.id == tenant_store.id

    def test_get_store_by_host_custom_domain(self, db_session, tenant_store):
        tenant_store.custom_domain = 'shop.example.com'
        db.session.flush()
        assert StoreService.get_store_by_host('shop.example.com') is tenant_store

    def test_get_store_by_host_subdomain(self, db_session, tenant_store):
        tenant_store.subdomain = 'mystore'
        db.session.flush()
        assert StoreService.get_store_by_host('mystore.example.com') is tenant_store

    def test_get_store_by_host_ignores_localhost(self):
        assert StoreService.get_store_by_host('localhost') is None

    def test_ensure_unique_subdomain(self, db_session, tenant_store):
        unique = StoreService.ensure_unique_subdomain(tenant_store.subdomain)
        assert unique != tenant_store.subdomain


class TestCatalogAndStock:
    def test_online_stock_map_empty_without_warehouse(self, sample_tenant):
        assert StoreService.online_stock_map(sample_tenant.id) == {}

    def test_online_stock_map_with_warehouse(self, mocker, sample_tenant, online_warehouse):
        mocker.patch(
            'services.store_service.get_branch_stock_map',
            return_value={1: Decimal('5')},
        )
        assert StoreService.online_stock_map(sample_tenant.id, [1])[1] == Decimal('5')

    def test_get_catalog_products_filters_zero(
        self, mocker, sample_tenant, sample_product_with_stock, online_warehouse,
    ):
        mocker.patch.object(
            StoreService, 'get_online_warehouse', return_value=online_warehouse,
        )
        mocker.patch.object(
            StoreService, 'online_stock_map',
            return_value={sample_product_with_stock.id: Decimal('3')},
        )
        products, stock = StoreService.get_catalog_products(sample_tenant.id)
        assert sample_product_with_stock.id in {p.id for p in products}
        assert stock[sample_product_with_stock.id] == Decimal('3')

    def test_get_catalog_no_warehouse(self, sample_tenant):
        products, stock = StoreService.get_catalog_products(sample_tenant.id)
        assert products == []
        assert stock == {}

    def test_count_visible_products(self, mocker, sample_tenant):
        mocker.patch.object(
            StoreService, 'get_catalog_products',
            return_value=([MagicMock(), MagicMock()], {}),
        )
        assert StoreService.count_visible_products(sample_tenant.id) == 2

    def test_get_related_products(self, mocker, sample_tenant, sample_product_with_stock):
        peer = MagicMock(
            id=sample_product_with_stock.id + 1,
            category_id=sample_product_with_stock.category_id,
            has_serial_number=False,
        )
        mocker.patch.object(
            StoreService, 'get_catalog_products',
            return_value=([sample_product_with_stock, peer], {
                sample_product_with_stock.id: Decimal('1'),
                peer.id: Decimal('2'),
            }),
        )
        related = StoreService.get_related_products(
            sample_tenant.id, sample_product_with_stock.id,
            sample_product_with_stock.category_id,
        )
        assert len(related) == 1
        assert related[0]['product'].id == peer.id


class TestPlatformFlags:
    def test_stores_globally_enabled(self, mocker):
        settings = MagicMock(enable_ecommerce=True)
        mocker.patch('models.system_settings.SystemSettings.get_current', return_value=settings)
        assert StoreService.stores_globally_enabled() is True

    def test_stores_globally_enabled_fallback(self, mocker):
        mocker.patch(
            'models.system_settings.SystemSettings.get_current',
            side_effect=RuntimeError(),
        )
        assert StoreService.stores_globally_enabled() is False

    def test_set_stores_globally_enabled(self, mocker):
        settings = MagicMock()
        mocker.patch('models.system_settings.SystemSettings.get_current', return_value=settings)
        StoreService.set_stores_globally_enabled(True)
        assert settings.enable_ecommerce is True

    def test_platform_lock_and_effective(self, tenant_store):
        assert StoreService.is_platform_locked(tenant_store) is False
        assert StoreService.effective_enabled(tenant_store) is True
        tenant_store.platform_disabled = True
        assert StoreService.effective_enabled(tenant_store) is False

    def test_set_platform_disabled(self, tenant_store):
        StoreService.set_platform_disabled(tenant_store, True)
        assert tenant_store.platform_disabled is True


class TestPublicAvailability:
    def test_unavailable_when_disabled(self, tenant_store):
        tenant_store.is_enabled = False
        assert StoreService.is_store_publicly_available(tenant_store) is False

    def test_unavailable_when_platform_locked(self, mocker, tenant_store):
        tenant_store.platform_disabled = True
        mocker.patch.object(StoreService, 'stores_globally_enabled', return_value=True)
        assert StoreService.is_store_publicly_available(tenant_store) is False

    def test_unavailable_when_globally_off(self, mocker, tenant_store):
        mocker.patch.object(StoreService, 'stores_globally_enabled', return_value=False)
        assert StoreService.is_store_publicly_available(tenant_store) is False

    def test_unavailable_when_tenant_suspended(self, mocker, tenant_store, sample_tenant):
        sample_tenant.is_suspended = True
        mocker.patch.object(StoreService, 'stores_globally_enabled', return_value=True)
        assert StoreService.is_store_publicly_available(tenant_store) is False

    def test_available_when_all_ok(self, mocker, tenant_store, online_warehouse):
        mocker.patch.object(StoreService, 'stores_globally_enabled', return_value=True)
        assert StoreService.is_store_publicly_available(tenant_store) is True


class TestCartHelpers:
    def test_cart_session_round_trip(self, sample_tenant):
        class CartSession:
            def __init__(self):
                self._data = {}
                self.modified = False

            def get(self, key, default=None):
                return self._data.get(key, default)

            def __setitem__(self, key, value):
                self._data[key] = value

        session = CartSession()
        StoreService.save_cart(session, sample_tenant.id, {'1': 2, 'abc': 'x'})
        cart = StoreService.get_cart(session, sample_tenant.id)
        assert cart == {'1': 2.0}

    def test_get_cart_non_dict_returns_empty(self, sample_tenant):
        session = MagicMock()
        session.get.return_value = 'not-a-dict'
        assert StoreService.get_cart(session, sample_tenant.id) == {}

    def test_cart_totals_caps_quantity(
        self, mocker, sample_tenant, sample_product_with_stock, online_warehouse,
    ):
        mocker.patch.object(
            StoreService, 'online_stock_map',
            return_value={sample_product_with_stock.id: Decimal('2')},
        )
        totals = StoreService.cart_totals(
            sample_tenant.id, {str(sample_product_with_stock.id): 10},
        )
        assert totals['count'] == Decimal('2')
        assert totals['subtotal'] > 0

    def test_get_public_catalog_filters(
        self, mocker, sample_tenant, sample_product_with_stock, online_warehouse,
    ):
        mocker.patch.object(
            StoreService, 'get_catalog_products',
            return_value=([sample_product_with_stock], {
                sample_product_with_stock.id: Decimal('5'),
            }),
        )
        sample_product_with_stock.regular_price = Decimal('100')
        sample_product_with_stock.name = 'Alpha'
        sample_product_with_stock.has_serial_number = False
        result = StoreService.get_public_catalog(
            sample_tenant.id,
            search='alpha',
            min_price=50,
            max_price=200,
            sort='price_asc',
            page=1,
            per_page=10,
        )
        assert result['total'] == 1
        assert len(result['items']) == 1


class TestLoyaltyAndVariants:
    def test_earn_loyalty_new_account(self, mocker, sample_tenant):
        mocker.patch('models.shop_loyalty.ShopLoyalty.query').filter_by.return_value.first.return_value = None
        add = mocker.patch('extensions.db.session.add')
        StoreService.earn_loyalty_points(sample_tenant.id, 9, 1, Decimal('25'))
        assert add.call_count == 2

    def test_earn_loyalty_existing_account(self, mocker, sample_tenant):
        lp = MagicMock(points=10, points_earned=10)
        mocker.patch('models.shop_loyalty.ShopLoyalty.query').filter_by.return_value.first.return_value = lp
        StoreService.earn_loyalty_points(sample_tenant.id, 9, 1, Decimal('25'))
        assert lp.points == 35

    def test_redeem_loyalty_success(self, mocker, sample_tenant):
        lp = MagicMock(points=100, points_redeemed=0)
        mocker.patch('models.shop_loyalty.ShopLoyalty.query').filter_by.return_value.first.return_value = lp
        mocker.patch('extensions.db.session.add')
        assert StoreService.redeem_loyalty_points(sample_tenant.id, 9, 40) == Decimal('0.4')
        assert lp.points == 60

    def test_redeem_insufficient_raises(self, db_session, sample_tenant):
        with pytest.raises(ValueError, match='Insufficient'):
            StoreService.redeem_loyalty_points(sample_tenant.id, 999888, 10)

    def test_get_loyalty_points_missing(self):
        assert StoreService.get_loyalty_points(999777) == 0

    def test_get_product_variants_empty(self, sample_tenant):
        assert StoreService.get_product_variants(sample_tenant.id, 999666) == []

    def test_get_recently_viewed_products(self, db_session, sample_tenant, sample_product):
        ordered = StoreService.get_recently_viewed_products(
            sample_tenant.id, [sample_product.id], exclude_id=None, limit=3,
        )
        assert ordered[0].id == sample_product.id

    def test_get_physical_warehouses_filters_online(
        self, mocker, sample_tenant, online_warehouse, sample_warehouse,
    ):
        mocker.patch(
            'services.store_service.get_accessible_warehouses',
            return_value=[online_warehouse, sample_warehouse],
        )
        physical = StoreService.get_physical_warehouses(sample_tenant.id, user=MagicMock())
        assert sample_warehouse in physical
        assert online_warehouse not in physical

    def test_resolve_tenant_id_delegates(self, mocker):
        mocker.patch('services.store_service.require_active_tenant_id', return_value=42)
        assert StoreService.resolve_tenant_id(MagicMock()) == 42
        assert StoreService.active_tenant_id_for_user(MagicMock()) == 42
