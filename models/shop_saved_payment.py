from extensions import db
from datetime import datetime, timezone


class ShopSavedPayment(db.Model):
    __tablename__ = "shop_saved_payments"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id = db.Column(
        db.Integer,
        db.ForeignKey("shop_customer_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method_code = db.Column(db.String(50), nullable=False)
    label = db.Column(db.String(100), nullable=True)
    details = db.Column(db.Text, nullable=True)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc),
    )

    account = db.relationship("ShopCustomerAccount", backref=db.backref("saved_payments", lazy="dynamic"))
