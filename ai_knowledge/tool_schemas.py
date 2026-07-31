"""
Native LLM Tool-Calling Schemas (P3-1).

JSON Schema definitions for every AI action registered in
``ai_knowledge.action_dispatcher``, compatible with the OpenAI/Groq
``tools`` request parameter, plus strict Pydantic validation of tool
arguments before they reach ``ActionDispatcher.dispatch``.

This replaces the legacy regex/JSON-in-content contract with native
function calling for providers that support it (Groq / OpenAI). Providers
without tool-calling (e.g. Gemini REST) keep the legacy fallback in
``services.ai_service._execute_ai_action``.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)


class _BaseArgs(BaseModel):
    """Common config: coerce loose LLM types, ignore unknown keys."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True, coerce_numbers_to_str=True)


# ===== CUSTOMERS =====


class CreateCustomerArgs(_BaseArgs):
    name: str = Field(min_length=1, description="اسم العميل")
    phone: str = ""
    email: str = ""
    address: str = ""
    credit_limit: float = 0
    type: str = "regular"


class ListCustomersArgs(_BaseArgs):
    search: str = ""


class CustomerBalanceArgs(_BaseArgs):
    name: str = Field(min_length=1, description="اسم العميل")


# ===== PRODUCTS =====


class CreateProductArgs(_BaseArgs):
    name: str = Field(min_length=1, description="اسم المنتج")
    sku: str = ""
    barcode: str = ""
    cost_price: float = 0
    selling_price: float = 0
    stock: float = 0
    min_stock: float = 0
    unit: str = "قطعة"


class ListProductsArgs(_BaseArgs):
    search: str = ""


class CheckStockArgs(_BaseArgs):
    pass


class TransferStockArgs(_BaseArgs):
    product_name: str = Field(min_length=1, description="اسم المنتج")
    from_warehouse_id: int = Field(gt=0, description="معرف المستودع المصدر")
    to_warehouse_id: int = Field(gt=0, description="معرف المستودع الوجهة")
    quantity: float = Field(gt=0, description="الكمية")
    notes: str = ""


# ===== SALES / PAYMENTS / EXPENSES =====


class CreateSaleArgs(_BaseArgs):
    customer_name: str = Field(min_length=1, description="اسم العميل")
    product_name: str = Field(min_length=1, description="اسم المنتج")
    quantity: int = Field(default=1, ge=1)
    unit_price: float | None = None
    payment_method: str = "cash"
    paid_amount: float = 0


class ListSalesArgs(_BaseArgs):
    pass


class CancelSaleArgs(_BaseArgs):
    sale_number: str = ""
    sale_id: int | None = None


class ReceivePaymentArgs(_BaseArgs):
    customer_name: str = Field(min_length=1, description="اسم العميل")
    amount: float = Field(gt=0, description="المبلغ")
    method: str = "cash"
    notes: str = ""


class AddExpenseArgs(_BaseArgs):
    description: str = Field(min_length=1, description="وصف المصروف")
    amount: float = Field(gt=0, description="المبلغ")
    method: str = "cash"
    category_id: int | None = None
    branch_id: int | None = None


# ===== SUPPLIERS / PURCHASES =====


class CreateSupplierArgs(_BaseArgs):
    name: str = Field(min_length=1, description="اسم المورد")
    company: str = ""
    phone: str = ""
    email: str = ""
    tax_number: str = ""


class CreatePurchaseArgs(_BaseArgs):
    supplier_name: str = Field(min_length=1, description="اسم المورد")
    product_name: str = Field(min_length=1, description="اسم المنتج")
    quantity: int = Field(default=1, ge=1)
    unit_cost: float = 0
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
    salary: float = 0
    employment_type: Literal["salary", "commission", "hourly"] = "salary"


class CreateUserArgs(_BaseArgs):
    username: str = Field(min_length=1, description="اسم المستخدم")
    password: str = Field(min_length=1, description="كلمة المرور")
    role: str = "seller"
    full_name: str = ""
    phone: str = ""


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

    Raises ``ValueError`` with an Arabic, user-readable message when the
    arguments do not satisfy the action's schema.
    """
    entry = ACTION_ARG_MODELS.get(action_type)
    if entry is None:
        raise ValueError(f"العملية '{action_type}' غير معروفة")
    model = entry[0]
    try:
        validated = model.model_validate(args or {})
    except ValidationError as exc:
        problems = []
        for err in exc.errors()[:3]:
            field = ".".join(str(p) for p in err.get("loc", [])) or "args"
            problems.append(f"{field}: {err.get('msg')}")
        raise ValueError("معطيات غير صالحة للعملية — " + " | ".join(problems)) from exc
    return validated.model_dump(exclude_none=True)
