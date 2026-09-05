"""Pydantic schemas for AI action packs (Master Directive expansion).

Mirrors the contract in ``ai_knowledge.tool_schemas``:
- Critical business fields are *required* — the assistant asks instead of
  guessing (mandatory interrogation).
- Only unambiguous fallbacks are allowed (``cheque_type`` detection from
  Arabic words happens in the command parser, never silently).
- Zero/negative quantities, prices, and amounts are rejected before any
  service layer is touched.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# NOTE: this module intentionally does NOT import ai_knowledge.tool_schemas
# or base at module level (tool_schemas merges EXTRA_* below, which would
# cycle). _PackBaseArgs mirrors tool_schemas._BaseArgs config; the phone
# pattern is imported lazily inside the validator (validation time = fully
# loaded). The module depends on pydantic only.


class _PackBaseArgs(BaseModel):
    """Common config: coerce loose LLM types, ignore unknown keys."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, coerce_numbers_to_str=True)


__all__ = [
    "CreateChequeArgs",
    "ListChequesArgs",
    "CreateSaleReturnArgs",
    "ListReturnsArgs",
    "QuotationLineIn",
    "CreateQuotationArgs",
    "ListQuotationsArgs",
    "AdvanceQuotationArgs",
    "UpdateCustomerArgs",
    "UpdateProductArgs",
    "AdjustStockArgs",
    "EXTRA_ACTION_ARG_MODELS",
    "EXTRA_FIELD_LABELS",
]


# ===== CHEQUES (perm: manage_payments) =====


class CreateChequeArgs(_PackBaseArgs):
    cheque_number: str = Field(min_length=1, description="رقم الشيك")
    cheque_type: Literal["incoming", "outgoing"] = Field(description="نوع الشيك: وارد/صادر")
    amount: float = Field(gt=0, description="مبلغ الشيك")
    bank_name: str = Field(min_length=1, description="اسم البنك")
    due_date: date = Field(description="تاريخ الاستحقاق YYYY-MM-DD")
    customer_name: str = ""
    supplier_name: str = ""
    notes: str = ""


class ListChequesArgs(_PackBaseArgs):
    search: str = ""
    status: str = ""
    cheque_type: Literal["", "incoming", "outgoing"] = ""


# ===== SALE RETURNS (perm: manage_sales) =====


class CreateSaleReturnArgs(_PackBaseArgs):
    sale_number: str = ""
    sale_id: int | None = Field(default=None, gt=0)
    product_name: str = Field(min_length=1, description="اسم المنتج المرتجع")
    quantity: float = Field(gt=0, description="الكمية المرتجعة")
    condition: Literal["good", "damaged"] = "good"
    notes: str = ""

    @model_validator(mode="after")
    def _one_identifier_required(self):
        if not self.sale_number and not self.sale_id:
            raise ValueError("يرجى تحديد رقم الفاتورة (sale_number) أو معرفها (sale_id)")
        return self


class ListReturnsArgs(_PackBaseArgs):
    pass


# ===== QUOTATIONS (perm: manage_sales) =====


class QuotationLineIn(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, coerce_numbers_to_str=True)

    product_name: str = Field(min_length=1, description="اسم المنتج")
    quantity: float = Field(gt=0, description="الكمية")
    unit_price: float | None = Field(default=None, ge=0, description="سعر الوحدة (اختياري: من الكتالوج)")


class CreateQuotationArgs(_PackBaseArgs):
    customer_name: str = Field(min_length=1, description="اسم العميل")
    lines: list[QuotationLineIn] = Field(min_length=1, description="بنود العرض (بند واحد على الأقل)")
    notes: str = ""


class ListQuotationsArgs(_PackBaseArgs):
    status: Literal["", "draft", "sent", "accepted", "rejected", "converted_to_sale"] = ""


class AdvanceQuotationArgs(_PackBaseArgs):
    quotation_number: str = Field(min_length=1, description="رقم عرض السعر")
    target: Literal["sent", "accepted", "rejected", "converted"] = Field(
        description="الخطوة: إرسال/قبول/رفض/تحويل لفاتورة"
    )


# ===== CATALOG UPDATES =====


class UpdateCustomerArgs(_PackBaseArgs):
    name: str = Field(min_length=1, description="اسم العميل المراد تحديثه")
    phone: str = ""
    email: str = ""
    address: str = ""
    credit_limit: float | None = Field(default=None, ge=0, description="حد الائتمان")

    @field_validator("phone")
    @classmethod
    def _phone_ok(cls, v: str) -> str:
        from ai_knowledge.tool_schemas import _PHONE_RE

        if v and not _PHONE_RE.match(v):
            raise ValueError("رقم هاتف غير صالح (أرقام ورموز + - فقط)")
        return v

    @field_validator("email")
    @classmethod
    def _email_ok(cls, v: str) -> str:
        if v and ("@" not in v or " " in v):
            raise ValueError("صيغة بريد إلكتروني غير صالحة")
        return v


class UpdateProductArgs(_PackBaseArgs):
    name: str = ""
    sku: str = ""
    new_name: str = ""
    selling_price: float | None = Field(default=None, ge=0)
    cost_price: float | None = Field(default=None, ge=0)
    min_stock: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _identifier_and_change_required(self):
        if not self.name and not self.sku:
            raise ValueError("يرجى تحديد المنتج بالاسم أو رمز SKU")
        if not self.new_name and self.selling_price is None and self.cost_price is None and self.min_stock is None:
            raise ValueError("يرجى تحديد حقل واحد على الأقل للتحديث (اسم/سعر/تكلفة/حد أدنى)")
        return self


class AdjustStockArgs(_PackBaseArgs):
    product_name: str = Field(min_length=1, description="اسم المنتج")
    quantity_delta: float = Field(description="فرق الكمية (موجب=زيادة، سالب=نقص)")
    reason: str = Field(min_length=1, description="سبب التسوية (إلزامي للتدقيق)")
    warehouse_id: int | None = Field(default=None, gt=0)

    @field_validator("quantity_delta")
    @classmethod
    def _nonzero(cls, v: float) -> float:
        if not v:
            raise ValueError("فرق الكمية لا يمكن أن يكون صفراً")
        return v


# ===== REGISTRY EXTENSION =====

EXTRA_ACTION_ARG_MODELS: dict[str, tuple[type[_PackBaseArgs], str]] = {
    "create_cheque": (CreateChequeArgs, "تسجيل شيك جديد (وارد/صادر)"),
    "list_cheques": (ListChequesArgs, "عرض الشيكات مع بحث اختياري"),
    "create_sale_return": (CreateSaleReturnArgs, "إنشاء مرتجع مبيعات من فاتورة"),
    "list_returns": (ListReturnsArgs, "عرض مرتجعات المبيعات الأخيرة"),
    "create_quotation": (CreateQuotationArgs, "إنشاء عرض سعر جديد"),
    "list_quotations": (ListQuotationsArgs, "عرض عروض الأسعار مع فلتر حالة"),
    "advance_quotation": (AdvanceQuotationArgs, "تقديم/قبول/رفض/تحويل عرض السعر"),
    "update_customer": (UpdateCustomerArgs, "تحديث بيانات عميل (هاتف/عنوان/ائتمان)"),
    "update_product": (UpdateProductArgs, "تحديث بيانات منتج (أسعار/حد أدنى)"),
    "adjust_stock": (AdjustStockArgs, "تسوية مخزون بسبب موثق عبر حركة GL"),
}

EXTRA_FIELD_LABELS: dict[str, str] = {
    "cheque_number": "رقم الشيك",
    "cheque_type": "نوع الشيك",
    "bank_name": "اسم البنك",
    "due_date": "تاريخ الاستحقاق",
    "condition": "حالة المرتجع",
    "quotation_number": "رقم عرض السعر",
    "target": "الخطوة التالية",
    "lines": "بنود العرض",
    "quantity_delta": "فرق الكمية",
    "reason": "سبب التسوية",
    "new_name": "الاسم الجديد",
    "warehouse_id": "المستودع",
}
