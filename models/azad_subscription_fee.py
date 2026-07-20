from datetime import datetime, timezone

from extensions import db


class AzadSubscriptionFee(db.Model):
    """Subscription fee (monthly/yearly/perpetual) billed to each tenant by Azad platform."""

    __tablename__ = "azad_subscription_fees"
    __table_args__ = (
        db.Index("ix_azad_subscription_fees_tenant_status", "tenant_id", "status"),
        db.Index(
            "ix_azad_subscription_fees_period",
            "billing_period_start",
            "billing_period_end",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    fee_type = db.Column(db.String(20), nullable=False, default="monthly")  # monthly, yearly, perpetual
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False)

    billing_period_start = db.Column(db.Date, nullable=True)
    billing_period_end = db.Column(db.Date, nullable=True)

    # accrued = posted to GL as payable (expense + liability)
    # paid = tenant actually paid cash/bank (liability + asset reduction)
    status = db.Column(db.String(20), nullable=False, default="accrued", index=True)

    gl_posted = db.Column(db.Boolean, nullable=False, default=False)
    gl_posted_at = db.Column(db.DateTime, nullable=True)

    # When tenant actually pays
    paid_at = db.Column(db.DateTime, nullable=True)
    paid_amount_aed = db.Column(db.Numeric(15, 3), nullable=True)
    payment_method = db.Column(db.String(50), nullable=True)  # cash, bank_transfer, card
    payment_reference = db.Column(db.String(120), nullable=True)

    notes = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<AzadSubscriptionFee tenant={self.tenant_id} type={self.fee_type} amount={self.amount_aed}>"
