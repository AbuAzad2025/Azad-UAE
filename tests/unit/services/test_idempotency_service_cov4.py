"""Cov4: idempotency_service — hash/expiry/replay/begin/complete arcs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.idempotency_service import (
    IdempotencyHashMismatchError,
    IdempotencyInFlightError,
    IdempotencyService,
    _is_expired,
    hash_request_payload,
)


def test_hash_deterministic_and_default_str():
    assert hash_request_payload({"b": 1, "a": 2}) == hash_request_payload({"a": 2, "b": 1})
    assert hash_request_payload(None) == hash_request_payload({})
    assert hash_request_payload({"d": datetime(2026, 1, 1)})  # default=str branch


def test_is_expired_branches(db_session, sample_tenant):
    from models import IdempotencyKey

    rec = IdempotencyKey(
        tenant_id=sample_tenant.id, endpoint="e", key="k1", request_hash="h",
        status=IdempotencyKey.STATUS_IN_PROGRESS,
    )
    rec.created_at = None
    assert _is_expired(rec) is False
    rec.created_at = datetime.now(UTC) - timedelta(hours=25)
    assert _is_expired(rec) is True
    naive = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=25)  # naive tzinfo branch
    rec.created_at = naive
    assert _is_expired(rec) is True
    rec.created_at = datetime.now(UTC)
    assert _is_expired(rec) is False


def _h(payload):
    return hash_request_payload(payload)


def test_replay_none_when_fresh(db_session, sample_tenant):
    assert IdempotencyService.replay_if_completed(
        tenant_id=sample_tenant.id, endpoint="cov4-ep", key="fresh-key", request_hash=_h({})
    ) is None


def test_begin_then_complete_then_replay(db_session, sample_tenant):
    h = _h({"a": 1})
    record, stored = IdempotencyService.begin(
        tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-replay",
        user_id=None, request_hash=h,
    )
    assert stored is None
    assert record is not None
    # in-flight replay raises
    with pytest.raises(IdempotencyInFlightError):
        IdempotencyService.replay_if_completed(
            tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-replay", request_hash=h
        )
    IdempotencyService.complete(record, {"ok": True}, 201)
    payload, status = IdempotencyService.replay_if_completed(
        tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-replay", request_hash=h
    )
    assert payload == {"ok": True}
    assert status == 201
    # begin on completed returns stored pair
    rec2, stored2 = IdempotencyService.begin(
        tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-replay",
        user_id=None, request_hash=h,
    )
    assert rec2 is None
    assert stored2 == ({"ok": True}, 201)


def test_hash_mismatch_and_inflight(db_session, sample_tenant):
    h1 = _h({"a": 1})
    h2 = _h({"a": 2})
    IdempotencyService.begin(
        tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-mm",
        user_id=None, request_hash=h1,
    )
    with pytest.raises(IdempotencyHashMismatchError):
        IdempotencyService.begin(
            tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-mm",
            user_id=None, request_hash=h2,
        )
    with pytest.raises(IdempotencyHashMismatchError):
        IdempotencyService.replay_if_completed(
            tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-mm", request_hash=h2
        )
    with pytest.raises(IdempotencyInFlightError):
        IdempotencyService.begin(
            tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-mm",
            user_id=None, request_hash=h1,
        )


def test_completed_without_body_replays_none(db_session, sample_tenant):
    from models import IdempotencyKey

    rec = IdempotencyKey(
        tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-nobody",
        request_hash=_h({}), status=IdempotencyKey.STATUS_COMPLETED, response_body=None,
    )
    db_session.add(rec)
    db_session.flush()
    assert IdempotencyService.replay_if_completed(
        tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-nobody", request_hash=_h({})
    ) is None
    _, stored = IdempotencyService.begin(
        tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-nobody",
        user_id=None, request_hash=_h({}),
    )
    assert stored is None


def test_expired_row_replaced_and_replay_none(db_session, sample_tenant):
    from models import IdempotencyKey

    rec = IdempotencyKey(
        tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-old",
        request_hash=_h({}), status=IdempotencyKey.STATUS_COMPLETED, response_body='{"a":1}',
    )
    db_session.add(rec)
    db_session.flush()
    rec.created_at = datetime.now(UTC) - timedelta(hours=30)
    db_session.flush()
    assert IdempotencyService.replay_if_completed(
        tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-old", request_hash=_h({})
    ) is None
    record, stored = IdempotencyService.begin(
        tenant_id=sample_tenant.id, endpoint="cov4-ep", key="k-old",
        user_id=None, request_hash=_h({}),
    )
    assert stored is None
    assert record is not None
