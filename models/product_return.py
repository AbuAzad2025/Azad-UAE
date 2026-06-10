from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from extensions import db


class ProductReturn(db.Model):
    __tablename__ = 'product_returns'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'return_number', name='uq_product_returns_tenant_return_number'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    return_number = db.Column(db.String(50), nullable=False, index=True)
    
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    
    return_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    total_amount = db.Column(db.Numeric(15, 3), nullable=False)
    refund_amount = db.Column(db.Numeric(15, 3), default=0)
    
    currency = db.Column(db.String(3), default='AED', nullable=False)  # TODO: use Config.DEFAULT_CURRENCY
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False)
    
    # Alias for unified currency handling
    @property
    def base_amount(self):
        return self.amount_aed
    
    @base_amount.setter
    def base_amount(self, value):
        self.amount_aed = value
    
    return_reason = db.Column(db.String(255))
    status = db.Column(db.String(20), default='pending', index=True)
    
    notes = db.Column(db.Text)
    
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    sale = db.relationship('Sale', backref='returns')
    customer = db.relationship('Customer', backref='returns')
    branch = db.relationship('Branch', backref='returns', foreign_keys=[branch_id])
    user = db.relationship('User', foreign_keys=[processed_by])
    lines = db.relationship('ProductReturnLine', back_populates='product_return', lazy='joined', cascade='all, delete-orphan')
    tenant = db.relationship('Tenant', backref='product_returns', foreign_keys=[tenant_id])
    
    def __repr__(self):
        return f'<ProductReturn {self.return_number}>'
    
    def calculate_totals(self):
        """Calculate return totals with proper decimal precision."""
        self.total_amount = sum((Decimal(str(line.line_total)) for line in self.lines), Decimal('0'))
        exchange_rate_decimal = Decimal(str(self.exchange_rate)) if self.exchange_rate else Decimal('1')
        refund = Decimal(str(self.refund_amount or self.total_amount or 0))
        self.amount_aed = (refund * exchange_rate_decimal).quantize(
            Decimal('0.001'), rounding=ROUND_HALF_UP
        )


class ProductReturnLine(db.Model):
    __tablename__ = 'product_return_lines'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    return_id = db.Column(db.Integer, db.ForeignKey('product_returns.id'), nullable=False, index=True)
    sale_line_id = db.Column(db.Integer, db.ForeignKey('sale_lines.id'), index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    
    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    unit_price = db.Column(db.Numeric(15, 3), nullable=False)
    line_total = db.Column(db.Numeric(15, 3), nullable=False)
    
    condition = db.Column(db.String(50))
    notes = db.Column(db.String(255))
    
    product_return = db.relationship('ProductReturn', back_populates='lines')
    sale_line = db.relationship('SaleLine')
    product = db.relationship('Product')
    tenant = db.relationship('Tenant', backref='product_return_lines', foreign_keys=[tenant_id])
    
    def __repr__(self):
        return f'<ProductReturnLine {self.product_id} x {self.quantity}>'
