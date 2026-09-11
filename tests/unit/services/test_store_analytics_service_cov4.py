"""Cov4: store_analytics_service — stats/top/low-stock/chart arcs."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

from services.store_analytics_service import StoreAnalyticsService


def test_since_returns_past():
    assert StoreAnalyticsService._since(7) < datetime.now(UTC)


def test_order_stats_empty_and_with_orders(db_session, sample_tenant, sample_customer,
                                           sample_user, sample_warehouse):
    stats = StoreAnalyticsService.order_stats(sample_tenant.id)
    assert stats["total_orders"] == 0
    assert stats["revenue_today"] == Decimal("0")
    from models import Sale

    sale = Sale(tenant_id=sample_tenant.id, sale_number="STORE-COV4-1",
                customer_id=sample_customer.id, seller_id=sample_user.id,
                warehouse_id=sample_warehouse.id, sale_date=datetime.now(UTC),
                source="online_store", status="confirmed",
                subtotal=Decimal("20"), total_amount=Decimal("20"), amount=Decimal("20"),
                amount_aed=Decimal("20"))
    db_session.add(sale)
    db_session.flush()
    stats = StoreAnalyticsService.order_stats(sample_tenant.id)
    assert stats["confirmed"] == 1
    assert stats["orders_today"] == 1
    assert float(stats["revenue_today"]) == 20.0


def test_top_products_with_and_without_lines(db_session, sample_tenant, sample_product,
                                             sample_customer, sample_user, sample_warehouse):
    assert StoreAnalyticsService.top_products(sample_tenant.id) == []
    from datetime import datetime as dt

    from models import Sale, SaleLine

    sale = Sale(tenant_id=sample_tenant.id, sale_number="STORE-COV4-2",
                customer_id=sample_customer.id, seller_id=sample_user.id,
                warehouse_id=sample_warehouse.id, sale_date=dt.now(UTC),
                source="online_store", status="confirmed",
                subtotal=Decimal("30"), total_amount=Decimal("30"), amount=Decimal("30"),
                amount_aed=Decimal("30"))
    db_session.add(sale)
    db_session.flush()
    line = SaleLine(tenant_id=sample_tenant.id, sale_id=sale.id, product_id=sample_product.id,
                    quantity=Decimal("2"), unit_price=Decimal("15"), line_total=Decimal("30"))
    db_session.add(line)
    db_session.flush()
    top = StoreAnalyticsService.top_products(sample_tenant.id)
    assert top and top[0]["product"].id == sample_product.id
    # missing product branch: line pointing at deleted product id
    line.product_id = 999999999
    db_session.flush()
    assert StoreAnalyticsService.top_products(sample_tenant.id) == []


def test_low_stock_default_and_custom_threshold(db_session, sample_tenant):
    with patch("services.store_analytics_service.StoreService.get_tenant_store",
               return_value=None), patch(
        "services.store_analytics_service.StoreService.get_catalog_products",
        return_value=([], {}),
    ):
        assert StoreAnalyticsService.low_stock_products(sample_tenant.id) == []
    from types import SimpleNamespace

    p = SimpleNamespace(id=1)
    with patch("services.store_analytics_service.StoreService.get_tenant_store",
               return_value=SimpleNamespace(low_stock_threshold=None)), patch(
        "services.store_analytics_service.StoreService.get_catalog_products",
        return_value=([p], {1: Decimal("3")}),
    ):
        alerts = StoreAnalyticsService.low_stock_products(sample_tenant.id)
        assert len(alerts) == 1  # default threshold 5 branch
    with patch("services.store_analytics_service.StoreService.get_tenant_store",
               return_value=SimpleNamespace(low_stock_threshold=10)), patch(
        "services.store_analytics_service.StoreService.get_catalog_products",
        return_value=([p], {1: Decimal("30")}),
    ):
        assert StoreAnalyticsService.low_stock_products(sample_tenant.id, Decimal("2")) == []


def test_daily_orders_chart(db_session, sample_tenant):
    assert StoreAnalyticsService.daily_orders_chart(sample_tenant.id) == []
