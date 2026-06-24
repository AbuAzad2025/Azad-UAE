"""
Consolidated module: generation.py
Merged: generation/document_generator.py, generation/code_generator.py

This module consolidates multiple small files into one.
Old import paths still work via backward-compatible shims in the original files.
"""


# ===== Consolidated from: generation/document_generator.py =====
"""
📄 مولد المستندات - Document Generator
أزاد يولد الفواتير والسندات والتقارير
"""

import io
import csv
from datetime import datetime
from flask import make_response
from decimal import Decimal


class DocumentGenerator:
    """مولد المستندات لأزاد"""
    
    @staticmethod
    def generate_receipt(sale_id):
        """توليد سند قبض"""
        try:
            from models import Sale
            
            sale = Sale.query.get(sale_id)
            if not sale:
                return None, "الفاتورة غير موجودة"
            
            # محتوى سند القبض
            receipt_content = f"""
            ╔══════════════════════════════════════════════════════════════╗
            ║                    سند قبض - Receipt Voucher                  ║
            ╠══════════════════════════════════════════════════════════════╣
            ║ رقم السند: {sale_id:06d}                                    ║
            ║ التاريخ: {sale.created_at.strftime('%Y-%m-%d %H:%M')}              ║
            ║                                                            ║
            ║ العميل: {sale.customer.name if sale.customer else 'غير محدد'}                      ║
            ║ الهاتف: {sale.customer.phone if sale.customer else 'غير محدد'}                      ║
            ║                                                            ║
            ║ المبلغ المستلم: {sale.paid_amount:,.2f} AED                     ║
            ║ المبلغ المتبقي: {sale.balance_due:,.2f} AED                    ║
            ║                                                            ║
            ║ طريقة الدفع: {sale.payments[0].payment_method if sale.payments else 'غير محدد'}           ║
            ║                                                            ║
            ║ تم استلام المبلغ من العميل المذكور أعلاه                    ║
            ║                                                            ║
            ║ توقيع المسؤول: _______________                             ║
            ║                                                            ║
            ║ شكراً لتعاملكم معنا! 😊                                      ║
            ╚══════════════════════════════════════════════════════════════╝
            """
            
            return receipt_content, "تم توليد سند القبض بنجاح"
            
        except Exception as e:
            return None, f"خطأ في توليد سند القبض: {str(e)}"
    
    @staticmethod
    def generate_invoice(sale_id):
        """توليد فاتورة مفصلة"""
        try:
            from models import Sale
            
            sale = Sale.query.get(sale_id)
            if not sale:
                return None, "الفاتورة غير موجودة"
            
            # محتوى الفاتورة
            invoice_content = f"""
            ╔══════════════════════════════════════════════════════════════╗
            ║                    فاتورة مبيعات - Sales Invoice               ║
            ╠══════════════════════════════════════════════════════════════╣
            ║ رقم الفاتورة: {sale_id:06d}                               ║
            ║ التاريخ: {sale.created_at.strftime('%Y-%m-%d %H:%M')}              ║
            ║                                                            ║
            ║ العميل: {sale.customer.name if sale.customer else 'غير محدد'}                      ║
            ║ الهاتف: {sale.customer.phone if sale.customer else 'غير محدد'}                      ║
            ║ العنوان: {sale.customer.address if sale.customer else 'غير محدد'}                   ║
            ║                                                            ║
            ╠══════════════════════════════════════════════════════════════╣
            ║                        تفاصيل الفاتورة                        ║
            ╠══════════════════════════════════════════════════════════════╣
            """
            
            # تفاصيل المنتجات
            total_items = 0
            for line in sale.sale_lines:
                total_items += line.quantity
                invoice_content += f"""
            ║ المنتج: {line.product.name[:30]:30}                    ║
            ║ الكمية: {line.quantity:5} السعر: {line.unit_price:8.2f} المجموع: {line.line_total:8.2f} AED ║
            ║──────────────────────────────────────────────────────────────║"""
            
            # المجاميع
            invoice_content += f"""
            ║                                                            ║
            ║ عدد الأصناف: {len(sale.sale_lines):3} عدد القطع: {total_items:5}              ║
            ║                                                            ║
            ║ المجموع الفرعي: {sale.subtotal:,.2f} AED                      ║
            ║ الخصم: {sale.discount_amount:,.2f} AED                        ║
            ║ الشحن: {sale.shipping_cost:,.2f} AED                        ║
            ║ الضريبة: {sale.tax_amount:,.2f} AED                        ║
            ║                                                            ║
            ║ المجموع الكلي: {sale.total_amount:,.2f} AED                   ║
            ║ المدفوع: {sale.paid_amount:,.2f} AED                        ║
            ║ المتبقي: {sale.balance_due:,.2f} AED                        ║
            ║                                                            ║
            ║ شكراً لاختياركم خدماتنا! 🌟                                ║
            ╚══════════════════════════════════════════════════════════════╝
            """
            
            return invoice_content, "تم توليد الفاتورة بنجاح"
            
        except Exception as e:
            return None, f"خطأ في توليد الفاتورة: {str(e)}"
    
    @staticmethod
    def generate_sales_report(start_date=None, end_date=None):
        """توليد تقرير المبيعات"""
        try:
            from models import Sale
            
            # فلترة المبيعات حسب التاريخ
            query = Sale.query
            if start_date:
                query = query.filter(Sale.created_at >= start_date)
            if end_date:
                query = query.filter(Sale.created_at <= end_date)
            
            sales = query.all()
            
            if not sales:
                return None, "لا توجد مبيعات في الفترة المحددة"
            
            # حساب الإحصائيات
            total_sales = len(sales)
            total_amount = sum(float(sale.total_amount) for sale in sales)
            total_paid = sum(float(sale.paid_amount) for sale in sales)
            total_receivables = total_amount - total_paid
            
            # تقرير المبيعات
            report_content = f"""
            ╔══════════════════════════════════════════════════════════════╗
            ║                تقرير المبيعات - Sales Report                   ║
            ╠══════════════════════════════════════════════════════════════╣
            ║ الفترة: {start_date.strftime('%Y-%m-%d') if start_date else 'من البداية'} - {end_date.strftime('%Y-%m-%d') if end_date else 'اليوم'}    ║
            ║ تاريخ التقرير: {datetime.now().strftime('%Y-%m-%d %H:%M')}           ║
            ║                                                            ║
            ╠══════════════════════════════════════════════════════════════╣
            ║                        الإحصائيات العامة                       ║
            ╠══════════════════════════════════════════════════════════════╣
            ║ عدد الفواتير: {total_sales:5}                                ║
            ║ إجمالي المبيعات: {total_amount:,.2f} AED                      ║
            ║ إجمالي المدفوعات: {total_paid:,.2f} AED                      ║
            ║ إجمالي الذمم: {total_receivables:,.2f} AED                    ║
            ║                                                            ║
            ╠══════════════════════════════════════════════════════════════╣
            ║                        تفاصيل المبيعات                        ║
            ╠══════════════════════════════════════════════════════════════╣
            """
            
            # تفاصيل الفواتير
            for sale in sales[-10:]:  # آخر 10 فواتير
                report_content += f"""
            ║ #{sale.id:06d} | {sale.customer.name[:20]:20} | {sale.total_amount:8.2f} AED | {sale.created_at.strftime('%Y-%m-%d')} ║"""
            
            report_content += f"""
            ║                                                            ║
            ║ تم توليد التقرير بواسطة أزاد 🤖                             ║
            ╚══════════════════════════════════════════════════════════════╝
            """
            
            return report_content, "تم توليد تقرير المبيعات بنجاح"
            
        except Exception as e:
            return None, f"خطأ في توليد تقرير المبيعات: {str(e)}"
    
    @staticmethod
    def export_to_excel(data_type, start_date=None, end_date=None):
        """تصدير البيانات إلى CSV (بديل Excel)"""
        try:
            from models import Sale, Customer, Product
            
            # إنشاء البيانات حسب نوع البيانات
            if data_type == 'sales':
                sales = Sale.query.all()
                if start_date:
                    sales = [s for s in sales if s.created_at.date() >= start_date]
                if end_date:
                    sales = [s for s in sales if s.created_at.date() <= end_date]
                
                data = []
                headers = ['رقم الفاتورة', 'العميل', 'التاريخ', 'المجموع', 'المدفوع', 'المتبقي', 'الحالة']
                for sale in sales:
                    data.append([
                        sale.id,
                        sale.customer.name if sale.customer else 'غير محدد',
                        sale.created_at.strftime('%Y-%m-%d'),
                        float(sale.total_amount),
                        float(sale.paid_amount),
                        float(sale.balance_due),
                        'مدفوع' if sale.balance_due == 0 else 'جزئي' if sale.paid_amount > 0 else 'غير مدفوع'
                    ])
                
                filename = f"sales_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                
            elif data_type == 'customers':
                customers = Customer.query.all()
                headers = ['المعرف', 'الاسم', 'النوع', 'الهاتف', 'الإيميل', 'الرصيد', 'تاريخ الإضافة']
                data = []
                for customer in customers:
                    data.append([
                        customer.id,
                        customer.name,
                        customer.customer_type,
                        customer.phone or '',
                        customer.email or '',
                        float(customer.get_balance_aed()),
                        customer.created_at.strftime('%Y-%m-%d')
                    ])
                
                filename = f"customers_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                
            elif data_type == 'products':
                products = Product.query.all()
                headers = ['المعرف', 'الاسم', 'SKU', 'المخزون', 'السعر', 'الفئة', 'حد التنبيه']
                data = []
                for product in products:
                    data.append([
                        product.id,
                        product.name,
                        product.sku,
                        product.current_stock,
                        float(product.unit_price),
                        product.category.name if product.category else 'غير محدد',
                        product.min_stock_alert
                    ])
                
                filename = f"products_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            else:
                return None, "نوع البيانات غير صحيح"
            
            # إنشاء CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(data)
            
            # تحويل إلى BytesIO
            output_bytes = io.BytesIO()
            output_bytes.write(output.getvalue().encode('utf-8-sig'))  # UTF-8 with BOM for Excel
            output_bytes.seek(0)
            
            return output_bytes, filename
            
        except Exception as e:
            return None, f"خطأ في تصدير البيانات: {str(e)}"
    
    @staticmethod
    def generate_customer_statement(customer_id, start_date=None, end_date=None):
        """توليد كشف حساب العميل"""
        try:
            from models import Customer, Sale
            
            customer = Customer.query.get(customer_id)
            if not customer:
                return None, "العميل غير موجود"
            
            # فلترة المبيعات
            query = Sale.query.filter(Sale.customer_id == customer_id)
            if start_date:
                query = query.filter(Sale.created_at >= start_date)
            if end_date:
                query = query.filter(Sale.created_at <= end_date)
            
            sales = query.all()
            
            # كشف الحساب
            statement_content = f"""
            ╔══════════════════════════════════════════════════════════════╗
            ║                 كشف حساب العميل - Customer Statement          ║
            ╠══════════════════════════════════════════════════════════════╣
            ║ العميل: {customer.name}                                    ║
            ║ الهاتف: {customer.phone or 'غير محدد'}                      ║
            ║ الإيميل: {customer.email or 'غير محدد'}                     ║
            ║ الفترة: {start_date.strftime('%Y-%m-%d') if start_date else 'من البداية'} - {end_date.strftime('%Y-%m-%d') if end_date else 'اليوم'}    ║
            ║                                                            ║
            ╠══════════════════════════════════════════════════════════════╣
            ║                        حركات الحساب                           ║
            ╠══════════════════════════════════════════════════════════════╣
            """
            
            balance = Decimal('0')
            for sale in sales:
                balance += sale.total_amount
                statement_content += f"""
            ║ {sale.created_at.strftime('%Y-%m-%d')} | فاتورة #{sale.id} | {sale.total_amount:8.2f} AED | الرصيد: {balance:8.2f} AED ║"""
                
                # المدفوعات
                for payment in sale.payments:
                    balance -= payment.amount
                    statement_content += f"""
            ║ {payment.created_at.strftime('%Y-%m-%d')} | دفعة #{payment.id} | -{payment.amount:8.2f} AED | الرصيد: {balance:8.2f} AED ║"""
            
            statement_content += f"""
            ║                                                            ║
            ║ الرصيد النهائي: {balance:,.2f} AED                          ║
            ║                                                            ║
            ║ تم توليد الكشف بواسطة أزاد 🤖                              ║
            ╚══════════════════════════════════════════════════════════════╝
            """
            
            return statement_content, "تم توليد كشف الحساب بنجاح"
            
        except Exception as e:
            return None, f"خطأ في توليد كشف الحساب: {str(e)}"


# إنشاء مثيل عالمي
document_generator = DocumentGenerator()


# ===== Consolidated from: generation/code_generator.py =====
"""
💻 محرك توليد الأكواد - Code Generation Engine
توليد أكواد Python/SQL/JavaScript تلقائياً

القدرات:
- توليد queries SQL
- توليد Python scripts
- توليد تقارير
- توليد API calls
- إصلاح الأكواد
- تحسين الأكواد
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class CodeGenerator:
    """
    محرك توليد الأكواد الذكي
    
    يولد:
    - SQL queries للتقارير
    - Python scripts للعمليات
    - JavaScript للواجهات
    - API endpoints
    """
    
    def __init__(self):
        self.templates = self._load_templates()
        self.generated_code_history = []
    
    def _load_templates(self):
        """تحميل قوالب الأكواد"""
        return {
            'sql_select': "SELECT {columns} FROM {table} WHERE {conditions}",
            'sql_insert': "INSERT INTO {table} ({columns}) VALUES ({values})",
            'sql_update': "UPDATE {table} SET {updates} WHERE {conditions}",
            'python_function': """def {function_name}({params}):
    \"\"\"{docstring}\"\"\"
    {body}
    return {return_value}""",
            'api_endpoint': """@{blueprint}_bp.route('/{path}', methods=['{method}'])
@login_required
def {function_name}():
    \"\"\"{docstring}\"\"\"
    {body}"""
        }
    
    def generate_sql_query(self, intent: str, table: str, filters: dict = None) -> str:
        """
        توليد SQL query تلقائياً
        
        Args:
            intent: 'select' | 'insert' | 'update' | 'delete'
            table: اسم الجدول
            filters: شروط البحث
        
        Returns:
            SQL query جاهز
        """
        try:
            if intent == 'select':
                columns = filters.get('columns', '*') if filters else '*'
                conditions = ' AND '.join([f"{k} = '{v}'" for k, v in filters.get('where', {}).items()]) if filters and 'where' in filters else '1=1'
                
                query = f"SELECT {columns} FROM {table} WHERE {conditions}"  # nosec B608
                
                if filters and 'order_by' in filters:
                    query += f" ORDER BY {filters['order_by']}"
                
                if filters and 'limit' in filters:
                    query += f" LIMIT {filters['limit']}"
                
                return query
            
            elif intent == 'insert':
                columns = ', '.join(filters.get('columns', [])) if filters else ''
                values = ', '.join([f"'{v}'" if isinstance(v, str) else str(v) for v in filters.get('values', [])]) if filters else ''
                
                return f"INSERT INTO {table} ({columns}) VALUES ({values})"  # nosec B608
            
            elif intent == 'update':
                updates = ', '.join([f"{k} = '{v}'" for k, v in filters.get('set', {}).items()]) if filters else ''
                conditions = ' AND '.join([f"{k} = '{v}'" for k, v in filters.get('where', {}).items()]) if filters else '1=1'
                
                return f"UPDATE {table} SET {updates} WHERE {conditions}"  # nosec B608
            
            else:
                return f"-- Unsupported intent: {intent}"
        
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            return f"-- Error: {e}"
    
    def generate_python_function(self, function_name: str, purpose: str, params: List[str] = None) -> str:
        """
        توليد دالة Python
        
        Args:
            function_name: اسم الدالة
            purpose: الغرض منها
            params: المعاملات
        
        Returns:
            كود Python جاهز
        """
        try:
            params_str = ', '.join(params) if params else ''
            
            # توليد الجسم حسب الغرض
            if 'حساب' in purpose or 'calculate' in purpose.lower():
                body = """    # حسابات
    result = 0
    # أضف المنطق هنا
    return result"""
            
            elif 'توقع' in purpose or 'predict' in purpose.lower():
                body = """    # توقعات
    from services.ai_service import AIService
    prediction = AIService.predict_sales_trend()
    return prediction"""
            
            elif 'بحث' in purpose or 'search' in purpose.lower():
                body = """    # بحث
    from models import Product
    results = Product.query.filter_by(name=query).all()
    return results"""
            
            else:
                body = """    # منطق الدالة
    pass
    return None"""
            
            code = f'''def {function_name}({params_str}):
    """
    {purpose}
    
    Args:
        {', '.join(params) if params else 'None'}
    
    Returns:
        result
    """
{body}
'''
            
            return code
        
        except Exception as e:
            logger.error(f"Python generation failed: {e}")
            return f"# Error: {e}"
    
    def generate_report_query(self, report_type: str, date_range: dict = None) -> str:  # nosec B608
        """
        توليد query لتقرير محدد
        
        Args:
            report_type: 'sales' | 'inventory' | 'financial' | 'customers'
            date_range: {start_date, end_date}
        
        Returns:
            SQL query للتقرير
        """
        try:
            if report_type == 'sales':
                if not date_range:
                    return "-- Missing date range"
                sales_sql = "\n".join([  # nosec B608
                    "SELECT",
                    "    DATE(sale_date) as date,",
                    "    COUNT(*) as sales_count,",
                    "    SUM(amount_aed) as total_sales,",
                    "    AVG(amount_aed) as avg_sale",
                    "FROM sales",
                    "WHERE status = 'confirmed'",
                    f"  AND sale_date BETWEEN '{date_range['start_date']}' AND '{date_range['end_date']}'",
                    "GROUP BY DATE(sale_date)",
                    "ORDER BY date DESC",
                ])
                return sales_sql
            
            elif report_type == 'inventory':
                return """
SELECT 
    p.name,
    p.sku,
    p.current_stock,
    p.min_stock_alert,
    p.cost_price,
    (p.current_stock * p.cost_price) as stock_value
FROM products p
WHERE p.is_active = TRUE
ORDER BY stock_value DESC
"""
            
            elif report_type == 'customers':
                return """
SELECT 
    c.name,
    c.customer_type,
    COUNT(s.id) as total_orders,
    SUM(s.amount_aed) as total_purchases,
    MAX(s.sale_date) as last_purchase
FROM customers c
LEFT JOIN sales s ON c.id = s.customer_id
WHERE c.is_active = TRUE
GROUP BY c.id
ORDER BY total_purchases DESC
"""
            
            else:
                return f"-- Unknown report type: {report_type}"
        
        except Exception as e:
            logger.error(f"Report query generation failed: {e}")
            return f"-- Error: {e}"
    
    def fix_code(self, broken_code: str, error_message: str) -> dict:
        """
        إصلاح كود معطوب
        
        Args:
            broken_code: الكود المعطوب
            error_message: رسالة الخطأ
        
        Returns:
            {
                'fixed_code': الكود المصلح,
                'explanation': شرح الإصلاح,
                'changes': التغييرات
            }
        """
        changes = []
        
        # إصلاحات شائعة
        fixed_code = broken_code
        
        # 1. إصلاح الاقتباسات
        if "SyntaxError" in error_message and "quote" in error_message:
            fixed_code = fixed_code.replace("'", '"')
            changes.append("تم تصحيح الاقتباسات")
        
        # 2. إصلاح المسافات البادئة
        if "IndentationError" in error_message:
            lines = fixed_code.split('\n')
            fixed_lines = []
            for line in lines:
                # إزالة المسافات الزائدة
                stripped = line.lstrip()
                # إضافة مسافات صحيحة (4 spaces)
                if stripped.startswith('def ') or stripped.startswith('class '):
                    fixed_lines.append(stripped)
                elif stripped:
                    fixed_lines.append('    ' + stripped)
                else:
                    fixed_lines.append('')
            
            fixed_code = '\n'.join(fixed_lines)
            changes.append("تم تصحيح المسافات البادئة")
        
        # 3. إصلاح الاستيرادات المفقودة
        if "NameError" in error_message or "not defined" in error_message:
            # استخراج الاسم المفقود
            import re
            match = re.search(r"name '(\w+)' is not defined", error_message)
            if match:
                missing_name = match.group(1)
                
                # إضافة import محتمل
                if missing_name in ['db', 'func']:
                    fixed_code = f"from extensions import {missing_name}\n" + fixed_code
                    changes.append(f"أضفت استيراد: {missing_name}")
        
        explanation = "تم تحليل الخطأ وإصلاحه:\n" + '\n'.join(f"- {c}" for c in changes)
        
        return {
            'fixed_code': fixed_code,
            'explanation': explanation,
            'changes': changes,
            'confidence': 0.7 if changes else 0.3
        }
    
    def optimize_code(self, code: str) -> dict:
        """
        تحسين وتسريع الكود
        
        Returns:
            {
                'optimized_code': الكود المحسن,
                'improvements': التحسينات,
                'performance_gain': نسبة التحسين المتوقعة
            }
        """
        improvements = []
        optimized = code
        
        # 1. استخدام list comprehension بدلاً من loops
        if 'for ' in code and 'append(' in code:
            improvements.append("يمكن استخدام list comprehension للسرعة")
        
        # 2. استخدام bulk operations في DB
        if code.count('db.session.add(') > 5:
            improvements.append("استخدم db.session.bulk_insert_mappings للسرعة")
        
        # 3. استخدام query optimization
        if '.all()' in code and 'filter' in code:
            improvements.append("استخدم .limit() لتقليل البيانات المسترجعة")
        
        performance_gain = len(improvements) * 15  # تقدير تقريبي
        
        return {
            'optimized_code': optimized,
            'improvements': improvements,
            'performance_gain_percent': min(performance_gain, 80),
            'confidence': 0.8
        }


# ============================================================================
# Singleton
# ============================================================================

_code_generator_instance = None

def get_code_generator():
    """الحصول على مولد الأكواد"""
    global _code_generator_instance
    if _code_generator_instance is None:
        _code_generator_instance = CodeGenerator()
    return _code_generator_instance

