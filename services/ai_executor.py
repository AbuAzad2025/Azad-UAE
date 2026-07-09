"""
AI Executor — real CRUD operations using the proper ERP service layer.
Called by AIService._execute_ai_action (Groq path) and by enhanced ActionDispatcher handlers.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from flask import current_app
from flask_login import current_user as flask_user
from extensions import db
from utils.db_safety import atomic_transaction
from utils.tenanting import get_active_tenant_id

logger = logging.getLogger(__name__)


class AIExecutorError(Exception):
    """Raised when an AI executor operation fails."""


class AIExecutor:
    """
    Executes real system operations on behalf of the AI assistant.
    Uses the proper service layer (SaleService, PurchaseService, etc.)
    for complex operations and ORM directly for simple CRUD.
    """

    def __init__(self, user=None):
        try:
            self.user = user or (flask_user if flask_user and flask_user.is_authenticated else None)
        except RuntimeError:
            self.user = user
        self.tenant_id = get_active_tenant_id(self.user)

    # ── helpers ────────────────────────────────────────────────

    def _require_tenant(self):
        if not self.tenant_id:
            raise AIExecutorError("لا يوجد تينانت نشط — يرجى تسجيل الدخول لشركة محددة")

    def _current_user_id(self):
        return getattr(self.user, "id", None)

    def _current_branch_id(self):
        return getattr(self.user, "branch_id", None)

    # ── CUSTOMER ───────────────────────────────────────────────

    def create_customer(self, name: str, phone: str = "",
                        email: str = "", address: str = "",
                        customer_type: str = "regular",
                        credit_limit: float = 0) -> dict:
        self._require_tenant()
        from models import Customer

        if not name:
            raise AIExecutorError("اسم العميل مطلوب")

        customer = Customer(
            tenant_id=self.tenant_id,
            name=name,
            phone=phone,
            email=email,
            address=address,
            customer_type=customer_type,
            credit_limit=Decimal(str(credit_limit)),
        )
        db.session.add(customer)
        db.session.flush()

        return {
            "success": True,
            "id": customer.id,
            "message": f'تم إنشاء العميل "{name}" بنجاح',
            "customer": customer.to_dict() if hasattr(customer, "to_dict") else {"id": customer.id, "name": name},
        }

    def list_customers(self, search: str = "", limit: int = 20) -> dict:
        self._require_tenant()
        from models import Customer

        q = Customer.query.filter_by(tenant_id=self.tenant_id, is_active=True)
        if search:
            q = q.filter(Customer.name.ilike(f"%{search}%"))
        customers = q.order_by(Customer.name).limit(limit).all()

        return {
            "success": True,
            "customers": [{"id": c.id, "name": c.name, "phone": c.phone,
                           "balance": float(c.balance or 0)} for c in customers],
            "count": len(customers),
        }

    def get_customer_balance(self, name: str) -> dict:
        self._require_tenant()
        from models import Customer

        c = Customer.query.filter_by(tenant_id=self.tenant_id, name=name, is_active=True).first()
        if not c:
            raise AIExecutorError(f'العميل "{name}" غير موجود')

        return {
            "success": True,
            "id": c.id,
            "name": c.name,
            "balance": float(c.balance or 0),
            "credit_limit": float(c.credit_limit or 0),
        }

    # ── PRODUCT ────────────────────────────────────────────────

    def create_product(self, name: str, sku: str = "",
                       regular_price: float = 0, cost_price: float = 0,
                       current_stock: float = 0, min_stock_alert: float = 0,
                       unit: str = "piece", category_id: int = None,
                       barcode: str = "") -> dict:
        self._require_tenant()
        from models import Product

        if not name:
            raise AIExecutorError("اسم المنتج مطلوب")
        if regular_price <= 0:
            raise AIExecutorError("سعر البيع يجب أن يكون أكبر من صفر")

        product = Product(
            tenant_id=self.tenant_id,
            name=name,
            sku=sku,
            barcode=barcode,
            regular_price=Decimal(str(regular_price)),
            cost_price=Decimal(str(cost_price)),
            current_stock=Decimal(str(current_stock)),
            min_stock_alert=Decimal(str(min_stock_alert)),
            unit=unit,
            category_id=category_id,
            is_active=True,
        )
        db.session.add(product)
        db.session.flush()

        return {
            "success": True,
            "id": product.id,
            "message": f'تم إنشاء المنتج "{name}" بنجاح',
            "product": {"id": product.id, "name": name, "sku": sku, "price": regular_price, "stock": current_stock},
        }

    def list_products(self, search: str = "", limit: int = 20) -> dict:
        self._require_tenant()
        from models import Product

        q = Product.query.filter_by(tenant_id=self.tenant_id, is_active=True)
        if search:
            q = q.filter(Product.name.ilike(f"%{search}%"))
        products = q.order_by(Product.name).limit(limit).all()

        return {
            "success": True,
            "products": [{"id": p.id, "name": p.name, "sku": p.sku,
                          "price": float(p.regular_price or 0),
                          "stock": float(p.current_stock or 0)} for p in products],
            "count": len(products),
        }

    def check_stock(self) -> dict:
        self._require_tenant()
        from models import Product

        low = Product.query.filter(
            Product.tenant_id == self.tenant_id,
            Product.is_active == True,
            Product.current_stock <= Product.min_stock_alert,
        ).all()

        return {
            "success": True,
            "low_stock": [{"name": p.name, "stock": float(p.current_stock or 0),
                           "min": float(p.min_stock_alert or 0)} for p in low[:20]],
            "count": len(low),
        }

    # ── SALE (uses SaleService for full accounting treatment) ──

    def create_sale(self, customer_name: str, product_lines: list[dict],
                    payment_method: str = "cash", paid_amount: float = 0,
                    notes: str = "") -> dict:
        self._require_tenant()
        from models import Customer, Product, User
        from services.sale_service import SaleService

        customer = Customer.query.filter_by(
            tenant_id=self.tenant_id, name=customer_name, is_active=True
        ).first()
        if not customer:
            raise AIExecutorError(f'العميل "{customer_name}" غير موجود')

        seller = self.user
        if not seller or not hasattr(seller, "id"):
            seller = User.query.filter_by(tenant_id=self.tenant_id, is_active=True).first()
            if not seller:
                raise AIExecutorError("لا يوجد مستخدم نشط لإنشاء الفاتورة")

        lines_data = []
        for pl in product_lines:
            pname = pl.get("name", pl.get("product_name", ""))
            qty = pl.get("quantity", 1)
            product = Product.query.filter_by(
                tenant_id=self.tenant_id, name=pname, is_active=True
            ).first()
            if not product:
                raise AIExecutorError(f'المنتج "{pname}" غير موجود')

            lines_data.append({
                "product": product,
                "quantity": qty,
                "unit_price": pl.get("unit_price") or None,
            })

        payment_data = None
        if paid_amount > 0:
            payment_data = {
                "amount": paid_amount,
                "payment_method": payment_method.lower(),
                "currency": "AED",
            }

        sale = SaleService.create_sale(
            customer=customer,
            seller=seller,
            lines_data=lines_data,
            payment_data=payment_data,
            notes=notes,
        )

        return {
            "success": True,
            "sale_id": sale.id,
            "sale_number": sale.sale_number,
            "total": float(sale.total_amount or 0),
            "message": f'تم إنشاء الفاتورة رقم {sale.sale_number} بقيمة {float(sale.total_amount or 0):,.2f} درهم',
        }

    def list_sales(self, limit: int = 10) -> dict:
        self._require_tenant()
        from models import Sale

        sales = Sale.query.filter_by(tenant_id=self.tenant_id, status="confirmed"
                                     ).order_by(Sale.sale_date.desc()).limit(limit).all()

        return {
            "success": True,
            "sales": [{"id": s.id, "number": s.sale_number,
                       "customer": s.customer.name if s.customer else "",
                       "total": float(s.total_amount or 0),
                       "status": s.payment_status or "unpaid",
                       "date": str(s.sale_date)[:10]} for s in sales],
        }

    # ── PAYMENT ───────────────────────────────────────────────

    def receive_payment(self, customer_name: str, amount: float,
                        method: str = "cash", notes: str = "") -> dict:
        self._require_tenant()
        from models import Customer, Payment, Sale
        from sqlalchemy import func

        customer = Customer.query.filter_by(
            tenant_id=self.tenant_id, name=customer_name, is_active=True
        ).first()
        if not customer:
            raise AIExecutorError(f'العميل "{customer_name}" غير موجود')
        if amount <= 0:
            raise AIExecutorError("مبلغ الدفع يجب أن يكون أكبر من صفر")

        amount_dec = Decimal(str(amount))

        payment_number = self._generate_number("PAY", Payment)
        payment = Payment(
            tenant_id=self.tenant_id,
            payment_number=payment_number,
            payment_type="sale_payment",
            direction="incoming",
            customer_id=customer.id,
            amount=amount_dec,
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=amount_dec,
            payment_method=method.lower(),
            notes=notes,
            user_id=self._current_user_id() or 1,
            branch_id=self._current_branch_id(),
        )
        db.session.add(payment)
        db.session.flush()

        customer.balance = (customer.balance or Decimal("0")) - amount_dec

        unpaid = Sale.query.filter(
            Sale.tenant_id == self.tenant_id,
            Sale.customer_id == customer.id,
            Sale.balance_due > 0,
            Sale.status.in_(["confirmed", "active"]),
        ).order_by(Sale.sale_date).all()

        remaining = amount_dec
        for sale in unpaid:
            if remaining <= 0:
                break
            due = sale.balance_due or Decimal("0")
            if remaining >= due:
                sale.paid_amount = (sale.paid_amount or Decimal("0")) + due
                sale.balance_due = Decimal("0")
                sale.payment_status = "paid"
                remaining -= due
            else:
                sale.paid_amount = (sale.paid_amount or Decimal("0")) + remaining
                sale.balance_due = due - remaining
                sale.payment_status = "partial"
                remaining = Decimal("0")
        db.session.flush()

        return {
            "success": True,
            "payment_id": payment.id,
            "payment_number": payment_number,
            "message": f"تم استلام {amount:,.2f} درهم من {customer_name}",
        }

    # ── EXPENSE ───────────────────────────────────────────────

    def add_expense(self, description: str, amount: float,
                    category_id: int = None, payment_method: str = "cash",
                    notes: str = "") -> dict:
        self._require_tenant()
        from models import Expense, ExpenseCategory
        from utils.helpers import generate_number

        if not description:
            raise AIExecutorError("وصف المصروف مطلوب")
        if amount <= 0:
            raise AIExecutorError("المبلغ يجب أن يكون أكبر من صفر")

        if not category_id:
            cat = ExpenseCategory.query.filter_by(tenant_id=self.tenant_id).first()
            if not cat:
                raise AIExecutorError("لا يوجد تصنيف مصروفات — أنشئ تصنيفاً أولاً")
            category_id = cat.id

        expense_number = generate_number("EXP", Expense, "expense_number",
                                          branch_id=self._current_branch_id(),
                                          tenant_id=self.tenant_id)
        amount_dec = Decimal(str(amount))
        expense = Expense(
            tenant_id=self.tenant_id,
            expense_number=expense_number,
            category_id=category_id,
            description=description,
            amount=amount_dec,
            currency="AED",
            exchange_rate=Decimal("1"),
            amount_aed=amount_dec,
            payment_method=payment_method.lower(),
            notes=notes,
            user_id=self._current_user_id() or 1,
            branch_id=self._current_branch_id(),
        )
        db.session.add(expense)
        db.session.flush()

        return {
            "success": True,
            "expense_id": expense.id,
            "expense_number": expense_number,
            "message": f'تم تسجيل المصروف "{description}" بقيمة {amount:,.2f} درهم',
        }

    # ── SUPPLIER ──────────────────────────────────────────────

    def create_supplier(self, name: str, phone: str = "",
                        email: str = "", company_name: str = "",
                        tax_number: str = "") -> dict:
        self._require_tenant()
        from models import Supplier

        if not name:
            raise AIExecutorError("اسم المورد مطلوب")

        supplier = Supplier(
            tenant_id=self.tenant_id,
            name=name,
            company_name=company_name,
            phone=phone,
            email=email,
            tax_number=tax_number,
            is_active=True,
        )
        db.session.add(supplier)
        db.session.flush()

        return {
            "success": True,
            "id": supplier.id,
            "message": f'تم إنشاء المورد "{name}" بنجاح',
        }

    # ── EMPLOYEE ──────────────────────────────────────────────

    def create_employee(self, name: str, phone: str = "",
                        email: str = "", basic_salary: float = 0,
                        employment_type: str = "salary") -> dict:
        self._require_tenant()
        from models.payroll import Employee

        if not name:
            raise AIExecutorError("اسم الموظف مطلوب")

        employee = Employee(
            tenant_id=self.tenant_id,
            name=name,
            phone=phone,
            email=email,
            basic_salary=Decimal(str(basic_salary)),
            employment_type=employment_type,
            branch_id=self._current_branch_id(),
            is_active=True,
        )
        db.session.add(employee)
        db.session.flush()

        return {
            "success": True,
            "id": employee.id,
            "message": f'تم إنشاء الموظف "{name}" بنجاح',
        }

    # ── PURCHASE (uses PurchaseService for full GL/stock) ─────

    def create_purchase(self, supplier_name: str, product_lines: list[dict],
                        notes: str = "") -> dict:
        self._require_tenant()
        from models import Supplier, Product, Warehouse, User
        from services.purchase_service import PurchaseService

        supplier = Supplier.query.filter_by(
            tenant_id=self.tenant_id, name=supplier_name, is_active=True
        ).first()
        if not supplier:
            raise AIExecutorError(f'المورد "{supplier_name}" غير موجود')

        warehouse = Warehouse.query.filter_by(tenant_id=self.tenant_id, is_active=True, is_main=True).first()
        if not warehouse:
            warehouse = Warehouse.query.filter_by(tenant_id=self.tenant_id, is_active=True).first()
        if not warehouse:
            raise AIExecutorError("لا يوجد مستودع نشط — أنشئ مستودعاً أولاً")

        lines_data = []
        for pl in product_lines:
            pname = pl.get("name", pl.get("product_name", ""))
            qty = pl.get("quantity", 1)
            cost = pl.get("unit_cost", 0)

            product = Product.query.filter_by(
                tenant_id=self.tenant_id, name=pname, is_active=True
            ).first()
            if not product:
                raise AIExecutorError(f'المنتج "{pname}" غير موجود')

            lines_data.append({
                "product_id": product.id,
                "quantity": qty,
                "unit_cost": cost,
            })

        purchase = PurchaseService.create_purchase(
            user=self.user,
            supplier_data={"supplier_id": supplier.id, "supplier_name": supplier.name},
            lines_data=lines_data,
            warehouse_id=warehouse.id,
            notes=notes,
        )

        return {
            "success": True,
            "purchase_id": purchase.id,
            "purchase_number": purchase.purchase_number,
            "message": f'تم إنشاء أمر الشراء رقم {purchase.purchase_number}',
        }

    # ── SALES SUMMARY / PROFIT ────────────────────────────────

    def sales_summary(self) -> dict:
        self._require_tenant()
        from models import Sale
        from sqlalchemy import func

        total = db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))\
            .filter(Sale.tenant_id == self.tenant_id,
                    Sale.status.in_(["confirmed", "active"])).scalar()
        count = Sale.query.filter(
            Sale.tenant_id == self.tenant_id,
            Sale.status.in_(["confirmed", "active"]),
        ).count()

        return {
            "success": True,
            "total_sales": float(total or 0),
            "count": count,
        }

    def profit_summary(self) -> dict:
        self._require_tenant()
        from models import Sale, SaleLine, Product
        from sqlalchemy import func

        total_revenue = db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))\
            .filter(Sale.tenant_id == self.tenant_id,
                    Sale.status.in_(["confirmed", "active"])).scalar()

        lines = SaleLine.query.join(Sale).filter(
            Sale.tenant_id == self.tenant_id,
            Sale.status.in_(["confirmed", "active"]),
        ).all()

        total_cost = Decimal("0")
        for line in lines:
            product = Product.query.get(line.product_id)
            if product and product.cost_price:
                total_cost += (product.cost_price or Decimal("0")) * (line.quantity or 0)

        profit = (total_revenue or 0) - total_cost
        margin = float(profit / total_revenue * 100) if total_revenue else 0

        return {
            "success": True,
            "revenue": float(total_revenue or 0),
            "cost": float(total_cost),
            "profit": float(profit),
            "margin_percent": round(margin, 1),
        }

    # ── INTERNAL ──────────────────────────────────────────────

    @staticmethod
    def _generate_number(prefix: str, model_class) -> str:
        from utils.helpers import generate_number as gn
        try:
            return gn(prefix, model_class, f"{prefix.lower()}_number",
                      tenant_id=getattr(flask_user, "tenant_id", None))
        except Exception:
            import random
            return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"


# Convenience singleton-pattern factory
_executor_cache: dict[int, AIExecutor] = {}


def get_ai_executor(user=None) -> AIExecutor:
    uid = getattr(user or flask_user, "id", None)
    if uid and uid in _executor_cache:
        return _executor_cache[uid]
    ex = AIExecutor(user=user)
    if uid:
        _executor_cache[uid] = ex
    return ex
