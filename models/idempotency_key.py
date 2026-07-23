"""POS Phase 4 — durable idempotency ledger for offline-first POS writes.

Modeled on the SyncBatch pattern: the record is created inside the same
``atomic_transaction`` as the write it protects, so a rollback removes it and
allows a clean retry. A completed record stores the exact JSON response so a
retried request (same tenant + endpoint + key) replays the original response
without re-executing the business write.
"""

from datetime import datetime, timezone

from extensions import db


class IdempotencyKey(db.Model):
    __tablename__ = "idempotency_keys"

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "endpoint", "key", name="uq_idempotency_keys_scope"),
        db.Index("ix_idempotency_keys_tenant_status", "tenant_id", "status"),
    )

    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint = db.Column(db.String(100), nullable=False)
    key = db.Column(db.String(128), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    request_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), default=STATUS_IN_PROGRESS, nullable=False, index=True)
    response_body = db.Column(db.Text, nullable=True)
    response_status = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    completed_at = db.Column(db.DateTime, nullable=True)

    tenant = db.relationship("Tenant", backref="idempotency_keys", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<IdempotencyKey {self.endpoint}:{self.key} [{self.status}]>"
