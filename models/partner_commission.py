from datetime import datetime, timezone
from extensions import db


class PartnerCommissionEntry(db.Model):
    __tablename__ = 'partner_commission_entries'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)

    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)
    sale_line_id = db.Column(db.Integer, db.ForeignKey('sale_lines.id'), nullable=True)

    partner_customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)

    percentage = db.Column(db.Numeric(5, 2), nullable=False)
    base_amount_aed = db.Column(db.Numeric(15, 3), nullable=False)
    commission_amount_aed = db.Column(db.Numeric(15, 3), nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])
    sale = db.relationship('Sale', foreign_keys=[sale_id])
    sale_line = db.relationship('SaleLine', foreign_keys=[sale_line_id])
    partner_customer = db.relationship('Customer', foreign_keys=[partner_customer_id])
    product = db.relationship('Product', foreign_keys=[product_id])

