"""Purchase-return action pack — RMA to suppliers via PurchaseService.

Independent domain module: handlers + command patterns + help lines live
here and are wired by ``ai_knowledge.actions``. The service reverses stock
(Remove + MWAC), supplier balance, VAT input, and posts the reversing GL
entry internally; the pack only resolves the purchase/line and wraps the
call in ``atomic_transaction``. Permission mirror of purchase flows:
``manage_purchases``.
"""

from __future__ import annotations

import re
from typing import Any

from ai_knowledge.actions.base import (
    ActionResult,
    actor,
    atomic_transaction,
    audit,
    escape_like,
    pack_error,
    tenant_guard,
)

PERMISSION = "manage_purchases"

HELP_LINES = [
    "↩️ **مردودات المشتريات:** `مرتجع مشتريات: رقم الفاتورة, المنتج, الكمية` | `تفاصيل مرتجع: الرقم`",
]


def _parse_purchase_return(body: str) -> tuple[str, dict[str, Any]] | None:
    parts = [p.strip() for p in body.split(",")]
    ref = parts[0] if len(parts) > 0 else ""
    product = parts[1] if len(parts) > 1 else ""
    qty_match = re.search(r"\d+(?:\.\d+)?", parts[2]) if len(parts) > 2 else None
    args: dict[str, Any] = {"product_name": product}
    if ref.isdigit():
        args["purchase_id"] = int(ref)
    else:
        args["purchase_number"] = ref
    args["quantity"] = float(qty_match.group()) if qty_match else 1
    if len(parts) > 3 and parts[3]:
        args["reason"] = parts[3]
    return "create_purchase_return", args


def _parse_return_details(body: str) -> tuple[str, dict[str, Any]] | None:
    ref = body.strip()
    if ref.isdigit():
        return "purchase_return_details", {"return_id": int(ref)}
    return "purchase_return_details", {"return_number": ref}


def _parse_list_purchase_returns(_match: re.Match) -> tuple[str, dict[str, Any]] | None:
    return "purchase_return_details", {}


PATTERNS = [
    (
        re.compile(r"^(مرتجع\s*مشتريات|مردود\s*مشتريات|مردود|purchase\s*return)\s*[:：=]\s*(.+)$", re.IGNORECASE),
        lambda m: _parse_purchase_return(m.group(2)),
    ),
    (
        re.compile(r"^(تفاصيل\s*مرتجع|تفاصيل\s*مردود|عرض\s*مرتجع\s*مشتريات)\s*[:：=]?\s*(.*)$", re.IGNORECASE),
        lambda m: _parse_return_details(m.group(2)),
    ),
    (
        re.compile(
            r"^(عرض|ارني|شوف|show|list)\s*(كل\s*)?(مرتجعات\s*المشتريات|مردودات\s*المشتريات|مردودات|purchase\s*returns)",
            re.IGNORECASE,
        ),
        _parse_list_purchase_returns,
    ),
]


def _resolve_purchase(tid: int, args: dict):
    """Tenant-scoped purchase by id or number (or None)."""
    from extensions import db
    from models import Purchase

    purchase_id = args.get("purchase_id")
    if purchase_id:
        purchase = db.session.get(Purchase, int(purchase_id))
        if purchase is not None and int(getattr(purchase, "tenant_id", -1)) == int(tid):
            return purchase
        return None
    number = str(args.get("purchase_number") or "").strip()
    if not number:
        return None
    return Purchase.query.filter_by(tenant_id=tid, purchase_number=number).first()


def _create_purchase_return(args: dict) -> ActionResult:
    product_name = str(args.get("product_name") or "").strip()
    if not product_name:
        return ActionResult(False, "يرجى إدخال اسم المنتج المرتجع للمورد")
    try:
        from services.purchase_service import PurchaseService

        tid, guard = tenant_guard()
        if guard:
            return guard
        user = actor()
        if user is None or getattr(user, "id", None) is None:
            return ActionResult(False, "🚫 لا يمكن إنشاء مرتجع مشتريات دون مستخدم موثّق — يرجى تسجيل الدخول")
        purchase = _resolve_purchase(tid, args)
        if purchase is None:
            return ActionResult(
                False,
                "⚠️ فاتورة الشراء غير موجودة في منشأتك — تحقق من الرقم",
            )
        if getattr(purchase, "status", "") == "cancelled":
            return ActionResult(False, "⚠️ لا يمكن عمل مرتجع لفاتورة شراء ملغاة")
        safe = escape_like(product_name).lower()
        line = next(
            (
                purchase_line
                for purchase_line in (purchase.lines or [])
                if safe in (getattr(purchase_line.product, "name", "") or "").lower()
            ),
            None,
        )
        if line is None:
            return ActionResult(
                False,
                f"⚠️ المنتج «{product_name}» غير موجود في فاتورة الشراء {purchase.purchase_number}",
            )
        quantity = float(args.get("quantity", 1))
        if quantity <= 0:
            return ActionResult(False, "⚠️ كمية المرتجع يجب أن تكون أكبر من صفر")
        unit_cost = args.get("unit_cost")
        if unit_cost is None:
            unit_cost = float(getattr(line, "unit_cost", 0) or 0)
        lines_data = [
            {
                "purchase_line_id": line.id,
                "product_id": line.product_id,
                "quantity": quantity,
                "unit_cost": float(unit_cost),
                "reason": str(args.get("reason") or ""),
            }
        ]
        with atomic_transaction("ai_create_purchase_return"):
            purchase_return = PurchaseService.create_purchase_return(
                purchase,
                user,
                lines_data,
                reason=str(args.get("reason") or ""),
                notes=str(args.get("notes") or ""),
            )
        audit(
            "create",
            "PurchaseReturn",
            purchase_return.id,
            {"purchase_number": purchase.purchase_number, "product": product_name},
        )
        total = float(purchase_return.total_amount or 0)
        return ActionResult(
            True,
            f"تم إنشاء مرتجع المشتريات {purchase_return.return_number} "
            f"لفاتورة {purchase.purchase_number} (الإجمالي: {total:,.2f} درهم)",
            {"return_id": purchase_return.id, "return_number": purchase_return.return_number, "total": total},
            "purchase_return_create",
            PERMISSION,
        )
    except ValueError as ve:
        return ActionResult(False, str(ve))
    except Exception as e:
        return pack_error("create_purchase_return", e, args)


def _purchase_return_details(args: dict) -> ActionResult:
    try:
        from extensions import db
        from models import PurchaseReturn

        tid, guard = tenant_guard()
        if guard:
            return guard
        number = str(args.get("return_number") or "").strip()
        return_id = args.get("return_id")
        if return_id:
            record = db.session.get(PurchaseReturn, int(return_id))
            if record is not None and int(getattr(record, "tenant_id", -1)) != int(tid):
                record = None
        elif number:
            record = PurchaseReturn.query.filter_by(tenant_id=tid, return_number=number).first()
        else:
            records = (
                PurchaseReturn.query.filter_by(tenant_id=tid).order_by(PurchaseReturn.created_at.desc()).limit(20).all()
            )
            data = [
                {
                    "id": r.id,
                    "number": r.return_number,
                    "purchase_id": r.purchase_id,
                    "total": float(r.total_amount or 0),
                    "reason": r.reason,
                }
                for r in records
            ]
            return ActionResult(
                True,
                f"آخر {len(data)} مردود مشتريات",
                {"returns": data, "count": len(data)},
                "purchase_return_list",
                PERMISSION,
            )
        if record is None:
            return ActionResult(False, "⚠️ مرتجع المشتريات غير موجود في منشأتك — تحقق من الرقم")
        lines = [
            {
                "product": line.product.name if getattr(line, "product", None) else "",
                "quantity": float(line.quantity or 0),
                "unit_cost": float(line.unit_cost or 0),
                "total": float(line.line_total or 0),
            }
            for line in (record.lines or [])
        ]
        return ActionResult(
            True,
            f"مرتجع المشتريات {record.return_number}: {len(lines)} بند (الإجمالي: {float(record.total_amount or 0):,.2f} درهم)",
            {
                "id": record.id,
                "number": record.return_number,
                "purchase_id": record.purchase_id,
                "total": float(record.total_amount or 0),
                "reason": record.reason,
                "lines": lines,
            },
            "purchase_return_details",
            PERMISSION,
        )
    except Exception as e:
        return pack_error("purchase_return_details", e, args)


def register(register_fn) -> None:
    """Register this pack's actions on the dispatcher registry."""
    register_fn(
        "create_purchase_return", _create_purchase_return, PERMISSION, "إنشاء مرتجع مشتريات", confirm_required=True
    )
    register_fn("purchase_return_details", _purchase_return_details, PERMISSION, "عرض مردودات المشتريات")
