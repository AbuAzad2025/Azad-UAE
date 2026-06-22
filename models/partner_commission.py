from datetime import datetime, timezone
from extensions import db
from utils.currency_utils import context_aware_default_currency


class PartnerCommissionEntry(db.Model):
    __tablename__ = 'partner_commission_entries'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True, index=True)

    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)
    sale_line_id = db.Column(db.Integer, db.ForeignKey('sale_lines.id'), nullable=True, index=True)

    partner_customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True, index=True)

    percentage = db.Column(db.Numeric(5, 2), nullable=False)
    currency = db.Column(db.String(3), default=context_aware_default_currency)
    base_currency = db.Column(db.String(3), default=context_aware_default_currency)

    # Financial basis for commission (Dynamic Profit Margin)
    cost_basis = db.Column(db.Numeric(15, 3), default=0)          # MWAC unit cost * qty
    profit_margin = db.Column(db.Numeric(15, 3), default=0)       # Net profit = revenue - cost - vat
    base_amount_aed = db.Column(db.Numeric(15, 3), nullable=False)  # profit margin in base currency
    commission_amount_aed = db.Column(db.Numeric(15, 3), nullable=False)
    
    @property
    def commission_amount(self):
        return self.commission_amount_aed
    
    @commission_amount.setter
    def commission_amount(self, value):
        self.commission_amount_aed = value
    
    # Aliases for unified currency handling
    @property
    def base_amount(self):
        return self.base_amount_aed
    
    @base_amount.setter
    def base_amount(self, value):
        self.base_amount_aed = value
    
    @property
    def commission_amount_base(self):
        return self.commission_amount_aed
    
    @commission_amount_base.setter
    def commission_amount_base(self, value):
        self.commission_amount_aed = value

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])
    warehouse = db.relationship('Warehouse', foreign_keys=[warehouse_id])
    sale = db.relationship('Sale', foreign_keys=[sale_id])
    sale_line = db.relationship('SaleLine', foreign_keys=[sale_line_id])
    partner_customer = db.relationship('Customer', foreign_keys=[partner_customer_id])
    product = db.relationship('Product', foreign_keys=[product_id])

