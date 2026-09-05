"""Sale-return action pack — RMA via ReturnService.

Independent domain module: handlers + command patterns + help lines live
here and are wired by ``ai_knowledge.actions``. The service validates
quantities, tenant/branch/seller scope, and posts GL + stock reversal
internally; the pack only resolves the sale/line and wraps the call in
``atomic_transaction``. Permission mirror of routes/returns.py:
``manage_sales``.
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

PERMISSION = "manage_sales"

HELP_LINES = [
    "↩️ **المرتجعات:** `مرتجع: رقم الفاتورة, المنتج, الكمية` | `عرض المرتجعات`",
]


def _parse_return_command(body: str) -> tuple[str, dict[str, Any]] | None:
    parts = [p.strip() for p in body.split(",")]
    sale_ref = parts[0] if len(parts) > 0 else ""
    product = parts[1] if len(parts) > 1 else ""
    qty_match = re.search(r"\d+(?:\.\d+)?", parts[2]) if len(parts) > 2 else None
    condition_raw = (parts[3] if len(parts) > 3 else "").strip()
    condition = "damaged" if condition_raw in ("تالف", "تالفة", "damaged", "defective") else "good"
    args: dict[str, Any] = {"product_name": product, "condition": condition}
    if sale_ref.isdigit():
        args["sale_id"] = int(sale_ref)
    else:
        args["sale_number"] = sale_ref
    args["quantity"] = float(qty_match.group()) if qty_match else 1
    return "create_sale_return", args


def _parse_list_returns(_match: re.Match) -> tuple[str, dict[str, Any]] | None:
    return "list_returns", {}


PATTERNS = [
    (
        re.compile(r"^(مرتجع|مرتجعات|إرجاع|استرجاع|return|rma)\s*[:：=]\s*(.+)$", re.IGNORECASE),
        lambda m: _parse_return_command(m.group(2)),
    ),
    (
        re.compile(r"^(عرض|ارني|شوف|show|list)\s*(كل\s*)?(المرتجعات|مرتجعات|المرتجع|returns|rma)", re.IGNORECASE),
        _parse_list_returns,
    ),
]


def _resolve_sale(tid: int, args: dict):
    """Tenant-scoped sale by id or number (or None)."""
    from extensions import db
    from models import Sale

    sale_id = args.get("sale_id")
    if sale_id:
        sale = db.session.get(Sale, int(sale_id))
        if sale is not None and int(getattr(sale, "tenant_id", -1)) == int(tid):
            return sale
        return None
    sale_number = str(args.get("sale_number") or "").strip()
    if not sale_number:
        return None
    return Sale.query.filter_by(tenant_id=tid, sale_number=sale_number).first()


def _create_sale_return(args: dict) -> ActionResult:
    product_name = str(args.get("product_name") or "").strip()
    if not product_name:
        return ActionResult(False, "يرجى إدخال اسم المنتج المرتجع")
    try:
        from services.return_service import ReturnService

        tid, guard = tenant_guard()
        if guard:
            return guard
        sale = _resolve_sale(tid, args)
        if sale is None:
            return ActionResult(
                False,
                "⚠️ الفاتورة غير موجودة في منشأتك — تحقق من الرقم أو اطلب «عرض الفواتير»",
            )
        if getattr(sale, "status", "") in ("cancelled", "pending"):
            return ActionResult(False, f"⚠️ لا يمكن إنشاء مرتجع لفاتورة بحالة «{sale.status}»")
        safe = escape_like(product_name).lower()
        line = next(
            (
                sale_line
                for sale_line in (sale.lines or [])
                if safe in (getattr(sale_line.product, "name", "") or "").lower()
            ),
            None,
        )
        if line is None:
            return ActionResult(
                False,
                f"⚠️ المنتج «{product_name}» غير موجود في الفاتورة {sale.sale_number} — تحقق من الاسم",
            )
        user = actor()
        return_lines = [
            {
                "sale_line_id": line.id,
                "quantity": float(args.get("quantity", 1)),
                "condition": args.get("condition") or "good",
            }
        ]
        with atomic_transaction("ai_create_sale_return"):
            product_return = ReturnService.create_return(
                sale_id=sale.id,
                return_lines_data=return_lines,
                user=user,
                notes=str(args.get("notes") or ""),
            )
        audit(
            "create",
            "ProductReturn",
            product_return.id,
            {"sale_number": sale.sale_number, "product": product_name},
        )
        refund = float(product_return.refund_amount or product_return.total_amount or 0)
        return ActionResult(
            True,
            f"تم إنشاء المرتجع {product_return.return_number} للفاتورة {sale.sale_number} "
            f"(المبلغ المسترد: {refund:,.2f} درهم)",
            {"return_id": product_return.id, "return_number": product_return.return_number},
            "sale_return_create",
            PERMISSION,
        )
    except ValueError as ve:
        return ActionResult(False, str(ve))
    except Exception as e:
        return pack_error("create_sale_return", e, args)


def _list_returns(args: dict) -> ActionResult:
    try:
        from models import ProductReturn

        tid, guard = tenant_guard()
        if guard:
            return guard
        returns = ProductReturn.query.filter_by(tenant_id=tid).order_by(ProductReturn.created_at.desc()).limit(20).all()
        data = [
            {
                "id": r.id,
                "number": r.return_number,
                "sale_id": r.sale_id,
                "total": float(r.total_amount or 0),
                "refund": float(r.refund_amount or 0),
                "status": r.status,
            }
            for r in returns
        ]
        return ActionResult(
            True,
            f"آخر {len(data)} مرتجع",
            {"returns": data, "count": len(data)},
            "sale_return_list",
            PERMISSION,
        )
    except Exception as e:
        return pack_error("list_returns", e, args)


def register(register_fn) -> None:
    """Register this pack's actions on the dispatcher registry."""
    register_fn("create_sale_return", _create_sale_return, PERMISSION, "إنشاء مرتجع مبيعات", confirm_required=True)
    register_fn("list_returns", _list_returns, PERMISSION, "عرض المرتجعات")
