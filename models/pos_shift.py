"""Cashier shift model — tracks per-cashier shift lifecycle within a POS session."""

from datetime import datetime, timezone
from decimal import Decimal

from extensions import db


class PosShift(db.Model):
    __tablename__ = "pos_shifts"

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "shift_number", name="uq_pos_shifts_tenant_shift_number"),
        db.Index("idx_pos_shift_session_status", "session_id", "status"),
        db.Index("idx_pos_shift_user_status", "user_id", "status"),
    )

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
    shift_number = db.Column(db.String(50), nullable=False, index=True)

    opened_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)

    starting_cash = db.Column(db.Numeric(15, 3), default=Decimal("0"), nullable=False)
    system_sales_expected = db.Column(db.Numeric(15, 3), default=Decimal("0"))
    actual_cash_counted = db.Column(db.Numeric(15, 3), nullable=True)
    discrepancy = db.Column(db.Numeric(15, 3), nullable=True)

    total_sales = db.Column(db.Numeric(15, 3), default=Decimal("0"))
    total_cash_sales = db.Column(db.Numeric(15, 3), default=Decimal("0"))
    total_card_sales = db.Column(db.Numeric(15, 3), default=Decimal("0"))

    status = db.Column(db.String(20), default="open", nullable=False, index=True)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    SHIFT_OPEN = "open"
    SHIFT_RECONCILED = "reconciled"
    SHIFT_CLOSED = "closed"

    def reconcile(self, actual_cash: Decimal, notes: str | None = None):
        self.actual_cash_counted = Decimal(str(actual_cash))
        self.system_sales_expected = Decimal(str(self.starting_cash or 0)) + Decimal(str(self.total_cash_sales or 0))
        self.discrepancy = self.actual_cash_counted - self.system_sales_expected
        self.status = self.SHIFT_RECONCILED
        if notes:
            self.notes = notes

    def close(self):
        self.status = self.SHIFT_CLOSED
        self.closed_at = datetime.now(timezone.utc)

    @property
    def duration_minutes(self):
        end = self.closed_at or datetime.now(timezone.utc)
        start = self.opened_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return int((end - start).total_seconds() / 60)

    def to_dict(self):
        return {
            "id": self.id,
            "shift_number": self.shift_number,
            "session_id": self.session_id,
            "status": self.status,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "starting_cash": float(self.starting_cash or 0),
            "system_sales_expected": float(self.system_sales_expected or 0),
            "actual_cash_counted": (float(self.actual_cash_counted) if self.actual_cash_counted is not None else None),
            "discrepancy": (float(self.discrepancy) if self.discrepancy is not None else None),
            "total_sales": float(self.total_sales or 0),
            "total_cash_sales": float(self.total_cash_sales or 0),
            "total_card_sales": float(self.total_card_sales or 0),
            "duration_minutes": self.duration_minutes,
        }
