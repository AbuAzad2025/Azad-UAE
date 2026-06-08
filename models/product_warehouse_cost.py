"""
نموذج تكلفة المخزن الموزعة (MWAC) - Product Warehouse Cost
Phase 3: Moving Weighted Average Cost Data Model
"""

from datetime import datetime, timezone
from extensions import db


class ProductWarehouseCost(db.Model):
    """
    تكلفة المنتج في كل مخزن باستخدام نظام المتوسط المتحرك المرجح (MWAC).
    Every product/warehouse pair maintains its own WAC.
    """
    __tablename__ = 'product_warehouse_costs'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'product_id', 'warehouse_id', name='uq_pwc_tenant_product_warehouse'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)

    # MWAC fields
    average_cost = db.Column(db.Numeric(18, 6), default=0, nullable=False)
    total_quantity = db.Column(db.Numeric(18, 3), default=0, nullable=False)
    total_value = db.Column(db.Numeric(18, 3), default=0, nullable=False)

    # Currency of the stored cost (usually AED or tenant default)
    currency = db.Column(db.String(3), default='AED', nullable=False)  # TODO: use Config.DEFAULT_CURRENCY

    # Lock to prevent concurrent WAC updates
    last_updated = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_by_movement_id = db.Column(db.Integer, db.ForeignKey('stock_movements.id'), nullable=True)

    # Audit
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    product = db.relationship('Product', backref='warehouse_costs')
    warehouse = db.relationship('Warehouse', backref='product_costs')
    tenant = db.relationship('Tenant', backref='product_warehouse_costs', foreign_keys=[tenant_id])

    def __repr__(self):
        return f'<ProductWarehouseCost p={self.product_id} w={self.warehouse_id} cost={self.average_cost}>'

    @property
    def is_empty(self):
        return (self.total_quantity or 0) <= 0
