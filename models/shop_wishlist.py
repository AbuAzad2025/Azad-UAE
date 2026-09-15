from datetime import UTC, datetime

from extensions import db


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
        db.ForeignKey("shop_customer_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(UTC),
    )
    __table_args__ = (
        db.UniqueConstraint("account_id", "product_id", name="uq_wishlist_account_product"),
        db.Index("ix_wishlist_tenant_account", "tenant_id", "account_id"),
        db.Index("ix_wishlist_tenant_product", "tenant_id", "product_id"),
    )
    account = db.relationship("ShopCustomerAccount", backref=db.backref("wishlist_items", lazy="dynamic"))
