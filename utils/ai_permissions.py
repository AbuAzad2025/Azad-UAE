"""
AI permission namespace — maps AI action types to ERP permissions.

Allows independent control of AI capabilities vs. UI permissions.
A user may have ``manage_sales`` for the web UI but not ``ai:manage_sales``
for the AI assistant.  When no AI-specific permission exists, the system
falls back to the base ERP permission to preserve backward compatibility.
"""

from __future__ import annotations

from flask_login import current_user


# Mapping: ai_action_type -> (base_erp_permission, ai_specific_permission)
_AI_PERM_MAP: dict[str, tuple[str, str]] = {
    "create_customer": ("manage_customers", "ai:manage_customers"),
    "list_customers": ("manage_customers", "ai:manage_customers"),
    "customer_balance": ("manage_customers", "ai:manage_customers"),
    "create_product": ("manage_products", "ai:manage_products"),
    "list_products": ("manage_products", "ai:manage_products"),
    "check_stock": ("manage_warehouse", "ai:manage_warehouse"),
    "create_sale": ("manage_sales", "ai:manage_sales"),
    "list_sales": ("manage_sales", "ai:manage_sales"),
    "receive_payment": ("manage_payments", "ai:manage_payments"),
    "add_expense": ("manage_expenses", "ai:manage_expenses"),
    "create_supplier": ("manage_suppliers", "ai:manage_suppliers"),
    "sales_summary": ("view_reports", "ai:view_reports"),
    "profit_summary": ("view_reports", "ai:view_reports"),
    "create_employee": ("manage_employees", "ai:manage_employees"),
    "create_purchase": ("manage_purchases", "ai:manage_purchases"),
    "create_user": ("manage_users", "ai:manage_users"),
}


def get_ai_permission(action_type: str) -> str:
    """Return the AI-specific permission code for an action.

    Falls back to the base ERP permission when no AI-specific mapping exists.
    """
    base, ai_specific = _AI_PERM_MAP.get(action_type, ("", ""))
    return ai_specific or base or ""


def user_has_ai_permission(action_type: str, user=None) -> bool:
    """Check if a user has permission to execute an AI action.

    Owners always pass.  For others:
    1. If the AI-specific permission exists and the user has it → allow.
    2. If the AI-specific permission does NOT exist on the user,
       fall back to the base ERP permission → allow if present.
    3. Otherwise → deny.
    """
    if user is None:
        user = current_user
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_owner", False):
        return True

    base_perm, ai_perm = _AI_PERM_MAP.get(action_type, ("", ""))
    has_ai = ai_perm and user.has_permission(ai_perm)
    has_base = base_perm and user.has_permission(base_perm)
    return has_ai or has_base


def list_permitted_ai_actions(user=None) -> list[str]:
    """Return the list of AI action types this user is allowed to execute."""
    return [action for action in _AI_PERM_MAP if user_has_ai_permission(action, user)]
