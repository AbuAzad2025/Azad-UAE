"""RBAC firewall — every data intent is gated before any query runs."""

from __future__ import annotations

import logging

from ai_knowledge.cognitive.contracts import CONVERSATIONAL_INTENTS, CognitiveIntent

logger = logging.getLogger(__name__)

INTENT_PERMISSION: dict[CognitiveIntent, str] = {
    CognitiveIntent.SALES_SUMMARY: "view_reports",
    CognitiveIntent.CUSTOMER_BALANCE: "manage_customers",
    CognitiveIntent.INVENTORY_STATUS: "manage_warehouse",
    CognitiveIntent.PURCHASE_SUMMARY: "manage_purchases",
    CognitiveIntent.EXPENSE_SUMMARY: "manage_expenses",
    CognitiveIntent.PAYMENT_STATUS: "manage_payments",
    CognitiveIntent.CHEQUE_STATUS: "manage_payments",
    CognitiveIntent.GL_BALANCE: "view_ledger",
    CognitiveIntent.HR_SUMMARY: "hr.view",
    CognitiveIntent.VAULT_BALANCE: "manage_payments",
    CognitiveIntent.PATTERN_ANALYSIS: "view_reports",
    CognitiveIntent.PROFIT_MARGIN: "view_reports",
    CognitiveIntent.DEAD_STOCK: "manage_warehouse",
    CognitiveIntent.TOP_PRODUCTS: "view_reports",
    CognitiveIntent.DEBT_OVERVIEW: "manage_customers",
    CognitiveIntent.TAX_SUMMARY: "view_reports",
    CognitiveIntent.SUPPLIER_STATUS: "manage_suppliers",
}

_DISPATCHER_ACTION: dict[CognitiveIntent, str] = {
    CognitiveIntent.CUSTOMER_BALANCE: "customer_balance",
    CognitiveIntent.SALES_SUMMARY: "sales_summary",
    CognitiveIntent.INVENTORY_STATUS: "check_stock",
}


def required_permission(intent: CognitiveIntent) -> str:
    return INTENT_PERMISSION.get(intent, "")


def check_access(intent: CognitiveIntent, user: object | None) -> tuple[bool, str]:
    if intent in CONVERSATIONAL_INTENTS:
        return True, ""
    needed = required_permission(intent)
    if user is None or not getattr(user, "is_authenticated", False):
        return False, needed
    try:
        from utils.ai_permissions import user_has_ai_permission

        action = _DISPATCHER_ACTION.get(intent)
        if action and user_has_ai_permission(action, user):
            return True, needed
    except Exception as exc:
        logger.debug("AI permission check skipped: %s", exc)
    try:
        has_perm = getattr(user, "has_permission", None)
        if callable(has_perm) and bool(has_perm(needed)):
            return True, needed
    except Exception as exc:
        logger.debug("Base permission check failed: %s", exc)
    logger.info("Cognitive RBAC denial: intent=%s needs=%s", intent.value, needed)
    return False, needed
