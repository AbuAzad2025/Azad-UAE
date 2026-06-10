"""
Partner Profit / Loss Distribution

Represents one distribution period for one partner.
Created per period (monthly / quarterly) by PartnerService.
"""
from datetime import datetime, timezone
from extensions import db


class PartnerProfitDistribution(db.Model):
    __tablename__ = 'partner_profit_distributions'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('partners.id'), nullable=False, index=True)

    # Period
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)

    # Revenue scope
    scope_type = db.Column(db.String(20), default='company')  # company / branch / warehouse
    scope_id = db.Column(db.Integer, nullable=True)

    # Financials (in base currency — unified)
    total_revenue = db.Column(db.Numeric(15, 3), default=0)
    total_cogs = db.Column(db.Numeric(15, 3), default=0)
    total_expenses = db.Column(db.Numeric(15, 3), default=0)
    net_profit = db.Column(db.Numeric(15, 3), default=0)

    # Partner share
    share_percentage = db.Column(db.Numeric(5, 2), default=0)
    share_amount = db.Column(db.Numeric(15, 3), default=0)

    # Expense share (if partner bears part of expenses)
    expense_share_percentage = db.Column(db.Numeric(5, 2), default=0)
    expense_share_amount = db.Column(db.Numeric(15, 3), default=0)

    # Loss (if net_profit < 0)
    loss_share_percentage = db.Column(db.Numeric(5, 2), default=0)
    loss_share_amount = db.Column(db.Numeric(15, 3), default=0)

    # Fixed amount (if partner has fixed monthly)
    fixed_amount = db.Column(db.Numeric(15, 3), default=0)

    # Final net amount due to partner
    net_due = db.Column(db.Numeric(15, 3), default=0)
    # formula: share_amount - expense_share_amount - loss_share_amount + fixed_amount

    # Status
    status = db.Column(db.String(20), default='draft', index=True)  # draft / approved / paid / cancelled

    # Audit
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    approver = db.relationship('User', foreign_keys=[approved_by])

    def __repr__(self):
        return (f'<Distribution P{self.partner_id} '
                f'{self.period_start}–{self.period_end} '
                f'@{self.share_percentage}% = {self.net_due}>')

    @property
    def status_label(self):
        labels = {
            'draft': 'مسودة',
            'approved': 'معتمد',
            'paid': 'مدفوع',
            'cancelled': 'ملغي',
        }
        return labels.get(self.status, self.status)
