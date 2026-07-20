from datetime import datetime, timezone
from extensions import db


class WarrantyClaim(db.Model):
    __tablename__ = "warranty_claims"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sale_line_id = db.Column(
        db.Integer,
        db.ForeignKey("sale_lines.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    claim_type = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="open", index=True)
    resolved_at = db.Column(db.DateTime)
    resolution_notes = db.Column(db.Text)
    cost_to_company = db.Column(db.Numeric(15, 3), default=0)
    warranty_start_date = db.Column(db.DateTime)
    warranty_end_date = db.Column(db.DateTime)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    sale = db.relationship("Sale", foreign_keys=[sale_id])
    sale_line = db.relationship("SaleLine", foreign_keys=[sale_line_id])
    product = db.relationship("Product", foreign_keys=[product_id])

    @property
    def remaining_days(self):
        if self.warranty_end_date:
            from datetime import datetime, timezone

            delta = self.warranty_end_date - datetime.now(timezone.utc)
            return max(0, delta.days)
        return 0

    def __repr__(self):
        return f"<WarrantyClaim S#{self.sale_id} {self.claim_type} {self.status}>"
