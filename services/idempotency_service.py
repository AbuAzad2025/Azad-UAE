"""POS Phase 4 — offline-first idempotency for POS write endpoints.

SyncBatch-style durable ledger, generalized for HTTP endpoints:

- ``begin()`` runs INSIDE the caller's ``atomic_transaction`` — on rollback
  the ledger row vanishes, so a failed attempt never poisons the key.
- First execution inserts an ``in_progress`` row, runs the business write,
  then ``complete()`` stores the exact JSON response on the same row.
- A retry with the same (tenant, endpoint, key) and the same request hash
  replays the stored response WITHOUT re-executing the write.
- A retry that finds an ``in_progress`` row (concurrent double-submit or a
  crashed attempt mid-flight) raises :class:`IdempotencyInFlightError` → 409.
- Same key with a DIFFERENT payload raises :class:`IdempotencyHashMismatchError`
  → 422, so clients cannot accidentally reuse keys.
- Keys carry a 24h TTL: expired rows are replaced by a fresh execution. A
  periodic sweep of old rows is optional (the unique constraint is scoped by
  endpoint, so un-swept rows only delay reuse of that exact key).

The in-transaction re-check closes the race between the pre-check and the
insert; the unique constraint ``(tenant_id, endpoint, key)`` is the final
guard — a losing concurrent insert surfaces as an IntegrityError which the
route maps to 409.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from extensions import db
from models import IdempotencyKey

IDEMPOTENCY_TTL = timedelta(hours=24)


class IdempotencyInFlightError(Exception):
    """A request with this key is currently being processed (or crashed)."""


class IdempotencyHashMismatchError(Exception):
    """Same idempotency key reused with a different request payload."""


def hash_request_payload(payload: Any) -> str:
    """Deterministic SHA-256 of the canonical JSON payload."""
    canonical = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_expired(record: IdempotencyKey) -> bool:
    created = record.created_at
    if created is None:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - created > IDEMPOTENCY_TTL


class IdempotencyService:
    """Flush-only service; the route owns the transaction boundary."""

    @staticmethod
    def _scoped_query(tenant_id: int, endpoint: str, key: str):
        return IdempotencyKey.query.filter_by(
            tenant_id=int(tenant_id),
            endpoint=endpoint,
            key=key,
        )

    @staticmethod
    def begin(*, tenant_id: int, endpoint: str, key: str, user_id: int | None, request_hash: str):
        """Start (or replay) an idempotent execution.

        Returns ``(record, stored)``: when ``stored`` is not None it is the
        previously stored ``(response_payload, status_code)`` pair and the
        caller must replay it without executing the business write. Otherwise
        ``record`` is a fresh in-progress row the caller completes later.
        """
        existing = IdempotencyService._scoped_query(tenant_id, endpoint, key).first()
        if existing is not None and _is_expired(existing):
            db.session.delete(existing)
            db.session.flush()
            existing = None

        if existing is not None:
            if existing.request_hash != request_hash:
                raise IdempotencyHashMismatchError("Idempotency key was already used with a different payload.")
            if existing.status == IdempotencyKey.STATUS_COMPLETED:
                stored = None
                if existing.response_body:
                    stored = (json.loads(existing.response_body), existing.response_status or 200)
                return None, stored
            raise IdempotencyInFlightError("A request with this idempotency key is in progress.")

        record = IdempotencyKey(
            tenant_id=int(tenant_id),
            endpoint=endpoint,
            key=key,
            user_id=user_id,
            request_hash=request_hash,
            status=IdempotencyKey.STATUS_IN_PROGRESS,
        )
        db.session.add(record)
        db.session.flush()
        return record, None

    @staticmethod
    def complete(record: IdempotencyKey, response_payload: dict, status_code: int = 200):
        """Persist the final response on the in-progress row (flush only)."""
        record.status = IdempotencyKey.STATUS_COMPLETED
        record.response_body = json.dumps(response_payload, ensure_ascii=False, default=str)
        record.response_status = int(status_code)
        record.completed_at = datetime.now(timezone.utc)
        db.session.flush()
