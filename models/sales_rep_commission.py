from datetime import datetime, timezone
from extensions import db
from utils.currency_utils import context_aware_default_currency


class SalesRepCommission(db.Model):
    __tablename__ = "sales_rep_commissions"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sale_id = db.Column(
        db.Integer, db.ForeignKey("sales.id"), nullable=False, index=True
    )
    sale_line_id = db.Column(
        db.Integer, db.ForeignKey("sale_lines.id"), nullable=True, index=True
    )
    sales_rep_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=True, index=True
    )
    commission_rate = db.Column(db.Numeric(5, 2), nullable=False)
    commission_amount = db.Column(db.Numeric(15, 3), nullable=False)
    currency = db.Column(db.String(3), default=context_aware_default_currency)
    is_paid = db.Column(db.Boolean, default=False, index=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    sale = db.relationship("Sale", foreign_keys=[sale_id])
    sale_line = db.relationship("SaleLine", foreign_keys=[sale_line_id])
    sales_rep = db.relationship("User", foreign_keys=[sales_rep_id])
    product = db.relationship("Product", foreign_keys=[product_id])

    def __repr__(self):
        return f"<SalesRepCommission S#{self.sale_id} rep={self.sales_rep_id} amt={self.commission_amount}>"
