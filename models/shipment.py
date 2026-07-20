from datetime import datetime, timezone
from extensions import db


class Shipment(db.Model):
    __tablename__ = "shipments"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type = db.Column(db.String(20), nullable=False)
    source_id = db.Column(db.Integer, nullable=False, index=True)
    carrier_name = db.Column(db.String(100))
    tracking_number = db.Column(db.String(100))
    tracking_url = db.Column(db.String(500))
    shipping_cost = db.Column(db.Numeric(15, 3), default=0)
    customs_duty = db.Column(db.Numeric(15, 3), default=0)
    insurance = db.Column(db.Numeric(15, 3), default=0)
    status = db.Column(db.String(20), default="pending", index=True)
    estimated_delivery = db.Column(db.DateTime)
    actual_delivery = db.Column(db.DateTime)
    recipient_name = db.Column(db.String(200))
    recipient_phone = db.Column(db.String(50))
    recipient_address = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (db.Index("ix_shipment_source", "source_type", "source_id"),)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<Shipment {self.source_type}#{self.source_id} {self.status}>"
