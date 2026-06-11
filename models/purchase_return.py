from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from extensions import db
from utils.currency_utils import context_aware_default_currency


class PurchaseReturn(db.Model):
    __tablename__ = 'purchase_returns'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'return_number', name='uq_purchase_returns_tenant_return_number'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    return_number = db.Column(db.String(50), nullable=False, index=True)

    purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id'), nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)

    return_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    subtotal = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(15, 3), default=0)
    total_amount = db.Column(db.Numeric(15, 3), nullable=False, default=0)

    currency = db.Column(db.String(3), default=context_aware_default_currency, nullable=False)
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False, default=0)

    @property
    def base_amount(self):
        return self.amount_aed

    @base_amount.setter
    def base_amount(self, value):
        self.amount_aed = value

    reason = db.Column(db.String(500))
    notes = db.Column(db.Text)

    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    purchase = db.relationship('Purchase', backref='returns')
    supplier = db.relationship('Supplier', backref='purchase_returns')
    warehouse = db.relationship('Warehouse', foreign_keys=[warehouse_id])
    branch = db.relationship('Branch', backref='purchase_returns', foreign_keys=[branch_id])
    user = db.relationship('User', foreign_keys=[processed_by])
    lines = db.relationship('PurchaseReturnLine', back_populates='purchase_return', lazy='joined', cascade='all, delete-orphan')

    def calculate_totals(self):
        self.subtotal = sum((Decimal(str(line.line_total)) for line in self.lines), Decimal('0'))
        self.total_amount = self.subtotal
        exchange_rate_decimal = Decimal(str(self.exchange_rate)) if self.exchange_rate else Decimal('1')
        self.amount_aed = (self.total_amount * exchange_rate_decimal).quantize(
            Decimal('0.001'), rounding=ROUND_HALF_UP
        )


class PurchaseReturnLine(db.Model):
    __tablename__ = 'purchase_return_lines'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    return_id = db.Column(db.Integer, db.ForeignKey('purchase_returns.id'), nullable=False, index=True)
    purchase_line_id = db.Column(db.Integer, db.ForeignKey('purchase_lines.id'), index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)

    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    unit_cost = db.Column(db.Numeric(15, 3), nullable=False)
    line_total = db.Column(db.Numeric(15, 3), nullable=False)

    reason = db.Column(db.String(255))
    notes = db.Column(db.String(255))

    purchase_return = db.relationship('PurchaseReturn', back_populates='lines')
    purchase_line = db.relationship('PurchaseLine')
    product = db.relationship('Product')
