from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, request
from flask_login import current_user, login_required

from extensions import limiter
from services.platform_query_service import PlatformQueryService
from utils.api_response import success_response
from utils.cache_decorators import cached_query
from utils.decorators import permission_required

api_analytics_bp = Blueprint("api_analytics", __name__, url_prefix="/api/analytics")


@api_analytics_bp.route("/overdue-payments")
@login_required
@permission_required("view_reports")
@limiter.limit("50 per minute")
@cached_query(timeout=300, key_prefix="overdue_payments")
def overdue_payments():
    customers = PlatformQueryService.analytics_overdue_customer_candidates(current_user)
    overdue = [c for c in customers if c.get_balance_aed() > Decimal("1000")]

    return success_response(
        data={
            "count": len(overdue),
            "total_amount": sum(float(c.get_balance_aed()) for c in overdue),
            "customers": [{"id": c.id, "name": c.name, "balance": float(c.get_balance_aed())} for c in overdue[:10]],
        }
    )


@api_analytics_bp.route("/daily-stats")
@login_required
@permission_required("view_reports")
@cached_query(timeout=60, key_prefix="daily_stats")
def daily_stats():
    today = datetime.now().date()

    today_sales = PlatformQueryService.analytics_today_sales(current_user, today)
    today_payments = PlatformQueryService.analytics_today_payments(current_user, today)

    return success_response(
        data={
            "sales": {
                "count": len(today_sales),
                "total": sum(float(s.amount_aed) for s in today_sales),
            },
            "payments": {
                "count": len(today_payments),
                "total": sum(float(p.amount_aed) for p in today_payments),
            },
        }
    )


@api_analytics_bp.route("/top-customers")
@login_required
@permission_required("view_reports")
@cached_query(timeout=600, key_prefix="top_customers")
def top_customers():
    limit = request.args.get("limit", 10, type=int)

    customers = PlatformQueryService.analytics_top_customers(current_user, limit)

    return success_response(
        data={
            "customers": [
                {
                    "id": c.id,
                    "name": c.name,
                    "total_purchases": float(c.total_purchases or 0),
                    "balance": float(c.get_balance_aed()),
                    "classification": c.customer_classification,
                }
                for c in customers
            ],
        }
    )


@api_analytics_bp.route("/low-stock-products")
@login_required
@permission_required("view_reports")
@cached_query(timeout=120, key_prefix="low_stock_products")
def low_stock_products():
    products = PlatformQueryService.analytics_low_stock_products(current_user)

    return success_response(
        data={
            "count": len(products),
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "current_stock": float(p.current_stock),
                    "min_stock": float(p.min_stock_alert),
                    "urgency": "critical" if p.current_stock == 0 else "high",
                }
                for p in products
            ],
        }
    )


@api_analytics_bp.route("/revenue-trend")
@login_required
@permission_required("view_reports")
@cached_query(timeout=300, key_prefix="revenue_trend")
def revenue_trend():
    days = request.args.get("days", 30, type=int)
    since = datetime.now() - timedelta(days=days)

    daily_revenue = PlatformQueryService.analytics_revenue_trend_rows(current_user, since)

    return success_response(
        data={"data": [{"date": str(row.date), "revenue": float(row.total or 0)} for row in daily_revenue]}
    )
