"""Defense layer for GamificationService surface.

Lookups up whitelisted reward actions and prevents arbitrary enums
from being used to inflate scoring or grant new badges.
"""

from __future__ import annotations

_WHITELISTED_ACTIONS: frozenset[str] = frozenset(
    {
        "sale_completed",
        "sale_paid_on_time",
        "perfect_attendance",
        "training_completed",
    }
)


def is_valid_award_action(action: str | None) -> bool:
    """Return True only if the action is in the curated whitelist."""
    if not action:
        return False
    return str(action).strip() in _WHITELISTED_ACTIONS
