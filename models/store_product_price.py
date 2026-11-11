"""Store product prices — per-currency pricing for the online storefront.

A product can carry multiple store prices (one per currency). The storefront
displays the price in the customer's chosen currency; the order is then
converted to the tenant base currency for accounting via ExchangeRateRecord.
"""

from __future__ import annotations

from datetime import UTC, datetime

from extensions import db


class StoreProductPrice(db.Model):
    """Price of a product in the online store for a given currency.

    tenant_id + product_id + currency_code is unique. At most one price per
    currency per product is active at any time; is_default marks the price
    used when the storefront has no explicit currency preference.
    """

    __tablename__ = "store_product_prices"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "product_id", "currency_code", name="uq_store_price_tenant_product_currency"),
        db.Index("ix_store_price_tenant_currency", "tenant_id", "currency_code"),
        db.Index("ix_store_price_tenant_active", "tenant_id", "is_active"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    currency_code = db.Column(db.String(3), nullable=False, index=True)  # USD, AED, ILS, ...
    price = db.Column(db.Numeric(15, 3), nullable=False)  # price in currency_code
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_default = db.Column(db.Boolean, default=False, nullable=False, index=True)
    source = db.Column(db.String(30), default="manual")  # manual, import, api
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    product = db.relationship("Product", foreign_keys=[product_id])
    creator = db.relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<StoreProductPrice product={self.product_id} ccy={self.currency_code} price={self.price}>"

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "currency_code": self.currency_code,
            "price": str(self.price),
            "is_active": self.is_active,
            "is_default": self.is_default,
            "source": self.source,
        }
