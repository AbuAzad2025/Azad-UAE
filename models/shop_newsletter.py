from extensions import db
from datetime import datetime, timezone


class ShopNewsletter(db.Model):
    __tablename__ = "shop_newsletters"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc),
    )
    __table_args__ = (db.UniqueConstraint("tenant_id", "email", name="uq_newsletter_tenant_email"),)
