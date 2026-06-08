"""
Consolidated module: analytics_engine.py
Merged: analytics/data_analyzer.py, analytics/analytics_predictions.py, analytics/market_insights.py

This module consolidates multiple small files into one.
Old import paths still work via backward-compatible shims in the original files.
"""


# ===== Consolidated from: analytics/data_analyzer.py =====
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
                return {'success': False, 'error': 'العميل غير موجود'}
            
            # المبيعات غير المدفوعة بالكامل
            unpaid_sales = Sale.query.filter(
                Sale.customer_id == customer_id,
                Sale.paid_amount < Sale.total_amount
            ).all()
            
            # تفصيل الديون
            debt_details = []
            total_debt = Decimal('0')
            
            for sale in unpaid_sales:
                remaining_amount = sale.total_amount - sale.paid_amount
                days_overdue = (datetime.now() - sale.created_at).days
                
                debt_details.append({
                    'sale_id': sale.id,
                    'sale_date': sale.created_at.strftime('%Y-%m-%d'),
                    'total_amount': float(sale.total_amount),
                    'paid_amount': float(sale.paid_amount),
                    'remaining_amount': float(remaining_amount),
                    'days_overdue': days_overdue,
                    'status': 'متأخر' if days_overdue > 30 else 'عادي'
                })
                
                total_debt += remaining_amount
            
            # إحصائيات الديون
            if debt_details:
                avg_debt_amount = statistics.mean([d['remaining_amount'] for d in debt_details])
                max_debt_amount = max([d['remaining_amount'] for d in debt_details])
                overdue_count = len([d for d in debt_details if d['days_overdue'] > 30])
            else:
                avg_debt_amount = 0
                max_debt_amount = 0
                overdue_count = 0
            
            return {
                'success': True,
                'customer': {
                    'id': customer.id,
                    'name': customer.name,
                    'total_debt': float(total_debt)
                },
                'debt_analysis': {
                    'total_debt': float(total_debt),
                    'unpaid_sales_count': len(debt_details),
                    'avg_debt_amount': avg_debt_amount,
                    'max_debt_amount': max_debt_amount,
                    'overdue_count': overdue_count,
                    'debt_details': debt_details
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في تحليل ديون العميل: {str(e)}'
            }
    
    def analyze_sales_performance(self, period_days=30):
        """تحليل أداء المبيعات"""
        try:
            from models import Sale
            
            start_date = datetime.now() - timedelta(days=period_days)
            
            # المبيعات في الفترة
            sales = Sale.query.filter(Sale.created_at >= start_date).all()
            
            if not sales:
                return {
                    'success': True,
                    'analysis': {
                        'period_days': period_days,
                        'total_sales': 0,
                        'total_amount': 0,
                        'avg_daily_sales': 0,
                        'trend': 'لا توجد بيانات'
                    }
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
                earlier_avg = statistics.mean(daily_amounts[:-7]) if len(daily_amounts) > 7 else recent_avg
                
                if recent_avg > earlier_avg * 1.1:
                    trend = 'تصاعدي'
                elif recent_avg < earlier_avg * 0.9:
                    trend = 'تنازلي'
                else:
                    trend = 'مستقر'
            else:
                trend = 'غير محدد'
            
            # أفضل العملاء
            customer_sales = {}
            for sale in sales:
                if sale.customer:
                    customer_name = sale.customer.name
                    if customer_name not in customer_sales:
                        customer_sales[customer_name] = 0
                    customer_sales[customer_name] += float(sale.total_amount)
            
            top_customers = sorted(
                customer_sales.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            
            return {
                'success': True,
                'analysis': {
                    'period_days': period_days,
                    'total_sales': total_sales,
                    'total_amount': total_amount,
                    'avg_daily_sales': avg_daily_sales,
                    'trend': trend,
                    'top_customers': [
                        {'name': name, 'amount': amount}
                        for name, amount in top_customers
                    ],
                    'daily_sales_count': len(daily_sales)
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في تحليل أداء المبيعات: {str(e)}'
            }
    
    def analyze_product_performance(self, product_id=None):
        """تحليل أداء المنتجات"""
        try:
            from models import Product, SaleLine, Sale
            
            if product_id:
                # تحليل منتج محدد
                product = Product.query.get(product_id)
                if not product:
                    return {'success': False, 'error': 'المنتج غير موجود'}
                
                # المبيعات للمنتج
                sales_lines = SaleLine.query.filter(
                    SaleLine.product_id == product_id
                ).all()
                
                total_quantity_sold = sum(line.quantity for line in sales_lines)
                total_revenue = sum(float(line.line_total) for line in sales_lines)
                
                # آخر مبيعات
                recent_sales = SaleLine.query.filter(
                    SaleLine.product_id == product_id
                ).join(Sale).order_by(Sale.created_at.desc()).limit(5).all()
                
                return {
                    'success': True,
                    'product': {
                        'id': product.id,
                        'name': product.name,
                        'sku': product.sku,
                        'current_stock': product.current_stock
                    },
                    'performance': {
                        'total_quantity_sold': total_quantity_sold,
                        'total_revenue': total_revenue,
                        'avg_price': total_revenue / total_quantity_sold if total_quantity_sold > 0 else 0,
                        'sales_count': len(sales_lines)
                    },
                    'recent_sales': [
                        {
                            'sale_id': line.sale_id,
                            'quantity': line.quantity,
                            'unit_price': float(line.unit_price),
                            'total': float(line.line_total),
                            'date': line.sale.created_at.strftime('%Y-%m-%d')
                        }
                        for line in recent_sales
                    ]
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
                        total_revenue = sum(float(line.line_total) for line in sales_lines)
                        
                        product_performance.append({
                            'id': product.id,
                            'name': product.name,
                            'sku': product.sku,
                            'current_stock': product.current_stock,
                            'total_sold': total_sold,
                            'total_revenue': total_revenue,
                            'sales_count': len(sales_lines)
                        })
                
                # ترتيب حسب الإيرادات
                product_performance.sort(key=lambda x: x['total_revenue'], reverse=True)
                
                return {
                    'success': True,
                    'top_products': product_performance[:10],  # أفضل 10 منتجات
                    'total_products': len(products),
                    'analyzed_products': len(product_performance)
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في تحليل أداء المنتجات: {str(e)}'
            }
    
    def analyze_payment_patterns(self, customer_id=None):
        """تحليل أنماط الدفع"""
        try:
            from models import Customer, Payment
            
            if customer_id:
                # تحليل عميل محدد
                customer = Customer.query.get(customer_id)
                if not customer:
                    return {'success': False, 'error': 'العميل غير موجود'}
                
                payments = Payment.query.filter(
                    Payment.sale.has(customer_id=customer_id)
                ).all()
            else:
                # تحليل جميع المدفوعات
                payments = Payment.query.all()
            
            if not payments:
                return {
                    'success': True,
                    'analysis': {
                        'total_payments': 0,
                        'payment_methods': {},
                        'avg_payment_amount': 0
                    }
                }
            
            # تحليل طرق الدفع
            payment_methods = {}
            total_amount = Decimal('0')
            
            for payment in payments:
                method = payment.payment_method
                if method not in payment_methods:
                    payment_methods[method] = {'count': 0, 'amount': Decimal('0')}
                
                payment_methods[method]['count'] += 1
                payment_methods[method]['amount'] += payment.amount
                total_amount += payment.amount
            
            # تحويل إلى قائمة
            method_analysis = []
            for method, data in payment_methods.items():
                method_analysis.append({
                    'method': method,
                    'count': data['count'],
                    'total_amount': float(data['amount']),
                    'percentage': float(data['amount'] / total_amount * 100) if total_amount > 0 else 0
                })
            
            method_analysis.sort(key=lambda x: x['total_amount'], reverse=True)
            
            return {
                'success': True,
                'analysis': {
                    'total_payments': len(payments),
                    'total_amount': float(total_amount),
                    'avg_payment_amount': float(total_amount / len(payments)),
                    'payment_methods': method_analysis,
                    'customer_id': customer_id
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في تحليل أنماط الدفع: {str(e)}'
            }
    
    def get_financial_ratios(self):
        """الحصول على النسب المالية"""
        try:
            from models import Sale, Payment, Customer, Product
            from extensions import db
            
            # المبيعات
            total_sales = db.session.query(
                db.func.sum(Sale.total_amount)
            ).scalar() or Decimal('0')
            
            # المدفوعات
            total_payments = db.session.query(
                db.func.sum(Payment.amount)
            ).scalar() or Decimal('0')
            
            # الذمم المدينة
            receivables = total_sales - total_payments
            
            # العملاء
            total_customers = Customer.query.count()
            
            # المنتجات
            total_products = Product.query.count()
            
            # النسب المالية
            ratios = {
                'collection_rate': float(total_payments / total_sales * 100) if total_sales > 0 else 0,
                'avg_sales_per_customer': float(total_sales / total_customers) if total_customers > 0 else 0,
                'receivables_ratio': float(receivables / total_sales * 100) if total_sales > 0 else 0,
                'product_diversity': total_products
            }
            
            return {
                'success': True,
                'ratios': ratios,
                'summary': {
                    'total_sales': float(total_sales),
                    'total_payments': float(total_payments),
                    'total_receivables': float(receivables),
                    'total_customers': total_customers,
                    'total_products': total_products
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في حساب النسب المالية: {str(e)}'
            }


# إنشاء مثيل عالمي
data_analyzer = DataAnalyzer()


# ===== Consolidated from: analytics/analytics_predictions.py =====
"""
Analytics and Predictions Module
وحدة التحليلات والتنبؤات
"""

from decimal import Decimal
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
            return {
                'prediction': 0,
                'confidence': 'low',
                'method': 'insufficient_data'
            }
        
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
        variance = sum((x - moving_average) ** 2 for x in recent_months) / len(recent_months)
        std_dev = variance ** 0.5
        
        if std_dev < moving_average * 0.1:
            confidence = 'high'
        elif std_dev < moving_average * 0.3:
            confidence = 'medium'
        else:
            confidence = 'low'
        
        return {
            'prediction': float(prediction),
            'confidence': confidence,
            'trend': 'up' if trend > 0 else 'down' if trend < 0 else 'stable',
            'trend_value': float(trend),
            'method': 'moving_average_with_trend'
        }
    
    @staticmethod
    def analyze_sales_pattern(sales_data):
        """
        تحليل نمط المبيعات
        """
        if not sales_data:
            return {'pattern': 'no_data'}
        
        # تحليل يومي
        daily = {}
        for sale in sales_data:
            day = sale.sale_date.strftime('%A')
            daily[day] = daily.get(day, 0) + 1
        
        # أكثر يوم مبيعات
        peak_day = max(daily, key=daily.get) if daily else None
        
        # تحليل شهري
        monthly_trend = []
        
        return {
            'peak_day': peak_day,
            'daily_distribution': daily,
            'trend': 'growing' if len(sales_data) > 5 else 'stable'
        }
    
    @staticmethod
    def customer_segmentation(customers_data):
        """
        تقسيم الزبائن (Segmentation)
        """
        segments = {
            'vip': [],      # أعلى 10%
            'regular': [],  # 80%
            'inactive': [], # لم يشتروا منذ 3 شهور
        }
        
        # ترتيب حسب المشتريات
        sorted_customers = sorted(
            customers_data,
            key=lambda c: c.get('total_purchases', 0),
            reverse=True
        )
        
        total = len(sorted_customers)
        vip_count = max(1, int(total * 0.1))
        
        segments['vip'] = sorted_customers[:vip_count]
        segments['regular'] = sorted_customers[vip_count:]
        
        # تحديد غير النشطين
        three_months_ago = datetime.now() - timedelta(days=90)
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
            return {'A': [], 'B': [], 'C': []}
        
        # ترتيب حسب الإيرادات
        sorted_products = sorted(
            products_data,
            key=lambda p: p.get('revenue', 0),
            reverse=True
        )
        
        total_revenue = sum(p.get('revenue', 0) for p in sorted_products)
        
        cumulative = 0
        categories = {'A': [], 'B': [], 'C': []}
        
        for product in sorted_products:
            revenue = product.get('revenue', 0)
            cumulative += revenue
            percentage = (cumulative / total_revenue) * 100 if total_revenue else 0
            
            if percentage <= 80:
                categories['A'].append(product)
            elif percentage <= 95:
                categories['B'].append(product)
            else:
                categories['C'].append(product)
        
        return categories


class InventoryAnalytics:
    """تحليلات المخزون"""
    
    @staticmethod
    def calculate_reorder_point(product_data):
        """
        حساب نقطة إعادة الطلب
        Reorder Point = (Average Daily Usage × Lead Time) + Safety Stock
        """
        avg_daily_sales = product_data.get('avg_daily_sales', 0)
        lead_time_days = product_data.get('lead_time_days', 7)  # افتراضي 7 أيام
        safety_stock = product_data.get('safety_stock', 0)
        
        reorder_point = (avg_daily_sales * lead_time_days) + safety_stock
        
        return {
            'reorder_point': round(reorder_point, 2),
            'current_stock': product_data.get('current_stock', 0),
            'status': 'order_now' if product_data.get('current_stock', 0) <= reorder_point else 'ok'
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
        annual_demand = product_data.get('annual_sales', 0)
        ordering_cost = product_data.get('ordering_cost', 100)  # تكلفة الطلب
        holding_cost = product_data.get('holding_cost_percent', 0.2)  # 20% من السعر
        unit_cost = product_data.get('cost_price', 1)
        
        if annual_demand == 0 or unit_cost == 0:
            return {'eoq': 0, 'orders_per_year': 0}
        
        H = unit_cost * holding_cost
        
        eoq = ((2 * annual_demand * ordering_cost) / H) ** 0.5
        orders_per_year = annual_demand / eoq if eoq > 0 else 0
        
        return {
            'eoq': round(eoq, 0),
            'orders_per_year': round(orders_per_year, 1),
            'order_frequency_days': round(365 / orders_per_year, 0) if orders_per_year > 0 else 0
        }
    
    @staticmethod
    def inventory_turnover(product_data):
        """
        معدل دوران المخزون
        Turnover = Cost of Goods Sold / Average Inventory
        """
        cogs = product_data.get('cogs_annual', 0)  # تكلفة البضاعة المباعة سنوياً
        avg_inventory = product_data.get('avg_inventory_value', 1)
        
        if avg_inventory == 0:
            return {'turnover': 0, 'status': 'no_inventory'}
        
        turnover = cogs / avg_inventory
        
        # التقييم
        if turnover >= 8:
            status = 'excellent'  # ممتاز
        elif turnover >= 5:
            status = 'good'       # جيد
        elif turnover >= 3:
            status = 'average'    # متوسط
        else:
            status = 'slow'       # بطيء
        
        return {
            'turnover': round(turnover, 2),
            'status': status,
            'days_in_inventory': round(365 / turnover, 0) if turnover > 0 else 999
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
                'break_even_units': 'infinite',
                'break_even_revenue': 'infinite',
                'warning': 'سعر البيع أقل من أو يساوي التكلفة المتغيرة!'
            }
        
        bep_units = fixed_costs / contribution_margin
        bep_revenue = bep_units * price_per_unit
        
        return {
            'break_even_units': round(bep_units, 0),
            'break_even_revenue': round(bep_revenue, 2),
            'contribution_margin': round(contribution_margin, 2)
        }


class CashFlowAnalytics:
    """تحليلات التدفق النقدي"""
    
    @staticmethod
    def forecast_cash_flow(collections, payments, days=30):
        """
        توقع التدفق النقدي
        """
        total_in = sum(c.get('amount', 0) for c in collections)
        total_out = sum(p.get('amount', 0) for p in payments)
        
        net_flow = total_in - total_out
        
        return {
            'cash_in': round(total_in, 2),
            'cash_out': round(total_out, 2),
            'net_cash_flow': round(net_flow, 2),
            'status': 'positive' if net_flow > 0 else 'negative',
            'forecast_period_days': days
        }
    
    @staticmethod
    def working_capital_ratio(current_assets, current_liabilities):
        """
        نسبة رأس المال العامل
        """
        if current_liabilities == 0:
            return {'ratio': 'infinite', 'status': 'excellent'}
        
        ratio = current_assets / current_liabilities
        
        if ratio >= 2:
            status = 'excellent'
        elif ratio >= 1.5:
            status = 'good'
        elif ratio >= 1:
            status = 'acceptable'
        else:
            status = 'critical'
        
        return {
            'ratio': round(ratio, 2),
            'status': status,
            'working_capital': round(current_assets - current_liabilities, 2)
        }


# مكتبة شاملة للتحليلات
ANALYTICS_LIBRARY = {
    'sales': SalesAnalytics,
    'inventory': InventoryAnalytics,
    'profit': ProfitAnalytics,
    'cashflow': CashFlowAnalytics,
}

def get_analytics(analytics_type):
    """الحصول على نوع تحليل معين"""
    return ANALYTICS_LIBRARY.get(analytics_type)



# ===== Consolidated from: analytics/market_insights.py =====
"""
📈 فهم السوق - Market Insights
"""

MARKET_INSIGHTS = {
    'uae_market': {
        'construction_sector': 'قطاع الإنشاءات نشط جداً - طلب عالي على المعدات الثقيلة',
        'automotive_sector': 'سوق السيارات متنوع - طلب على قطع الغيار الأصلية والتجارية',
        'peak_seasons': [
            'سبتمبر - ديسمبر: موسم المشاريع الكبرى',
            'يناير - مارس: موسم الصيانة',
            'رمضان: تباطؤ نسبي',
            'الصيف (يونيو-أغسطس): طلب على قطع التكييف'
        ]
    },
    'pricing_strategy': {
        'individuals': 'سعر كامل + هامش ربح 20-30%',
        'merchants': 'خصم 10-15% للكميات',
        'partners': 'خصم 20-25% للشراكات طويلة الأمد',
        'vip': 'خصم إضافي 5% + خدمات مميزة'
    },
    'competitors': {
        'strengths': 'استفد من: التكنولوجيا، السرعة، الخدمة',
        'weaknesses': 'تجنب: حرب الأسعار، التأخير، سوء الخدمة'
    },
    'trends': [
        '📈 زيادة الطلب على القطع الكهربائية (السيارات الكهربائية)',
        '🌍 التوجه للقطع الصديقة للبيئة',
        '💻 التحول الرقمي في إدارة المخزون',
        '🚚 التوصيل السريع (24 ساعة) ميزة تنافسية',
        '🔧 خدمات الصيانة الشاملة تزيد الولاء'
    ]
}

def get_market_insights():
    """فهم السوق"""
    pricing = "\n".join(f"• {k}: {v}" for k, v in MARKET_INSIGHTS['pricing_strategy'].items())
    return f"""📈 **فهم السوق الإماراتي:**

🏗️ **القطاعات:**
• الإنشاءات: طلب عالي على المعدات الثقيلة
• السيارات: تنوع كبير - أصلي + تجاري

📅 **المواسم:**
• سبتمبر-ديسمبر: ذروة المشاريع
• يناير-مارس: موسم الصيانة
• الصيف: طلب على قطع التكييف

💰 **استراتيجية التسعير:**
{pricing}"""
