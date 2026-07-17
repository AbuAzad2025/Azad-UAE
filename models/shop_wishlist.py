from extensions import db
from datetime import datetime, timezone


class ShopWishlist(db.Model):
    __tablename__ = "shop_wishlist"
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id = db.Column(
        db.Integer,
        db.ForeignKey("shop_customer_accounts.id"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=False, index=True
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc),
    )
    __table_args__ = (
        db.UniqueConstraint(
            "account_id", "product_id", name="uq_wishlist_account_product"
        ),
    )
    account = db.relationship(
        "ShopCustomerAccount", backref=db.backref("wishlist_items", lazy="dynamic")
    )
