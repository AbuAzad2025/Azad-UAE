from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from extensions import db
from models import Product, Sale, SaleLine
from services.store_analytics_service import StoreAnalyticsService


class TestOrderStats:
    def test_counts_and_revenue_by_period(self, db_session, sample_tenant, online_sale, sample_user, sample_customer, online_warehouse):
        confirmed = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f'WEB-{uuid.uuid4().hex[:6]}',
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            warehouse_id=online_warehouse.id,
            source='online_store',
            status='confirmed',
            payment_status='paid',
            subtotal=Decimal('250'),
            total_amount=Decimal('250'),
            amount=Decimal('250'),
            amount_aed=Decimal('250'),
            sale_date=datetime.now(timezone.utc),
            checkout_payment_method='card',
        )
        cancelled = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f'WEB-{uuid.uuid4().hex[:6]}',
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            warehouse_id=online_warehouse.id,
            source='online_store',
            status='cancelled',
            payment_status='unpaid',
            subtotal=Decimal('50'),
            total_amount=Decimal('50'),
            amount=Decimal('50'),
            amount_aed=Decimal('50'),
            sale_date=datetime.now(timezone.utc),
            checkout_payment_method='cod',
        )
        db_session.add_all([confirmed, cancelled])
        db_session.flush()

        stats = StoreAnalyticsService.order_stats(sample_tenant.id)
        assert stats['pending'] >= 1
        assert stats['confirmed'] >= 1
        assert stats['cancelled'] >= 1
        assert stats['total_orders'] >= 3
        assert stats['orders_today'] >= 2
        assert float(stats['revenue_today']) >= 250.0

    def test_tenant_isolation(self, db_session, sample_tenant, online_sale):
        other_tid = sample_tenant.id + 99999
        stats = StoreAnalyticsService.order_stats(other_tid)
        assert stats['total_orders'] == 0
        assert stats['pending'] == 0


class TestTopProducts:
    def test_ranks_by_line_total(self, db_session, sample_tenant, sample_product_with_stock, sample_user, sample_customer, online_warehouse):
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f'WEB-{uuid.uuid4().hex[:6]}',
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            warehouse_id=online_warehouse.id,
            source='online_store',
            status='confirmed',
            payment_status='paid',
            subtotal=Decimal('200'),
            total_amount=Decimal('200'),
            amount=Decimal('200'),
            amount_aed=Decimal('200'),
            sale_date=datetime.now(timezone.utc),
        )
        db_session.add(sale)
        db_session.flush()
        line = SaleLine(
            tenant_id=sample_tenant.id,
            sale_id=sale.id,
            product_id=sample_product_with_stock.id,
            quantity=Decimal('4'),
            unit_price=Decimal('50'),
            line_total=Decimal('200'),
        )
        db_session.add(line)
        db_session.flush()

        top = StoreAnalyticsService.top_products(sample_tenant.id, limit=3)
        assert len(top) == 1
        assert top[0]['product'].id == sample_product_with_stock.id
        assert top[0]['quantity'] == Decimal('4')


class TestLowStockProducts:
    def test_uses_store_threshold(self, mocker, sample_tenant, tenant_store, sample_product_with_stock):
        mocker.patch.object(
            StoreAnalyticsService, '_since',
            return_value=datetime.now(timezone.utc) - timedelta(days=1),
        )
        mocker.patch(
            'services.store_analytics_service.StoreService.get_tenant_store',
            return_value=tenant_store,
        )
        product = sample_product_with_stock
        mocker.patch(
            'services.store_analytics_service.StoreService.get_catalog_products',
            return_value=([product], {product.id: Decimal('2')}),
        )
        tenant_store.low_stock_threshold = Decimal('5')
        alerts = StoreAnalyticsService.low_stock_products(sample_tenant.id)
        assert len(alerts) == 1
        assert alerts[0]['quantity'] == Decimal('2')
        assert alerts[0]['threshold'] == Decimal('5')

    def test_no_store_uses_default_threshold(self, mocker, sample_tenant):
        mocker.patch(
            'services.store_analytics_service.StoreService.get_tenant_store',
            return_value=None,
        )
        product = Product(id=1, name='P', tenant_id=sample_tenant.id)
        mocker.patch(
            'services.store_analytics_service.StoreService.get_catalog_products',
            return_value=([product], {1: Decimal('3')}),
        )
        alerts = StoreAnalyticsService.low_stock_products(sample_tenant.id)
        assert alerts[0]['threshold'] == Decimal('5')


class TestDailyOrdersChart:
    def test_groups_by_day(self, db_session, sample_tenant, sample_user, sample_customer, online_warehouse):
        day = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        for i in range(2):
            sale = Sale(
                tenant_id=sample_tenant.id,
                sale_number=f'WEB-{uuid.uuid4().hex[:4]}-{i}',
                customer_id=sample_customer.id,
                seller_id=sample_user.id,
                warehouse_id=online_warehouse.id,
                source='online_store',
                status='pending',
                payment_status='unpaid',
                subtotal=Decimal('10'),
                total_amount=Decimal('10'),
                amount=Decimal('10'),
                amount_aed=Decimal('10'),
                sale_date=day,
            )
            db_session.add(sale)
        db_session.flush()

        chart = StoreAnalyticsService.daily_orders_chart(sample_tenant.id, days=7)
        assert any(row['count'] >= 2 for row in chart)
