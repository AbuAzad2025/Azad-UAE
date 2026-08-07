"""Personality & responses."""

from ai_knowledge.personality.azad_personality import azad_personality
from ai_knowledge.personality.azad_responses import azad_responses
from ai_knowledge.personality.beginners_mode import BEGINNERS_TUTORIALS, beginners_guide
from ai_knowledge.personality.dialects import (
    apply_dialect,
    dialect_manager,
    get_dialectal_greeting,
)

__all__ = [
    "azad_personality",
    "azad_responses",
    "dialect_manager",
    "apply_dialect",
    "get_dialectal_greeting",
    "beginners_guide",
    "BEGINNERS_TUTORIALS",
]
