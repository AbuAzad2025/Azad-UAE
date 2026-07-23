"""Server-side parked POS cart (Phase 2 — concurrent tabs).

Replaces the localStorage-only hold carts with tenant-scoped, user-scoped
parked carts linked to the cashier's open PosSession, so a cart can be
parked on one terminal and resumed on another exactly once.
"""

from datetime import datetime, timezone

from extensions import db


class PosCart(db.Model):
    __tablename__ = "pos_carts"

    __table_args__ = (
        db.Index("idx_pos_cart_user_session_status", "user_id", "session_id", "status"),
        db.Index("idx_pos_cart_tenant_status", "tenant_id", "status"),
    )

    STATUS_PARKED = "parked"
    STATUS_RESUMED = "resumed"
    STATUS_EXPIRED = "expired"
    STATUSES = (STATUS_PARKED, STATUS_RESUMED, STATUS_EXPIRED)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("pos_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    label = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(20), default=STATUS_PARKED, nullable=False, index=True)

    # Compact cart snapshot: whitelisted keys only (lines, customer_id,
    # warehouse_id, currency, exchange_rate, order_type, notes, totals hints).
    payload = db.Column(db.JSON, nullable=False)

    # Denormalized summary fields so list endpoints never parse the payload.
    item_count = db.Column(db.Integer, default=0, nullable=False)
    total_estimate = db.Column(db.Numeric(15, 3), default=0, nullable=False)
    currency = db.Column(db.String(3), nullable=True)

    parked_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    resumed_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    session = db.relationship("PosSession", foreign_keys=[session_id])
    user = db.relationship("User", foreign_keys=[user_id])
    tenant = db.relationship("Tenant", backref="pos_carts", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<PosCart {self.id} ({self.status})>"

    def to_summary_dict(self):
        """Lightweight shape for list endpoints — never includes payload."""
        return {
            "id": self.id,
            "label": self.label or "",
            "status": self.status,
            "item_count": int(self.item_count or 0),
            "total_estimate": float(self.total_estimate or 0),
            "currency": self.currency,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "parked_at": self.parked_at.isoformat() if self.parked_at else None,
            "resumed_at": self.resumed_at.isoformat() if self.resumed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_detail_dict(self):
        data = self.to_summary_dict()
        data["payload"] = self.payload
        return data
