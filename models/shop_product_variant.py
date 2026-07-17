from extensions import db
from datetime import datetime, timezone


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
    price_adjustment = db.Column(db.Numeric(15, 3), default=0, nullable=False)
    stock_quantity = db.Column(db.Numeric(15, 3), default=0, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc),
    )

    def get_display_name(self, lang="ar"):
        if lang == "ar" and self.name_ar:
            return self.name_ar
        return self.name
