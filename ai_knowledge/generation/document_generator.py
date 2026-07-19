"""
📄 مولد المستندات - Document Generator
أزاد يولد الفواتير والسندات والتقارير
"""

import io
import csv
from datetime import datetime
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
            ║ التاريخ: {sale.created_at.strftime("%Y-%m-%d %H:%M")}              ║
            ║                                                            ║
            ║ العميل: {sale.customer.name if sale.customer else "غير محدد"}                      ║
            ║ الهاتف: {sale.customer.phone if sale.customer else "غير محدد"}                      ║
            ║                                                            ║
            ║ المبلغ المستلم: {sale.paid_amount:,.2f} AED                     ║
            ║ المبلغ المتبقي: {sale.balance_due:,.2f} AED                    ║
            ║                                                            ║
            ║ طريقة الدفع: {sale.payments[0].payment_method if sale.payments else "غير محدد"}           ║
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
            ║ التاريخ: {sale.created_at.strftime("%Y-%m-%d %H:%M")}              ║
            ║                                                            ║
            ║ العميل: {sale.customer.name if sale.customer else "غير محدد"}                      ║
            ║ الهاتف: {sale.customer.phone if sale.customer else "غير محدد"}                      ║
            ║ العنوان: {sale.customer.address if sale.customer else "غير محدد"}                   ║
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
            ║ الفترة: {start_date.strftime("%Y-%m-%d") if start_date else "من البداية"} - {end_date.strftime("%Y-%m-%d") if end_date else "اليوم"}    ║
            ║ تاريخ التقرير: {datetime.now().strftime("%Y-%m-%d %H:%M")}           ║
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
            ║ #{sale.id:06d} | {sale.customer.name[:20]:20} | {sale.total_amount:8.2f} AED | {sale.created_at.strftime("%Y-%m-%d")} ║"""

            report_content += """
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
            if data_type == "sales":
                sales = Sale.query.all()
                if start_date:
                    sales = [s for s in sales if s.created_at.date() >= start_date]
                if end_date:
                    sales = [s for s in sales if s.created_at.date() <= end_date]

                data = []
                headers = [
                    "رقم الفاتورة",
                    "العميل",
                    "التاريخ",
                    "المجموع",
                    "المدفوع",
                    "المتبقي",
                    "الحالة",
                ]
                for sale in sales:
                    data.append(
                        [
                            sale.id,
                            sale.customer.name if sale.customer else "غير محدد",
                            sale.created_at.strftime("%Y-%m-%d"),
                            float(sale.total_amount),
                            float(sale.paid_amount),
                            float(sale.balance_due),
                            (
                                "مدفوع"
                                if sale.balance_due == 0
                                else "جزئي"
                                if sale.paid_amount > 0
                                else "غير مدفوع"
                            ),
                        ]
                    )

                filename = (
                    f"sales_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                )

            elif data_type == "customers":
                customers = Customer.query.all()
                headers = [
                    "المعرف",
                    "الاسم",
                    "النوع",
                    "الهاتف",
                    "الإيميل",
                    "الرصيد",
                    "تاريخ الإضافة",
                ]
                data = []
                for customer in customers:
                    data.append(
                        [
                            customer.id,
                            customer.name,
                            customer.customer_type,
                            customer.phone or "",
                            customer.email or "",
                            float(customer.get_balance_aed()),
                            customer.created_at.strftime("%Y-%m-%d"),
                        ]
                    )

                filename = (
                    f"customers_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                )

            elif data_type == "products":
                products = Product.query.all()
                headers = [
                    "المعرف",
                    "الاسم",
                    "SKU",
                    "المخزون",
                    "السعر",
                    "الفئة",
                    "حد التنبيه",
                ]
                data = []
                for product in products:
                    data.append(
                        [
                            product.id,
                            product.name,
                            product.sku,
                            product.current_stock,
                            float(product.unit_price),
                            product.category.name if product.category else "غير محدد",
                            product.min_stock_alert,
                        ]
                    )

                filename = (
                    f"products_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                )

            else:
                return None, "نوع البيانات غير صحيح"

            # إنشاء CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(data)

            # تحويل إلى BytesIO
            output_bytes = io.BytesIO()
            output_bytes.write(
                output.getvalue().encode("utf-8-sig")
            )  # UTF-8 with BOM for Excel
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
            ║ الهاتف: {customer.phone or "غير محدد"}                      ║
            ║ الإيميل: {customer.email or "غير محدد"}                     ║
            ║ الفترة: {start_date.strftime("%Y-%m-%d") if start_date else "من البداية"} - {end_date.strftime("%Y-%m-%d") if end_date else "اليوم"}    ║
            ║                                                            ║
            ╠══════════════════════════════════════════════════════════════╣
            ║                        حركات الحساب                           ║
            ╠══════════════════════════════════════════════════════════════╣
            """

            balance = Decimal("0")
            for sale in sales:
                balance += sale.total_amount
                statement_content += f"""
            ║ {sale.created_at.strftime("%Y-%m-%d")} | فاتورة #{sale.id} | {sale.total_amount:8.2f} AED | الرصيد: {balance:8.2f} AED ║"""

                # المدفوعات
                for payment in sale.payments:
                    balance -= payment.amount
                    statement_content += f"""
            ║ {payment.created_at.strftime("%Y-%m-%d")} | دفعة #{payment.id} | -{payment.amount:8.2f} AED | الرصيد: {balance:8.2f} AED ║"""

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
