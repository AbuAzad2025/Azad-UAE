"""Cashier shift model — tracks per-cashier shift lifecycle within a POS session."""

from datetime import UTC, datetime
from decimal import Decimal

from extensions import db


class PosShift(db.Model):
    __tablename__ = "pos_shifts"

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "shift_number", name="uq_pos_shifts_tenant_shift_number"),
        db.Index("idx_pos_shift_session_status", "tenant_id", "session_id", "status"),
        db.Index("idx_pos_shift_user_status", "tenant_id", "user_id", "status"),
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
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    shift_number = db.Column(db.String(50), nullable=False, index=True)

    session = db.relationship("PosSession", backref="shifts")

    opened_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    starting_cash = db.Column(db.Numeric(15, 3), default=Decimal("0"), nullable=False)
    system_sales_expected = db.Column(db.Numeric(15, 3), default=Decimal("0"))
    actual_cash_counted = db.Column(db.Numeric(15, 3), nullable=True)
    discrepancy = db.Column(db.Numeric(15, 3), nullable=True)

    total_sales = db.Column(db.Numeric(15, 3), default=Decimal("0"))
    total_cash_sales = db.Column(db.Numeric(15, 3), default=Decimal("0"))
    total_card_sales = db.Column(db.Numeric(15, 3), default=Decimal("0"))
    # Phase 3 — blind-close reconciliation inputs (base currency).
    total_change_given = db.Column(db.Numeric(15, 3), default=Decimal("0"))
    # Phase 4 — cash refunds paid out of the drawer for POS returns.
    total_cash_refunds = db.Column(db.Numeric(15, 3), default=Decimal("0"))
    total_pay_ins = db.Column(db.Numeric(15, 3), default=Decimal("0"))
    total_pay_outs = db.Column(db.Numeric(15, 3), default=Decimal("0"))

    status = db.Column(db.String(20), default="open", nullable=False, index=True)
    notes = db.Column(db.Text)

    SHIFT_OPEN = "open"
    SHIFT_RECONCILED = "reconciled"
    SHIFT_CLOSED = "closed"

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    @property
    def branch_id(self):
        """Branch ID via the parent session (PosShift has no direct branch_id column)."""
        return getattr(self.session, "branch_id", None) if self.session else None

    def compute_expected_cash(self) -> Decimal:
        """Expected drawer = starting + cash tendered − change − cash refunds + pay-ins − pay-outs."""
        starting = Decimal(str(self.starting_cash or 0))
        cash_sales = Decimal(str(self.total_cash_sales or 0))
        change = Decimal(str(self.total_change_given or 0))
        cash_refunds = Decimal(str(self.total_cash_refunds or 0))
        pay_ins = Decimal(str(self.total_pay_ins or 0))
        pay_outs = Decimal(str(self.total_pay_outs or 0))
        return starting + cash_sales - change - cash_refunds + pay_ins - pay_outs

    def reconcile(self, actual_cash: Decimal, notes: str | None = None):
        self.actual_cash_counted = Decimal(str(actual_cash))
        self.system_sales_expected = self.compute_expected_cash()
        self.discrepancy = self.actual_cash_counted - self.system_sales_expected
        self.status = self.SHIFT_RECONCILED
        if notes:
            self.notes = notes

    def close(self):
        self.status = self.SHIFT_CLOSED
        self.closed_at = datetime.now(UTC)

    @property
    def duration_minutes(self):
        end = self.closed_at or datetime.now(UTC)
        start = self.opened_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        return int((end - start).total_seconds() / 60)

    def to_dict(self, include_sensitive: bool = True):
        """Serialize the shift. Blind-close: expected/actual/discrepancy and
        tender totals are hidden from roles without expected-balance visibility
        (``include_sensitive=False``)."""
        data = {
            "id": self.id,
            "shift_number": self.shift_number,
            "session_id": self.session_id,
            "status": self.status,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "starting_cash": float(self.starting_cash or 0),
            "duration_minutes": self.duration_minutes,
        }
        if include_sensitive:
            data.update(
                {
                    "system_sales_expected": float(self.system_sales_expected or 0),
                    "actual_cash_counted": (
                        float(self.actual_cash_counted) if self.actual_cash_counted is not None else None
                    ),
                    "discrepancy": (float(self.discrepancy) if self.discrepancy is not None else None),
                    "total_sales": float(self.total_sales or 0),
                    "total_cash_sales": float(self.total_cash_sales or 0),
                    "total_card_sales": float(self.total_card_sales or 0),
                    "total_change_given": float(self.total_change_given or 0),
                    "total_cash_refunds": float(self.total_cash_refunds or 0),
                    "total_pay_ins": float(self.total_pay_ins or 0),
                    "total_pay_outs": float(self.total_pay_outs or 0),
                }
            )
        return data
