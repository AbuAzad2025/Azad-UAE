"""
Analytics and Predictions Module
وحدة التحليلات والتنبؤات
"""

from datetime import datetime, timedelta


class SalesAnalytics:
    """تحليلات المبيعات والتنبؤات"""

    @staticmethod
    def predict_next_month_sales(historical_data):
        """
        تنبؤ مبيعات الشهر القادم
        Based on: Moving Average + Trend Analysis
        """
        if not historical_data or len(historical_data) < 3:
            return {"prediction": 0, "confidence": "low", "method": "insufficient_data"}

        # حساب المتوسط المتحرك للأشهر الثلاثة الأخيرة
        recent_months = historical_data[-3:]
        moving_average = sum(recent_months) / len(recent_months)

        # حساب الاتجاه (Trend)
        if len(historical_data) >= 6:
            first_half = sum(historical_data[-6:-3]) / 3
            second_half = sum(historical_data[-3:]) / 3
            trend = second_half - first_half
        else:
            trend = 0

        # التنبؤ = المتوسط + الاتجاه
        prediction = moving_average + trend

        # مستوى الثقة
        variance = sum((x - moving_average) ** 2 for x in recent_months) / len(
            recent_months
        )
        std_dev = variance**0.5

        if std_dev < moving_average * 0.1:
            confidence = "high"
        elif std_dev < moving_average * 0.3:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "prediction": float(prediction),
            "confidence": confidence,
            "trend": "up" if trend > 0 else "down" if trend < 0 else "stable",
            "trend_value": float(trend),
            "method": "moving_average_with_trend",
        }

    @staticmethod
    def analyze_sales_pattern(sales_data):
        """
        تحليل نمط المبيعات
        """
        if not sales_data:
            return {"pattern": "no_data"}

        # تحليل يومي
        daily = {}
        for sale in sales_data:
            day = sale.sale_date.strftime("%A")
            daily[day] = daily.get(day, 0) + 1

        # أكثر يوم مبيعات
        peak_day = max(daily, key=daily.get) if daily else None

        # تحليل شهري

        return {
            "peak_day": peak_day,
            "daily_distribution": daily,
            "trend": "growing" if len(sales_data) > 5 else "stable",
        }

    @staticmethod
    def customer_segmentation(customers_data):
        """
        تقسيم الزبائن (Segmentation)
        """
        segments = {
            "vip": [],  # أعلى 10%
            "regular": [],  # 80%
            "inactive": [],  # لم يشتروا منذ 3 شهور
        }

        # ترتيب حسب المشتريات
        sorted_customers = sorted(
            customers_data, key=lambda c: c.get("total_purchases", 0), reverse=True
        )

        total = len(sorted_customers)
        vip_count = max(1, int(total * 0.1))

        segments["vip"] = sorted_customers[:vip_count]
        segments["regular"] = sorted_customers[vip_count:]

        # تحديد غير النشطين
        datetime.now() - timedelta(days=90)
        # سيتم التنفيذ مع البيانات الحقيقية

        return segments

    @staticmethod
    def abc_analysis(products_data):
        """
        تحليل ABC للمنتجات
        A: 20% من المنتجات = 80% من الإيرادات
        B: 30% من المنتجات = 15% من الإيرادات
        C: 50% من المنتجات = 5% من الإيرادات
        """
        if not products_data:
            return {"A": [], "B": [], "C": []}

        # ترتيب حسب الإيرادات
        sorted_products = sorted(
            products_data, key=lambda p: p.get("revenue", 0), reverse=True
        )

        total_revenue = sum(p.get("revenue", 0) for p in sorted_products)

        cumulative = 0
        categories = {"A": [], "B": [], "C": []}

        for product in sorted_products:
            revenue = product.get("revenue", 0)
            cumulative += revenue
            percentage = (cumulative / total_revenue) * 100 if total_revenue else 0

            if percentage <= 80:
                categories["A"].append(product)
            elif percentage <= 95:
                categories["B"].append(product)
            else:
                categories["C"].append(product)

        return categories


class InventoryAnalytics:
    """تحليلات المخزون"""

    @staticmethod
    def calculate_reorder_point(product_data):
        """
        حساب نقطة إعادة الطلب
        Reorder Point = (Average Daily Usage × Lead Time) + Safety Stock
        """
        avg_daily_sales = product_data.get("avg_daily_sales", 0)
        lead_time_days = product_data.get("lead_time_days", 7)  # افتراضي 7 أيام
        safety_stock = product_data.get("safety_stock", 0)

        reorder_point = (avg_daily_sales * lead_time_days) + safety_stock

        return {
            "reorder_point": round(reorder_point, 2),
            "current_stock": product_data.get("current_stock", 0),
            "status": (
                "order_now"
                if product_data.get("current_stock", 0) <= reorder_point
                else "ok"
            ),
        }

    @staticmethod
    def calculate_eoq(product_data):
        """
        حساب الكمية الاقتصادية للطلب
        EOQ = sqrt((2 × D × S) / H)
        D = Annual Demand
        S = Ordering Cost
        H = Holding Cost per unit per year
        """
        annual_demand = product_data.get("annual_sales", 0)
        ordering_cost = product_data.get("ordering_cost", 100)  # تكلفة الطلب
        holding_cost = product_data.get("holding_cost_percent", 0.2)  # 20% من السعر
        unit_cost = product_data.get("cost_price", 1)

        if annual_demand == 0 or unit_cost == 0:
            return {"eoq": 0, "orders_per_year": 0}

        h = unit_cost * holding_cost

        eoq = ((2 * annual_demand * ordering_cost) / h) ** 0.5
        orders_per_year = annual_demand / eoq if eoq > 0 else 0

        return {
            "eoq": round(eoq, 0),
            "orders_per_year": round(orders_per_year, 1),
            "order_frequency_days": (
                round(365 / orders_per_year, 0) if orders_per_year > 0 else 0
            ),
        }

    @staticmethod
    def inventory_turnover(product_data):
        """
        معدل دوران المخزون
        Turnover = Cost of Goods Sold / Average Inventory
        """
        cogs = product_data.get("cogs_annual", 0)  # تكلفة البضاعة المباعة سنوياً
        avg_inventory = product_data.get("avg_inventory_value", 1)

        if avg_inventory == 0:
            return {"turnover": 0, "status": "no_inventory"}

        turnover = cogs / avg_inventory

        # التقييم
        if turnover >= 8:
            status = "excellent"  # ممتاز
        elif turnover >= 5:
            status = "good"  # جيد
        elif turnover >= 3:
            status = "average"  # متوسط
        else:
            status = "slow"  # بطيء

        return {
            "turnover": round(turnover, 2),
            "status": status,
            "days_in_inventory": round(365 / turnover, 0) if turnover > 0 else 999,
        }


class ProfitAnalytics:
    """تحليلات الربحية"""

    @staticmethod
    def gross_profit_margin(sales, cogs):
        """
        هامش الربح الإجمالي
        GPM = ((Sales - COGS) / Sales) × 100
        """
        if sales == 0:
            return 0

        gpm = ((sales - cogs) / sales) * 100
        return round(gpm, 2)

    @staticmethod
    def net_profit_margin(revenue, total_expenses):
        """
        هامش الربح الصافي
        NPM = (Net Profit / Revenue) × 100
        """
        if revenue == 0:
            return 0

        net_profit = revenue - total_expenses
        npm = (net_profit / revenue) * 100

        return round(npm, 2)

    @staticmethod
    def break_even_analysis(fixed_costs, variable_cost_per_unit, price_per_unit):
        """
        تحليل نقطة التعادل
        BEP = Fixed Costs / (Price - Variable Cost)
        """
        contribution_margin = price_per_unit - variable_cost_per_unit

        if contribution_margin <= 0:
            return {
                "break_even_units": "infinite",
                "break_even_revenue": "infinite",
                "warning": "سعر البيع أقل من أو يساوي التكلفة المتغيرة!",
            }

        bep_units = fixed_costs / contribution_margin
        bep_revenue = bep_units * price_per_unit

        return {
            "break_even_units": round(bep_units, 0),
            "break_even_revenue": round(bep_revenue, 2),
            "contribution_margin": round(contribution_margin, 2),
        }


class CashFlowAnalytics:
    """تحليلات التدفق النقدي"""

    @staticmethod
    def forecast_cash_flow(collections, payments, days=30):
        """
        توقع التدفق النقدي
        """
        total_in = sum(c.get("amount", 0) for c in collections)
        total_out = sum(p.get("amount", 0) for p in payments)

        net_flow = total_in - total_out

        return {
            "cash_in": round(total_in, 2),
            "cash_out": round(total_out, 2),
            "net_cash_flow": round(net_flow, 2),
            "status": "positive" if net_flow > 0 else "negative",
            "forecast_period_days": days,
        }

    @staticmethod
    def working_capital_ratio(current_assets, current_liabilities):
        """
        نسبة رأس المال العامل
        """
        if current_liabilities == 0:
            return {"ratio": "infinite", "status": "excellent"}

        ratio = current_assets / current_liabilities

        if ratio >= 2:
            status = "excellent"
        elif ratio >= 1.5:
            status = "good"
        elif ratio >= 1:
            status = "acceptable"
        else:
            status = "critical"

        return {
            "ratio": round(ratio, 2),
            "status": status,
            "working_capital": round(current_assets - current_liabilities, 2),
        }


# مكتبة شاملة للتحليلات
ANALYTICS_LIBRARY = {
    "sales": SalesAnalytics,
    "inventory": InventoryAnalytics,
    "profit": ProfitAnalytics,
    "cashflow": CashFlowAnalytics,
}


def get_analytics(analytics_type):
    """الحصول على نوع تحليل معين"""
    return ANALYTICS_LIBRARY.get(analytics_type)
