"""Registered storefront customer — scoped per tenant, linked to CRM Customer."""

from datetime import UTC, datetime

from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class ShopCustomerAccount(db.Model):
    __tablename__ = "shop_customer_accounts"
    __table_args__ = (db.UniqueConstraint("tenant_id", "email", name="uq_shop_customer_tenant_email"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    phone = db.Column(db.String(30))
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.Text)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    last_login_at = db.Column(db.DateTime(timezone=True))
    password_reset_token = db.Column(db.String(128), index=True)
    password_reset_expires_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    tenant = db.relationship("Tenant", backref=db.backref("shop_customers", lazy="dynamic"))
    customer = db.relationship("Customer", foreign_keys=[customer_id])

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)
