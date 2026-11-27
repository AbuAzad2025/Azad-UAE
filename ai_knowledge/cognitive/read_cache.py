"""Bounded, tenant-safe local cache for grounded read results.

Keys carry tenant, user, permission/cost-visibility signature, locale, intent
and normalized slots. A cached entry is only returned when the *current* user
still resolves to the same identity and signature. Writes invalidate the
tenant's entries through ``ai_write_transaction`` / the action dispatcher.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from ai_knowledge.cognitive.contracts import CognitiveIntent, NormalizedMessage, SlotSet
from ai_knowledge.cognitive.followup import permission_signature

DEFAULT_TTL_SECONDS = 10 * 60
MAX_ENTRIES = 512


@dataclass(frozen=True)
class CacheKey:
    tenant_id: int
    user_id: int
    signature: tuple[bool, ...]
    locale: str
    intent: str
    slots: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _Entry:
    value: Any
    expires_at: float


def make_key(
    normalized: NormalizedMessage,
    intent: CognitiveIntent,
    slots: SlotSet,
    user: object | None,
) -> CacheKey | None:
    """Return None for context-free callers so anonymous reads are never cached."""

    from utils.tenanting import get_active_tenant_id

    tenant_id = get_active_tenant_id(user)
    user_id = getattr(user, "id", None)
    if tenant_id is None or user_id is None:
        return None
    return CacheKey(
        tenant_id=int(tenant_id),
        user_id=int(user_id),
        signature=permission_signature(user),
        locale=normalized.locale,
        intent=intent.value,
        slots=tuple(sorted((key, str(value)) for key, value in slots.values.items())),
    )


class ReadCache:
    """TTL + size bounded cache with explicit tenant invalidation."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS, max_entries: int = MAX_ENTRIES) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._entries: OrderedDict[CacheKey, _Entry] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def _purge(self, now: float) -> None:
        for key in [key for key, entry in self._entries.items() if entry.expires_at <= now]:
            self._entries.pop(key, None)

    def get(self, key: CacheKey, user: object | None = None) -> Any | None:
        """Return a value only when identity and permissions still match."""

        from utils.tenanting import get_active_tenant_id

        if user is not None:
            tenant_id = get_active_tenant_id(user)
            user_id = getattr(user, "id", None)
            if (
                tenant_id is None
                or user_id is None
                or int(tenant_id) != key.tenant_id
                or int(user_id) != key.user_id
                or permission_signature(user) != key.signature
            ):
                return None
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return None
            self._entries.move_to_end(key)
            self.hits += 1
            return entry.value

    def set(self, key: CacheKey, value: Any) -> None:
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            self._entries[key] = _Entry(value=value, expires_at=now + self._ttl)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max:
                self._entries.popitem(last=False)

    def invalidate_tenant(self, tenant_id: int) -> None:
        with self._lock:
            for key in [key for key in self._entries if key.tenant_id == int(tenant_id)]:
                self._entries.pop(key, None)

    def invalidate_all(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"hits": self.hits, "misses": self.misses, "entries": len(self._entries)}


_default_cache = ReadCache()


def get_default_cache() -> ReadCache:
    return _default_cache


def invalidate_tenant_reads(tenant_id: int | None) -> None:
    if tenant_id is not None:
        _default_cache.invalidate_tenant(int(tenant_id))


@contextmanager
def ai_write_transaction(description: str, tenant_id: int | None = None) -> Iterator[None]:
    """Commit through the canonical transaction helper, then drop stale reads."""

    from utils.db_safety import atomic_transaction

    with atomic_transaction(description):
        yield
    invalidate_tenant_reads(tenant_id)


__all__ = [
    "CacheKey",
    "ReadCache",
    "ai_write_transaction",
    "get_default_cache",
    "invalidate_tenant_reads",
    "make_key",
]
