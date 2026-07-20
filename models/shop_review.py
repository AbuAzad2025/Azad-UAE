from extensions import db
from datetime import datetime, timezone


class ShopReview(db.Model):
    __tablename__ = "shop_reviews"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    account_id = db.Column(
        db.Integer,
        db.ForeignKey("shop_customer_accounts.id"),
        nullable=True,
        index=True,
    )
    customer_name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    is_approved = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc),
    )
    product = db.relationship("Product", backref=db.backref("shop_reviews", lazy="dynamic"))
