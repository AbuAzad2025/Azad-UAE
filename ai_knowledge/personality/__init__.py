"""Personality & responses."""
from ai_knowledge.personality.azad_personality import azad_personality
from ai_knowledge.personality.azad_responses import azad_responses
from ai_knowledge.personality.dialects import dialect_manager, apply_dialect, get_dialectal_greeting
from ai_knowledge.personality.beginners_mode import beginners_guide, BEGINNERS_TUTORIALS

__all__ = [
    'azad_personality', 'azad_responses',
    'dialect_manager', 'apply_dialect', 'get_dialectal_greeting',
    'beginners_guide', 'BEGINNERS_TUTORIALS',
]
