"""
Analytics Service - خدمة التحليلات
تحليلات متقدمة للمدفوعات والعملاء
"""
from datetime import datetime, timezone, timedelta
from extensions import db
from models import Donation, PackagePurchase, Package, Sale, Product, SaleLine
from sqlalchemy import func, desc
import logging

logger = logging.getLogger(__name__)


class AnalyticsService:
    """خدمة التحليلات المتقدمة"""

    @staticmethod
    def get_sales_insights(tenant_id, branch_id=None):
        today = datetime.now().date()
        last_30_days = today - timedelta(days=30)

        daily_sales = db.session.query(
            func.date(Sale.sale_date).label('date'),
            func.count(Sale.id).label('count'),
            func.sum(Sale.total_amount).label('total')
        ).filter(
            Sale.sale_date >= last_30_days,
            Sale.status == 'confirmed',
            Sale.tenant_id == tenant_id,
        )
        if branch_id is not None:
            daily_sales = daily_sales.filter(Sale.branch_id == branch_id)
        daily_sales = daily_sales.group_by(func.date(Sale.sale_date)).all()

        top_products = db.session.query(
            Product.name,
            func.sum(SaleLine.quantity).label('total_qty'),
            func.sum(SaleLine.line_total).label('total_revenue')
        ).select_from(Product).join(
            SaleLine, SaleLine.product_id == Product.id
        ).join(
            Sale, Sale.id == SaleLine.sale_id
        ).filter(
            Sale.sale_date >= last_30_days,
            Sale.status == 'confirmed',
            Sale.tenant_id == tenant_id,
        )
        if branch_id is not None:
            top_products = top_products.filter(Sale.branch_id == branch_id)
        top_products = top_products.group_by(
            Product.id,
            Product.name,
        ).order_by(desc('total_revenue')).limit(10).all()

        insights = {
            'daily_sales': [{'date': str(d.date), 'count': d.count, 'total': float(d.total)} for d in daily_sales],
            'top_products': [{'name': p.name, 'qty': float(p.total_qty), 'revenue': float(p.total_revenue)} for p in top_products]
        }
        return insights

    @staticmethod
    def get_revenue_by_period(period='month', months=6, tenant_id=None):
        """
        الحصول على الإيرادات حسب الفترة
        """
        from utils.tenanting import active_tenant_id
        tid = tenant_id or active_tenant_id()
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30 * months)

        # جلب جميع المعاملات المكتملة للمستأجر
        query = Donation.query.filter(
            Donation.status == 'completed',
            Donation.created_at >= start_date
        )
        if tid:
            query = query.filter(Donation.tenant_id == tid)
        donations = query.all()

        # تجميع البيانات حسب الفترة
        labels = []
        purchases_data = []
        donations_data = []

        for i in range(months):
            month_start = end_date - timedelta(days=30 * (months - i))
            month_end = month_start + timedelta(days=30)
            month_label = month_start.strftime('%b %Y')

            # حساب المشتريات
            month_purchases = 0
            for d in donations:
                if d.transaction_type == 'purchase' and d.created_at:
                    try:
                        dt = d.created_at.replace(tzinfo=None) if d.created_at.tzinfo else d.created_at
                        if month_start.replace(tzinfo=None) <= dt < month_end.replace(tzinfo=None):
                            month_purchases += float(d.amount_usd or 0)
                    except:
                        pass

            # حساب التبرعات
            month_donations = 0
            for d in donations:
                if d.transaction_type == 'donation' and d.created_at:
                    try:
                        dt = d.created_at.replace(tzinfo=None) if d.created_at.tzinfo else d.created_at
                        if month_start.replace(tzinfo=None) <= dt < month_end.replace(tzinfo=None):
                            month_donations += float(d.amount_usd or 0)
                    except:
                        pass

            labels.append(month_label)
            purchases_data.append(round(month_purchases, 2))
            donations_data.append(round(month_donations, 2))

        return {
            'labels': labels,
            'purchases': purchases_data,
            'donations': donations_data,
            'total_revenue': sum(purchases_data) + sum(donations_data)
        }

    @staticmethod
    def get_package_performance(tenant_id=None):
        """تحليل أداء الباقات"""
        from utils.tenanting import active_tenant_id
        tid = tenant_id or active_tenant_id()

        query = Package.query.filter_by(is_active=True)
        if tid:
            query = query.filter_by(tenant_id=tid)
        packages = query.all()

        performance = []
        for package in packages:
            purchases = PackagePurchase.query.filter_by(package_id=package.id)
            if tid:
                purchases = purchases.filter_by(tenant_id=tid)
            purchases = purchases.all()

            completed = [p for p in purchases if p.payment_status == 'completed']
            pending = [p for p in purchases if p.payment_status == 'pending']

            total_revenue = sum(float(p.amount_paid) for p in completed)

            performance.append({
                'package_name': package.name_ar,
                'total_sales': len(purchases),
                'completed': len(completed),
                'pending': len(pending),
                'revenue': round(total_revenue, 2),
                'avg_price': round(total_revenue / len(completed), 2) if completed else 0
            })

        return performance

    @staticmethod
    def get_payment_method_stats(tenant_id=None):
        """إحصائيات طرق الدفع"""
        from utils.tenanting import active_tenant_id
        tid = tenant_id or active_tenant_id()

        query = Donation.query.filter_by(status='completed')
        if tid:
            query = query.filter_by(tenant_id=tid)
        donations = query.all()

        methods = {}
        for donation in donations:
            method = donation.payment_method or 'unknown'
            if method not in methods:
                methods[method] = {'count': 0, 'total': 0}

            methods[method]['count'] += 1
            methods[method]['total'] += float(donation.amount_usd or 0)

        return {
            'methods': list(methods.keys()),
            'counts': [methods[m]['count'] for m in methods],
            'totals': [round(methods[m]['total'], 2) for m in methods]
        }

    @staticmethod
    def get_customer_behavior(tenant_id=None):
        """تحليل سلوك العملاء"""
        from utils.tenanting import active_tenant_id
        tid = tenant_id or active_tenant_id()

        # جلب جميع المشتريات
        query = PackagePurchase.query
        if tid:
            query = query.filter_by(tenant_id=tid)
        purchases = query.all()

        # تحليل توزيع العملاء
        customers = {}
        for purchase in purchases:
            email = purchase.customer_email
            if email not in customers:
                customers[email] = {
                    'purchases': 0,
                    'total_spent': 0,
                    'packages': []
                }

            customers[email]['purchases'] += 1
            customers[email]['total_spent'] += float(purchase.amount_paid)
            if purchase.package:
                customers[email]['packages'].append(purchase.package.name_ar)

        # تصنيف العملاء
        new_customers = sum(1 for c in customers.values() if c['purchases'] == 1)
        returning_customers = sum(1 for c in customers.values() if c['purchases'] > 1)
        vip_customers = sum(1 for c in customers.values() if c['total_spent'] > 1000)

        return {
            'total_customers': len(customers),
            'new_customers': new_customers,
            'returning_customers': returning_customers,
            'vip_customers': vip_customers,
            'avg_purchases_per_customer': round(
                sum(c['purchases'] for c in customers.values()) / len(customers), 2
            ) if customers else 0,
            'avg_spent_per_customer': round(
                sum(c['total_spent'] for c in customers.values()) / len(customers), 2
            ) if customers else 0
        }

    @staticmethod
    def predict_revenue(months=3, tenant_id=None):
        """
        توقع الإيرادات المستقبلية
        """
        # جلب بيانات آخر 6 أشهر
        revenue_data = AnalyticsService.get_revenue_by_period(months=6, tenant_id=tenant_id)

        # حساب المتوسط الشهري
        total_revenue = revenue_data['total_revenue']
        avg_monthly = total_revenue / 6

        # توقع الأشهر القادمة
        predictions = []
        for i in range(1, months + 1):
            month = datetime.now(timezone.utc) + timedelta(days=30 * i)
            # إضافة نمو 5% افتراضياً
            predicted = avg_monthly * (1.05 ** i)
            predictions.append({
                'month': month.strftime('%b %Y'),
                'predicted_revenue': round(predicted, 2)
            })

        return {
            'historical_avg': round(avg_monthly, 2),
            'predictions': predictions,
            'growth_rate': 0.05  # 5% نمو افتراضي
        }

    @staticmethod
    def get_daily_stats(tenant_id=None):
        """إحصائيات اليوم"""
        from utils.tenanting import active_tenant_id
        tid = tenant_id or active_tenant_id()
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        query = Donation.query.filter(Donation.created_at >= today_start)
        if tid:
            query = query.filter_by(tenant_id=tid)
        today_donations = query.all()

        today_revenue = sum(float(d.amount_usd or 0) for d in today_donations if d.status == 'completed')
        pending_today = sum(1 for d in today_donations if d.status == 'pending')

        return {
            'today_revenue': round(today_revenue, 2),
            'today_transactions': len(today_donations),
            'pending_today': pending_today,
            'completed_today': sum(1 for d in today_donations if d.status == 'completed')
        }
