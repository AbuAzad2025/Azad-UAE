from datetime import UTC, datetime

from extensions import db


class ShopReview(db.Model):
    __tablename__ = "shop_reviews"

    __table_args__ = (
        db.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_shop_review_rating_1_5"),
        db.Index("ix_shop_reviews_tenant_product_approved", "tenant_id", "product_id", "is_approved"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    account_id = db.Column(
        db.Integer,
        db.ForeignKey("shop_customer_accounts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    customer_name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    is_approved = db.Column(db.Boolean, default=False, nullable=False, server_default="false", index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(UTC),
    )
    product = db.relationship("Product", backref=db.backref("shop_reviews", lazy="dynamic"))
