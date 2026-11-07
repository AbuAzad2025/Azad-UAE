"""
Global Localization Engine — Phase 9
Country-specific compliance engines for Palestine, UAE, and Saudi Arabia.
"""

from .engine import LocalizationStrategy
from .israel import IsraelStrategy
from .ksa import KSAStrategy
from .null import NullStrategy
from .palestine import PalestineStrategy
from .registry import get_strategy
from .uae import UAEStrategy

__all__ = [
    "get_strategy",
    "LocalizationStrategy",
    "NullStrategy",
    "PalestineStrategy",
    "IsraelStrategy",
    "UAEStrategy",
    "KSAStrategy",
]
