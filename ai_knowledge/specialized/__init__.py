"""Specialized domain modules."""

from ai_knowledge.specialized.advanced_laws import AdvancedLaws, advanced_laws
from ai_knowledge.specialized.security_rules import SecurityRules, security_rules
from ai_knowledge.specialized.system_guide import SYSTEM_TERMS, get_system_guide
from ai_knowledge.specialized.user_guide import USER_GUIDE, get_guide, get_help_for_task
from ai_knowledge.specialized.customer_service import (
    CUSTOMER_SERVICE,
    get_customer_service_tip,
)
from ai_knowledge.specialized.tax_system import UAE_TAX_SYSTEM, get_tax_advice

USER_GUIDE_FULL = USER_GUIDE

__all__ = [
    "advanced_laws",
    "AdvancedLaws",
    "security_rules",
    "SecurityRules",
    "SYSTEM_TERMS",
    "get_system_guide",
    "USER_GUIDE",
    "USER_GUIDE_FULL",
    "get_guide",
    "get_help_for_task",
    "CUSTOMER_SERVICE",
    "get_customer_service_tip",
    "UAE_TAX_SYSTEM",
    "get_tax_advice",
]
