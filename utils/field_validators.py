"""
Lightweight field validators for write paths — no DB constraints in this module.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from utils.constants import (
    PAYMENT_METHOD_CODES,
    PAYMENT_TYPES,
    SALE_PAYMENT_STATUSES,
    STOCK_MOVEMENT_TYPES,
    normalize_payment_method_code,
)
from utils.gl_reference_types import LEGACY_REF_MAP, normalize_ref_type

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_PHONE_MAX_LEN = 50
_PHONE_ALLOWED_RE = re.compile(r"^[\d\s+\-().#/]+$")
_USER_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# sale.status values observed in DB + constants
# pending is required for deferred online-store checkout flow before fulfillment.
ALLOWED_SALE_STATUSES = frozenset({"pending", "confirmed", "cancelled", "completed"})
ALLOWED_PAYMENT_TYPES = frozenset(PAYMENT_TYPES) | frozenset({"sale"})  # legacy read
CANONICAL_PAYMENT_TYPE_SALE = "sale_payment"
PAYMENT_TYPE_LEGACY_WRITE = {"sale": CANONICAL_PAYMENT_TYPE_SALE}

ALLOWED_STOCK_MOVEMENT_TYPES = frozenset(t[0] for t in STOCK_MOVEMENT_TYPES) | frozenset(
    {"transfer", "test_store_setup"}
)

_GL_SIDE_TOLERANCE = Decimal("0.01")


class FieldValidationError(ValueError):
    """Invalid user/service input for a canonical field."""


def validate_currency_code(value: Optional[str], *, field_label: str = "currency") -> str:
    if value is None or not str(value).strip():
        raise FieldValidationError(f"{field_label}: العملة مطلوبة.")
    code = str(value).strip().upper()
    if not _CURRENCY_RE.match(code):
        raise FieldValidationError(f"{field_label}: يجب أن تكون رمز ISO من 3 أحرف (مثل AED).")
    return code


def normalize_user_email_required(value: Optional[str]) -> str:
    if value is None or not str(value).strip():
        raise FieldValidationError(
            "البريد الإلكتروني مطلوب. / Email is required.\n"
            "مثال: ahmed@example.com"
        )
    email = str(value).strip().lower()
    if len(email) > 254:
        raise FieldValidationError("البريد الإلكتروني طويل جداً. / Email exceeds maximum length.")
    if not _USER_EMAIL_RE.match(email):
        raise FieldValidationError(
            "البريد الإلكتروني غير صحيح. / Invalid email format.\n"
            "مثال: ahmed@example.com"
        )
    return email


def normalize_phone_optional(value: Optional[str], *, field_label: str = "phone") -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > _PHONE_MAX_LEN:
        raise FieldValidationError(f"{field_label}: الطول الأقصى {_PHONE_MAX_LEN} حرفاً.")
    if not _PHONE_ALLOWED_RE.match(text):
        raise FieldValidationError(
            f"{field_label}: أحرف غير مسموحة (استخدم أرقاماً و + - مسافات فقط)."
        )
    return text


def validate_sale_status(value: Optional[str], *, allow_none: bool = False) -> Optional[str]:
    if value is None or not str(value).strip():
        if allow_none:
            return None
        raise FieldValidationError("حالة الفاتورة غير صالحة.")
    status = str(value).strip().lower()
    if status not in ALLOWED_SALE_STATUSES:
        raise FieldValidationError(f"حالة الفاتورة غير مدعومة: {value}")
    return status


def validate_sale_payment_status(value: Optional[str]) -> str:
    if value is None or not str(value).strip():
        raise FieldValidationError("حالة الدفع غير صالحة.")
    status = str(value).strip().lower()
    if status not in SALE_PAYMENT_STATUSES:
        raise FieldValidationError(f"حالة الدفع غير مدعومة: {value}")
    return status


def canonical_payment_type(value: Optional[str], *, for_new: bool = True) -> str:
    """Map legacy 'sale' to sale_payment on new writes; accept both when reading."""
    raw = (value or "").strip()
    if not raw:
        raise FieldValidationError("نوع الدفعة مطلوب.")
    if for_new and raw in PAYMENT_TYPE_LEGACY_WRITE:
        raw = PAYMENT_TYPE_LEGACY_WRITE[raw]
    if raw not in ALLOWED_PAYMENT_TYPES:
        raise FieldValidationError(f"نوع الدفعة غير مدعوم: {value}")
    return raw


def validate_payment_method(value: Optional[str]) -> str:
    method = normalize_payment_method_code(value)
    if not method or method not in PAYMENT_METHOD_CODES:
        raise FieldValidationError(f"طريقة الدفع غير مدعومة: {value}")
    return method


def validate_stock_movement_type(value: Optional[str]) -> str:
    if value is None or not str(value).strip():
        raise FieldValidationError("نوع حركة المخزون مطلوب.")
    mtype = str(value).strip().lower()
    if mtype not in ALLOWED_STOCK_MOVEMENT_TYPES:
        raise FieldValidationError(f"نوع حركة المخزون غير مدعوم: {value}")
    return mtype


def validate_reference_type_write(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return value
    normalized = normalize_ref_type(str(value).strip()) or str(value).strip()
    # Prefer PascalCase canonical from GLRef when legacy maps exist
    if normalized in LEGACY_REF_MAP.values():
        return normalized
    return normalized


def validate_gl_line_sides(
    debit,
    credit,
    *,
    tolerance: Decimal | None = None,
) -> None:
    """Reject new GL lines with both sides materially non-zero or both zero."""
    tol = tolerance if tolerance is not None else _GL_SIDE_TOLERANCE
    d = Decimal(str(debit or 0))
    c = Decimal(str(credit or 0))
    if d <= 0 and c <= 0:
        raise FieldValidationError("سطر القيد: يجب أن يحتوي على مبلغ مدين أو دائن.")
    if d > tol and c > tol:
        raise FieldValidationError(
            "سطر القيد: لا يجوز أن يكون المدين والدائن كلاهما أكبر من صفر في نفس السطر."
        )
