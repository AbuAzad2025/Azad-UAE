"""
Consolidated module: personality_core.py
Re-exports from ai_knowledge.personality sub-package (single source of truth).
"""

from ai_knowledge.agents.intelligent_assistant import intelligent_assistant
from ai_knowledge.core.learning_system import learning_system
from ai_knowledge.core.system_integration import system_integrator
from ai_knowledge.neural.semantic_matcher import semantic_matcher, understand_message
from ai_knowledge.personality.azad_personality import AzadPersonality, azad_personality
from ai_knowledge.personality.azad_responses import AzadResponses, azad_responses
from ai_knowledge.personality.beginners_mode import (
    BEGINNERS_TUTORIALS,
    BeginnersGuide,
    beginners_guide,
)
from ai_knowledge.personality.dialects import (
    DialectManager,
    apply_dialect,
    dialect_manager,
    get_dialectal_greeting,
)

__all__ = [
    "AzadPersonality",
    "azad_personality",
    "DialectManager",
    "dialect_manager",
    "apply_dialect",
    "get_dialectal_greeting",
    "BeginnersGuide",
    "beginners_guide",
    "BEGINNERS_TUTORIALS",
    "AzadResponses",
    "azad_responses",
    "system_integrator",
    "semantic_matcher",
    "understand_message",
    "intelligent_assistant",
    "learning_system",
]
