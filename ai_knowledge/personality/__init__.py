"""Personality & responses - AI personality, response templates, dialects, beginners mode."""
from .azad_personality import azad_personality
from .azad_responses import azad_responses
from .dialects import dialect_manager, apply_dialect, get_dialectal_greeting
from .beginners_mode import BeginnersGuide, beginners_guide, BEGINNERS_TUTORIALS

__all__ = [
    'azad_personality',
    'azad_responses',
    'dialect_manager',
    'apply_dialect',
    'get_dialectal_greeting',
    'BeginnersGuide',
    'beginners_guide',
    'BEGINNERS_TUTORIALS',
]
