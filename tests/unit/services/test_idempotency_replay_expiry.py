"""IdempotencyService — replay lookup, TTL expiry edges, empty-body replay.

Complements test_idempotency_service.py by covering the read-only
``replay_if_completed`` contract and the ``_is_expired`` timezone branches
that decide whether a stored response is still fresh.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from models import IdempotencyKey
from services.idempotency_service import (
    IDEMPOTENCY_TTL,
    IdempotencyHashMismatchError,
    IdempotencyInFlightError,
    IdempotencyService,
    hash_request_payload,
)

PAYLOAD = {"lines": [{"sku": "X", "qty": 2}]}


def _hash(payload=None):
    return hash_request_payload(payload if payload is not None else PAYLOAD)


def _make_record(
    db_session,
    sample_tenant,
    *,
    key="k",
    endpoint="pos.checkout",
    body=None,
    status=IdempotencyKey.STATUS_COMPLETED,
    response_status=200,
    created_at=None,
):
    record = IdempotencyKey(
        tenant_id=sample_tenant.id,
        endpoint=endpoint,
        key=key,
        user_id=None,
        request_hash=_hash(),
        status=status,
    )
    if body is not None:
        record.response_body = body
    record.response_status = response_status
    db_session.add(record)
    db_session.flush()
    if created_at is not None:
        record.created_at = created_at
        db_session.flush()
    return record


class TestReplayIfCompleted:
    def test_fresh_key_returns_none(self, db_session, sample_tenant):
        assert (
            IdempotencyService.replay_if_completed(
                tenant_id=sample_tenant.id, endpoint="pos.checkout", key="fresh", request_hash=_hash()
            )
            is None
        )

    def test_completed_row_replays_exact_payload_and_status(self, db_session, sample_tenant):
        _make_record(db_session, sample_tenant, key="done", body='{"ok": true, "id": 7}', response_status=201)
        stored = IdempotencyService.replay_if_completed(
            tenant_id=sample_tenant.id, endpoint="pos.checkout", key="done", request_hash=_hash()
        )
        assert stored == ({"ok": True, "id": 7}, 201)

    def test_hash_mismatch_raises_even_when_completed(self, db_session, sample_tenant):
        _make_record(db_session, sample_tenant, key="hmm", body='{"ok": true}')
        with pytest.raises(IdempotencyHashMismatchError):
            IdempotencyService.replay_if_completed(
                tenant_id=sample_tenant.id, endpoint="pos.checkout", key="hmm", request_hash=_hash({"other": 1})
            )

    def test_in_progress_row_raises(self, db_session, sample_tenant):
        _make_record(
            db_session,
            sample_tenant,
            key="wip",
            status=IdempotencyKey.STATUS_IN_PROGRESS,
        )
        with pytest.raises(IdempotencyInFlightError):
            IdempotencyService.replay_if_completed(
                tenant_id=sample_tenant.id, endpoint="pos.checkout", key="wip", request_hash=_hash()
            )

    def test_expired_completed_row_returns_none(self, db_session, sample_tenant):
        stale = datetime.now(UTC) - IDEMPOTENCY_TTL - timedelta(minutes=5)
        _make_record(db_session, sample_tenant, key="old", body='{"ok": true}', created_at=stale)
        assert (
            IdempotencyService.replay_if_completed(
                tenant_id=sample_tenant.id, endpoint="pos.checkout", key="old", request_hash=_hash()
            )
            is None
        )


class TestIsExpiredBranches:
    def test_created_at_none_means_never_expired(self):
        """A NULL created_at record never expires (defensive clock branch)."""
        from types import SimpleNamespace

        from services.idempotency_service import _is_expired

        assert _is_expired(SimpleNamespace(created_at=None)) is False

    def test_naive_timestamp_compared_as_utc(self, db_session, sample_tenant):
        naive_stale = (datetime.now(UTC) - IDEMPOTENCY_TTL - timedelta(hours=2)).replace(tzinfo=None)
        _make_record(db_session, sample_tenant, key="naive-old", body='{"ok": 1}', created_at=naive_stale)
        assert (
            IdempotencyService.replay_if_completed(
                tenant_id=sample_tenant.id, endpoint="pos.checkout", key="naive-old", request_hash=_hash()
            )
            is None
        )

        naive_recent = (datetime.now(UTC) - timedelta(minutes=1)).replace(tzinfo=None)
        _make_record(db_session, sample_tenant, key="naive-new", body='{"ok": 2}', created_at=naive_recent)
        assert IdempotencyService.replay_if_completed(
            tenant_id=sample_tenant.id, endpoint="pos.checkout", key="naive-new", request_hash=_hash()
        ) == ({"ok": 2}, 200)


class TestBeginWithEmptyStoredBody:
    def test_begin_on_completed_row_without_body_returns_none_none(self, db_session, sample_tenant):
        _make_record(db_session, sample_tenant, key="empty", body="", status=IdempotencyKey.STATUS_COMPLETED)
        record, stored = IdempotencyService.begin(
            tenant_id=sample_tenant.id,
            endpoint="pos.checkout",
            key="empty",
            user_id=None,
            request_hash=_hash(),
        )
        assert record is None
        assert stored is None

    def test_replay_of_bodyless_completed_row_is_none_not_in_flight(self, db_session, sample_tenant):
        _make_record(db_session, sample_tenant, key="empty2", body="", status=IdempotencyKey.STATUS_COMPLETED)
        result = IdempotencyService.replay_if_completed(
            tenant_id=sample_tenant.id, endpoint="pos.checkout", key="empty2", request_hash=_hash()
        )
        assert result is None

    def test_begin_deletes_expired_row_and_creates_fresh(self, db_session, sample_tenant):
        stale = datetime.now(UTC) - IDEMPOTENCY_TTL - timedelta(days=1)
        old = _make_record(db_session, sample_tenant, key="rot", body='{"ok": 1}', created_at=stale)
        record, stored = IdempotencyService.begin(
            tenant_id=sample_tenant.id,
            endpoint="pos.checkout",
            key="rot",
            user_id=None,
            request_hash=_hash(),
        )
        assert stored is None
        assert record is not None
        assert record.id != old.id
        assert record.status == IdempotencyKey.STATUS_IN_PROGRESS
