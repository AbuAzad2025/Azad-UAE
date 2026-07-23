"""POS cash movements — pay-ins / pay-outs against the session drawer (Phase 3)."""

from datetime import datetime, timezone

from extensions import db


class PosCashMovement(db.Model):
    __tablename__ = "pos_cash_movements"

    __table_args__ = (
        db.Index("idx_pos_cash_movement_session", "session_id", "movement_type"),
        db.Index("idx_pos_cash_movement_shift", "shift_id"),
    )

    TYPE_PAY_IN = "pay_in"
    TYPE_PAY_OUT = "pay_out"
    TYPES = (TYPE_PAY_IN, TYPE_PAY_OUT)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False, index=True)
    # Acting cashier who performed the movement.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("pos_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shift_id = db.Column(db.Integer, db.ForeignKey("pos_shifts.id", ondelete="SET NULL"), nullable=True)
    # Supervisor who authorized the movement via override, when applicable.
    authorized_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    movement_type = db.Column(db.String(10), nullable=False, index=True)
    # Amount in tenant base currency, quantized to 0.001.
    amount = db.Column(db.Numeric(15, 3), nullable=False)
    reason = db.Column(db.String(255), nullable=False)

    gl_entry_id = db.Column(db.Integer, db.ForeignKey("gl_journal_entries.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    session = db.relationship("PosSession", foreign_keys=[session_id])
    shift = db.relationship("PosShift", foreign_keys=[shift_id])
    user = db.relationship("User", foreign_keys=[user_id])
    authorized_by = db.relationship("User", foreign_keys=[authorized_by_user_id])
    gl_entry = db.relationship("GLJournalEntry", foreign_keys=[gl_entry_id])

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "shift_id": self.shift_id,
            "movement_type": self.movement_type,
            "amount": float(self.amount or 0),
            "reason": self.reason or "",
            "user_id": self.user_id,
            "authorized_by_user_id": self.authorized_by_user_id,
            "gl_entry_id": self.gl_entry_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<PosCashMovement {self.movement_type} {self.amount} session={self.session_id}>"
