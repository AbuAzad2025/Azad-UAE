"""Cheque-lifecycle action pack — deposit/clear/bounce via ChequeService.

Independent domain module: handlers + command patterns + help lines live
here and are wired by ``ai_knowledge.actions``. Every transition reuses the
service's own processors (``process_cheque_deposit`` / ``process_cheque_clear``
/ ``process_cheque_bounce``) with their state-machine validation, GL
postings, idempotency guards, and bounce-fee logic — the pack only resolves
the cheque tenant-scoped and wraps the call in ``atomic_transaction``.
Permission mirror of routes/cheques.py: ``manage_payments``.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ai_knowledge.actions.base import (
    ActionResult,
    atomic_transaction,
    audit,
    pack_error,
    tenant_guard,
)

PERMISSION = "manage_payments"

HELP_LINES = [
    "🏦 **دورة الشيكات:** `إيداع شيك: الرقم` | `تحصيل شيك: الرقم` | `ارتداد شيك: الرقم, السبب`",
]


def _parse_deposit(body: str) -> tuple[str, dict[str, Any]] | None:
    parts = [p.strip() for p in body.split(",")]
    args: dict[str, Any] = {"cheque_number": parts[0] if parts else ""}
    if len(parts) > 1 and parts[1]:
        args["deposit_date"] = parts[1]
    return "deposit_cheque", args


def _parse_clear(body: str) -> tuple[str, dict[str, Any]] | None:
    parts = [p.strip() for p in body.split(",")]
    args: dict[str, Any] = {"cheque_number": parts[0] if parts else ""}
    if len(parts) > 1 and parts[1]:
        args["clearance_date"] = parts[1]
    rate_match = re.search(r"[\d.]+", parts[2]) if len(parts) > 2 else None
    if rate_match:
        args["clearance_exchange_rate"] = float(rate_match.group())
    return "clear_cheque", args


def _parse_bounce(body: str) -> tuple[str, dict[str, Any]] | None:
    parts = [p.strip() for p in body.split(",")]
    args: dict[str, Any] = {
        "cheque_number": parts[0] if parts else "",
        "reason": parts[1] if len(parts) > 1 else "",
    }
    fee_match = re.search(r"[\d.]+", parts[2]) if len(parts) > 2 else None
    if fee_match:
        args["bounce_fee"] = float(fee_match.group())
    return "bounce_cheque", args


PATTERNS = [
    (
        re.compile(r"^(إيداع\s*شيك|ايداع\s*شيك|deposit\s*cheque|deposit)\s*[:：=]\s*(.+)$", re.IGNORECASE),
        lambda m: _parse_deposit(m.group(2)),
    ),
    (
        re.compile(
            r"^(تحصيل\s*شيك|صرف\s*شيك|تخليص\s*شيك|clear\s*cheque|clear)\s*[:：=]\s*(.+)$",
            re.IGNORECASE,
        ),
        lambda m: _parse_clear(m.group(2)),
    ),
    (
        re.compile(r"^(ارتداد\s*شيك|رفض\s*شيك|رجوع\s*شيك|bounce\s*cheque|bounce)\s*[:：=]\s*(.+)$", re.IGNORECASE),
        lambda m: _parse_bounce(m.group(2)),
    ),
]


def _resolve_cheque(tid: int, cheque_number: str):
    """Tenant-scoped cheque by number (or None)."""
    from models import Cheque

    number = (cheque_number or "").strip()
    if not number:
        return None
    return Cheque.query.filter_by(tenant_id=tid, cheque_number=number).first()


def _parse_date(value: str, field_label: str) -> tuple[Any, ActionResult | None]:
    text = (value or "").strip()
    if not text:
        return None, None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date(), None
    except ValueError:
        return None, ActionResult(
            False,
            f"⚠️ {field_label} غير صالح — الصيغة المطلوبة YYYY-MM-DD (مثال: 2026-12-31)",
        )


def _deposit_cheque(args: dict) -> ActionResult:
    try:
        from services.cheque_service import process_cheque_deposit

        tid, guard = tenant_guard()
        if guard:
            return guard
        cheque = _resolve_cheque(tid, str(args.get("cheque_number") or ""))
        if cheque is None:
            return ActionResult(False, "⚠️ الشيك غير موجود في منشأتك — تحقق من الرقم")
        deposit_date, error = _parse_date(str(args.get("deposit_date") or ""), "تاريخ الإيداع")
        if error:
            return error
        with atomic_transaction("ai_deposit_cheque"):
            process_cheque_deposit(cheque, deposit_date)
        audit("deposit", "Cheque", cheque.id, {"number": cheque.cheque_number})
        return ActionResult(
            True,
            f"تم إيداع الشيك رقم {cheque.cheque_number} في البنك (تحت التحصيل)",
            {"id": cheque.id, "cheque_number": cheque.cheque_number},
            "cheque_deposit",
            PERMISSION,
        )
    except ValueError as ve:
        return ActionResult(False, str(ve))
    except Exception as e:
        return pack_error("deposit_cheque", e, args)


def _clear_cheque(args: dict) -> ActionResult:
    try:
        from services.cheque_service import process_cheque_clear

        tid, guard = tenant_guard()
        if guard:
            return guard
        cheque = _resolve_cheque(tid, str(args.get("cheque_number") or ""))
        if cheque is None:
            return ActionResult(False, "⚠️ الشيك غير موجود في منشأتك — تحقق من الرقم")
        clearance_date, error = _parse_date(str(args.get("clearance_date") or ""), "تاريخ التحصيل")
        if error:
            return error
        with atomic_transaction("ai_clear_cheque"):
            process_cheque_clear(cheque, clearance_date, args.get("clearance_exchange_rate"))
        audit("clear", "Cheque", cheque.id, {"number": cheque.cheque_number})
        gain_loss = float(getattr(cheque, "currency_gain_loss", 0) or 0)
        extra = f" (فرق عملة: {gain_loss:+.2f})" if abs(gain_loss) > 0.01 else ""
        return ActionResult(
            True,
            f"تم تأكيد تحصيل الشيك رقم {cheque.cheque_number} وإغلاق الالتزام{extra}",
            {"id": cheque.id, "cheque_number": cheque.cheque_number},
            "cheque_clear",
            PERMISSION,
        )
    except ValueError as ve:
        return ActionResult(False, str(ve))
    except Exception as e:
        return pack_error("clear_cheque", e, args)


def _bounce_cheque(args: dict) -> ActionResult:
    reason = str(args.get("reason") or "").strip()
    if not reason:
        return ActionResult(False, "⚠️ سبب الارتداد إلزامي — أعد الإرسال مع ذكر السبب")
    try:
        from services.cheque_service import process_cheque_bounce

        tid, guard = tenant_guard()
        if guard:
            return guard
        cheque = _resolve_cheque(tid, str(args.get("cheque_number") or ""))
        if cheque is None:
            return ActionResult(False, "⚠️ الشيك غير موجود في منشأتك — تحقق من الرقم")
        fee = args.get("bounce_fee")
        with atomic_transaction("ai_bounce_cheque"):
            process_cheque_bounce(cheque, reason, fee)
        audit("bounce", "Cheque", cheque.id, {"number": cheque.cheque_number, "reason": reason})
        fee_text = f" مع رسوم ارتداد {float(fee):,.2f} درهم" if fee else ""
        return ActionResult(
            True,
            f"تم تسجيل ارتداد الشيك رقم {cheque.cheque_number} وإعادة الدين للعميل{fee_text}",
            {"id": cheque.id, "cheque_number": cheque.cheque_number},
            "cheque_bounce",
            PERMISSION,
        )
    except ValueError as ve:
        return ActionResult(False, str(ve))
    except Exception as e:
        return pack_error("bounce_cheque", e, args)


def register(register_fn) -> None:
    """Register this pack's actions on the dispatcher registry."""
    register_fn("deposit_cheque", _deposit_cheque, PERMISSION, "إيداع شيك في البنك", confirm_required=True)
    register_fn("clear_cheque", _clear_cheque, PERMISSION, "تأكيد تحصيل شيك", confirm_required=True)
    register_fn("bounce_cheque", _bounce_cheque, PERMISSION, "معالجة شيك مرتد", confirm_required=True)
