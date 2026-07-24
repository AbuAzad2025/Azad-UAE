"""POS Phase 4 — idempotency ledger service (real db_session, savepoint-isolated)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from models import IdempotencyKey
from services.idempotency_service import (
    IDEMPOTENCY_TTL,
    IdempotencyHashMismatchError,
    IdempotencyInFlightError,
    IdempotencyService,
    hash_request_payload,
)


def _begin(tenant_id, key="k1", endpoint="pos.checkout", payload=None, user_id=None):
    return IdempotencyService.begin(
        tenant_id=tenant_id,
        endpoint=endpoint,
        key=key,
        user_id=user_id,
        request_hash=hash_request_payload(payload or {"lines": [1]}),
    )


class TestHashRequestPayload:
    def test_deterministic_and_order_insensitive(self):
        a = hash_request_payload({"b": 2, "a": 1})
        b = hash_request_payload({"a": 1, "b": 2})
        assert a == b

    def test_different_payloads_differ(self):
        assert hash_request_payload({"a": 1}) != hash_request_payload({"a": 2})


class TestBeginCompleteReplay:
    def test_first_execution_creates_in_progress_row(self, db_session, sample_tenant):
        record, stored = _begin(sample_tenant.id)
        assert stored is None
        assert record.status == IdempotencyKey.STATUS_IN_PROGRESS
        assert record.tenant_id == sample_tenant.id

    def test_completed_key_replays_stored_response(self, db_session, sample_tenant):
        record, _ = _begin(sample_tenant.id, payload={"lines": [1]})
        IdempotencyService.complete(record, {"success": True, "sale_id": 5}, 200)

        record2, stored = _begin(sample_tenant.id, payload={"lines": [1]})
        assert record2 is None
        assert stored == ({"success": True, "sale_id": 5}, 200)

    def test_in_progress_key_raises_in_flight(self, db_session, sample_tenant):
        _begin(sample_tenant.id)
        with pytest.raises(IdempotencyInFlightError):
            _begin(sample_tenant.id)

    def test_hash_mismatch_raises(self, db_session, sample_tenant):
        record, _ = _begin(sample_tenant.id, payload={"lines": [1]})
        IdempotencyService.complete(record, {"success": True}, 200)
        with pytest.raises(IdempotencyHashMismatchError):
            _begin(sample_tenant.id, payload={"lines": [2]})

    def test_same_key_different_endpoint_is_independent(self, db_session, sample_tenant):
        record, _ = _begin(sample_tenant.id, key="shared", endpoint="pos.checkout")
        IdempotencyService.complete(record, {"success": True}, 200)
        record2, stored = _begin(sample_tenant.id, key="shared", endpoint="pos.return")
        assert stored is None
        assert record2 is not None

    def test_same_key_different_tenant_is_independent(self, db_session, sample_tenant):
        from models import Tenant

        other = Tenant(
            name="Other Co",
            name_ar="أخرى",
            slug="other-co-idem",
            email="other-idem@example.com",
            country="AE",
            subscription_plan="pro",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(other)
        db_session.flush()

        record, _ = _begin(sample_tenant.id, key="shared")
        IdempotencyService.complete(record, {"success": True}, 200)
        record2, stored = _begin(other.id, key="shared")
        assert stored is None
        assert record2.tenant_id == other.id


class TestExpiry:
    def test_expired_completed_key_allows_fresh_execution(self, db_session, sample_tenant):
        record, _ = _begin(sample_tenant.id)
        IdempotencyService.complete(record, {"success": True, "sale_id": 9}, 200)
        record.created_at = datetime.now(timezone.utc) - IDEMPOTENCY_TTL - timedelta(hours=1)
        db_session.flush()

        record2, stored = _begin(sample_tenant.id)
        assert stored is None
        assert record2 is not None
        assert record2.id != record.id

    def test_fresh_completed_key_not_expired(self, db_session, sample_tenant):
        record, _ = _begin(sample_tenant.id)
        IdempotencyService.complete(record, {"success": True}, 200)
        record.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.flush()
        _, stored = _begin(sample_tenant.id)
        assert stored == ({"success": True}, 200)


class TestUniqueConstraint:
    def test_duplicate_insert_fails(self, db_session, sample_tenant):
        from sqlalchemy.exc import IntegrityError

        _begin(sample_tenant.id, key="dup")
        db_session.add(
            IdempotencyKey(
                tenant_id=sample_tenant.id,
                endpoint="pos.checkout",
                key="dup",
                request_hash="x" * 64,
                status=IdempotencyKey.STATUS_IN_PROGRESS,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()
