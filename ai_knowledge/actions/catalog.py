"""Catalog action pack — safe master-data updates + GL-backed stock takes.

Independent domain module: handlers + command patterns + help lines live
here and are wired by ``ai_knowledge.actions``.

Deliberate boundaries (protected systems stay protected):
- Customer/product updates touch a strict scalar whitelist only — never
  balances, never ``current_stock``, never GL rows.
- Stock corrections go exclusively through ``StockService.adjust_stock``,
  which creates the audited movement + GL posting itself.
- Customer balance changes are NOT exposed (balance stays a service-layer
  concern: receipts, sales, returns).
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from ai_knowledge.actions.base import (
    ActionResult,
    atomic_transaction,
    audit,
    pack_error,
    resolve_customer,
    resolve_product,
    resolve_warehouse,
    tenant_guard,
)

HELP_LINES = [
    "🗂️ **الكتالوج:** `تحديث عميل: الاسم, الهاتف, العنوان` | `تحديث منتج: الاسم, السعر` | `تسوية مخزون: المنتج, الفرق, السبب`",
]


def _split_parts(body: str) -> list[str]:
    return [p.strip() for p in body.split(",")]


def _parse_update_customer(body: str) -> tuple[str, dict[str, Any]] | None:
    parts = _split_parts(body)
    args: dict[str, Any] = {"name": parts[0] if len(parts) > 0 else ""}
    if len(parts) > 1 and parts[1]:
        args["phone"] = parts[1]
    if len(parts) > 2 and parts[2]:
        args["address"] = parts[2]
    credit_match = re.search(r"[\d.]+", parts[3]) if len(parts) > 3 else None
    if credit_match:
        args["credit_limit"] = float(credit_match.group())
    return "update_customer", args


def _parse_update_product(body: str) -> tuple[str, dict[str, Any]] | None:
    parts = _split_parts(body)
    args: dict[str, Any] = {"name": parts[0] if len(parts) > 0 else ""}
    price_match = re.search(r"[\d.]+", parts[1]) if len(parts) > 1 else None
    if price_match:
        args["selling_price"] = float(price_match.group())
    min_match = re.search(r"[\d.]+", parts[2]) if len(parts) > 2 else None
    if min_match:
        args["min_stock"] = float(min_match.group())
    return "update_product", args


def _parse_adjust_stock(body: str) -> tuple[str, dict[str, Any]] | None:
    parts = _split_parts(body)
    qty_match = re.search(r"-?\d+(?:\.\d+)?", parts[1]) if len(parts) > 1 else None
    return (
        "adjust_stock",
        {
            "product_name": parts[0] if len(parts) > 0 else "",
            "quantity_delta": float(qty_match.group()) if qty_match else 0,
            "reason": parts[2] if len(parts) > 2 else "",
        },
    )


PATTERNS = [
    (
        re.compile(r"^(تحديث\s*عميل|تعديل\s*عميل|update\s*customer)\s*[:：=]\s*(.+)$", re.IGNORECASE),
        lambda m: _parse_update_customer(m.group(2)),
    ),
    (
        re.compile(r"^(تحديث\s*منتج|تعديل\s*منتج|update\s*product)\s*[:：=]\s*(.+)$", re.IGNORECASE),
        lambda m: _parse_update_product(m.group(2)),
    ),
    (
        re.compile(r"^(تسوية\s*مخزون|تسوية|adjust\s*stock|stock\s*adjust)\s*[:：=]\s*(.+)$", re.IGNORECASE),
        lambda m: _parse_adjust_stock(m.group(2)),
    ),
]

_CUSTOMER_WRITABLE = ("phone", "email", "address")
_PRODUCT_WRITABLE = ("selling_price", "cost_price")


def _update_customer(args: dict) -> ActionResult:
    name = str(args.get("name") or "").strip()
    if not name:
        return ActionResult(False, "يرجى إدخال اسم العميل المراد تحديثه")
    try:
        from extensions import db

        tid, guard = tenant_guard()
        if guard:
            return guard
        customer = resolve_customer(tid, name)
        if customer is None:
            return ActionResult(False, f"⚠️ العميل «{name}» غير موجود في منشأتك")
        changes: dict[str, Any] = {}
        for field in _CUSTOMER_WRITABLE:
            value = args.get(field)
            if isinstance(value, str) and value.strip():
                setattr(customer, field, value.strip())
                changes[field] = value.strip()
        credit_limit = args.get("credit_limit")
        if credit_limit is not None:
            customer.credit_limit = Decimal(str(credit_limit))
            changes["credit_limit"] = float(credit_limit)
        if not changes:
            return ActionResult(False, "⚠️ لم يتم تحديد أي حقل للتحديث (هاتف/بريد/عنوان/حد ائتمان)")
        with atomic_transaction("ai_update_customer"):
            db.session.flush()
        audit("update", "Customer", customer.id, changes)
        fields = "، ".join(changes.keys())
        return ActionResult(
            True,
            f"تم تحديث العميل {customer.name} ({fields}) بنجاح",
            {"id": customer.id, "name": customer.name, "changes": changes},
            "customer_update",
            "manage_customers",
        )
    except Exception as e:
        return pack_error("update_customer", e, args)


def _update_product(args: dict) -> ActionResult:
    try:
        from extensions import db
        from models import Product

        tid, guard = tenant_guard()
        if guard:
            return guard
        product = None
        sku = str(args.get("sku") or "").strip()
        if sku:
            product = Product.query.filter_by(tenant_id=tid, sku=sku).first()
        if product is None:
            product = resolve_product(tid, str(args.get("name") or ""))
        if product is None:
            return ActionResult(False, "⚠️ المنتج غير موجود في منشأتك — تحقق من الاسم أو رمز SKU")
        changes: dict[str, Any] = {}
        new_name = str(args.get("new_name") or "").strip()
        if new_name:
            product.name = new_name
            changes["name"] = new_name
        for field in _PRODUCT_WRITABLE:
            raw_value = args.get(field)
            if raw_value is not None and hasattr(product, field):
                setattr(product, field, Decimal(str(raw_value)))
                changes[field] = float(raw_value)
        min_stock = args.get("min_stock")
        if min_stock is not None and hasattr(product, "min_stock_alert"):
            product.min_stock_alert = Decimal(str(min_stock))
            changes["min_stock_alert"] = float(min_stock)
        if not changes:
            return ActionResult(False, "⚠️ لم يتم تحديد أي حقل للتحديث (اسم/سعر بيع/تكلفة/حد أدنى)")
        with atomic_transaction("ai_update_product"):
            db.session.flush()
        audit("update", "Product", product.id, changes)
        return ActionResult(
            True,
            f"تم تحديث المنتج {product.name} بنجاح",
            {"id": product.id, "name": product.name, "changes": changes},
            "product_update",
            "manage_products",
        )
    except Exception as e:
        return pack_error("update_product", e, args)


def _adjust_stock(args: dict) -> ActionResult:
    product_name = str(args.get("product_name") or "").strip()
    if not product_name:
        return ActionResult(False, "يرجى إدخال اسم المنتج")
    reason = str(args.get("reason") or "").strip()
    if not reason:
        return ActionResult(
            False,
            "⚠️ سبب التسوية إلزامي للتدقيق — أعد الإرسال مع confirmed=true والسبب",
        )
    try:
        from services.stock_service import StockService

        tid, guard = tenant_guard()
        if guard:
            return guard
        product = resolve_product(tid, product_name)
        if product is None:
            return ActionResult(False, f"⚠️ المنتج «{product_name}» غير موجود في منشأتك")
        warehouse = None
        warehouse_id = args.get("warehouse_id")
        if warehouse_id:
            warehouse = resolve_warehouse(tid, int(warehouse_id))
            if warehouse is None:
                return ActionResult(False, "⚠️ المستودع المحدد غير موجود في منشأتك")
        delta = float(args.get("quantity_delta") or 0)
        if not delta:
            return ActionResult(False, "⚠️ فرق الكمية لا يمكن أن يكون صفراً")
        with atomic_transaction("ai_adjust_stock"):
            movement = StockService.adjust_stock(
                product_id=product.id,
                quantity=delta,
                notes=f"AI: {reason}",
                warehouse_id=warehouse.id if warehouse else None,
            )
        audit(
            "adjust",
            "Product",
            product.id,
            {"delta": delta, "reason": reason, "movement_id": getattr(movement, "id", None)},
        )
        direction = "زيادة" if delta > 0 else "نقصاً"
        return ActionResult(
            True,
            f"تمت تسوية مخزون {product.name} {direction} بمقدار {abs(delta):,.0f} (السبب: {reason})",
            {"product_id": product.id, "delta": delta},
            "stock_adjust",
            "manage_warehouse",
        )
    except Exception as e:
        return pack_error("adjust_stock", e, args)


def register(register_fn) -> None:
    """Register this pack's actions on the dispatcher registry."""
    register_fn("update_customer", _update_customer, "manage_customers", "تحديث بيانات عميل", confirm_required=True)
    register_fn("update_product", _update_product, "manage_products", "تحديث بيانات منتج", confirm_required=True)
    register_fn("adjust_stock", _adjust_stock, "manage_warehouse", "تسوية مخزون بسبب موثق", confirm_required=True)
