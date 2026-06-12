from datetime import datetime, timezone
from decimal import Decimal
from extensions import db


class PosSession(db.Model):
    __tablename__ = 'pos_sessions'

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'session_number', name='uq_pos_sessions_tenant_session_number'),
        db.Index('idx_pos_session_branch_status', 'branch_id', 'status'),
        db.Index('idx_pos_session_user_status', 'user_id', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    session_number = db.Column(db.String(50), nullable=False, index=True)

    opened_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)

    opening_balance_cash = db.Column(db.Numeric(15, 3), default=0)

    closing_balance_cash = db.Column(db.Numeric(15, 3), nullable=True)
    expected_balance = db.Column(db.Numeric(15, 3), nullable=True)
    difference = db.Column(db.Numeric(15, 3), nullable=True)

    total_sales = db.Column(db.Numeric(15, 3), default=0)
    total_cash_sales = db.Column(db.Numeric(15, 3), default=0)
    total_card_sales = db.Column(db.Numeric(15, 3), default=0)

    status = db.Column(db.String(20), default='open', index=True)
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', foreign_keys=[user_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])
    tenant = db.relationship('Tenant', backref='pos_sessions', foreign_keys=[tenant_id])

    def close(self, closing_cash: Decimal, notes: str = None):
        self.closing_balance_cash = closing_cash
        self.expected_balance = Decimal(str(self.opening_balance_cash or 0)) + Decimal(str(self.total_cash_sales or 0))
        self.difference = closing_cash - self.expected_balance
        self.status = 'closed'
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
        return f'<PosSession {self.session_number} ({self.status})>'
