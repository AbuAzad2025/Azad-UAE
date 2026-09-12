"""Cov5: store_service — warehouse backfill, host miss, cart clamp/currency, fetch arcs."""

from __future__ import annotations

from decimal import Decimal

import pytest


def test_ensure_tenant_store_backfills_warehouse(mocker, sample_tenant):
    from unittest.mock import MagicMock

    from services.store_service import StoreService

    store = MagicMock(warehouse_id=None)
    mocker.patch("services.store_service.TenantStore.query").filter_by.return_value.first.return_value = store
    mocker.patch(
        "services.store_service.StoreService.ensure_online_warehouse",
        return_value=MagicMock(id=4242),
    )
    out = StoreService.ensure_tenant_store(sample_tenant.id)
    assert out.warehouse_id == 4242


def test_get_store_by_host_subdomain_miss(sample_tenant):
    from services.store_service import StoreService

    assert StoreService.get_store_by_host("shop.example.com") is None


def test_cart_totals_clamps_over_stock(mocker, sample_tenant, sample_product):
    from services.store_service import StoreService

    mocker.patch(
        "services.store_service.StoreService.online_stock_map",
        return_value={},
    )
    out = StoreService.cart_totals(sample_tenant.id, {str(sample_product.id): 2})
    assert out["lines"] == []


def test_cart_totals_display_currency(mocker, sample_tenant, sample_product_with_stock):
    from services.store_service import StoreService

    mocker.patch(
        "services.store_service.StoreService.online_stock_map",
        return_value={sample_product_with_stock.id: Decimal("50")},
    )
    mocker.patch(
        "services.store_checkout_service.StockService.check_availability_in_warehouse",
        return_value=(True, ""),
    )
    mocker.patch(
        "services.store_pricing_service.StorePricingService.resolve_display_price",
        return_value=Decimal("5"),
    )
    out = StoreService.cart_totals(
        sample_tenant.id, {str(sample_product_with_stock.id): 2}, display_currency="USD"
    )
    assert out["display_subtotal"] == Decimal("10.00")
    assert len(out["lines"]) == 1


def test_find_custom_domain_clash(sample_tenant):
    from services.store_service import StoreService

    assert StoreService.find_custom_domain_clash("nope.example.com", sample_tenant.id) is None


def test_get_transfer_product(db_session, sample_tenant, sample_product):
    from services.store_service import StoreService

    assert StoreService.get_transfer_product(sample_tenant.id, sample_product.id).id == sample_product.id
    with pytest.raises(ValueError, match="المنتج"):
        StoreService.get_transfer_product(sample_tenant.id, 999999999)


def test_online_orders_query_status(sample_tenant):
    from services.store_service import StoreService

    assert StoreService.online_orders_query(sample_tenant.id, status_filter="pending") is not None
    assert StoreService.online_orders_query(sample_tenant.id) is not None


def test_save_abandoned_cart_snapshot_update(db_session, sample_tenant):
    from models.shop_abandoned_cart import ShopAbandonedCart
    from services.store_service import StoreService

    row = ShopAbandonedCart(
        tenant_id=sample_tenant.id, account_id=None, email="a@b.c", cart_data='{"x": 1}', recovered=False
    )
    db_session.add(row)
    db_session.flush()
    StoreService.save_abandoned_cart_snapshot(sample_tenant.id, None, "a@b.c", '{"x": 2}')
    db_session.flush()
    assert row.cart_data == '{"x": 2}'
