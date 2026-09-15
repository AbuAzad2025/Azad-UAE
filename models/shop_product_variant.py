from datetime import UTC, datetime
from decimal import Decimal

from extensions import db


class ShopProductVariant(db.Model):
    __tablename__ = "shop_product_variants"

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
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100), nullable=True)
    sku = db.Column(db.String(100), nullable=True)
    price_adjustment = db.Column(db.Numeric(15, 3), default=Decimal("0.000"), nullable=False)
    stock_quantity = db.Column(db.Numeric(15, 3), default=Decimal("0.000"), nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(UTC),
    )

    def get_display_name(self, lang="ar"):
        if lang == "ar" and self.name_ar:
            return self.name_ar
        return self.name

    __table_args__ = (
        db.Index("ix_variant_tenant_sku", "tenant_id", "sku"),
        db.Index("ix_variant_product_sort", "product_id", "sort_order"),
    )
