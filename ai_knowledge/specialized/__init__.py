"""Specialized modules - consolidated in specialized_knowledge.py"""
from ai_knowledge.specialized_knowledge import (
    advanced_laws, security_rules,
    SYSTEM_TERMS, get_system_guide,
    USER_GUIDE, get_guide, get_help_for_task,
    CUSTOMER_SERVICE, get_customer_service_tip,
    UAE_TAX_SYSTEM, get_tax_advice,
)
# USER_GUIDE_FULL is the user_guide version of USER_GUIDE
from ai_knowledge.specialized_knowledge import USER_GUIDE_FULL

__all__ = [
    'advanced_laws', 'security_rules', 'SYSTEM_TERMS', 'USER_GUIDE',
    'get_system_guide', 'USER_GUIDE_FULL', 'get_guide', 'get_help_for_task',
    'CUSTOMER_SERVICE', 'get_customer_service_tip',
    'UAE_TAX_SYSTEM', 'get_tax_advice',
]
