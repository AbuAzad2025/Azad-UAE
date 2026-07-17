from datetime import datetime, timezone

from extensions import db


class AzadPlatformFee(db.Model):
    """Azad's 1% share from tenant online-store transactions."""

    __tablename__ = "azad_platform_fees"
    __table_args__ = (
        db.UniqueConstraint(
            "idempotency_key", name="uq_azad_platform_fees_idempotency_key"
        ),
        db.Index("ix_azad_platform_fees_tenant_sale", "tenant_id", "sale_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    idempotency_key = db.Column(db.String(180), nullable=False)

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sale_id = db.Column(
        db.Integer, db.ForeignKey("sales.id"), nullable=False, index=True
    )
    payment_id = db.Column(
        db.Integer, db.ForeignKey("payments.id"), nullable=True, index=True
    )
    vault_id = db.Column(
        db.Integer, db.ForeignKey("payment_vault.id"), nullable=True, index=True
    )

    rate_percent = db.Column(db.Numeric(5, 2), nullable=False, default=1)
    base_amount_aed = db.Column(db.Numeric(15, 3), nullable=False)
    fee_amount_aed = db.Column(db.Numeric(15, 3), nullable=False)

    transaction_scope = db.Column(db.String(30), nullable=False, default="online_store")
    payment_channel = db.Column(db.String(50), nullable=False, default="online_pay")
    gateway_name = db.Column(db.String(50))
    gateway_reference = db.Column(db.String(120))
    status = db.Column(db.String(20), nullable=False, default="accrued", index=True)
    gl_posted = db.Column(db.Boolean, nullable=False, default=False)

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
    sale = db.relationship("Sale", foreign_keys=[sale_id])
    payment = db.relationship("Payment", foreign_keys=[payment_id])
    vault = db.relationship("PaymentVault", foreign_keys=[vault_id])

    def __repr__(self):
        return f"<AzadPlatformFee sale={self.sale_id} amount={self.fee_amount_aed}>"
