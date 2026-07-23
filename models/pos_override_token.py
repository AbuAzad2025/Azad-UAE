"""One-time POS manager override tokens (Phase 3).

A supervisor authorizes a critical POS action with their PIN; the row below
is the server-side record that gives the issued token its single-use
semantics. The token string itself is ``<id>.<nonce>.<hmac>`` — signed via
``utils/pos_security.sign_override_token``.
"""

from datetime import datetime, timezone

from extensions import db


class PosOverrideToken(db.Model):
    __tablename__ = "pos_override_tokens"

    __table_args__ = (db.Index("idx_pos_override_token_cashier", "cashier_user_id", "action"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = db.Column(db.String(40), nullable=False, index=True)
    cashier_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    supervisor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey("pos_sessions.id", ondelete="SET NULL"), nullable=True)

    nonce = db.Column(db.String(64), nullable=False, unique=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    cashier = db.relationship("User", foreign_keys=[cashier_user_id])
    supervisor = db.relationship("User", foreign_keys=[supervisor_user_id])
    session = db.relationship("PosSession", foreign_keys=[session_id])

    def is_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        expires = self.expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires is None or now >= expires

    def __repr__(self):
        return f"<PosOverrideToken {self.action} cashier={self.cashier_user_id} by={self.supervisor_user_id}>"
