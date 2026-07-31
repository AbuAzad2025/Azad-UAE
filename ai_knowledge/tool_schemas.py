"""
Native LLM Tool-Calling Schemas (P3-1) + Missing-Data Guards.

JSON Schema definitions for every AI action registered in
``ai_knowledge.action_dispatcher``, compatible with the OpenAI/Groq
``tools`` request parameter, plus strict Pydantic validation of tool
arguments before they reach ``ActionDispatcher.dispatch``.

Missing-data & edge-case contract (Human-Operator directive):

- **Mandatory interrogation** — critical business fields (items, quantities,
  amounts, party names, invoice identifiers, warehouses) are *required*;
  the assistant must stop and ask instead of guessing.
- **Safe smart defaults** — only unambiguous fallbacks are allowed
  (``payment_method="cash"``, ``date=today``, catalog-derived unit price).
- **Boundary validation** — zero/negative quantities, prices and amounts are
  rejected before any service layer is touched.
- **Structured clarification** — :class:`ToolValidationError` carries the
  missing/invalid field lists plus a friendly Arabic prompt that tells the
  user exactly what to provide.

This replaces the legacy regex/JSON-in-content contract with native
function calling for providers that support it (Groq / OpenAI). Providers
without tool-calling (e.g. Gemini REST) keep the legacy fallback in
``services.ai_service._execute_ai_action``.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

logger = logging.getLogger(__name__)

# Payment methods aligned with utils.constants.PAYMENT_METHODS (+ "credit" for آجل)
PAYMENT_METHOD_CODES = ("cash", "card", "bank_transfer", "cheque", "e_wallet", "credit")
PaymentMethod = Literal["cash", "card", "bank_transfer", "cheque", "e_wallet", "credit"]

_PHONE_RE = re.compile(r"^[0-9+\-\s()]{3,20}$")


class _BaseArgs(BaseModel):
    """Common config: coerce loose LLM types, ignore unknown keys."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, coerce_numbers_to_str=True)


def _check_phone(v: str) -> str:
    if v and not _PHONE_RE.match(v):
        raise ValueError("رقم هاتف غير صالح (أرقام ورموز + - فقط)")
    return v


def _check_email(v: str) -> str:
    if v and ("@" not in v or " " in v):
        raise ValueError("صيغة بريد إلكتروني غير صالحة")
    return v


# ===== CUSTOMERS =====


class CreateCustomerArgs(_BaseArgs):
    name: str = Field(min_length=1, description="اسم العميل")
    phone: str = ""
    email: str = ""
    address: str = ""
    credit_limit: float = Field(default=0, ge=0)
    type: str = "regular"

    _phone_ok = field_validator("phone")(_check_phone)
    _email_ok = field_validator("email")(_check_email)


class ListCustomersArgs(_BaseArgs):
    search: str = ""


class CustomerBalanceArgs(_BaseArgs):
    name: str = Field(min_length=1, description="اسم العميل")


# ===== PRODUCTS =====


class CreateProductArgs(_BaseArgs):
    name: str = Field(min_length=1, description="اسم المنتج")
    sku: str = ""
    barcode: str = ""
    cost_price: float = Field(default=0, ge=0)
    selling_price: float = Field(default=0, ge=0)
    stock: float = Field(default=0, ge=0)
    min_stock: float = Field(default=0, ge=0)
    unit: str = "قطعة"


class ListProductsArgs(_BaseArgs):
    search: str = ""


class CheckStockArgs(_BaseArgs):
    search: str = Field(default="", description="اسم المنتج أو رمز SKU للاستعلام عنه (اختياري)")


class TransferStockArgs(_BaseArgs):
    product_name: str = Field(min_length=1, description="اسم المنتج")
    from_warehouse_id: int = Field(gt=0, description="معرف المستودع المصدر")
    to_warehouse_id: int = Field(gt=0, description="معرف المستودع الوجهة")
    quantity: float = Field(gt=0, description="الكمية")
    notes: str = ""

    @model_validator(mode="after")
    def _different_warehouses(self):
        if self.from_warehouse_id == self.to_warehouse_id:
            raise ValueError("المستودع المصدر والوجهة متطابقان — لا يمكن التحويل إلى نفس المستودع")
        return self


# ===== SALES / PAYMENTS / EXPENSES =====


class CreateSaleArgs(_BaseArgs):
    customer_name: str = Field(min_length=1, description="اسم العميل")
    product_name: str = Field(min_length=1, description="اسم المنتج")
    # الكمية إلزامية — ممنوع التخمين (Mandatory interrogation)
    quantity: int = Field(ge=1, description="الكمية المباعة (إلزامي)")
    # سعر الوحدة اختياري: يُشتق من كتالوج المتجر عند غيابه (safe default)
    unit_price: float | None = Field(default=None, ge=0)
    payment_method: PaymentMethod = "cash"
    paid_amount: float = Field(default=0, ge=0)


class ListSalesArgs(_BaseArgs):
    pass


class CancelSaleArgs(_BaseArgs):
    sale_number: str = ""
    sale_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _one_identifier_required(self):
        if not self.sale_number and not self.sale_id:
            raise ValueError("يرجى تحديد رقم الفاتورة (sale_number) أو معرفها (sale_id)")
        return self


class ReceivePaymentArgs(_BaseArgs):
    customer_name: str = Field(min_length=1, description="اسم العميل")
    amount: float = Field(gt=0, description="المبلغ")
    method: PaymentMethod = "cash"
    notes: str = ""


class AddExpenseArgs(_BaseArgs):
    description: str = Field(min_length=1, description="وصف المصروف")
    amount: float = Field(gt=0, description="المبلغ")
    method: PaymentMethod = "cash"
    category: str = Field(default="", description="اسم فئة المصروف (اختياري)")
    category_id: int | None = Field(default=None, gt=0)
    branch_id: int | None = Field(default=None, gt=0)


# ===== SUPPLIERS / PURCHASES =====


class CreateSupplierArgs(_BaseArgs):
    name: str = Field(min_length=1, description="اسم المورد")
    company: str = ""
    phone: str = ""
    email: str = ""
    tax_number: str = ""

    _phone_ok = field_validator("phone")(_check_phone)
    _email_ok = field_validator("email")(_check_email)


class CreatePurchaseArgs(_BaseArgs):
    supplier_name: str = Field(min_length=1, description="اسم المورد")
    product_name: str = Field(min_length=1, description="اسم المنتج")
    # الكمية إلزامية — ممنوع التخمين (Mandatory interrogation)
    quantity: int = Field(ge=1, description="الكمية المشتراة (إلزامي)")
    # سعر التكلفة صفر = غير محدد → يسأل المشغّل عنه قبل التنفيذ (dispatcher)
    unit_cost: float = Field(default=0, ge=0)
    notes: str = ""


# ===== REPORTS / EMPLOYEES / USERS =====


class SalesSummaryArgs(_BaseArgs):
    pass


class ProfitSummaryArgs(_BaseArgs):
    pass


class CreateEmployeeArgs(_BaseArgs):
    name: str = Field(min_length=1, description="اسم الموظف")
    phone: str = ""
    email: str = ""
    salary: float = Field(default=0, ge=0)
    employment_type: Literal["salary", "commission", "hourly"] = "salary"

    _phone_ok = field_validator("phone")(_check_phone)
    _email_ok = field_validator("email")(_check_email)


class CreateUserArgs(_BaseArgs):
    username: str = Field(min_length=3, description="اسم المستخدم (3 أحرف فأكثر)")
    password: str = Field(min_length=6, description="كلمة المرور (6 أحرف فأكثر)")
    role: str = "seller"
    full_name: str = ""
    phone: str = ""

    _phone_ok = field_validator("phone")(_check_phone)


# ===== REGISTRY =====

# action_type -> (pydantic model, Arabic description for the LLM)
ACTION_ARG_MODELS: dict[str, tuple[type[_BaseArgs], str]] = {
    "create_customer": (CreateCustomerArgs, "إنشاء عميل جديد في النظام"),
    "list_customers": (ListCustomersArgs, "عرض قائمة العملاء مع بحث اختياري"),
    "customer_balance": (CustomerBalanceArgs, "عرض رصيد عميل محدد"),
    "create_product": (CreateProductArgs, "إنشاء منتج جديد في المخزون"),
    "list_products": (ListProductsArgs, "عرض قائمة المنتجات مع بحث اختياري"),
    "check_stock": (CheckStockArgs, "فحص المنتجات منخفضة المخزون"),
    "transfer_stock": (TransferStockArgs, "تحويل كمية من منتج بين مستودعين"),
    "create_sale": (CreateSaleArgs, "إنشاء فاتورة مبيعات جديدة"),
    "list_sales": (ListSalesArgs, "عرض آخر فواتير المبيعات"),
    "cancel_sale": (CancelSaleArgs, "إلغاء فاتورة مبيعات وعكس قيودها ومخزونها"),
    "receive_payment": (ReceivePaymentArgs, "استلام دفعة من عميل"),
    "add_expense": (AddExpenseArgs, "تسجيل مصروف جديد"),
    "create_supplier": (CreateSupplierArgs, "إنشاء مورد جديد"),
    "create_purchase": (CreatePurchaseArgs, "إنشاء أمر شراء جديد"),
    "sales_summary": (SalesSummaryArgs, "ملخص إجمالي المبيعات"),
    "profit_summary": (ProfitSummaryArgs, "ملخص الأرباح وهامش الربح"),
    "create_employee": (CreateEmployeeArgs, "إنشاء موظف جديد"),
    "create_user": (CreateUserArgs, "إنشاء مستخدم جديد (للمالك فقط)"),
}

# Arabic labels for tool argument fields — used in clarification prompts
FIELD_LABELS: dict[str, str] = {
    "name": "الاسم",
    "customer_name": "اسم العميل",
    "supplier_name": "اسم المورد",
    "product_name": "اسم المنتج",
    "quantity": "الكمية",
    "unit_price": "سعر بيع الوحدة",
    "unit_cost": "سعر تكلفة الوحدة",
    "amount": "المبلغ",
    "description": "وصف المصروف",
    "payment_method": "طريقة الدفع",
    "method": "طريقة الدفع",
    "paid_amount": "المبلغ المدفوع",
    "sale_number": "رقم الفاتورة",
    "sale_id": "معرف الفاتورة",
    "from_warehouse_id": "معرف المستودع المصدر",
    "to_warehouse_id": "معرف مستودع الوجهة",
    "username": "اسم المستخدم",
    "password": "كلمة المرور",
    "role": "الدور الوظيفي",
    "phone": "رقم الهاتف",
    "email": "البريد الإلكتروني",
    "credit_limit": "حد الائتمان",
    "salary": "الراتب",
    "category": "فئة المصروف",
    "category_id": "فئة المصروف",
    "args": "معطيات العملية",
}


class ToolValidationError(ValueError):
    """Structured missing/invalid tool-arguments error.

    Carries the failing field names so callers can build targeted
    clarification prompts. Subclasses ``ValueError`` so legacy callers
    (``except ValueError``) keep working unchanged.
    """

    def __init__(
        self,
        action_type: str,
        missing_fields: list[str],
        invalid_fields: list[tuple[str, str]],
        message: str,
    ) -> None:
        super().__init__(message)
        self.action_type = action_type
        self.missing_fields = missing_fields
        self.invalid_fields = invalid_fields


def _field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


_ERROR_TRANSLATIONS: list[tuple[str, str]] = [
    ("greater than or equal to 0", "لا يمكن أن تكون القيمة سالبة"),
    ("greater than or equal to 1", "يجب أن تكون القيمة 1 على الأقل"),
    ("greater than 0", "يجب أن تكون القيمة أكبر من صفر"),
    ("valid integer", "يجب إدخال رقم صحيح"),
    ("valid number", "يجب إدخال رقم"),
    ("at least 3 characters", "يجب ألا يقل عن 3 أحرف"),
    ("at least 6 characters", "يجب ألا يقل عن 6 أحرف"),
    ("at least 1 character", "لا يمكن أن يكون فارغاً"),
    ("Input should be", "قيمة غير مدعومة"),
]


def _arabic_error(err: dict) -> str:
    """Translate a Pydantic error message into a short Arabic reason."""
    msg = str(err.get("msg", ""))
    if msg.startswith("Value error, "):
        msg = msg[len("Value error, ") :]
    ctx = err.get("ctx") or {}
    if err.get("type") == "literal_error" and ctx.get("expected"):
        return f"قيمة غير مدعومة — القيم المتاحة: {ctx['expected']}"
    for needle, arabic in _ERROR_TRANSLATIONS:
        if needle in msg:
            return arabic
    # Validators already raise Arabic messages — keep them
    return msg[:120] if msg else "قيمة غير صالحة"


def _build_clarification(
    action_type: str,
    missing_fields: list[str],
    invalid_fields: list[tuple[str, str]],
) -> str:
    """Friendly, structured Arabic clarification prompt (Human-Operator)."""
    entry = ACTION_ARG_MODELS.get(action_type)
    description = entry[1] if entry else action_type
    lines = [f"معطيات غير صالحة للعملية «{description}»"]
    if missing_fields:
        lines.append("📋 البيانات الناقصة المطلوبة لإتمام العملية:")
        lines.extend(f"• {_field_label(f)}" for f in missing_fields)
    if invalid_fields:
        lines.append("⚠️ قيم غير مقبولة:")
        lines.extend(f"• {_field_label(f)}: {reason}" for f, reason in invalid_fields)
    lines.append("يرجى تزويدي بالبيانات الصحيحة لإكمال العملية دون تخمين.")
    return "\n".join(lines)


def get_openai_tools() -> list[dict[str, Any]]:
    """OpenAI/Groq-compatible ``tools`` parameter for chat completions."""
    tools: list[dict[str, Any]] = []
    for action_type, (model, description) in ACTION_ARG_MODELS.items():
        schema = model.model_json_schema()
        schema.pop("title", None)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": action_type,
                    "description": description,
                    "parameters": schema,
                },
            }
        )
    return tools


def validate_tool_args(action_type: str, args: dict | None) -> dict[str, Any]:
    """Strictly validate and coerce tool arguments before dispatch.

    Raises :class:`ToolValidationError` (a ``ValueError``) with a structured
    Arabic clarification message when arguments are missing or invalid;
    raises plain ``ValueError`` for unknown action types.
    """
    entry = ACTION_ARG_MODELS.get(action_type)
    if entry is None:
        raise ValueError(f"العملية '{action_type}' غير معروفة")
    model = entry[0]
    try:
        validated = model.model_validate(args or {})
    except ValidationError as exc:
        missing: list[str] = []
        invalid: list[tuple[str, str]] = []
        for err in exc.errors():
            field = ".".join(str(p) for p in err.get("loc", [])) or "args"
            if err.get("type") == "missing":
                missing.append(field)
            else:
                invalid.append((field, _arabic_error(err)))
        raise ToolValidationError(
            action_type,
            missing,
            invalid,
            _build_clarification(action_type, missing, invalid),
        ) from exc
    dump = validated.model_dump(exclude_none=True)
    # Drop empty-string defaults so optional-but-empty fields stay absent
    return {k: v for k, v in dump.items() if v != ""}


def validate_tool_args_safe(
    action_type: str, args: dict | None
) -> tuple[dict[str, Any] | None, ToolValidationError | None]:
    """Non-raising variant: returns ``(clean_args, error)``."""
    try:
        return validate_tool_args(action_type, args), None
    except ToolValidationError as exc:
        return None, exc


def get_missing_data_prompt(action_type: str, args: dict | None) -> str | None:
    """Clarification prompt for incomplete tool args, or ``None`` when valid.

    Used by the conversational layer to ask targeted questions before any
    execution is attempted (Intelligent Conversational Interrogation).
    """
    _clean, err = validate_tool_args_safe(action_type, args)
    return str(err) if err else None
