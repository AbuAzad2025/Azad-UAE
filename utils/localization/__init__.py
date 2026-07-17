"""
Global Localization Engine — Phase 9
Country-specific compliance engines for Palestine, UAE, and Saudi Arabia.
"""

from .registry import get_strategy
from .engine import LocalizationStrategy
from .null import NullStrategy
from .palestine import PalestineStrategy
from .uae import UAEStrategy
from .ksa import KSAStrategy

__all__ = [
    "get_strategy",
    "LocalizationStrategy",
    "NullStrategy",
    "PalestineStrategy",
    "UAEStrategy",
    "KSAStrategy",
]
