"""Knowledge bases - consolidated in knowledge_base.py"""

from ai_knowledge.knowledge_base import (
    ALL_MODULES,
    COMPANY_INFO,
    CUSTOMS_CLEARANCE,
    PARTS_DATABASE,
    TAX_CUSTOMS_GUIDE,
    get_automotive_ecu_knowledge,
    get_customs_advice,
    get_customs_info,
    get_module_help,
    get_part_info,
    get_tax_info,
    get_welcome_message,
    search_knowledge,
    search_parts,
)

__all__ = [
    "ALL_MODULES",
    "get_module_help",
    "search_knowledge",
    "COMPANY_INFO",
    "get_welcome_message",
    "PARTS_DATABASE",
    "get_part_info",
    "search_parts",
    "get_automotive_ecu_knowledge",
    "TAX_CUSTOMS_GUIDE",
    "get_tax_info",
    "get_customs_info",
    "CUSTOMS_CLEARANCE",
    "get_customs_advice",
]
