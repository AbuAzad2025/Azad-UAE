"""
نموذج تاريخ تكاليف المنتج - Product Cost History
Phase 3: MWAC Audit Trail
"""

from datetime import datetime, timezone
from extensions import db


class ProductCostHistory(db.Model):
    """
    سجل تاريخي لكل حركة تكلفة (MWAC recalculation).
    Immutable audit trail for WAC changes.
    """
    __tablename__ = 'product_cost_history'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)

    # Movement details
    movement_type = db.Column(db.String(30), nullable=False)  # purchase, sale, adjustment, return
    movement_id = db.Column(db.Integer, nullable=True)
    reference_type = db.Column(db.String(50), nullable=True)
    reference_id = db.Column(db.Integer, nullable=True)

    # Cost snapshot before/after
    old_average_cost = db.Column(db.Numeric(18, 6), nullable=True)
    new_average_cost = db.Column(db.Numeric(18, 6), nullable=False)
    quantity_change = db.Column(db.Numeric(18, 3), nullable=False)
    old_total_quantity = db.Column(db.Numeric(18, 3), nullable=True)
    new_total_quantity = db.Column(db.Numeric(18, 3), nullable=False)
    old_total_value = db.Column(db.Numeric(18, 3), nullable=True)
    new_total_value = db.Column(db.Numeric(18, 3), nullable=False)

    # Unit cost of this movement (for purchases)
    movement_unit_cost = db.Column(db.Numeric(18, 6), nullable=True)

    currency = db.Column(db.String(3), default='AED', nullable=False)  # TODO: use Config.DEFAULT_CURRENCY

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    product = db.relationship('Product', backref='cost_history')
    warehouse = db.relationship('Warehouse', backref='cost_history')
    tenant = db.relationship('Tenant', backref='product_cost_history', foreign_keys=[tenant_id])

    def __repr__(self):
        return f'<CostHistory p={self.product_id} {self.movement_type} old={self.old_average_cost} new={self.new_average_cost}>'
