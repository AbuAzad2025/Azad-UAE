from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from extensions import db

_AED_QUANTUM = Decimal("0.001")


class PosSession(db.Model):
    __tablename__ = "pos_sessions"

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "session_number", name="uq_pos_sessions_tenant_session_number"),
        db.Index("idx_pos_session_branch_status", "branch_id", "status"),
        db.Index("idx_pos_session_user_status", "user_id", "status"),
    )

    STATUS_OPEN = "open"
    STATUS_PAUSED = "paused"
    STATUS_CLOSED = "closed"
    # Allowed state-machine transitions: open -> paused -> open, and
    # open|paused -> closed. Closed is terminal.
    ALLOWED_TRANSITIONS = frozenset(
        {
            (STATUS_OPEN, STATUS_PAUSED),
            (STATUS_PAUSED, STATUS_OPEN),
            (STATUS_OPEN, STATUS_CLOSED),
            (STATUS_PAUSED, STATUS_CLOSED),
        }
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    session_number = db.Column(db.String(50), nullable=False, index=True)

    # Phase 3 — terminal binding. Client-supplied terminal identifier; when
    # set, session-scoped mutations require the HMAC session token issued at
    # open (see utils/pos_security.py).
    terminal_id = db.Column(db.String(100), nullable=True)

    opened_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    paused_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)

    opening_balance_cash = db.Column(db.Numeric(15, 3), default=0)

    closing_balance_cash = db.Column(db.Numeric(15, 3), nullable=True)
    expected_balance = db.Column(db.Numeric(15, 3), nullable=True)
    difference = db.Column(db.Numeric(15, 3), nullable=True)

    total_sales = db.Column(db.Numeric(15, 3), default=0)
    # Gross cash tendered (base currency) — change handed back is tracked
    # separately so the expected drawer never double-counts it.
    total_cash_sales = db.Column(db.Numeric(15, 3), default=0)
    total_card_sales = db.Column(db.Numeric(15, 3), default=0)
    total_change_given = db.Column(db.Numeric(15, 3), default=0)
    # Phase 4 — cash refunds handed out of the drawer for POS returns (base
    # currency). Tracked separately so gross tendered cash stays intact.
    total_cash_refunds = db.Column(db.Numeric(15, 3), default=0)
    total_pay_ins = db.Column(db.Numeric(15, 3), default=0)
    total_pay_outs = db.Column(db.Numeric(15, 3), default=0)

    status = db.Column(db.String(20), default="open", index=True)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", foreign_keys=[user_id])
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    tenant = db.relationship("Tenant", backref="pos_sessions", foreign_keys=[tenant_id])

    def _transition(self, target: str):
        if (self.status, target) not in self.ALLOWED_TRANSITIONS:
            raise ValueError(f"انتقال غير مسموح لحالة الجلسة: {self.status} → {target}.")
        self.status = target

    def pause(self):
        self._transition(self.STATUS_PAUSED)
        self.paused_at = datetime.now(timezone.utc)

    def resume(self):
        self._transition(self.STATUS_OPEN)
        self.paused_at = None

    def compute_expected_balance(self) -> Decimal:
        """Expected drawer = opening + cash tendered − change − cash refunds + pay-ins − pay-outs."""
        opening = Decimal(str(self.opening_balance_cash or 0))
        cash_sales = Decimal(str(self.total_cash_sales or 0))
        change = Decimal(str(self.total_change_given or 0))
        cash_refunds = Decimal(str(self.total_cash_refunds or 0))
        pay_ins = Decimal(str(self.total_pay_ins or 0))
        pay_outs = Decimal(str(self.total_pay_outs or 0))
        return (opening + cash_sales - change - cash_refunds + pay_ins - pay_outs).quantize(
            _AED_QUANTUM, rounding=ROUND_HALF_UP
        )

    def close(self, closing_cash: Decimal, notes: str | None = None):
        if self.status == self.STATUS_CLOSED:
            raise ValueError("الجلسة مغلقة مسبقاً.")
        closing_cash = Decimal(str(closing_cash)).quantize(_AED_QUANTUM, rounding=ROUND_HALF_UP)
        self.closing_balance_cash = closing_cash
        self.expected_balance = self.compute_expected_balance()
        self.difference = (closing_cash - self.expected_balance).quantize(_AED_QUANTUM, rounding=ROUND_HALF_UP)
        self._transition(self.STATUS_CLOSED)
        self.closed_at = datetime.now(timezone.utc)
        if notes:
            self.notes = notes

    @property
    def duration_minutes(self):
        opened = self.opened_at
        if opened and opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        if not self.closed_at:
            return int((datetime.now(timezone.utc) - opened).total_seconds() / 60)
        closed = self.closed_at
        if closed and closed.tzinfo is None:
            closed = closed.replace(tzinfo=timezone.utc)
        return int((closed - opened).total_seconds() / 60)

    def __repr__(self):
        return f"<PosSession {self.session_number} ({self.status})>"
