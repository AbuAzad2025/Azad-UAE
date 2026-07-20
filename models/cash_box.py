"""
نموذج الصناديق والبنوك - Cash Box / Treasury
Phase 8: Treasury & Cash Position
"""

from datetime import datetime, timezone
from extensions import db
from utils.currency_utils import context_aware_default_currency


class CashBox(db.Model):
    """
    صناديق النقدية والبنوك والبوابات الإلكترونية.
    Unified liquidity container for treasury reporting.
    """

    __tablename__ = "cash_boxes"
    __table_args__ = (db.UniqueConstraint("tenant_id", "code", name="uq_cash_boxes_tenant_code"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True, index=True)

    code = db.Column(db.String(20), nullable=False, index=True)
    name_ar = db.Column(db.String(200), nullable=False)
    name_en = db.Column(db.String(200), nullable=True)

    box_type = db.Column(db.String(30), default="cash", nullable=False)
    # cash, bank_account, payment_gateway, cheque_under_collection, digital_wallet

    currency = db.Column(
        db.String(3), default=context_aware_default_currency, nullable=False
    )  # TODO: use Config.DEFAULT_CURRENCY

    # Balance tracking (denormalized for fast reads)
    current_balance = db.Column(db.Numeric(18, 3), default=0, nullable=False)

    # Bank-specific fields (nullable for cash boxes)
    bank_name = db.Column(db.String(200), nullable=True)
    account_number = db.Column(db.String(100), nullable=True)
    iban = db.Column(db.String(50), nullable=True)
    swift_code = db.Column(db.String(20), nullable=True)

    # Payment gateway fields
    gateway_provider = db.Column(db.String(50), nullable=True)  # stripe, nowpayments, etc.
    gateway_merchant_id = db.Column(db.String(100), nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_default = db.Column(db.Boolean, default=False, nullable=False)

    # GL linkage
    gl_account_id = db.Column(db.Integer, db.ForeignKey("gl_accounts.id"), nullable=True, index=True)

    # Audit
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

    tenant = db.relationship("Tenant", backref="cash_boxes", foreign_keys=[tenant_id])
    branch = db.relationship("Branch", backref="cash_boxes", foreign_keys=[branch_id])
    gl_account = db.relationship("GLAccount", foreign_keys=[gl_account_id])

    def __repr__(self):
        return f"<CashBox {self.code} ({self.box_type}) balance={self.current_balance}>"

    @property
    def full_name(self):
        return f"{self.code} - {self.name_ar or self.name_en}"
