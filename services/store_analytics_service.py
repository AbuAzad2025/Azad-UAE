"""Store analytics — orders, revenue, low stock."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func

from extensions import db
from models import Product, Sale
from services.store_service import StoreService


class StoreAnalyticsService:
    @staticmethod
    def _since(days: int) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=days)

    @staticmethod
    def order_stats(tenant_id: int) -> dict:
        tid = int(tenant_id)
        base = Sale.query.filter_by(tenant_id=tid, source='online_store')
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = StoreAnalyticsService._since(7)
        month_start = StoreAnalyticsService._since(30)

        def _sum(q):
            return q.with_entities(func.coalesce(func.sum(Sale.total_amount), 0)).scalar() or Decimal('0')

        return {
            'pending': base.filter_by(status='pending').count(),
            'confirmed': base.filter_by(status='confirmed').count(),
            'cancelled': base.filter_by(status='cancelled').count(),
            'total_orders': base.count(),
            'orders_today': base.filter(Sale.sale_date >= today_start).count(),
            'orders_week': base.filter(Sale.sale_date >= week_start).count(),
            'orders_month': base.filter(Sale.sale_date >= month_start).count(),
            'revenue_today': _sum(base.filter(Sale.sale_date >= today_start, Sale.status == 'confirmed')),
            'revenue_week': _sum(base.filter(Sale.sale_date >= week_start, Sale.status == 'confirmed')),
            'revenue_month': _sum(base.filter(Sale.sale_date >= month_start, Sale.status == 'confirmed')),
        }

    @staticmethod
    def top_products(tenant_id: int, limit: int = 5):
        from models import SaleLine

        tid = int(tenant_id)
        rows = (
            db.session.query(
                SaleLine.product_id,
                func.sum(SaleLine.quantity).label('qty'),
                func.sum(SaleLine.line_total).label('total'),
            )
            .join(Sale, Sale.id == SaleLine.sale_id)
            .filter(Sale.tenant_id == tid, Sale.source == 'online_store', Sale.status == 'confirmed')
            .group_by(SaleLine.product_id)
            .order_by(func.sum(SaleLine.line_total).desc())
            .limit(limit)
            .all()
        )
        result = []
        for product_id, qty, total in rows:
            product = db.session.get(Product, product_id)
            if product:
                result.append({
                    'product': product,
                    'quantity': qty,
                    'total': total,
                })
        return result

    @staticmethod
    def low_stock_products(tenant_id: int, threshold: Decimal | None = None) -> list[dict]:
        store = StoreService.get_tenant_store(tenant_id, create=False)
        if threshold is None:
            threshold = Decimal(str(getattr(store, 'low_stock_threshold', None) or 5))
        products, stock_map = StoreService.get_catalog_products(tenant_id, include_zero=True)
        alerts = []
        for product in products:
            qty = stock_map.get(product.id, Decimal('0'))
            if qty <= threshold:
                alerts.append({'product': product, 'quantity': qty, 'threshold': threshold})
        alerts.sort(key=lambda row: row['quantity'])
        return alerts

    @staticmethod
    def daily_orders_chart(tenant_id: int, days: int = 14) -> list[dict]:
        tid = int(tenant_id)
        start = StoreAnalyticsService._since(days)
        rows = (
            db.session.query(
                func.date(Sale.sale_date).label('day'),
                func.count(Sale.id).label('cnt'),
            )
            .filter(
                Sale.tenant_id == tid,
                Sale.source == 'online_store',
                Sale.sale_date >= start,
            )
            .group_by(func.date(Sale.sale_date))
            .order_by(func.date(Sale.sale_date))
            .all()
        )
        return [{'day': str(day), 'count': int(cnt)} for day, cnt in rows]
