"""Provisional store orders — WhatsApp checkout flow.

A customer builds a cart and clicks "Checkout". Instead of paying online,
the system creates a provisional order and redirects the customer to the
tenant's WhatsApp with a message containing product details, prices, and
a provisional invoice number.

The tenant reviews the WhatsApp message, approves the order from the
store admin panel, and the provisional order is converted into a real
Sale (source="online_store") with stock deduction and GL posting.
Payment is collected later (Cash on Delivery / bank transfer).
"""

from __future__ import annotations

from datetime import UTC, datetime

from extensions import db


class StoreProvisionalOrder(db.Model):
    """A customer's cart converted into a provisional order awaiting tenant approval."""

    __tablename__ = "store_provisional_orders"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "provisional_number", name="uq_provisional_tenant_number"),
        db.Index("ix_provisional_tenant_status", "tenant_id", "status"),
        db.Index("ix_provisional_tenant_created", "tenant_id", "created_at"),
    )

    STATUS_PENDING = "pending"  # Customer sent WhatsApp, tenant hasn't approved
    STATUS_APPROVED = "approved"  # Tenant approved, ready to convert to Sale
    STATUS_CONVERTED = "converted"  # Converted to a real Sale
    STATUS_CANCELLED = "cancelled"  # Cancelled by tenant or customer

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provisional_number = db.Column(db.String(50), nullable=False, index=True)
    customer_name = db.Column(db.String(200), nullable=True)
    customer_phone = db.Column(db.String(50), nullable=True, index=True)
    customer_email = db.Column(db.String(120), nullable=True)
    # Cart snapshot as JSON: [{"product_id": 1, "quantity": 2, "unit_price": "10.000", "line_total": "20.000"}, ...]
    cart_json = db.Column(db.JSON, nullable=False)
    currency_code = db.Column(db.String(3), nullable=False, default="USD")
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)  # currency -> base currency
    subtotal_tx_ccy = db.Column(db.Numeric(15, 3), nullable=False)  # subtotal in transaction currency
    subtotal_aed = db.Column(db.Numeric(15, 3), nullable=False)  # subtotal in base currency
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING, index=True)
    whatsapp_message = db.Column(db.Text, nullable=True)  # Generated WhatsApp message
    whatsapp_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    approved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    converted_sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"), nullable=True, index=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    approver = db.relationship("User", foreign_keys=[approved_by])
    converted_sale = db.relationship("Sale", foreign_keys=[converted_sale_id])

    def __repr__(self):
        return f"<StoreProvisionalOrder {self.provisional_number} status={self.status}>"

    def to_dict(self):
        return {
            "id": self.id,
            "provisional_number": self.provisional_number,
            "tenant_id": self.tenant_id,
            "customer_name": self.customer_name,
            "customer_phone": self.customer_phone,
            "customer_email": self.customer_email,
            "cart_json": self.cart_json,
            "currency_code": self.currency_code,
            "exchange_rate": str(self.exchange_rate),
            "subtotal_tx_ccy": str(self.subtotal_tx_ccy),
            "subtotal_aed": str(self.subtotal_aed),
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "converted_sale_id": self.converted_sale_id,
        }
