"""
🔗 تكامل النظام - System Integration
أزاد يتفاعل مباشرة مع النظام
"""

from datetime import datetime
from decimal import Decimal


def _active_tid():
    from flask import has_request_context, g

    if has_request_context():
        return getattr(g, "active_tenant_id", None)
    return None


def _maybe_tenant_query(model):
    q = model.query
    tid = _active_tid()
    if tid is not None:
        q = q.filter(model.tenant_id == tid)
    return q


class SystemIntegrator:
    """مكامل النظام لأزاد"""

    def __init__(self):
        pass

    @staticmethod
    def get_customer_balance(customer_name_or_id):
        """الحصول على رصيد العميل"""
        try:
            from models import Customer, Sale

            tid = _active_tid()
            if customer_name_or_id.isdigit():
                customer = Customer.query.get(int(customer_name_or_id))
            else:
                q = Customer.query.filter(
                    Customer.name.ilike(f"%{customer_name_or_id}%")
                )
                if tid is not None:
                    q = q.filter(Customer.tenant_id == tid)
                customer = q.first()
            if customer is not None and tid is not None and customer.tenant_id != tid:
                return {"success": False, "error": "العميل غير موجود في هذا السياق"}

            if not customer:
                return {
                    "success": False,
                    "error": f'العميل "{customer_name_or_id}" غير موجود',
                }

            # حساب الرصيد - استخدام الدالة الصحيحة
            balance_aed = customer.get_balance_aed()  # ✅ تم التحديث 2025-10-19
            total_sales = customer.sales.count()
            last_sale = customer.sales.order_by(Sale.created_at.desc()).first()

            return {
                "success": True,
                "customer": {
                    "id": customer.id,
                    "name": customer.name,
                    "balance_aed": float(balance_aed),
                    "total_sales": total_sales,
                    "last_sale_date": (
                        last_sale.created_at.strftime("%Y-%m-%d") if last_sale else None
                    ),
                    "customer_type": customer.customer_type,
                    "phone": customer.phone,
                    "email": customer.email,
                },
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في جلب بيانات العميل: {str(e)}"}

    @staticmethod
    def get_supplier_balance(supplier_name_or_id):
        """الحصول على رصيد المورد - ✅ جديد 2025-10-19"""
        try:
            from models import Supplier, Purchase

            tid = _active_tid()
            if str(supplier_name_or_id).isdigit():
                supplier = Supplier.query.get(int(supplier_name_or_id))
            else:
                q = Supplier.query.filter(
                    Supplier.name.ilike(f"%{supplier_name_or_id}%")
                )
                if tid is not None:
                    q = q.filter(Supplier.tenant_id == tid)
                supplier = q.first()
            if supplier is not None and tid is not None and supplier.tenant_id != tid:
                return {"success": False, "error": "المورد غير موجود في هذا السياق"}

            if not supplier:
                return {
                    "success": False,
                    "error": f'المورد "{supplier_name_or_id}" غير موجود',
                }

            # حساب الرصيد - استخدام الدالة المحدثة
            balance_aed = supplier.get_balance_aed()  # ✅ الدالة الصحيحة
            total_purchases = supplier.purchases.count()
            last_purchase = supplier.purchases.order_by(
                Purchase.created_at.desc()
            ).first()

            return {
                "success": True,
                "supplier": {
                    "id": supplier.id,
                    "name": supplier.name,
                    "balance_aed": float(balance_aed),
                    "total_purchases": total_purchases,
                    "last_purchase_date": (
                        last_purchase.created_at.strftime("%Y-%m-%d")
                        if last_purchase
                        else None
                    ),
                    "supplier_type": supplier.supplier_type,
                    "phone": supplier.phone,
                    "email": supplier.email,
                },
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في جلب بيانات المورد: {str(e)}"}

    @staticmethod
    def get_customer_sales_summary(customer_id):
        """ملخص مبيعات العميل"""
        try:
            from models import Customer, Sale

            tid = _active_tid()
            customer = Customer.query.get(int(customer_id))
            if customer is not None and tid is not None and customer.tenant_id != tid:
                return {"success": False, "error": "العميل غير موجود في هذا السياق"}

            if not customer:
                return {"success": False, "error": "العميل غير موجود"}

            if tid is not None:
                sales = (
                    Sale.query.filter_by(customer_id=customer.id, tenant_id=tid)
                    .order_by(Sale.created_at.desc())
                    .all()
                )
            else:
                sales = (
                    Sale.query.filter_by(customer_id=customer.id)
                    .order_by(Sale.created_at.desc())
                    .all()
                )
            total_sales = len(sales)
            total_amount = sum(float(sale.total_amount) for sale in sales)
            paid_amount = sum(float(sale.paid_amount) for sale in sales)
            balance_due = total_amount - paid_amount

            recent_sales = sales[:5]

            return {
                "success": True,
                "summary": {
                    "total_sales": total_sales,
                    "total_amount": total_amount,
                    "paid_amount": paid_amount,
                    "balance_due": balance_due,
                    "recent_sales": [
                        {
                            "id": sale.id,
                            "date": sale.created_at.strftime("%Y-%m-%d"),
                            "amount": float(sale.total_amount),
                            "status": (
                                "مدفوع"
                                if sale.paid_amount >= sale.total_amount
                                else "جزئي"
                                if sale.paid_amount > 0
                                else "غير مدفوع"
                            ),
                        }
                        for sale in recent_sales
                    ],
                },
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في جلب ملخص المبيعات: {str(e)}"}

    @staticmethod
    def add_customer(customer_data):
        """إضافة عميل جديد"""
        try:
            from models import Customer
            from extensions import db

            # التحقق من البيانات المطلوبة
            required_fields = ["name", "customer_type"]
            for field in required_fields:
                if field not in customer_data or not customer_data[field]:
                    return {"success": False, "error": f'المجال "{field}" مطلوب'}

            # تحديد التينانت
            from models.tenant import Tenant

            tenant = Tenant.get_current()
            tenant_id = tenant.id if tenant else customer_data.get("tenant_id")
            if not tenant_id:
                return {
                    "success": False,
                    "error": "لا يوجد تينانت نشط — يرجى تسجيل الدخول لشركة محددة",
                }

            # إنشاء العميل
            customer = Customer(
                tenant_id=tenant_id,
                name=customer_data["name"],
                customer_type=customer_data["customer_type"],
                phone=customer_data.get("phone", ""),
                email=customer_data.get("email", ""),
                address=customer_data.get("address", ""),
                credit_limit=customer_data.get("credit_limit", 0),
            )

            db.session.add(customer)
            db.session.flush()

            return {
                "success": True,
                "customer": {
                    "id": customer.id,
                    "name": customer.name,
                    "customer_type": customer.customer_type,
                    "phone": customer.phone,
                    "email": customer.email,
                },
                "message": f'تم إضافة العميل "{customer.name}" بنجاح',
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في إضافة العميل: {str(e)}"}

    @staticmethod
    def get_product_stock(product_name_or_sku):
        """الحصول على مخزون المنتج"""
        try:
            from models import Product

            tid = _active_tid()
            q = Product.query.filter(
                (Product.name.ilike(f"%{product_name_or_sku}%"))
                | (Product.sku.ilike(f"%{product_name_or_sku}%"))
            )
            if tid is not None:
                q = q.filter(Product.tenant_id == tid)
            product = q.first()
            if product is not None and tid is not None and product.tenant_id != tid:
                return {"success": False, "error": "المنتج غير موجود في هذا السياق"}

            if not product:
                return {
                    "success": False,
                    "error": f'المنتج "{product_name_or_sku}" غير موجود',
                }

            return {
                "success": True,
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "sku": product.sku,
                    "current_stock": product.current_stock,
                    "alert_limit": product.min_stock_alert,
                    "unit_price": float(product.unit_price),
                    "category": (
                        product.category.name if product.category else "غير محدد"
                    ),
                    "status": (
                        "منخفض"
                        if product.current_stock <= product.min_stock_alert
                        else "جيد"
                    ),
                },
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في جلب بيانات المنتج: {str(e)}"}

    @staticmethod
    def get_system_summary():
        """ملخص النظام الشامل"""
        try:
            from models import Customer, Sale, Product, Payment

            base_c = _maybe_tenant_query(Customer)
            base_s = _maybe_tenant_query(Sale)
            base_pr = _maybe_tenant_query(Product)
            base_pm = _maybe_tenant_query(Payment)

            total_customers = base_c.count()
            vip_customers = base_c.filter(Customer.customer_type == "VIP").count()

            total_sales = base_s.count()
            today_sales = base_s.filter(
                Sale.created_at >= datetime.now().date()
            ).count()

            total_products = base_pr.count()
            low_stock_products = base_pr.filter(
                Product.current_stock <= Product.min_stock_alert
            ).count()
            out_of_stock_products = base_pr.filter(Product.current_stock == 0).count()

            total_payments = base_pm.count()
            today_payments = base_pm.filter(
                Payment.created_at >= datetime.now().date()
            ).count()

            recent_sales = base_s.order_by(Sale.created_at.desc()).limit(5).all()
            recent_customers = (
                base_c.order_by(Customer.created_at.desc()).limit(5).all()
            )

            return {
                "success": True,
                "summary": {
                    "customers": {
                        "total": total_customers,
                        "vip": vip_customers,
                        "recent": [
                            {
                                "id": c.id,
                                "name": c.name,
                                "type": c.customer_type,
                                "balance": float(c.get_balance_aed()),
                            }
                            for c in recent_customers
                        ],
                    },
                    "sales": {
                        "total": total_sales,
                        "today": today_sales,
                        "recent": [
                            {
                                "id": s.id,
                                "customer": (
                                    s.customer.name if s.customer else "غير محدد"
                                ),
                                "amount": float(s.total_amount),
                                "date": s.created_at.strftime("%Y-%m-%d %H:%M"),
                            }
                            for s in recent_sales
                        ],
                    },
                    "products": {
                        "total": total_products,
                        "low_stock": low_stock_products,
                        "out_of_stock": out_of_stock_products,
                    },
                    "payments": {"total": total_payments, "today": today_payments},
                },
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في جلب ملخص النظام: {str(e)}"}

    @staticmethod
    def get_financial_summary():
        """ملخص مالي شامل"""
        try:
            from models import Sale, Payment
            from extensions import db

            tid = _active_tid()
            base_sale_q = db.session.query(db.func.sum(Sale.total_amount))
            base_pay_q = db.session.query(db.func.sum(Payment.amount))
            if tid is not None:
                base_sale_q = base_sale_q.filter(Sale.tenant_id == tid)
                base_pay_q = base_pay_q.filter(Payment.tenant_id == tid)

            total_sales_amount = base_sale_q.scalar() or Decimal("0")
            total_payments_amount = base_pay_q.scalar() or Decimal("0")
            total_receivables = total_sales_amount - total_payments_amount

            today_sales = base_sale_q.filter(
                Sale.created_at >= datetime.now().date()
            ).scalar() or Decimal("0")

            today_payments = base_pay_q.filter(
                Payment.created_at >= datetime.now().date()
            ).scalar() or Decimal("0")

            month_start = datetime.now().replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            monthly_sales = base_sale_q.filter(
                Sale.created_at >= month_start
            ).scalar() or Decimal("0")

            return {
                "success": True,
                "financial": {
                    "total_sales": float(total_sales_amount),
                    "total_payments": float(total_payments_amount),
                    "total_receivables": float(total_receivables),
                    "today_sales": float(today_sales),
                    "today_payments": float(today_payments),
                    "monthly_sales": float(monthly_sales),
                    "currency": "AED",
                },
            }

        except Exception as e:
            return {"success": False, "error": f"خطأ في جلب الملخص المالي: {str(e)}"}

    @staticmethod
    def search_data(query, data_type="all"):
        """البحث في البيانات"""
        try:
            from models import Customer, Product, Sale

            results = {"customers": [], "products": [], "sales": []}
            base_c = _maybe_tenant_query(Customer)
            base_pr = _maybe_tenant_query(Product)

            if data_type in ["all", "customers"]:
                customers = (
                    base_c.filter(Customer.name.ilike(f"%{query}%")).limit(10).all()
                )

                results["customers"] = [
                    {
                        "id": c.id,
                        "name": c.name,
                        "type": c.customer_type,
                        "phone": c.phone,
                        "balance": float(c.get_balance_aed()),
                    }
                    for c in customers
                ]

            if data_type in ["all", "products"]:
                products = (
                    base_pr.filter(
                        (Product.name.ilike(f"%{query}%"))
                        | (Product.sku.ilike(f"%{query}%"))
                    )
                    .limit(10)
                    .all()
                )

                results["products"] = [
                    {
                        "id": p.id,
                        "name": p.name,
                        "sku": p.sku,
                        "stock": p.current_stock,
                        "price": float(p.unit_price),
                    }
                    for p in products
                ]

            if data_type in ["all", "sales"]:
                tid = _active_tid()
                base_s_q = Sale.query.join(Customer)
                if tid is not None:
                    base_s_q = base_s_q.filter(Sale.tenant_id == tid)
                sales = (
                    base_s_q.filter(Customer.name.ilike(f"%{query}%")).limit(10).all()
                )

                results["sales"] = [
                    {
                        "id": s.id,
                        "customer": s.customer.name if s.customer else "غير محدد",
                        "amount": float(s.total_amount),
                        "date": s.created_at.strftime("%Y-%m-%d"),
                    }
                    for s in sales
                ]

            return {"success": True, "query": query, "results": results}

        except Exception as e:
            return {"success": False, "error": f"خطأ في البحث: {str(e)}"}


# إنشاء مثيل عالمي
system_integrator = SystemIntegrator()
