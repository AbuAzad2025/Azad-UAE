"""Knowledge expansion."""

from ai_knowledge.expansion.knowledge_expansion import knowledge_expander
from ai_knowledge.expansion.knowledge_sources import (
    KNOWLEDGE_SOURCES,
    knowledge_manager,
)
from ai_knowledge.expansion.global_knowledge import global_connector, expertise_updater

__all__ = [
    "knowledge_expander",
    "KNOWLEDGE_SOURCES",
    "knowledge_manager",
    "global_connector",
    "expertise_updater",
]
