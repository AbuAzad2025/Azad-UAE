"""Append-only POS fraud/irregularity signal log (hash-chained, insert-only)."""

from __future__ import annotations

from datetime import UTC, datetime

from extensions import db


class PosFraudSignal(db.Model):
    """Immutable POS irregularity signal.

    Rows are hash-chained per tenant: ``entry_hash`` covers the row content
    prefixed by the previous row's hash, so silent edits or deletions break
    the chain and are detectable on verification. Rows are never updated or
    deleted — there is no purge path.
    """

    __tablename__ = "pos_fraud_signals"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("pos_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type = db.Column(db.String(40), nullable=False, index=True)
    severity = db.Column(db.String(10), nullable=False, default="medium")
    repeat_count = db.Column(db.Integer, nullable=False, default=1)
    details = db.Column(db.Text, nullable=True)
    prev_hash = db.Column(db.String(64), nullable=False, default="")
    entry_hash = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
