"""Server-side parked POS cart service (Phase 2 — concurrent tabs).

All multi-step writes here rely on the caller wrapping the call in
``atomic_transaction`` at the route boundary; this module only flushes.
Every query is tenant-scoped via ``tenant_query`` and additionally
restricted to the owning cashier (``user_id``) and their open session.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from models import PosCart
from utils.tenanting import get_active_tenant_id, tenant_query

_AED_QUANTUM = Decimal("0.001")

# Payload keys persisted on park — anything else is dropped to keep
# parked-cart rows compact.
_ALLOWED_PAYLOAD_KEYS = (
    "lines",
    "customer_id",
    "warehouse_id",
    "currency",
    "exchange_rate",
    "order_type",
    "notes",
    "discount_amount",
    "shipping_cost",
    "tax_rate",
    "quick_customer",
    "table_id",
)


class PosCartConflictError(Exception):
    """Raised when a parked cart was already resumed/expired (double-resume)."""


class PosCartService:
    MAX_CARTS_PER_SESSION = 25
    MAX_LIST_LIMIT = 50
    MAX_PAYLOAD_BYTES = 48 * 1024

    @staticmethod
    def _sanitize_payload(payload: dict) -> tuple[dict, int, Decimal]:
        if not isinstance(payload, dict):
            raise ValueError("بيانات السلة غير صالحة.")
        clean = {key: payload[key] for key in _ALLOWED_PAYLOAD_KEYS if key in payload}

        lines = clean.get("lines") or []
        if not isinstance(lines, list) or not lines:
            raise ValueError("لا يمكن ركن سلة فارغة — أضف منتجات أولاً.")

        item_count = 0
        total = Decimal("0")
        for row in lines:
            if not isinstance(row, dict):
                raise ValueError("بيانات السلة غير صالحة.")
            qty = Decimal(str(row.get("quantity") or "0"))
            if qty <= 0:
                raise ValueError("الكمية يجب أن تكون أكبر من صفر.")
            price_raw = row.get("unit_price")
            price = Decimal(str(price_raw)) if price_raw not in (None, "") else Decimal("0")
            discount = Decimal(str(row.get("discount_percent") or "0"))
            line_total = (qty * price * (Decimal("100") - discount) / Decimal("100")).quantize(
                _AED_QUANTUM, rounding=ROUND_HALF_UP
            )
            total += line_total
            item_count += 1

        blob = json.dumps(clean, ensure_ascii=False, default=str)
        if len(blob.encode("utf-8")) > PosCartService.MAX_PAYLOAD_BYTES:
            raise ValueError("حجم السلة كبير جداً — قلّل عدد الأصناف أو الملاحظات.")
        return clean, item_count, total

    @staticmethod
    def _own_cart_query(user):
        return tenant_query(PosCart, user=user).filter(PosCart.user_id == user.id)

    @staticmethod
    def park_cart(*, user, session, payload: dict, label: str | None = None, cart_id=None) -> PosCart:
        """Create or update a parked cart for the cashier's open session."""
        if not session:
            raise ValueError("لا توجد جلسة كاشير مفتوحة. يرجى فتح جلسة أولاً.")
        tenant_id = get_active_tenant_id(user)
        if not tenant_id:
            raise ValueError("لا توجد شركة نشطة.")

        clean, item_count, total = PosCartService._sanitize_payload(payload)
        label = (label or "").strip()[:120] or None
        currency = (clean.get("currency") or "").strip().upper()[:3] or None

        if cart_id:
            cart = PosCartService._own_cart_query(user).filter(PosCart.id == int(cart_id)).first()
            if cart is None:
                raise LookupError("السلة غير موجودة.")
            cart.payload = clean
            cart.label = label
            cart.item_count = item_count
            cart.total_estimate = total
            cart.currency = currency
            cart.session_id = session.id
            cart.status = PosCart.STATUS_PARKED
            cart.resumed_at = None
            cart.parked_at = datetime.now(timezone.utc)
            db.session.flush()
            return cart

        parked_count = (
            PosCartService._own_cart_query(user)
            .filter(PosCart.session_id == session.id, PosCart.status == PosCart.STATUS_PARKED)
            .count()
        )
        if parked_count >= PosCartService.MAX_CARTS_PER_SESSION:
            raise ValueError(
                f"وصلت للحد الأقصى من السلات المركونة ({PosCartService.MAX_CARTS_PER_SESSION}). استرجع أو احذف سلة أولاً."
            )

        cart = PosCart(
            tenant_id=int(tenant_id),
            session_id=session.id,
            user_id=user.id,
            label=label,
            status=PosCart.STATUS_PARKED,
            payload=clean,
            item_count=item_count,
            total_estimate=total,
            currency=currency,
        )
        db.session.add(cart)
        db.session.flush()
        return cart

    @staticmethod
    def list_carts(*, user, session, limit: int = 25) -> list[PosCart]:
        """Parked carts for the cashier's current session — summaries only."""
        if not session:
            return []
        limit = max(1, min(int(limit or 25), PosCartService.MAX_LIST_LIMIT))
        return (
            PosCartService._own_cart_query(user)
            .filter(PosCart.session_id == session.id, PosCart.status == PosCart.STATUS_PARKED)
            .order_by(PosCart.updated_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def resume_cart(*, user, cart_id) -> PosCart:
        """Atomically mark a parked cart as resumed.

        The row is locked (``with_for_update``) and the status transition is
        checked under the lock, so two terminals cannot resume the same cart.
        """
        cart = PosCartService._own_cart_query(user).filter(PosCart.id == int(cart_id)).with_for_update().first()
        if cart is None:
            raise LookupError("السلة غير موجودة.")
        if cart.status != PosCart.STATUS_PARKED:
            raise PosCartConflictError("تم استرجاع هذه السلة مسبقاً أو انتهت صلاحيتها.")
        cart.status = PosCart.STATUS_RESUMED
        cart.resumed_at = datetime.now(timezone.utc)
        db.session.flush()
        return cart

    @staticmethod
    def void_line(*, user, cart_id, product_id) -> PosCart:
        """Remove a single line from a parked cart (Phase 3 — supervisor-gated
        at the route boundary). Totals are recomputed from the payload."""
        cart = PosCartService._own_cart_query(user).filter(PosCart.id == int(cart_id)).first()
        if cart is None:
            raise LookupError("السلة غير موجودة.")
        if cart.status != PosCart.STATUS_PARKED:
            raise PosCartConflictError("لا يمكن تعديل سلة تم استرجاعها أو انتهت صلاحيتها.")
        payload = dict(cart.payload or {})
        lines = list(payload.get("lines") or [])
        remaining = [row for row in lines if int(row.get("product_id") or 0) != int(product_id or 0)]
        if len(remaining) == len(lines):
            raise LookupError("الصنف غير موجود في السلة.")
        if not remaining:
            raise ValueError("لا يمكن إفراغ السلة بالكامل عبر الإلغاء — احذف السلة بدلاً من ذلك.")
        payload["lines"] = remaining
        clean, item_count, total = PosCartService._sanitize_payload(payload)
        cart.payload = clean
        cart.item_count = item_count
        cart.total_estimate = total
        db.session.flush()
        return cart

    @staticmethod
    def delete_cart(*, user, cart_id) -> None:
        cart = PosCartService._own_cart_query(user).filter(PosCart.id == int(cart_id)).first()
        if cart is None:
            raise LookupError("السلة غير موجودة.")
        db.session.delete(cart)
        db.session.flush()
