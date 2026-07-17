"""
Localization Strategy Registry — maps country codes to strategy classes.
"""

from .null import NullStrategy
from .palestine import PalestineStrategy
from .uae import UAEStrategy
from .ksa import KSAStrategy

_STRATEGIES = {
    "PS": PalestineStrategy,
    "AE": UAEStrategy,
    "SA": KSAStrategy,
}


def get_strategy(country_code: str):
    """Return strategy instance for country_code, or NullStrategy if unsupported."""
    code = (country_code or "").strip().upper()
    cls = _STRATEGIES.get(code, NullStrategy)
    return cls()


def list_supported_countries() -> list:
    return list(_STRATEGIES.keys())
