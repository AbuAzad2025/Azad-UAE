"""
Consolidated module: specialized_knowledge.py
Re-exports from ai_knowledge.specialized sub-package (single source of truth).
"""

from ai_knowledge.specialized.customer_service import CUSTOMER_SERVICE, get_customer_service_tip
from ai_knowledge.specialized.tax_system import UAE_TAX_SYSTEM, get_tax_advice
from ai_knowledge.specialized.system_guide import SYSTEM_TERMS, get_system_guide
from ai_knowledge.specialized.security_rules import SecurityRules, security_rules
from ai_knowledge.specialized.user_guide import USER_GUIDE, get_guide, get_help_for_task
from ai_knowledge.specialized.advanced_laws import AdvancedLaws, advanced_laws

USER_GUIDE_FULL = USER_GUIDE

__all__ = [
    'CUSTOMER_SERVICE', 'get_customer_service_tip',
    'UAE_TAX_SYSTEM', 'get_tax_advice',
    'SYSTEM_TERMS', 'get_system_guide',
    'SecurityRules', 'security_rules',
    'USER_GUIDE', 'USER_GUIDE_FULL', 'get_guide', 'get_help_for_task',
    'AdvancedLaws', 'advanced_laws',
]
