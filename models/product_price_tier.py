from datetime import datetime, timezone
from extensions import db


class ProductPriceTier(db.Model):
    __tablename__ = 'product_price_tiers'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'product_id', 'tier_code', name='uq_product_price_tier'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)

    tier_code = db.Column(db.String(30), nullable=False, index=True)
    # 'wholesale', 'retail', 'distributor', 'rep'

    min_quantity = db.Column(db.Numeric(15, 3), default=0)
    price = db.Column(db.Numeric(15, 3), nullable=False)
    currency = db.Column(db.String(3), default='AED')
    is_active = db.Column(db.Boolean, default=True, index=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    product = db.relationship('Product', back_populates='price_tiers')
    tenant = db.relationship('Tenant', backref='product_price_tiers', foreign_keys=[tenant_id])

    def __repr__(self):
        return f'<ProductPriceTier P#{self.product_id} {self.tier_code} = {self.price}>'
