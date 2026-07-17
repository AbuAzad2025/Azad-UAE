"""
📊 محلل البيانات - Data Analyzer
أزاد يحلل البيانات بدقة عالية
"""

from datetime import datetime, timedelta
from decimal import Decimal
import statistics


class DataAnalyzer:
    """محلل البيانات لأزاد"""

    def __init__(self):
        pass

    def analyze_customer_debt(self, customer_id):
        """تحليل ديون العميل بالتفصيل"""
        try:
            from models import Customer, Sale
            from extensions import db

            customer = db.session.get(Customer, customer_id)
            if not customer:
                return {"success": False, "error": "العميل غير موجود"}

            # المبيعات غير المدفوعة بالكامل
            unpaid_sales = Sale.query.filter(
                Sale.customer_id == customer_id, Sale.paid_amount < Sale.total_amount
            ).all()

            # تفصيل الديون
            debt_details = []
            total_debt = Decimal("0")

            for sale in unpaid_sales:
                remaining_amount = sale.total_amount - sale.paid_amount
                days_overdue = (datetime.now() - sale.created_at).days

                debt_details.append(
                    {
                        "sale_id": sale.id,
                        "sale_date": sale.created_at.strftime("%Y-%m-%d"),
                        "total_amount": float(sale.total_amount),
                        "paid_amount": float(sale.paid_amount),
                        "remaining_amount": float(remaining_amount),
                        "days_overdue": days_overdue,
                        "status": "متأخر" if days_overdue > 30 else "عادي",
                    }
                )

                total_debt += remaining_amount

            # إحصائيات الديون
            if debt_details:
                avg_debt_amount = statistics.mean(
                    [d["remaining_amount"] for d in debt_details]
                )
                max_debt_amount = max([d["remaining_amount"] for d in debt_details])
                overdue_count = len([d for d in debt_details if d["days_overdue"] > 30])
            else:
                avg_debt_amount = 0
                max_debt_amount = 0
                overdue_count = 0

            return {
                "success": True,
                "customer": {
                    "id": customer.id,
                    "name": customer.name,
                    "total_debt": float(total_debt),
                },
                "debt_analysis": {
                    "total_debt": float(total_debt),
                    "unpaid_sales_count": len(debt_details),
                    "avg_debt_amount": avg_debt_amount,
                    "max_debt_amount": max_debt_amount,
                    "overdue_count": overdue_count,
                    "debt_details": debt_details,
                },
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في تحليل ديون العميل: {str(e)}"}

    def analyze_sales_performance(self, period_days=30):
        """تحليل أداء المبيعات"""
        try:
            from models import Sale

            start_date = datetime.now() - timedelta(days=period_days)

            # المبيعات في الفترة
            sales = Sale.query.filter(Sale.created_at >= start_date).all()

            if not sales:
                return {
                    "success": True,
                    "analysis": {
                        "period_days": period_days,
                        "total_sales": 0,
                        "total_amount": 0,
                        "avg_daily_sales": 0,
                        "trend": "لا توجد بيانات",
                    },
                }

            # إحصائيات أساسية
            total_sales = len(sales)
            total_amount = sum(float(sale.total_amount) for sale in sales)
            avg_daily_sales = total_amount / period_days

            # المبيعات اليومية
            daily_sales = {}
            for sale in sales:
                date_key = sale.created_at.date()
                if date_key not in daily_sales:
                    daily_sales[date_key] = 0
                daily_sales[date_key] += float(sale.total_amount)

            # تحليل الاتجاه
            daily_amounts = list(daily_sales.values())
            if len(daily_amounts) > 1:
                recent_avg = statistics.mean(daily_amounts[-7:])  # آخر أسبوع
                earlier_avg = (
                    statistics.mean(daily_amounts[:-7])
                    if len(daily_amounts) > 7
                    else recent_avg
                )

                if recent_avg > earlier_avg * 1.1:
                    trend = "تصاعدي"
                elif recent_avg < earlier_avg * 0.9:
                    trend = "تنازلي"
                else:
                    trend = "مستقر"
            else:
                trend = "غير محدد"

            # أفضل العملاء
            customer_sales = {}
            for sale in sales:
                if sale.customer:
                    customer_name = sale.customer.name
                    if customer_name not in customer_sales:
                        customer_sales[customer_name] = 0
                    customer_sales[customer_name] += float(sale.total_amount)

            top_customers = sorted(
                customer_sales.items(), key=lambda x: x[1], reverse=True
            )[:5]

            return {
                "success": True,
                "analysis": {
                    "period_days": period_days,
                    "total_sales": total_sales,
                    "total_amount": total_amount,
                    "avg_daily_sales": avg_daily_sales,
                    "trend": trend,
                    "top_customers": [
                        {"name": name, "amount": amount}
                        for name, amount in top_customers
                    ],
                    "daily_sales_count": len(daily_sales),
                },
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في تحليل أداء المبيعات: {str(e)}"}

    def analyze_product_performance(self, product_id=None):
        """تحليل أداء المنتجات"""
        try:
            from models import Product, SaleLine, Sale

            if product_id:
                # تحليل منتج محدد
                product = Product.query.get(product_id)
                if not product:
                    return {"success": False, "error": "المنتج غير موجود"}

                # المبيعات للمنتج
                sales_lines = SaleLine.query.filter(
                    SaleLine.product_id == product_id
                ).all()

                total_quantity_sold = sum(line.quantity for line in sales_lines)
                total_revenue = sum(float(line.line_total) for line in sales_lines)

                # آخر مبيعات
                recent_sales = (
                    SaleLine.query.filter(SaleLine.product_id == product_id)
                    .join(Sale)
                    .order_by(Sale.created_at.desc())
                    .limit(5)
                    .all()
                )

                return {
                    "success": True,
                    "product": {
                        "id": product.id,
                        "name": product.name,
                        "sku": product.sku,
                        "current_stock": product.current_stock,
                    },
                    "performance": {
                        "total_quantity_sold": total_quantity_sold,
                        "total_revenue": total_revenue,
                        "avg_price": (
                            total_revenue / total_quantity_sold
                            if total_quantity_sold > 0
                            else 0
                        ),
                        "sales_count": len(sales_lines),
                    },
                    "recent_sales": [
                        {
                            "sale_id": line.sale_id,
                            "quantity": line.quantity,
                            "unit_price": float(line.unit_price),
                            "total": float(line.line_total),
                            "date": line.sale.created_at.strftime("%Y-%m-%d"),
                        }
                        for line in recent_sales
                    ],
                }
            else:
                # تحليل جميع المنتجات
                products = Product.query.all()
                product_performance = []

                for product in products:
                    sales_lines = SaleLine.query.filter(
                        SaleLine.product_id == product.id
                    ).all()

                    if sales_lines:
                        total_sold = sum(line.quantity for line in sales_lines)
                        total_revenue = sum(
                            float(line.line_total) for line in sales_lines
                        )

                        product_performance.append(
                            {
                                "id": product.id,
                                "name": product.name,
                                "sku": product.sku,
                                "current_stock": product.current_stock,
                                "total_sold": total_sold,
                                "total_revenue": total_revenue,
                                "sales_count": len(sales_lines),
                            }
                        )

                # ترتيب حسب الإيرادات
                product_performance.sort(key=lambda x: x["total_revenue"], reverse=True)

                return {
                    "success": True,
                    "top_products": product_performance[:10],  # أفضل 10 منتجات
                    "total_products": len(products),
                    "analyzed_products": len(product_performance),
                }

        except Exception as e:
            return {"success": False, "error": f"خطأ في تحليل أداء المنتجات: {str(e)}"}

    def analyze_payment_patterns(self, customer_id=None):
        """تحليل أنماط الدفع"""
        try:
            from models import Customer, Payment

            if customer_id:
                # تحليل عميل محدد
                customer = Customer.query.get(customer_id)
                if not customer:
                    return {"success": False, "error": "العميل غير موجود"}

                payments = Payment.query.filter(
                    Payment.sale.has(customer_id=customer_id)
                ).all()
            else:
                # تحليل جميع المدفوعات
                payments = Payment.query.all()

            if not payments:
                return {
                    "success": True,
                    "analysis": {
                        "total_payments": 0,
                        "payment_methods": {},
                        "avg_payment_amount": 0,
                    },
                }

            # تحليل طرق الدفع
            payment_methods = {}
            total_amount = Decimal("0")

            for payment in payments:
                method = payment.payment_method
                if method not in payment_methods:
                    payment_methods[method] = {"count": 0, "amount": Decimal("0")}

                payment_methods[method]["count"] += 1
                payment_methods[method]["amount"] += payment.amount
                total_amount += payment.amount

            # تحويل إلى قائمة
            method_analysis = []
            for method, data in payment_methods.items():
                method_analysis.append(
                    {
                        "method": method,
                        "count": data["count"],
                        "total_amount": float(data["amount"]),
                        "percentage": (
                            float(data["amount"] / total_amount * 100)
                            if total_amount > 0
                            else 0
                        ),
                    }
                )

            method_analysis.sort(key=lambda x: x["total_amount"], reverse=True)

            return {
                "success": True,
                "analysis": {
                    "total_payments": len(payments),
                    "total_amount": float(total_amount),
                    "avg_payment_amount": float(total_amount / len(payments)),
                    "payment_methods": method_analysis,
                    "customer_id": customer_id,
                },
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في تحليل أنماط الدفع: {str(e)}"}

    def get_financial_ratios(self):
        """الحصول على النسب المالية"""
        try:
            from models import Sale, Payment, Customer, Product
            from extensions import db

            # المبيعات
            total_sales = db.session.query(
                db.func.sum(Sale.total_amount)
            ).scalar() or Decimal("0")

            # المدفوعات
            total_payments = db.session.query(
                db.func.sum(Payment.amount)
            ).scalar() or Decimal("0")

            # الذمم المدينة
            receivables = total_sales - total_payments

            # العملاء
            total_customers = Customer.query.count()

            # المنتجات
            total_products = Product.query.count()

            # النسب المالية
            ratios = {
                "collection_rate": (
                    float(total_payments / total_sales * 100) if total_sales > 0 else 0
                ),
                "avg_sales_per_customer": (
                    float(total_sales / total_customers) if total_customers > 0 else 0
                ),
                "receivables_ratio": (
                    float(receivables / total_sales * 100) if total_sales > 0 else 0
                ),
                "product_diversity": total_products,
            }

            return {
                "success": True,
                "ratios": ratios,
                "summary": {
                    "total_sales": float(total_sales),
                    "total_payments": float(total_payments),
                    "total_receivables": float(receivables),
                    "total_customers": total_customers,
                    "total_products": total_products,
                },
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في حساب النسب المالية: {str(e)}"}


# إنشاء مثيل عالمي
data_analyzer = DataAnalyzer()
