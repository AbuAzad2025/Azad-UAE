"""
Action Dispatcher - Secure ERP operation execution via AI.
Maps user intents to system operations with permission validation,
input sanitization, error handling, and audit logging.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from flask_login import current_user
from sqlalchemy import func

from extensions import db
from services.logging_core import LoggingCore

logger = logging.getLogger(__name__)

# ===== HELPERS =====


def _escape_ilike(term: str) -> str:
    """Escape SQL LIKE wildcards in user-provided search terms."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _get_active_tenant_id():
    """Get current tenant ID from Flask g or user."""
    try:
        from flask import g

        tenant_id = getattr(g, "active_tenant_id", None)
        if tenant_id:
            return tenant_id
    except RuntimeError:
        logger.debug("No Flask app context for tenant lookup")
    user = getattr(current_user, "is_authenticated", False)
    if user:
        return getattr(current_user, "tenant_id", None)
    return None


def _require_tenant():
    """Return active tenant_id or None if missing."""
    return _get_active_tenant_id()


def _tenant_guard():
    """Block create operations when no tenant context is active."""
    tid = _get_active_tenant_id()
    if not tid:
        return None, ActionResult(
            False,
            "لا يوجد تينانت نشط — يرجى تسجيل الدخول لشركة محددة",
        )
    return tid, None


def _has_permission(perm_code: str) -> bool:
    """Check if current user has a specific permission."""
    try:
        if hasattr(current_user, "has_permission") and current_user.is_authenticated:
            return current_user.has_permission(perm_code)
    except Exception as exc:
        logger.debug("Permission check failed: %s", exc)
    return False


def _is_owner() -> bool:
    """Check if current user is owner."""
    try:
        return getattr(current_user, "is_owner", False) or _has_permission("admin")
    except Exception as exc:
        logger.debug("Owner check failed: %s", exc)
        return False


def _audit(action: str, entity: str, entity_id: int | None = None, details: dict | None = None):
    """Log an audit entry."""
    try:
        LoggingCore.log_audit(action=action, table_name=entity, record_id=entity_id, changes=details or {})
    except Exception as exc:
        logger.warning("Audit log failed for %s/%s: %s", action, entity, exc)


def _log_ai_error(
    error_type: str,
    message: str,
    endpoint: str = "ai_chat",
    request_data: dict | None = None,
):
    """Log an AI operation error to ErrorAuditLog."""
    try:
        from models import ErrorAuditLog

        log = ErrorAuditLog(
            error_type=error_type,
            error_message=str(message)[:500],
            endpoint=endpoint,
            user_id=getattr(current_user, "id", None),
            request_data=request_data or {},
            traceback="",
            timestamp=datetime.now(timezone.utc),
        )
        db.session.add(log)
        db.session.flush()
    except Exception as exc:
        logger.warning("AI error log failed (%s): %s", error_type, exc)


# ===== ACTION DEFINITIONS =====


class ActionResult:
    """Result of an executed action."""

    def __init__(
        self,
        success: bool,
        message: str,
        data: Any = None,
        action_type: str = "",
        needs_permission: str = "",
    ):
        self.success = success
        self.message = message
        self.data = data or {}
        self.action_type = action_type
        self.needs_permission = needs_permission

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "action_type": self.action_type,
        }


class ActionDispatcher:
    """
    Dispatches user requests to the correct system operation.
    Each action has: name, required_permission, handler function, description.
    """

    def __init__(self) -> None:
        self._registry: dict[str, dict] = {}
        self._register_all()

    def _register(
        self,
        action_type: str,
        handler: Callable,
        permission: str = "",
        description: str = "",
    ):
        """Register an action handler."""
        self._registry[action_type] = {
            "handler": handler,
            "permission": permission,
            "description": description,
        }

    def _register_all(self):
        """Register all known actions."""

        # ===== CUSTOMERS =====
        def _create_customer(args: dict) -> ActionResult:
            name = args.get("name", "").strip()
            if not name:
                return ActionResult(False, "يرجى إدخال اسم العميل")
            try:
                from models import Customer

                tid, guard = _tenant_guard()
                if guard:
                    return guard
                customer = Customer(
                    tenant_id=tid,
                    name=name,
                    phone=args.get("phone", ""),
                    email=args.get("email", ""),
                    address=args.get("address", ""),
                    credit_limit=Decimal(str(args.get("credit_limit", 0))),
                    customer_type=args.get("type", "regular"),
                )
                db.session.add(customer)
                db.session.flush()
                _audit("create", "Customer", customer.id, {"name": name})
                return ActionResult(
                    True,
                    f"تم إنشاء العميل {name} بنجاح",
                    {"id": customer.id, "name": name},
                    "customer_create",
                    "manage_customers",
                )
            except Exception as e:
                _log_ai_error("customer_create_error", str(e), request_data=args)
                return ActionResult(False, f"خطأ في إنشاء العميل: {str(e)[:100]}")

        def _list_customers(args: dict) -> ActionResult:
            try:
                from models import Customer

                tid = _get_active_tenant_id()
                q = Customer.query.filter_by(tenant_id=tid, is_active=True)
                search = args.get("search", "")
                if search:
                    safe = _escape_ilike(search.strip())
                    q = q.filter(Customer.name.ilike(f"%{safe}%", escape="\\"))
                customers = q.order_by(Customer.name).limit(20).all()
                data = [
                    {
                        "id": c.id,
                        "name": c.name,
                        "phone": c.phone,
                        "balance": float(c.balance or 0),
                    }
                    for c in customers
                ]
                return ActionResult(
                    True,
                    f"تم العثور على {len(data)} عميل",
                    {"customers": data, "count": len(data)},
                    "customer_list",
                    "manage_customers",
                )
            except Exception as e:
                return ActionResult(False, f"خطأ في جلب العملاء: {str(e)[:100]}")

        def _get_customer_balance(args: dict) -> ActionResult:
            name = args.get("name", "").strip()
            if not name:
                return ActionResult(False, "يرجى إدخال اسم العميل")
            try:
                from models import Customer

                tid = _get_active_tenant_id()
                customer = Customer.query.filter_by(tenant_id=tid, name=name, is_active=True).first()
                if not customer:
                    return ActionResult(False, f"العميل {name} غير موجود")
                balance = float(customer.balance or 0)
                status = "طبيعي" if balance < 1000 else ("تنبيه" if balance < 5000 else "خطير")
                return ActionResult(
                    True,
                    f"رصيد العميل {name}: {balance:,.2f} درهم - {status}",
                    {
                        "id": customer.id,
                        "name": name,
                        "balance": balance,
                        "credit_limit": float(customer.credit_limit or 0),
                    },
                    "customer_balance",
                    "manage_customers",
                )
            except Exception as e:
                return ActionResult(False, f"خطأ: {str(e)[:100]}")

        # ===== PRODUCTS =====
        def _create_product(args: dict) -> ActionResult:
            name = args.get("name", "").strip()
            if not name:
                return ActionResult(False, "يرجى إدخال اسم المنتج")
            try:
                from models import Product

                tid, guard = _tenant_guard()
                if guard:
                    return guard
                product = Product(
                    tenant_id=tid,
                    name=name,
                    sku=args.get("sku", ""),
                    barcode=args.get("barcode", ""),
                    cost_price=Decimal(str(args.get("cost_price", 0))),
                    selling_price=Decimal(str(args.get("selling_price", 0))),
                    current_stock=Decimal(str(args.get("stock", 0))),
                    min_stock_level=Decimal(str(args.get("min_stock", 0))),
                    unit=args.get("unit", "قطعة"),
                    is_active=True,
                )
                db.session.add(product)
                db.session.flush()
                _audit("create", "Product", product.id, {"name": name})
                return ActionResult(
                    True,
                    f"تم إنشاء المنتج {name} بنجاح",
                    {"id": product.id, "name": name},
                    "product_create",
                    "manage_products",
                )
            except Exception as e:
                _log_ai_error("product_create_error", str(e), request_data=args)
                return ActionResult(False, f"خطأ في إنشاء المنتج: {str(e)[:100]}")

        def _list_products(args: dict) -> ActionResult:
            try:
                from models import Product

                tid = _get_active_tenant_id()
                q = Product.query.filter_by(tenant_id=tid, is_active=True)
                search = args.get("search", "")
                if search:
                    safe = _escape_ilike(search.strip())
                    q = q.filter(Product.name.ilike(f"%{safe}%", escape="\\"))
                products = q.order_by(Product.name).limit(20).all()
                data = [
                    {
                        "id": p.id,
                        "name": p.name,
                        "sku": p.sku,
                        "price": float(p.selling_price or 0),
                        "stock": float(p.current_stock or 0),
                    }
                    for p in products
                ]
                return ActionResult(
                    True,
                    f"تم العثور على {len(data)} منتج",
                    {"products": data, "count": len(data)},
                    "product_list",
                    "manage_products",
                )
            except Exception as e:
                return ActionResult(False, f"خطأ: {str(e)[:100]}")

        def _check_stock(_args: dict) -> ActionResult:
            try:
                from models import Product

                tid = _get_active_tenant_id()
                low = Product.query.filter(
                    Product.tenant_id == tid,
                    Product.is_active,
                    Product.current_stock <= Product.min_stock_level,
                ).all()
                data = [
                    {
                        "name": p.name,
                        "stock": float(p.current_stock or 0),
                        "min": float(p.min_stock_level or 0),
                    }
                    for p in low[:20]
                ]
                if not data:
                    return ActionResult(
                        True,
                        "جميع المنتجات متوفرة بكميات جيدة",
                        {"low_stock": []},
                        "stock_check",
                        "manage_warehouse",
                    )
                return ActionResult(
                    True,
                    f"يوجد {len(data)} منتجات منخفضة المخزون",
                    {"low_stock": data, "count": len(data)},
                    "stock_check",
                    "manage_warehouse",
                )
            except Exception as e:
                return ActionResult(False, f"خطأ: {str(e)[:100]}")

        # ===== SALES / INVOICES =====
        def _create_sale(args: dict[str, Any]) -> ActionResult:
            from services.ai_executor import AIExecutor

            customer_name = args.get("customer_name", "").strip()
            product_name = args.get("product_name", "").strip()
            quantity = int(args.get("quantity", 1))
            if not customer_name or not product_name:
                return ActionResult(False, "يرجى إدخال اسم العميل والمنتج")
            try:
                ex = AIExecutor()
                lines = [{"name": product_name, "quantity": quantity}]
                if args.get("unit_price"):
                    lines[0]["unit_price"] = float(args["unit_price"])
                result = ex.create_sale(
                    customer_name=customer_name,
                    product_lines=lines,
                    payment_method=args.get("payment_method", "cash"),
                    paid_amount=float(args.get("paid_amount", 0)),
                )
                if result.get("success"):
                    _audit(
                        "create",
                        "Sale",
                        result.get("sale_id"),
                        {"customer": customer_name, "total": result.get("total", 0)},
                    )
                    return ActionResult(
                        True,
                        result["message"],
                        {
                            "sale_id": result.get("sale_id"),
                            "sale_number": result.get("sale_number"),
                            "total": result.get("total", 0),
                        },
                        "sale_create",
                        "manage_sales",
                    )
                return ActionResult(False, result.get("message", "حدث خطأ"))
            except Exception as e:
                _log_ai_error("sale_create_error", str(e), request_data=args)
                return ActionResult(False, f"خطأ في إنشاء الفاتورة: {str(e)[:100]}")

        def _list_sales(_args: dict) -> ActionResult:
            try:
                from models import Sale

                tid = _get_active_tenant_id()
                sales = (
                    Sale.query.filter_by(tenant_id=tid, status="active").order_by(Sale.sale_date.desc()).limit(10).all()
                )
                data = [
                    {
                        "id": s.id,
                        "number": s.sale_number,
                        "total": float(s.total_amount or 0),
                        "status": s.payment_status,
                        "date": str(s.sale_date)[:10],
                    }
                    for s in sales
                ]
                return ActionResult(
                    True,
                    f"آخر {len(data)} فواتير",
                    {"sales": data},
                    "sale_list",
                    "manage_sales",
                )
            except Exception as e:
                return ActionResult(False, f"خطأ: {str(e)[:100]}")

        # ===== PAYMENTS =====
        def _receive_payment(args: dict) -> ActionResult:
            from services.ai_executor import AIExecutor

            customer_name = args.get("customer_name", "").strip()
            amount = float(args.get("amount", 0))
            if not customer_name or amount <= 0:
                return ActionResult(False, "يرجى إدخال اسم العميل والمبلغ")
            try:
                ex = AIExecutor()
                result = ex.receive_payment(
                    customer_name=customer_name,
                    amount=amount,
                    method=args.get("method", "cash"),
                    notes=args.get("notes", ""),
                )
                if result.get("success"):
                    _audit(
                        "create",
                        "Payment",
                        result.get("payment_id"),
                        {"customer": customer_name, "amount": amount},
                    )
                    return ActionResult(
                        True,
                        result["message"],
                        {"payment_id": result.get("payment_id"), "amount": amount},
                        "payment_receive",
                        "manage_payments",
                    )
                return ActionResult(False, result.get("message", "حدث خطأ"))
            except Exception as e:
                _log_ai_error("payment_error", str(e), request_data=args)
                return ActionResult(False, f"خطأ في استلام الدفعة: {str(e)[:100]}")

        def _add_expense(args: dict) -> ActionResult:
            description = args.get("description", "").strip()
            amount = Decimal(str(args.get("amount", 0)))
            if not description or amount <= 0:
                return ActionResult(False, "يرجى إدخال الوصف والمبلغ")
            try:
                from models import Expense

                tid, guard = _tenant_guard()
                if guard:
                    return guard
                expense = Expense(
                    tenant_id=tid,
                    description=description,
                    amount=amount,
                    currency="AED",
                    amount_aed=amount,
                    expense_date=datetime.now(timezone.utc),
                    payment_method=args.get("method", "cash"),
                    category_id=args.get("category_id"),
                    branch_id=args.get("branch_id"),
                )
                db.session.add(expense)
                db.session.flush()
                _audit(
                    "create",
                    "Expense",
                    expense.id,
                    {"description": description, "amount": float(amount)},
                )
                return ActionResult(
                    True,
                    f"تم تسجيل المصروف {description} بقيمة {float(amount):,.2f} درهم",
                    {"expense_id": expense.id},
                    "expense_add",
                    "manage_expenses",
                )
            except Exception as e:
                _log_ai_error("expense_error", str(e), request_data=args)
                return ActionResult(False, f"خطأ: {str(e)[:100]}")

        # ===== SUPPLIERS =====
        def _create_supplier(args: dict) -> ActionResult:
            name = args.get("name", "").strip()
            if not name:
                return ActionResult(False, "يرجى إدخال اسم المورد")
            try:
                from models import Supplier

                tid, guard = _tenant_guard()
                if guard:
                    return guard
                supplier = Supplier(
                    tenant_id=tid,
                    name=name,
                    company_name=args.get("company", ""),
                    phone=args.get("phone", ""),
                    email=args.get("email", ""),
                    tax_number=args.get("tax_number", ""),
                )
                db.session.add(supplier)
                db.session.flush()
                _audit("create", "Supplier", supplier.id, {"name": name})
                return ActionResult(
                    True,
                    f"تم إنشاء المورد {name} بنجاح",
                    {"id": supplier.id, "name": name},
                    "supplier_create",
                    "manage_suppliers",
                )
            except Exception as e:
                _log_ai_error("supplier_error", str(e), request_data=args)
                return ActionResult(False, f"خطأ: {str(e)[:100]}")

        # ===== REPORTS =====
        def _sales_summary(_args: dict) -> ActionResult:
            try:
                from models import Sale

                tid = _get_active_tenant_id()
                total = (
                    db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))
                    .filter(Sale.tenant_id == tid, Sale.status == "active")
                    .scalar()
                )
                count = Sale.query.filter_by(tenant_id=tid, status="active").count()
                return ActionResult(
                    True,
                    f"إجمالي المبيعات: {float(total):,.2f} درهم | عدد الفواتير: {count}",
                    {"total_sales": float(total), "count": count},
                    "sales_summary",
                    "view_reports",
                )
            except Exception as e:
                return ActionResult(False, f"خطأ: {str(e)[:100]}")

        def _profit_summary(_args: dict) -> ActionResult:
            try:
                from models import Sale, SaleLine, Product

                tid = _get_active_tenant_id()
                sales = (
                    db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))
                    .filter(Sale.tenant_id == tid, Sale.status == "active")
                    .scalar()
                )
                lines = (
                    db.session.query(SaleLine).join(Sale).filter(Sale.tenant_id == tid, Sale.status == "active").all()
                )
                cost = Decimal("0")
                for line in lines:
                    product = Product.query.get(line.product_id)
                    if product and product.cost_price:
                        cost += (product.cost_price or 0) * (line.quantity or 0)
                profit = (sales or 0) - cost
                margin = float(profit / sales * 100) if sales else 0
                return ActionResult(
                    True,
                    f"إجمالي الربح: {float(profit):,.2f} درهم | هامش الربح: {margin:.1f}%",
                    {
                        "revenue": float(sales or 0),
                        "cost": float(cost),
                        "profit": float(profit),
                        "margin_percent": margin,
                    },
                    "profit_summary",
                    "view_reports",
                )
            except Exception as e:
                return ActionResult(False, f"خطأ: {str(e)[:100]}")

        # ===== EMPLOYEES =====
        def _create_employee(args: dict) -> ActionResult:
            from services.ai_executor import AIExecutor

            name = args.get("name", "").strip()
            if not name:
                return ActionResult(False, "يرجى إدخال اسم الموظف")
            try:
                ex = AIExecutor()
                result = ex.create_employee(
                    name=name,
                    phone=args.get("phone", ""),
                    email=args.get("email", ""),
                    basic_salary=float(args.get("salary", 0)),
                    employment_type=args.get("employment_type", "salary"),
                )
                if result.get("success"):
                    _audit("create", "Employee", result.get("id"), {"name": name})
                    return ActionResult(
                        True,
                        result["message"],
                        {"id": result.get("id"), "name": name},
                        "employee_create",
                        "manage_employees",
                    )
                return ActionResult(False, result.get("message", "حدث خطأ"))
            except Exception as e:
                _log_ai_error("employee_create_error", str(e), request_data=args)
                return ActionResult(False, f"خطأ: {str(e)[:100]}")

        # ===== PURCHASES =====
        def _create_purchase(args: dict) -> ActionResult:
            from services.ai_executor import AIExecutor

            supplier_name = args.get("supplier_name", "").strip()
            product_name = args.get("product_name", "").strip()
            quantity = int(args.get("quantity", 1))
            if not supplier_name or not product_name:
                return ActionResult(False, "يرجى إدخال اسم المورد والمنتج")
            try:
                ex = AIExecutor()
                lines = [
                    {
                        "name": product_name,
                        "quantity": quantity,
                        "unit_cost": float(args.get("unit_cost", 0)),
                    }
                ]
                result = ex.create_purchase(
                    supplier_name=supplier_name,
                    product_lines=lines,
                    notes=args.get("notes", ""),
                )
                if result.get("success"):
                    _audit(
                        "create",
                        "Purchase",
                        result.get("purchase_id"),
                        {"supplier": supplier_name},
                    )
                    return ActionResult(
                        True,
                        result["message"],
                        {
                            "purchase_id": result.get("purchase_id"),
                            "purchase_number": result.get("purchase_number"),
                        },
                        "purchase_create",
                        "manage_purchases",
                    )
                return ActionResult(False, result.get("message", "حدث خطأ"))
            except Exception as e:
                _log_ai_error("purchase_create_error", str(e), request_data=args)
                return ActionResult(False, f"خطأ: {str(e)[:100]}")

        # ===== USERS (owner only) =====
        def _create_user(args: dict) -> ActionResult:
            if not _is_owner():
                return ActionResult(False, "هذه العملية تتصلاحيات المالك فقط", needs_permission="admin")
            username = args.get("username", "").strip()
            password = args.get("password", "").strip()
            role_slug = args.get("role", "seller")
            if not username or not password:
                return ActionResult(False, "يرجى إدخال اسم المستخدم وكلمة المرور")
            try:
                from models import User, Role
                from werkzeug.security import generate_password_hash

                tid, guard = _tenant_guard()
                if guard:
                    return guard
                role = Role.query.filter_by(slug=role_slug).first()
                user = User(
                    tenant_id=tid,
                    username=username,
                    password_hash=generate_password_hash(password),
                    role_id=role.id if role else None,
                    full_name=args.get("full_name", username),
                    phone=args.get("phone", ""),
                    is_active=True,
                )
                db.session.add(user)
                db.session.flush()
                _audit("create", "User", user.id, {"username": username})
                return ActionResult(
                    True,
                    f"تم إنشاء المستخدم {username} بنجاح",
                    {"id": user.id, "username": username},
                    "user_create",
                    "manage_users",
                )
            except Exception as e:
                return ActionResult(False, f"خطأ: {str(e)[:100]}")

        # Register all actions
        self._register("create_customer", _create_customer, "manage_customers", "إنشاء عميل جديد")
        self._register("list_customers", _list_customers, "manage_customers", "عرض العملاء")
        self._register(
            "customer_balance",
            _get_customer_balance,
            "manage_customers",
            "عرض رصيد عميل",
        )
        self._register("create_product", _create_product, "manage_products", "إنشاء منتج جديد")
        self._register("list_products", _list_products, "manage_products", "عرض المنتجات")
        self._register("check_stock", _check_stock, "manage_warehouse", "فحص المخزون")
        self._register("create_sale", _create_sale, "manage_sales", "إنشاء فاتورة مبيعات")
        self._register("list_sales", _list_sales, "manage_sales", "عرض الفواتير")
        self._register("receive_payment", _receive_payment, "manage_payments", "استلام دفعة")
        self._register("add_expense", _add_expense, "manage_expenses", "تسجيل مصروف")
        self._register("create_supplier", _create_supplier, "manage_suppliers", "إنشاء مورد")
        self._register("sales_summary", _sales_summary, "view_reports", "ملخص المبيعات")
        self._register("profit_summary", _profit_summary, "view_reports", "ملخص الأرباح")
        self._register("create_employee", _create_employee, "manage_employees", "إنشاء موظف")
        self._register("create_purchase", _create_purchase, "manage_purchases", "إنشاء أمر شراء")
        self._register("create_user", _create_user, "manage_users", "إنشاء مستخدم")

    def get_registered_actions(self) -> list[str]:
        """List all registered action types."""
        return list(self._registry.keys())

    def dispatch(self, action_type: str, args: dict | None = None) -> ActionResult:
        """
        Execute an action with permission check and error handling.
        Returns ActionResult with success/failure, message, and data.
        """
        action = self._registry.get(action_type)
        if not action:
            return ActionResult(False, f"العملية '{action_type}' غير معروفة")

        # Permission check
        perm = action["permission"]
        if perm and not _is_owner() and not _has_permission(perm):
            _log_ai_error(
                "permission_denied",
                f"Missing permission: {perm}",
                request_data={"action": action_type, "args": args},
            )
            return ActionResult(
                False,
                f"ليس لديك صلاحية لهذه العملية. تحتاج صلاحية: {perm}",
                needs_permission=perm,
            )

        # Execute
        try:
            return action["handler"](args or {})
        except Exception as e:
            _log_ai_error(
                "action_dispatch_error",
                str(e),
                request_data={"action": action_type, "args": args},
            )
            return ActionResult(False, f"حدث خطأ غير متوقع: {str(e)[:100]}")

    @staticmethod
    def parse_chat_action(message: str) -> tuple[str, dict] | None:
        """
        Parse a user chat message into (action_type, args).
        Returns None if no action matches.
        """
        msg = message.strip()

        # ===== CUSTOMER OPERATIONS =====
        # عميل: الاسم, الهاتف, العنوان
        m = re.match(r"^(عميل|زبون|customer)\s*[::=]\s*(.+)$", msg, re.IGNORECASE)
        if m:
            parts = [p.strip() for p in m.group(2).split(",")]
            return (
                "create_customer",
                {
                    "name": parts[0] if len(parts) > 0 else "",
                    "phone": parts[1] if len(parts) > 1 else "",
                    "address": parts[2] if len(parts) > 2 else "",
                    "email": parts[3] if len(parts) > 3 else "",
                },
            )

        # رصيد: اسم العميل or balance: customer name
        m = re.match(r"^(رصيد|balance)\s*[::=]\s*(.+)$", msg, re.IGNORECASE)
        if m:
            return "customer_balance", {"name": m.group(2).strip()}

        # عرض العملاء / show customers
        if re.search(
            r"^(عرض|ارني|شوف|show|list)\s*(كل\s*)?(العملاء|الزبائن|customers)",
            msg,
            re.IGNORECASE,
        ):
            return "list_customers", {}

        # ===== PRODUCT OPERATIONS =====
        # منتج: الاسم, السعر, الكمية
        m = re.match(r"^(منتج|product)\s*[::=]\s*(.+)$", msg, re.IGNORECASE)
        if m:
            parts = [p.strip() for p in m.group(2).split(",")]
            return (
                "create_product",
                {
                    "name": parts[0] if len(parts) > 0 else "",
                    "selling_price": parts[1] if len(parts) > 1 else "0",
                    "stock": parts[2] if len(parts) > 2 else "0",
                },
            )

        # عرض المنتجات / show products
        if re.search(
            r"^(عرض|ارني|شوف|show|list)\s*(كل\s*)?(المنتجات|products)",
            msg,
            re.IGNORECASE,
        ):
            return "list_products", {}

        # فحص المخزون / stock check
        if re.search(r"(فحص|check|low\s*stock|المخزون|نقص|منخفض)", msg, re.IGNORECASE):
            return "check_stock", {}

        # ===== SALE OPERATIONS =====
        # فاتورة: اسم العميل, اسم المنتج, الكمية
        m = re.match(r"^(فاتورة|sale|invoice|بيع)\s*[::=]\s*(.+)$", msg, re.IGNORECASE)
        if m:
            parts = [p.strip() for p in m.group(2).split(",")]
            qty_m = re.search(r"\d+", parts[2]) if len(parts) > 2 else None
            return (
                "create_sale",
                {
                    "customer_name": parts[0] if len(parts) > 0 else "",
                    "product_name": parts[1] if len(parts) > 1 else "",
                    "quantity": int(qty_m.group()) if qty_m else 1,
                    "payment_method": parts[3] if len(parts) > 3 else "cash",
                },
            )

        # عرض الفواتير / show sales
        if re.search(
            r"^(عرض|ارني|شوف|show|list)\s*(كل\s*)?(الفواتير|المبيعات|sales|invoices)",
            msg,
            re.IGNORECASE,
        ):
            return "list_sales", {}

        # ملخص المبيعات / sales summary
        if re.search(r"(ملخص|تقرير|summary|report)\s*(المبيعات|المبيعات)", msg, re.IGNORECASE) or re.search(
            r"(المبيعات|sales)\s*(ملخص|تقرير|summary|report)", msg, re.IGNORECASE
        ):
            return "sales_summary", {}

        # ===== PAYMENT OPERATIONS =====
        # استلام: اسم العميل, المبلغ
        m = re.match(r"^(استلام|قبض|payment|receive)\s*[::=]\s*(.+)$", msg, re.IGNORECASE)
        if m:
            parts = [p.strip() for p in m.group(2).split(",")]
            amt_m = re.search(r"[\d.]+", parts[1]) if len(parts) > 1 else None
            return (
                "receive_payment",
                {
                    "customer_name": parts[0] if len(parts) > 0 else "",
                    "amount": float(amt_m.group()) if amt_m else 0,
                    "method": parts[2] if len(parts) > 2 else "cash",
                },
            )

        # ===== EXPENSE OPERATIONS =====
        # مصروف: الوصف, المبلغ
        m = re.match(r"^(مصروف|expense)\s*[::=]\s*(.+)$", msg, re.IGNORECASE)
        if m:
            parts = [p.strip() for p in m.group(2).split(",")]
            amt_m = re.search(r"[\d.]+", parts[1]) if len(parts) > 1 else None
            return (
                "add_expense",
                {
                    "description": parts[0] if len(parts) > 0 else "",
                    "amount": float(amt_m.group()) if amt_m else 0,
                },
            )

        # ===== SUPPLIER OPERATIONS =====
        # مورد: الاسم, الهاتف
        m = re.match(r"^(مورد|supplier)\s*[::=]\s*(.+)$", msg, re.IGNORECASE)
        if m:
            parts = [p.strip() for p in m.group(2).split(",")]
            return (
                "create_supplier",
                {
                    "name": parts[0] if len(parts) > 0 else "",
                    "company": parts[1] if len(parts) > 1 else "",
                    "phone": parts[2] if len(parts) > 2 else "",
                },
            )

        # ===== EMPLOYEE OPERATIONS =====
        # موظف: الاسم, الهاتف, الراتب
        m = re.match(r"^(موظف|employee)\s*[::=]\s*(.+)$", msg, re.IGNORECASE)
        if m:
            parts = [p.strip() for p in m.group(2).split(",")]
            sal_m = re.search(r"[\d.]+", parts[2]) if len(parts) > 2 else None
            return (
                "create_employee",
                {
                    "name": parts[0] if len(parts) > 0 else "",
                    "phone": parts[1] if len(parts) > 1 else "",
                    "salary": float(sal_m.group()) if sal_m else 0,
                },
            )

        # ===== PURCHASE OPERATIONS =====
        # أمر شراء: اسم المورد, اسم المنتج, الكمية
        m = re.match(r"^(أمر\s*شراء|شراء|purchase|order)\s*[::=]\s*(.+)$", msg, re.IGNORECASE)
        if m:
            parts = [p.strip() for p in m.group(2).split(",")]
            qty_m = re.search(r"\d+", parts[2]) if len(parts) > 2 else None
            return (
                "create_purchase",
                {
                    "supplier_name": parts[0] if len(parts) > 0 else "",
                    "product_name": parts[1] if len(parts) > 1 else "",
                    "quantity": int(qty_m.group()) if qty_m else 1,
                },
            )

        # ===== PROFIT / REPORTS =====
        if re.search(r"(أرباح|ربح|profit|هامش|margin)", msg, re.IGNORECASE) and re.search(
            r"(تقرير|ملخص|summary|report|تحليل|analysis)", msg, re.IGNORECASE
        ):
            return "profit_summary", {}

        # ===== GREETINGS =====
        if re.search(r"^(مرحبا|اهلا|hello|hi|السلام عليكم)", msg, re.IGNORECASE):
            return "greeting", {"name": getattr(current_user, "full_name", "") or ""}

        # ===== HELP =====
        if re.search(r"^(مساعدة|help|اوامر|commands|مساعدة|what can you do)", msg, re.IGNORECASE):
            return "help", {}

        return None

    @staticmethod
    def format_help() -> str:
        """Return a list of available commands."""
        return """**الأوامر المتاحة:**
📦 **العملاء:** `عميل: الاسم, الهاتف, العنوان` | `عرض العملاء` | `رصيد: اسم العميل`
📋 **المنتجات:** `منتج: الاسم, السعر, الكمية` | `عرض المنتجات` | `فحص المخزون`
💰 **المبيعات:** `فاتورة: اسم العميل, اسم المنتج, الكمية` | `عرض الفواتير`
💳 **المدفوعات:** `استلام: اسم العميل, المبلغ`
📊 **المصروفات:** `مصروف: الوصف, المبلغ`
🤝 **الموردين:** `مورد: الاسم, الهاتف`
👥 **الموظفين:** `موظف: الاسم, الهاتف, الراتب`
📦 **المشتريات:** `أمر شراء: اسم المورد, اسم المنتج, الكمية`
📈 **التقارير:** `ملخص المبيعات` | `تقرير الأرباح`
❓ اسألني عن أي شيء عن النظام!

**ملاحظة:** بعض العمليات تتطلب صلاحيات محددة."""


# Singleton
action_dispatcher = ActionDispatcher()
