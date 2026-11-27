"""Bounded, tenant-scoped follow-up context with permission-aware expiry.

This store is deliberately in-memory and read-only with respect to the ERP
database. Every entry is keyed by ``(tenant_id, user_id)`` and additionally
validated against a permission/cost-visibility signature on retrieval, so a
follow-up turn can never inherit slots from a different tenant, role or cost
clearance.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

TTL_SECONDS = 15 * 60
MAX_ENTRIES = 256

_RESET_RE = re.compile(
    r"(^\s*(reset|clear)\b|clear context|forget (that|it)|ابدأ من جديد|امسح السياق|انسِ السياق)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Entry:
    slots: dict[str, str]
    signature: tuple[bool, ...]
    expires_at: float


_store: dict[tuple[int | None, int | None], _Entry] = {}
_lock = threading.Lock()


def is_reset(message: str) -> bool:
    """True when the user explicitly asks to drop inherited context."""
    return bool(_RESET_RE.search(message or ""))


def permission_signature(user: object | None) -> tuple[bool, ...]:
    """Stable permission/cost fingerprint for follow-up revalidation."""
    if user is None:
        return ()
    from ai_knowledge.cognitive.access import INTENT_PERMISSION

    codes = sorted(set(INTENT_PERMISSION.values()) | {"view_costs"})
    has_permission = getattr(user, "has_permission", None)
    parts = [bool(has_permission(code)) if callable(has_permission) else False for code in codes]
    can_see_costs = getattr(user, "can_see_costs", None)
    parts.append(bool(can_see_costs()) if callable(can_see_costs) else False)
    return tuple(parts)


def set_context(tenant_id: int | None, user_id: int | None, signature: tuple[bool, ...], slots: dict[str, str]) -> None:
    """Store a non-empty slot snapshot with a bounded TTL."""

    if not slots or tenant_id is None or user_id is None:
        return
    key = (int(tenant_id), int(user_id))
    with _lock:
        now = time.monotonic()
        expired = [k for k, entry in _store.items() if entry.expires_at <= now]
        for stale in expired:
            _store.pop(stale, None)
        while len(_store) >= MAX_ENTRIES:
            oldest = min(_store, key=lambda k: _store[k].expires_at)
            _store.pop(oldest, None)
        _store[key] = _Entry(dict(slots), tuple(signature), now + TTL_SECONDS)


def get_context(tenant_id: int | None, user_id: int | None, signature: tuple[bool, ...]) -> dict[str, str]:
    """Return stored slots only for the same tenant, user and permission set."""

    if tenant_id is None or user_id is None:
        return {}
    key = (int(tenant_id), int(user_id))
    now = time.monotonic()
    with _lock:
        entry = _store.get(key)
        if entry is None:
            return {}
        if entry.expires_at <= now:
            _store.pop(key, None)
            return {}
        if tuple(signature) != entry.signature:
            _store.pop(key, None)
            return {}
        return dict(entry.slots)


def clear_context(tenant_id: int | None = None, user_id: int | None = None) -> None:
    """Clear one entry, or the whole bounded store when no key is given."""

    with _lock:
        if tenant_id is None and user_id is None:
            _store.clear()
            return
        for key in list(_store):
            if tenant_id is not None and key[0] != int(tenant_id):
                continue
            if user_id is not None and key[1] != int(user_id):
                continue
            _store.pop(key, None)


__all__ = [
    "MAX_ENTRIES",
    "TTL_SECONDS",
    "clear_context",
    "get_context",
    "is_reset",
    "permission_signature",
    "set_context",
]
