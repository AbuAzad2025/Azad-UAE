"""Cheque action pack — register/list cheques via ChequeService.

Independent domain module: handlers + command patterns + help lines live
here and are wired by ``ai_knowledge.actions``. Mutations go exclusively
through ``ChequeService`` inside ``atomic_transaction``; reads use the
service's tenant-scoped queries. Permission mirror of routes/cheques.py:
``manage_payments``.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from ai_knowledge.actions.base import (
    ActionResult,
    actor,
    atomic_transaction,
    audit,
    escape_like,
    pack_error,
    resolve_customer,
    resolve_supplier,
    tenant_guard,
)

PERMISSION = "manage_payments"

HELP_LINES = [
    "🧾 **الشيكات:** `شيك: الرقم, المبلغ, وارد/صادر, البنك, التاريخ` | `عرض الشيكات`",
]

_CHEQUE_TYPE_WORDS = {
    "وارد": "incoming",
    "واردة": "incoming",
    "incoming": "incoming",
    "received": "incoming",
    "صادر": "outgoing",
    "صادرة": "outgoing",
    "outgoing": "outgoing",
    "issued": "outgoing",
}


def _parse_cheque_command(body: str) -> tuple[str, dict[str, Any]] | None:
    parts = [p.strip() for p in body.split(",")]
    number = parts[0] if len(parts) > 0 else ""
    amount_raw = parts[1] if len(parts) > 1 else ""
    type_raw = (parts[2] if len(parts) > 2 else "").strip().lower()
    bank = parts[3] if len(parts) > 3 else ""
    due = parts[4] if len(parts) > 4 else ""
    amount_match = re.search(r"[\d.]+", amount_raw or "")
    cheque_type = _CHEQUE_TYPE_WORDS.get(type_raw, "")
    return (
        "create_cheque",
        {
            "cheque_number": number,
            "amount": float(amount_match.group()) if amount_match else 0,
            "cheque_type": cheque_type,
            "bank_name": bank,
            "due_date": due,
        },
    )


def _parse_list_cheques(_match: re.Match) -> tuple[str, dict[str, Any]] | None:
    return "list_cheques", {}


PATTERNS = [
    (re.compile(r"^(شيك|cheque|check)\s*[:：=]\s*(.+)$", re.IGNORECASE), lambda m: _parse_cheque_command(m.group(2))),
    (
        re.compile(r"^(عرض|ارني|شوف|show|list)\s*(كل\s*)?(الشيكات|شيكات|cheques|checks)", re.IGNORECASE),
        _parse_list_cheques,
    ),
]


def _create_cheque(args: dict) -> ActionResult:
    number = str(args.get("cheque_number") or "").strip()
    if not number:
        return ActionResult(False, "يرجى إدخال رقم الشيك")
    try:
        from models import Cheque
        from services.cheque_service import ChequeService

        tid, guard = tenant_guard()
        if guard:
            return guard
        existing = Cheque.query.filter_by(tenant_id=tid, cheque_number=number).first()
        if existing is not None and isinstance(getattr(existing, "id", None), int):
            return ActionResult(
                False,
                f"⚠️ الشيك رقم «{number}» مسجل مسبقاً (#{existing.id}) — تحقق من الرقم قبل التسجيل مجدداً",
                {"id": existing.id, "cheque_number": number},
            )
        cheque_type = args.get("cheque_type") or "incoming"
        try:
            due_date = datetime.strptime(str(args.get("due_date") or ""), "%Y-%m-%d")
        except ValueError:
            return ActionResult(False, "⚠️ تاريخ الاستحقاق غير صالح — الصيغة المطلوبة YYYY-MM-DD (مثال: 2026-12-31)")
        customer = resolve_customer(tid, str(args.get("customer_name") or "")) if args.get("customer_name") else None
        supplier = resolve_supplier(tid, str(args.get("supplier_name") or "")) if args.get("supplier_name") else None
        user = actor()
        with atomic_transaction("ai_create_cheque"):
            cheque = ChequeService.create_cheque(
                cheque_number=number,
                cheque_bank_number=number,
                cheque_type=cheque_type,
                bank_name=str(args.get("bank_name") or ""),
                amount=Decimal(str(args.get("amount", 0))),
                currency="AED",
                due_date=due_date,
                issue_date=datetime.now(),
                customer_id=customer.id if customer else None,
                supplier_id=supplier.id if supplier else None,
                notes=str(args.get("notes") or ""),
                user_id=getattr(user, "id", None),
                branch_id=getattr(user, "branch_id", None),
                tenant_id=tid,
            )
            from extensions import db

            db.session.flush()
        audit("create", "Cheque", cheque.id, {"number": number, "amount": float(args.get("amount", 0) or 0)})
        kind = "وارد" if cheque_type == "incoming" else "صادر"
        return ActionResult(
            True,
            f"تم تسجيل الشيك {kind} رقم {number} بقيمة {float(args.get('amount', 0) or 0):,.2f} درهم",
            {"id": cheque.id, "cheque_number": number},
            "cheque_create",
            PERMISSION,
        )
    except Exception as e:
        return pack_error("create_cheque", e, args)


def _list_cheques(args: dict) -> ActionResult:
    try:
        from models import Cheque
        from services.cheque_service import ChequeService

        tid, guard = tenant_guard()
        if guard:
            return guard
        query = ChequeService.scoped_cheques_query(tenant_id=tid)
        search = str(args.get("search") or "").strip()
        if search:
            query = query.filter(Cheque.cheque_number.ilike(f"%{escape_like(search)}%", escape="\\"))
        status = str(args.get("status") or "").strip()
        if status:
            query = query.filter(Cheque.status == status)
        cheque_type = str(args.get("cheque_type") or "").strip()
        if cheque_type:
            query = query.filter(Cheque.cheque_type == cheque_type)
        cheques = query.order_by(Cheque.due_date.desc()).limit(20).all()
        data = [
            {
                "id": c.id,
                "number": c.cheque_number,
                "type": c.cheque_type,
                "amount": float(c.amount or 0),
                "bank": c.bank_name,
                "status": c.status,
                "due": c.due_date.strftime("%Y-%m-%d") if c.due_date else None,
            }
            for c in cheques
        ]
        return ActionResult(
            True,
            f"تم العثور على {len(data)} شيك",
            {"cheques": data, "count": len(data)},
            "cheque_list",
            PERMISSION,
        )
    except Exception as e:
        return pack_error("list_cheques", e, args)


def register(register_fn) -> None:
    """Register this pack's actions on the dispatcher registry."""
    register_fn("create_cheque", _create_cheque, PERMISSION, "تسجيل شيك جديد", confirm_required=True)
    register_fn("list_cheques", _list_cheques, PERMISSION, "عرض الشيكات")
