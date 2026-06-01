from datetime import datetime, timezone
from extensions import db


class Warehouse(db.Model):
    __tablename__ = 'warehouses'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'name', name='uq_warehouses_tenant_name'),
        db.UniqueConstraint('tenant_id', 'code', name='uq_warehouses_tenant_code'),
    )

    TYPE_PHYSICAL = 'physical'
    TYPE_ONLINE = 'online'
    WAREHOUSE_TYPES = (TYPE_PHYSICAL, TYPE_ONLINE)
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    code = db.Column(db.String(50))
    location = db.Column(db.String(255))
    warehouse_type = db.Column(db.String(20), default=TYPE_PHYSICAL, nullable=False, index=True)
    
    parent_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'))
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True) # Linked Branch
    
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    is_active = db.Column(db.Boolean, default=True)
    is_main = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    parent = db.relationship('Warehouse', remote_side=[id], backref='sub_warehouses')
    manager = db.relationship('User', foreign_keys=[manager_id])
    branch = db.relationship('Branch', backref='warehouses', foreign_keys=[branch_id])
    tenant = db.relationship('Tenant', backref='warehouses', foreign_keys=[tenant_id])
    stock_movements = db.relationship('StockMovement', back_populates='warehouse', lazy='dynamic')
    
    def __repr__(self):
        return f'<Warehouse {self.name}>'

    @property
    def is_online(self):
        return (self.warehouse_type or self.TYPE_PHYSICAL) == self.TYPE_ONLINE

    def type_label_ar(self):
        return 'أونلاين' if self.is_online else 'فعلي'


class StockMovement(db.Model):
    __tablename__ = 'stock_movements'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)

    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    
    movement_type = db.Column(db.String(20), nullable=False, index=True)
    
    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    
    reference_type = db.Column(db.String(50))
    reference_id = db.Column(db.Integer)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    product = db.relationship('Product', back_populates='stock_movements')
    warehouse = db.relationship('Warehouse', back_populates='stock_movements')
    user = db.relationship('User', foreign_keys=[user_id])
    tenant = db.relationship('Tenant', backref='stock_movements', foreign_keys=[tenant_id])
    
    def __repr__(self):
        return f'<StockMovement {self.movement_type} {self.quantity}>'
    
    def get_type_display(self, lang='ar'):
        types = {
            'purchase': {'ar': 'شراء', 'en': 'Purchase'},
            'sale': {'ar': 'بيع', 'en': 'Sale'},
            'adjustment': {'ar': 'تسوية', 'en': 'Adjustment'},
            'return': {'ar': 'إرجاع', 'en': 'Return'},
            'damage': {'ar': 'تالف', 'en': 'Damage'},
            'transfer': {'ar': 'تحويل', 'en': 'Transfer'},
        }
        return types.get(self.movement_type, {}).get(lang, self.movement_type)
    
    def to_dict(self):
        return {
            'id': self.id,
            'product': self.product.name if self.product else None,
            'movement_type': self.movement_type,
            'quantity': float(self.quantity),
            'reference': f'{self.reference_type} #{self.reference_id}' if self.reference_type else None,
            'created_at': self.created_at.isoformat(),
        }

