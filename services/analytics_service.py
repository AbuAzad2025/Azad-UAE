"""
Analytics Service - خدمة التحليلات
تحليلات متقدمة للمدفوعات والعملاء
"""

from datetime import datetime, timezone, timedelta
import models
from sqlalchemy import func, desc
import logging

logger = logging.getLogger(__name__)


def _db_session():
    from extensions import db

    return db.session


class AnalyticsService:
    """خدمة التحليلات المتقدمة"""

    @staticmethod
    def get_customer_insights(tenant_id, branch_id=None):
        # TODO: optimize N+1 queries in a separate behavior-preserving patch
        customers_data = []
        session = _db_session()
        customers_query = session.query(models.Customer).filter_by(
            is_active=True, tenant_id=tenant_id
        )
        if branch_id is not None:
            customers_query = (
                customers_query.join(
                    models.Sale, models.Customer.id == models.Sale.customer_id
                )
                .filter(models.Sale.branch_id == branch_id)
                .distinct()
            )

        for customer in customers_query.all():
            total_sales = session.query(func.sum(models.Sale.total_amount)).filter(
                models.Sale.customer_id == customer.id,
                models.Sale.status == "confirmed",
                models.Sale.tenant_id == tenant_id,
            )
            if branch_id is not None:
                total_sales = total_sales.filter(models.Sale.branch_id == branch_id)
            total_sales = total_sales.scalar() or 0

            sales_count = session.query(models.Sale).filter_by(
                customer_id=customer.id, status="confirmed", tenant_id=tenant_id
            )
            if branch_id is not None:
                sales_count = sales_count.filter(models.Sale.branch_id == branch_id)
            sales_count = sales_count.count()

            last_sale = session.query(models.Sale).filter_by(
                customer_id=customer.id, tenant_id=tenant_id
            )
            if branch_id is not None:
                last_sale = last_sale.filter(models.Sale.branch_id == branch_id)
            last_sale = last_sale.order_by(models.Sale.sale_date.desc()).first()

            if last_sale:
                sale_date = (
                    last_sale.sale_date.date()
                    if hasattr(last_sale.sale_date, "date")
                    else last_sale.sale_date
                )
                days_since_last = (datetime.now().date() - sale_date).days
            else:
                days_since_last = 999

            customers_data.append(
                {
                    "name": customer.name,
                    "lifetime_value": float(total_sales),
                    "sales_count": sales_count,
                    "avg_sale": (
                        float(total_sales / sales_count) if sales_count > 0 else 0
                    ),
                    "days_since_last": days_since_last,
                    "status": (
                        "نشط"
                        if days_since_last < 30
                        else "خامل" if days_since_last < 90 else "متوقف"
                    ),
                }
            )
        customers_data.sort(key=lambda x: x["lifetime_value"], reverse=True)
        return customers_data[:50]

    @staticmethod
    def get_sales_insights(tenant_id, branch_id=None):
        today = datetime.now().date()
        last_30_days = today - timedelta(days=30)

        daily_sales = (
            _db_session()
            .query(
                func.date(models.Sale.sale_date).label("date"),
                func.count(models.Sale.id).label("count"),
                func.sum(models.Sale.total_amount).label("total"),
            )
            .filter(
                models.Sale.sale_date >= last_30_days,
                models.Sale.status == "confirmed",
                models.Sale.tenant_id == tenant_id,
            )
        )
        if branch_id is not None:
            daily_sales = daily_sales.filter(models.Sale.branch_id == branch_id)
        daily_sales = daily_sales.group_by(func.date(models.Sale.sale_date)).all()

        top_products = (
            _db_session()
            .query(
                models.Product.name,
                func.sum(models.SaleLine.quantity).label("total_qty"),
                func.sum(models.SaleLine.line_total).label("total_revenue"),
            )
            .select_from(models.Product)
            .join(models.SaleLine, models.SaleLine.product_id == models.Product.id)
            .join(models.Sale, models.Sale.id == models.SaleLine.sale_id)
            .filter(
                models.Sale.sale_date >= last_30_days,
                models.Sale.status == "confirmed",
                models.Sale.tenant_id == tenant_id,
            )
        )
        if branch_id is not None:
            top_products = top_products.filter(models.Sale.branch_id == branch_id)
        top_products = (
            top_products.group_by(
                models.Product.id,
                models.Product.name,
            )
            .order_by(desc("total_revenue"))
            .limit(10)
            .all()
        )

        insights = {
            "daily_sales": [
                {"date": str(d.date), "count": d.count, "total": float(d.total)}
                for d in daily_sales
            ],
            "top_products": [
                {
                    "name": p.name,
                    "qty": float(p.total_qty),
                    "revenue": float(p.total_revenue),
                }
                for p in top_products
            ],
        }
        return insights

    @staticmethod
    def get_product_performance(tenant_id, branch_id=None):
        from decimal import Decimal

        last_90_days = datetime.now().date() - timedelta(days=90)

        query = (
            _db_session()
            .query(
                models.Product.id,
                models.Product.name,
                models.Product.sku,
                models.Product.cost_price,
                func.sum(models.SaleLine.quantity).label("total_sold"),
                func.sum(models.SaleLine.line_total).label("total_revenue"),
                func.count(func.distinct(models.Sale.id)).label("transactions"),
            )
            .select_from(models.Product)
            .join(models.SaleLine, models.SaleLine.product_id == models.Product.id)
            .join(models.Sale, models.Sale.id == models.SaleLine.sale_id)
            .filter(
                models.Sale.sale_date >= last_90_days,
                models.Sale.status == "confirmed",
                models.Sale.tenant_id == tenant_id,
            )
        )
        if branch_id is not None:
            query = query.filter(models.Sale.branch_id == branch_id)
        products_perf = query.group_by(
            models.Product.id,
            models.Product.name,
            models.Product.sku,
            models.Product.cost_price,
        ).all()

        sold_values = [float(p.total_sold or 0) for p in products_perf if p.total_sold]
        avg_sold = (sum(sold_values) / len(sold_values)) if sold_values else 0
        high_threshold = avg_sold * 1.5
        low_threshold = avg_sold * 0.3

        performance_data = []
        for p in products_perf:
            total_sold = p.total_sold or Decimal("0")
            total_revenue = p.total_revenue or Decimal("0")
            cost_price = p.cost_price or Decimal("0")
            margin = total_revenue - (cost_price * total_sold)
            margin_percent = (margin / total_revenue * 100) if total_revenue > 0 else 0
            status = (
                "ممتاز"
                if total_sold > high_threshold
                else "جيد" if total_sold > low_threshold else "ضعيف"
            )
            performance_data.append(
                {
                    "name": p.name,
                    "code": p.sku,
                    "sold": float(total_sold),
                    "revenue": float(total_revenue),
                    "transactions": p.transactions,
                    "margin": float(margin),
                    "margin_percent": float(margin_percent),
                    "status": status,
                }
            )
        performance_data.sort(key=lambda x: x["revenue"], reverse=True)
        return performance_data

    @staticmethod
    def get_forecasting_data(tenant_id, branch_id=None):
        months_back = 12
        today = datetime.now().date()
        historical_data = []
        for i in range(months_back):
            month_start = (today.replace(day=1) - timedelta(days=30 * i)).replace(day=1)
            if month_start.month == 12:
                month_end = month_start.replace(
                    year=month_start.year + 1, month=1, day=1
                ) - timedelta(days=1)
            else:
                month_end = month_start.replace(
                    month=month_start.month + 1, day=1
                ) - timedelta(days=1)
            revenue = (
                _db_session()
                .query(func.sum(models.Sale.total_amount))
                .filter(
                    models.Sale.sale_date >= month_start,
                    models.Sale.sale_date <= month_end,
                    models.Sale.status == "confirmed",
                    models.Sale.tenant_id == tenant_id,
                )
            )
            if branch_id is not None:
                revenue = revenue.filter(models.Sale.branch_id == branch_id)
            revenue = revenue.scalar() or 0
            historical_data.append(
                {"month": month_start.strftime("%Y-%m"), "revenue": float(revenue)}
            )
        historical_data.reverse()
        forecast = {"next_month": 0, "next_3_months": 0, "confidence": "غير متوفرة"}
        if len(historical_data) >= 3:
            avg_revenue = sum(m["revenue"] for m in historical_data[-3:]) / 3
            trend = (
                historical_data[-1]["revenue"] - historical_data[-3]["revenue"]
            ) / 3
            revenues = [m["revenue"] for m in historical_data if m["revenue"] > 0]
            volatility = (
                (max(revenues) - min(revenues)) / max(avg_revenue, 1) if revenues else 0
            )
            confidence = (
                "عالية"
                if volatility < 0.2
                else "متوسطة" if volatility < 0.5 else "منخفضة"
            )
            forecast = {
                "next_month": avg_revenue + trend,
                "next_3_months": (avg_revenue + trend) * 3,
                "confidence": confidence,
            }
        return historical_data, forecast

    @staticmethod
    def get_revenue_by_period(period="month", months=6, tenant_id=None):
        """
        الحصول على الإيرادات حسب الفترة
        """
        from utils.tenanting import get_active_tenant_id

        tid = tenant_id or get_active_tenant_id()
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30 * months)

        # جلب جميع المعاملات المكتملة للمستأجر
        query = (
            _db_session()
            .query(models.Donation)
            .filter(
                models.Donation.status == "completed",
                models.Donation.created_at >= start_date,
            )
        )
        if tid:
            query = query.filter(models.Donation.tenant_id == tid)
        donations = query.all()

        # تجميع البيانات حسب الفترة
        labels = []
        purchases_data = []
        donations_data = []

        for i in range(months):
            month_start = end_date - timedelta(days=30 * (months - i))
            month_end = month_start + timedelta(days=30)
            month_label = month_start.strftime("%b %Y")

            # حساب المشتريات
            month_purchases = 0
            for d in donations:
                if d.transaction_type == "purchase" and d.created_at:
                    try:
                        dt = (
                            d.created_at.replace(tzinfo=None)
                            if d.created_at.tzinfo
                            else d.created_at
                        )
                        if (
                            month_start.replace(tzinfo=None)
                            <= dt
                            < month_end.replace(tzinfo=None)
                        ):
                            month_purchases += float(d.amount_usd or 0)
                    except Exception:
                        pass

            # حساب التبرعات
            month_donations = 0
            for d in donations:
                if d.transaction_type == "donation" and d.created_at:
                    try:
                        dt = (
                            d.created_at.replace(tzinfo=None)
                            if d.created_at.tzinfo
                            else d.created_at
                        )
                        if (
                            month_start.replace(tzinfo=None)
                            <= dt
                            < month_end.replace(tzinfo=None)
                        ):
                            month_donations += float(d.amount_usd or 0)
                    except Exception:
                        pass

            labels.append(month_label)
            purchases_data.append(round(month_purchases, 2))
            donations_data.append(round(month_donations, 2))

        return {
            "labels": labels,
            "purchases": purchases_data,
            "donations": donations_data,
            "total_revenue": sum(purchases_data) + sum(donations_data),
        }

    @staticmethod
    def get_package_performance(tenant_id=None):
        """تحليل أداء الباقات"""
        from utils.tenanting import get_active_tenant_id

        tid = tenant_id or get_active_tenant_id()

        query = _db_session().query(models.Package).filter_by(is_active=True)
        if tid:
            query = query.filter_by(tenant_id=tid)
        packages = query.all()

        performance = []
        for package in packages:
            purchases = (
                _db_session()
                .query(models.PackagePurchase)
                .filter_by(package_id=package.id)
            )
            if tid:
                purchases = purchases.filter_by(tenant_id=tid)
            purchases = purchases.all()

            completed = [p for p in purchases if p.payment_status == "completed"]
            pending = [p for p in purchases if p.payment_status == "pending"]

            total_revenue = sum(float(p.amount_paid) for p in completed)

            performance.append(
                {
                    "package_name": package.name_ar,
                    "total_sales": len(purchases),
                    "completed": len(completed),
                    "pending": len(pending),
                    "revenue": round(total_revenue, 2),
                    "avg_price": (
                        round(total_revenue / len(completed), 2) if completed else 0
                    ),
                }
            )

        return performance

    @staticmethod
    def get_payment_method_stats(tenant_id=None):
        """إحصائيات طرق الدفع"""
        from utils.tenanting import get_active_tenant_id

        tid = tenant_id or get_active_tenant_id()

        query = _db_session().query(models.Donation).filter_by(status="completed")
        if tid:
            query = query.filter_by(tenant_id=tid)
        donations = query.all()

        methods = {}
        for donation in donations:
            method = donation.payment_method or "unknown"
            if method not in methods:
                methods[method] = {"count": 0, "total": 0}

            methods[method]["count"] += 1
            methods[method]["total"] += float(donation.amount_usd or 0)

        return {
            "methods": list(methods.keys()),
            "counts": [methods[m]["count"] for m in methods],
            "totals": [round(methods[m]["total"], 2) for m in methods],
        }

    @staticmethod
    def get_customer_behavior(tenant_id=None):
        """تحليل سلوك العملاء"""
        from utils.tenanting import get_active_tenant_id

        tid = tenant_id or get_active_tenant_id()

        # جلب جميع المشتريات
        query = _db_session().query(models.PackagePurchase)
        if tid:
            query = query.filter_by(tenant_id=tid)
        purchases = query.all()

        # تحليل توزيع العملاء
        customers = {}
        for purchase in purchases:
            email = purchase.customer_email
            if email not in customers:
                customers[email] = {"purchases": 0, "total_spent": 0, "packages": []}

            customers[email]["purchases"] += 1
            customers[email]["total_spent"] += float(purchase.amount_paid)
            if purchase.package:
                customers[email]["packages"].append(purchase.package.name_ar)

        # تصنيف العملاء
        new_customers = sum(1 for c in customers.values() if c["purchases"] == 1)
        returning_customers = sum(1 for c in customers.values() if c["purchases"] > 1)
        vip_customers = sum(1 for c in customers.values() if c["total_spent"] > 1000)

        return {
            "total_customers": len(customers),
            "new_customers": new_customers,
            "returning_customers": returning_customers,
            "vip_customers": vip_customers,
            "avg_purchases_per_customer": (
                round(
                    sum(c["purchases"] for c in customers.values()) / len(customers), 2
                )
                if customers
                else 0
            ),
            "avg_spent_per_customer": (
                round(
                    sum(c["total_spent"] for c in customers.values()) / len(customers),
                    2,
                )
                if customers
                else 0
            ),
        }

    @staticmethod
    def predict_revenue(months=3, tenant_id=None):
        """
        توقع الإيرادات المستقبلية
        """
        # جلب بيانات آخر 6 أشهر
        revenue_data = AnalyticsService.get_revenue_by_period(
            months=6, tenant_id=tenant_id
        )

        # حساب المتوسط الشهري
        total_revenue = revenue_data["total_revenue"]
        avg_monthly = total_revenue / 6

        # توقع الأشهر القادمة
        predictions = []
        for i in range(1, months + 1):
            month = datetime.now(timezone.utc) + timedelta(days=30 * i)
            # إضافة نمو 5% افتراضياً
            predicted = avg_monthly * (1.05**i)
            predictions.append(
                {
                    "month": month.strftime("%b %Y"),
                    "predicted_revenue": round(predicted, 2),
                }
            )

        return {
            "historical_avg": round(avg_monthly, 2),
            "predictions": predictions,
            "growth_rate": 0.05,  # 5% نمو افتراضي
        }

    @staticmethod
    def get_daily_stats(tenant_id=None):
        """إحصائيات اليوم"""
        from utils.tenanting import get_active_tenant_id

        tid = tenant_id or get_active_tenant_id()
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        query = (
            _db_session()
            .query(models.Donation)
            .filter(models.Donation.created_at >= today_start)
        )
        if tid:
            query = query.filter_by(tenant_id=tid)
        today_donations = query.all()

        today_revenue = sum(
            float(d.amount_usd or 0) for d in today_donations if d.status == "completed"
        )
        pending_today = sum(1 for d in today_donations if d.status == "pending")

        return {
            "today_revenue": round(today_revenue, 2),
            "today_transactions": len(today_donations),
            "pending_today": pending_today,
            "completed_today": sum(
                1 for d in today_donations if d.status == "completed"
            ),
        }
