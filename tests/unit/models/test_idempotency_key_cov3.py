"""Gap coverage for models/idempotency_key.py — defaults, constants, repr."""

from __future__ import annotations

from models.idempotency_key import IdempotencyKey


class TestIdempotencyKeyBasics:
    def test_status_constants(self):
        assert IdempotencyKey.STATUS_IN_PROGRESS == "in_progress"
        assert IdempotencyKey.STATUS_COMPLETED == "completed"
        assert IdempotencyKey.STATUS_FAILED == "failed"

    def test_repr(self):
        key = IdempotencyKey(endpoint="/api/pos/checkout", key="abc-123", status="in_progress")
        text = repr(key)
        assert "/api/pos/checkout" in text
        assert "abc-123" in text
        assert "in_progress" in text

    def test_persist_defaults(self, db_session, sample_tenant):
        key = IdempotencyKey(
            tenant_id=sample_tenant.id,
            endpoint="/api/pos/checkout",
            key="cov3-key-1",
            request_hash="deadbeef",
        )
        db_session.add(key)
        db_session.flush()
        db_session.refresh(key)
        assert key.status == IdempotencyKey.STATUS_IN_PROGRESS
        assert key.created_at is not None
        assert key.completed_at is None
        assert key.response_body is None

    def test_persist_completed(self, db_session, sample_tenant):
        key = IdempotencyKey(
            tenant_id=sample_tenant.id,
            endpoint="/api/pos/refund",
            key="cov3-key-2",
            request_hash="cafef00d",
            status=IdempotencyKey.STATUS_COMPLETED,
            response_body='{"ok": true}',
            response_status=200,
        )
        db_session.add(key)
        db_session.flush()
        fetched = (
            db_session.query(IdempotencyKey)
            .filter_by(tenant_id=sample_tenant.id, endpoint="/api/pos/refund", key="cov3-key-2")
            .first()
        )
        assert fetched.response_status == 200
        assert "completed" in repr(fetched)
