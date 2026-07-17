"""
Partner Transaction / Movement Ledger

Tracks every financial movement with a partner:
  • profit_share        — توزيع أرباح
  • loss_share          — توزيع خسارة
  • investment_return   — عائد استثمار
  • withdrawal          — مسحوبات
  • additional_investment — استثمار إضافي
  • expense_payment     — دفع نصيب من مصاريف
  • adjustment          — تسوية يدوية
"""

from datetime import datetime, timezone
from extensions import db
from utils.currency_utils import context_aware_default_currency


class PartnerTransaction(db.Model):
    __tablename__ = "partner_transactions"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    partner_id = db.Column(
        db.Integer, db.ForeignKey("partners.id"), nullable=False, index=True
    )

    # Link to distribution (optional)
    distribution_id = db.Column(
        db.Integer,
        db.ForeignKey("partner_profit_distributions.id"),
        nullable=True,
        index=True,
    )

    transaction_type = db.Column(db.String(30), nullable=False)
    # profit_share | loss_share | investment_return |
    # withdrawal | additional_investment | expense_payment | adjustment

    amount = db.Column(db.Numeric(15, 3), nullable=False)

    currency = db.Column(
        db.String(3), default=context_aware_default_currency
    )  # TODO: use Config.DEFAULT_CURRENCY
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    amount_base = db.Column(db.Numeric(15, 3), nullable=False)

    balance_after = db.Column(db.Numeric(15, 3), default=0)

    # Document reference
    reference_number = db.Column(db.String(100))
    reference_type = db.Column(
        db.String(30)
    )  # payment_voucher | journal_entry | manual
    reference_id = db.Column(db.Integer, nullable=True)

    transaction_date = db.Column(
        db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date()
    )

    notes = db.Column(db.Text)

    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    distribution = db.relationship(
        "PartnerProfitDistribution", foreign_keys=[distribution_id]
    )
    creator = db.relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<Tx {self.transaction_type} {self.amount} bal={self.balance_after}>"

    @property
    def transaction_type_label(self):
        labels = {
            "profit_share": "توزيع أرباح",
            "loss_share": "توزيع خسارة",
            "investment_return": "عائد استثمار",
            "withdrawal": "مسحوبات",
            "additional_investment": "استثمار إضافي",
            "expense_payment": "دفع مصاريف",
            "adjustment": "تسوية",
        }
        return labels.get(self.transaction_type, self.transaction_type)

    @property
    def is_credit(self):
        return float(self.amount or 0) > 0

    @property
    def is_debit(self):
        return float(self.amount or 0) < 0
