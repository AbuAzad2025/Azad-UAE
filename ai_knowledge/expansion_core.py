"""
Consolidated module: expansion_core.py
Re-exports from ai_knowledge.expansion sub-package (single source of truth).
"""

from ai_knowledge.expansion.knowledge_expansion import KnowledgeExpander, knowledge_expander
from ai_knowledge.expansion.global_knowledge import (
    GlobalKnowledgeConnector,
    GlobalExpertiseUpdater,
    global_connector,
    expertise_updater,
)
from ai_knowledge.expansion.knowledge_sources import (
    KnowledgeSourceManager,
    knowledge_manager,
    KNOWLEDGE_SOURCES,
    SOURCES_GUIDE,
    get_learning_resources,
    recommend_sources_for_query,
)

__all__ = [
    'KnowledgeExpander', 'knowledge_expander',
    'GlobalKnowledgeConnector', 'GlobalExpertiseUpdater',
    'global_connector', 'expertise_updater',
    'KnowledgeSourceManager', 'knowledge_manager',
    'KNOWLEDGE_SOURCES', 'SOURCES_GUIDE',
    'get_learning_resources', 'recommend_sources_for_query',
]
