"""Schema-guided dynamic fallback — safe ORM reads only, never raw SQL.

Runs ONLY when the intent router finds zero evidence. Resolves a mentioned
business object to its model, enforces the model's RBAC permission, then
returns a bounded count (+ recent names from an allowlisted label column).
Secret columns are never selected for display.
"""

from __future__ import annotations

import logging

from ai_knowledge.cognitive.access import check_access
from ai_knowledge.cognitive.contracts import (
    CognitiveIntent,
    CognitiveResult,
    NormalizedMessage,
    Provenance,
    ReasoningStep,
    ReasoningTrace,
)
from utils.tenanting import tenant_query

logger = logging.getLogger(__name__)

COUNT_WORDS = frozenset({"عدد", "كم", "احصاء", "احصائيه", "total", "count", "how many"})
RECENT_LIMIT = 5
QUERY_LIMIT = 200

# keyword -> (model import path, attribute name, required permission, label, display attrs)
_MODEL_REGISTRY: dict[str, tuple[str, str, str, str, tuple[str, ...]]] = {
    "عميل": ("models.customer", "Customer", "manage_customers", "العملاء", ("name",)),
    "عملاء": ("models.customer", "Customer", "manage_customers", "العملاء", ("name",)),
    "زبون": ("models.customer", "Customer", "manage_customers", "العملاء", ("name",)),
    "منتج": ("models.product", "Product", "manage_products", "المنتجات", ("name",)),
    "منتجات": ("models.product", "Product", "manage_products", "المنتجات", ("name",)),
    "فاتوره": ("models.sale", "Sale", "manage_sales", "الفواتير", ("sale_number",)),
    "فواتير": ("models.sale", "Sale", "manage_sales", "الفواتير", ("sale_number",)),
    "مبيعات": ("models.sale", "Sale", "manage_sales", "الفواتير", ("sale_number",)),
    "مورد": ("models.supplier", "Supplier", "manage_suppliers", "الموردين", ("name",)),
    "موردين": ("models.supplier", "Supplier", "manage_suppliers", "الموردين", ("name",)),
    "مشتريات": ("models.purchase", "Purchase", "manage_purchases", "المشتريات", ("purchase_number",)),
    "مصروف": ("models.expense", "Expense", "manage_expenses", "المصروفات", ("expense_number", "description")),
    "مصاريف": ("models.expense", "Expense", "manage_expenses", "المصروفات", ("expense_number", "description")),
    "دفعه": ("models.payment", "Payment", "manage_payments", "المدفوعات", ("payment_number",)),
    "مدفوعات": ("models.payment", "Payment", "manage_payments", "المدفوعات", ("payment_number",)),
    "شيك": ("models.cheque", "Cheque", "manage_payments", "الشيكات", ("cheque_number",)),
    "شيكات": ("models.cheque", "Cheque", "manage_payments", "الشيكات", ("cheque_number",)),
    "موظف": ("models.payroll", "Employee", "hr.view", "الموظفين", ("name",)),
    "موظفين": ("models.payroll", "Employee", "hr.view", "الموظفين", ("name",)),
    "حساب": ("models.gl", "GLAccount", "view_ledger", "الحسابات", ("code", "name")),
    "قيود": ("models.gl", "GLJournalEntry", "view_ledger", "القيود", ("code",)),
    "صندوق": ("models.cash_box", "CashBox", "manage_payments", "الصناديق", ("code", "name")),
}

_INTENT_FOR_PERMISSION: dict[str, CognitiveIntent] = {
    "manage_customers": CognitiveIntent.CUSTOMER_BALANCE,
    "manage_products": CognitiveIntent.INVENTORY_STATUS,
    "manage_sales": CognitiveIntent.SALES_SUMMARY,
    "manage_suppliers": CognitiveIntent.SUPPLIER_STATUS,
    "manage_purchases": CognitiveIntent.PURCHASE_SUMMARY,
    "manage_expenses": CognitiveIntent.EXPENSE_SUMMARY,
    "manage_payments": CognitiveIntent.PAYMENT_STATUS,
    "hr.view": CognitiveIntent.HR_SUMMARY,
    "view_ledger": CognitiveIntent.GL_BALANCE,
}


def _load_model(path: str, attr: str):
    import importlib

    return getattr(importlib.import_module(path), attr)


def _display_label(row: object, attrs: tuple[str, ...]) -> str:
    for attr in attrs:
        value = getattr(row, attr, None)
        if value:
            return str(value)[:60]
    return f"#{getattr(row, 'id', '?')}"


def try_dynamic_fallback(normalized: NormalizedMessage, user: object | None) -> CognitiveResult | None:
    tokens = set(normalized.tokens)
    for token in sorted(tokens):
        if token.startswith("ال") and len(token) > 4:
            tokens.add(token[2:])
    hit = next((key for key in _MODEL_REGISTRY if key in tokens), None)
    if hit is None or user is None or not getattr(user, "is_authenticated", False):
        return None
    path, attr, permission, label, display = _MODEL_REGISTRY[hit]
    proxy = _INTENT_FOR_PERMISSION.get(permission, CognitiveIntent.UNKNOWN)
    allowed, _required = check_access(proxy, user)
    if not allowed:
        return None
    try:
        model = _load_model(path, attr)
        rows = tenant_query(model, user).order_by(model.id.desc()).limit(QUERY_LIMIT).all()
    except Exception as exc:
        logger.debug("Dynamic fallback query failed: %s", exc)
        return None
    count_mode = bool(tokens & COUNT_WORDS)
    if count_mode:
        conclusion = f"يوجد {len(rows)} من {label} ضمن نطاق شركتك."
    else:
        sample = ", ".join(_display_label(row, display) for row in rows[:RECENT_LIMIT])
        conclusion = f"يوجد {len(rows)} من {label} ضمن نطاق شركتك."
        if sample:
            conclusion += f" الأحدث: {sample}."
    steps = (
        ReasoningStep("intent-decoded", f"Dynamic object query: {label} (signal:{hit}).", 0.6),
        ReasoningStep("rbac-passed", f"Permission {permission} verified before query.", 1.0),
        ReasoningStep("query", conclusion, 0.85, provenance=f"{attr}[tenant]"),
        ReasoningStep("constraint-check", "Tenant scope enforced; label columns only.", 1.0),
    )
    trace = ReasoningTrace(
        plan=("intent-decoded", "rbac-passed", "query", "constraint-check"),
        steps=steps,
        conclusion=conclusion,
        confidence=0.6,
    )
    response = f"{conclusion}\n<sub>المصدر: نطاق الشركة — {attr}[tenant] (صفوف: {len(rows)})</sub>"
    return CognitiveResult(
        success=True,
        response=response,
        intent=f"dynamic:{attr.lower()}",
        confidence=0.6,
        decision="answer",
        trace=trace,
        provenance=Provenance(tenant_id=None, queries=(f"{attr}[tenant]",), row_counts=(len(rows),)),
    )
