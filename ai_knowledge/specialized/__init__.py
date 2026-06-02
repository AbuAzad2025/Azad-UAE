"""Specialized modules - advanced laws, security, guides, customer service, tax system."""
from .advanced_laws import advanced_laws
from .security_rules import security_rules
from .system_guide import SYSTEM_TERMS, USER_GUIDE, get_system_guide
from .user_guide import USER_GUIDE as USER_GUIDE_FULL, get_guide, get_help_for_task
from .customer_service import CUSTOMER_SERVICE, get_customer_service_tip
from .tax_system import UAE_TAX_SYSTEM, get_tax_advice

__all__ = [
    'advanced_laws',
    'security_rules',
    'SYSTEM_TERMS',
    'USER_GUIDE',
    'get_system_guide',
    'USER_GUIDE_FULL',
    'get_guide',
    'get_help_for_task',
    'CUSTOMER_SERVICE',
    'get_customer_service_tip',
    'UAE_TAX_SYSTEM',
    'get_tax_advice',
]
