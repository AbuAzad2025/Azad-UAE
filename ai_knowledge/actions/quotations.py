"""Quotation action pack — create/list/advance via QuotationService.

Independent domain module: handlers + command patterns + help lines live
here and are wired by ``ai_knowledge.actions``. All transitions
(send/accept/reject/convert) reuse the service's own state machine, so
invalid transitions fail with the service's message instead of corrupt
state. Permission mirror of routes/quotations.py: ``manage_sales``.
"""

from __future__ import annotations

import re
from typing import Any

from ai_knowledge.actions.base import (
    ActionResult,
    actor,
    atomic_transaction,
    audit,
    pack_error,
    resolve_customer,
    resolve_product,
    tenant_guard,
)

PERMISSION = "manage_sales"

HELP_LINES = [
    "📝 **عروض الأسعار:** `عرض سعر: العميل, المنتج, الكمية` | `عرض عروض الأسعار` | `قبول عرض: الرقم`",
]

_TARGET_VERBS = {
    "تقديم": "sent",
    "ارسال": "sent",
    "إرسال": "sent",
    "send": "sent",
    "قبول": "accepted",
    "accept": "accepted",
    "اعتماد": "accepted",
    "رفض": "rejected",
    "reject": "rejected",
    "تحويل": "converted",
    "convert": "converted",
}

_TARGET_LABELS = {
    "sent": "إرسال",
    "accepted": "قبول",
    "rejected": "رفض",
    "converted": "تحويل لفاتورة",
}


def _parse_quotation_create(body: str) -> tuple[str, dict[str, Any]] | None:
    parts = [p.strip() for p in body.split(",")]
    customer = parts[0] if len(parts) > 0 else ""
    product = parts[1] if len(parts) > 1 else ""
    qty_match = re.search(r"\d+(?:\.\d+)?", parts[2]) if len(parts) > 2 else None
    price_match = re.search(r"[\d.]+", parts[3]) if len(parts) > 3 else None
    line: dict[str, Any] = {"product_name": product}
    line["quantity"] = float(qty_match.group()) if qty_match else 1
    if price_match:
        line["unit_price"] = float(price_match.group())
    return "create_quotation", {"customer_name": customer, "lines": [line]}


def _parse_quotation_advance(match: re.Match) -> tuple[str, dict[str, Any]] | None:
    verb = (match.group(1) or "").strip().lower()
    number = (match.group(3) or "").strip()
    target = _TARGET_VERBS.get(verb, "")
    if not target or not number:
        return None
    return "advance_quotation", {"quotation_number": number, "target": target}


def _parse_list_quotations(_match: re.Match) -> tuple[str, dict[str, Any]] | None:
    return "list_quotations", {}


PATTERNS = [
    (
        re.compile(r"^(عرض\s*سعر|عروض\s*أسعار|quotation|quote)\s*[:：=]\s*(.+)$", re.IGNORECASE),
        lambda m: _parse_quotation_create(m.group(2)),
    ),
    (
        re.compile(
            r"^(تقديم|ارسال|إرسال|send|قبول|اعتماد|accept|رفض|reject|تحويل|convert)\s+(عرض|العرض)\s*[:：=]?\s*(.+)$",
            re.IGNORECASE,
        ),
        _parse_quotation_advance,
    ),
    (
        re.compile(
            r"^(عرض|ارني|شوف|show|list)\s*(كل\s*)?(عروض\s*الأسعار|عروض|العروض|quotations|quotes)", re.IGNORECASE
        ),
        _parse_list_quotations,
    ),
]


def _create_quotation(args: dict) -> ActionResult:
    customer_name = str(args.get("customer_name") or "").strip()
    if not customer_name:
        return ActionResult(False, "يرجى إدخال اسم العميل")
    try:
        from services.quotation_service import QuotationService

        tid, guard = tenant_guard()
        if guard:
            return guard
        user = actor()
        if user is None or getattr(user, "id", None) is None:
            return ActionResult(False, "🚫 لا يمكن إنشاء عرض سعر دون مستخدم موثّق — يرجى تسجيل الدخول")
        customer = resolve_customer(tid, customer_name)
        if customer is None:
            return ActionResult(False, f"⚠️ العميل «{customer_name}» غير موجود — أنشئ العميل أولاً أو تحقق من الاسم")
        lines_data = []
        for raw in args.get("lines") or []:
            product = resolve_product(tid, str(raw.get("product_name") or ""))
            if product is None:
                return ActionResult(
                    False,
                    f"⚠️ المنتج «{raw.get('product_name') or ''}» غير موجود — تحقق من الاسم أو أنشئ المنتج أولاً",
                )
            quantity = float(raw.get("quantity") or 1)
            if quantity <= 0:
                return ActionResult(False, "⚠️ كمية البند يجب أن تكون أكبر من صفر")
            catalog_price = getattr(product, "selling_price", None) or getattr(product, "regular_price", None) or 0
            entry: dict[str, Any] = {
                "product_id": product.id,
                "quantity": quantity,
                "unit_price": float(raw.get("unit_price") if raw.get("unit_price") is not None else catalog_price),
            }
            lines_data.append(entry)
        if not lines_data:
            return ActionResult(False, "يرجى إدخال بند واحد على الأقل (منتج + كمية)")
        with atomic_transaction("ai_create_quotation"):
            quotation = QuotationService.create_quotation(
                {
                    "customer_id": customer.id,
                    "notes": str(args.get("notes") or ""),
                    "lines": lines_data,
                },
                user,
            )
        audit("create", "Quotation", quotation.id, {"customer": customer.name})
        total = float(quotation.total_amount or 0)
        return ActionResult(
            True,
            f"تم إنشاء عرض السعر {quotation.quotation_number} للعميل {customer.name} بقيمة {total:,.2f} درهم",
            {"quotation_id": quotation.id, "quotation_number": quotation.quotation_number, "total": total},
            "quotation_create",
            PERMISSION,
        )
    except Exception as e:
        return pack_error("create_quotation", e, args)


def _list_quotations(args: dict) -> ActionResult:
    try:
        from services.quotation_service import QuotationService

        tid, guard = tenant_guard()
        if guard:
            return guard
        filters = {}
        status = str(args.get("status") or "").strip()
        if status:
            filters["status"] = status
        quotations = QuotationService.list_quotations(tid, filters or None)
        data = [
            {
                "id": q.id,
                "number": q.quotation_number,
                "customer": q.customer.name if getattr(q, "customer", None) else "",
                "total": float(q.total_amount or 0),
                "status": q.status,
            }
            for q in quotations[:20]
        ]
        return ActionResult(
            True,
            f"تم العثور على {len(data)} عرض سعر",
            {"quotations": data, "count": len(data)},
            "quotation_list",
            PERMISSION,
        )
    except Exception as e:
        return pack_error("list_quotations", e, args)


def _advance_quotation(args: dict) -> ActionResult:
    number = str(args.get("quotation_number") or "").strip()
    target = str(args.get("target") or "").strip()
    if not number:
        return ActionResult(False, "يرجى إدخال رقم عرض السعر")
    try:
        from models import Quotation
        from services.quotation_service import QuotationService

        tid, guard = tenant_guard()
        if guard:
            return guard
        quotation = Quotation.query.filter_by(tenant_id=tid, quotation_number=number).first()
        if quotation is None:
            return ActionResult(False, f"⚠️ عرض السعر «{number}» غير موجود في منشأتك")
        user = actor()
        label = _TARGET_LABELS.get(target, target)
        with atomic_transaction("ai_advance_quotation"):
            if target == "sent":
                QuotationService.send_quotation(quotation)
                message = f"تم إرسال عرض السعر {number} للعميل"
            elif target == "accepted":
                QuotationService.accept_quotation(quotation)
                message = f"تم قبول عرض السعر {number}"
            elif target == "rejected":
                QuotationService.reject_quotation(quotation)
                message = f"تم رفض عرض السعر {number}"
            elif target == "converted":
                if user is None or getattr(user, "id", None) is None:
                    return ActionResult(False, "🚫 لا يمكن التحويل لفاتورة دون مستخدم موثّق")
                sale = QuotationService.convert_to_sale(quotation, user)
                message = f"تم تحويل عرض السعر {number} إلى فاتورة رقم {sale.sale_number}"
            else:
                return ActionResult(False, f"⚠️ خطوة غير معروفة «{target}» — المتاح: إرسال/قبول/رفض/تحويل")
        audit("update", "Quotation", quotation.id, {"advance": target})
        return ActionResult(
            True,
            message,
            {"quotation_id": quotation.id, "quotation_number": number, "target": target},
            "quotation_advance",
            PERMISSION,
        )
    except ValueError as ve:
        return ActionResult(False, f"⚠️ تعذّر {label} العرض {number}: {ve}")
    except Exception as e:
        return pack_error("advance_quotation", e, args)


def register(register_fn) -> None:
    """Register this pack's actions on the dispatcher registry."""
    register_fn("create_quotation", _create_quotation, PERMISSION, "إنشاء عرض سعر", confirm_required=True)
    register_fn("list_quotations", _list_quotations, PERMISSION, "عرض عروض الأسعار")
    register_fn(
        "advance_quotation", _advance_quotation, PERMISSION, "تقديم/قبول/رفض/تحويل العرض", confirm_required=True
    )
