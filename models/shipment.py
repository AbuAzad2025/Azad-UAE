from datetime import UTC, datetime

from sqlalchemy.orm import validates

from extensions import db


class Shipment(db.Model):
    """
    Tracks physical shipment/delivery of a sale order.

    ARCHITECTURE NOTE: POLYMORPHIC SOURCE PATTERN
    ===============================================
    Shipment uses source_type + source_id as a polymorphic reference.
    The source_id is NOT NULL but has no FK constraint — it is a
    logical reference only.

    Supported source_type values and their semantic meaning:
      "sale" → source_id = sale.id  (most common)

    Unlike Receipt, Shipment currently has no FK enforcement on source_id.
    Adding proper nullable FKs per source type is recommended for future
    releases to provide referential integrity.
    """

    __tablename__ = "shipments"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    VALID_SOURCE_TYPES = frozenset({"sale", "purchase_return"})
    source_type = db.Column(db.String(20), nullable=False)
    source_id = db.Column(db.Integer, nullable=False, index=True)  # LEGACY polymorphic — retained
    # Explicit FKs (F-02 remediation)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"), index=True, nullable=True)
    purchase_return_id = db.Column(
        db.Integer, db.ForeignKey("purchase_returns.id", ondelete="SET NULL"), index=True, nullable=True
    )
    carrier_name = db.Column(db.String(100))
    tracking_number = db.Column(db.String(100))
    tracking_url = db.Column(db.String(500))
    shipping_cost = db.Column(db.Numeric(15, 3), default=0)
    customs_duty = db.Column(db.Numeric(15, 3), default=0)
    insurance = db.Column(db.Numeric(15, 3), default=0)
    status = db.Column(db.String(20), default="pending", index=True)
    estimated_delivery = db.Column(db.DateTime(timezone=True))
    actual_delivery = db.Column(db.DateTime(timezone=True))
    recipient_name = db.Column(db.String(200))
    recipient_phone = db.Column(db.String(50))
    recipient_address = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (db.Index("ix_shipment_source", "tenant_id", "source_type", "source_id"),)

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    sale = db.relationship("Sale", foreign_keys=[sale_id])
    purchase_return = db.relationship("PurchaseReturn", foreign_keys=[purchase_return_id])

    _EXPLICIT_FKS = ("sale_id", "purchase_return_id")

    @validates("sale_id", "purchase_return_id")
    def _validate_exactly_one_explicit(self, key, value):
        """F-02: exactly one explicit FK must be set, matching source_type."""
        if value is not None:
            others = [f for f in self._EXPLICIT_FKS if f != key and getattr(self, f, None) is not None]
            if others:
                raise ValueError(f"Shipment can reference exactly one explicit FK, {key} vs {others}")
            expected = {"sale_id": "sale", "purchase_return_id": "purchase_return"}[key]
            if self.source_type and self.source_type != expected:
                raise ValueError(f"Shipment.{key} requires source_type={expected!r}, got {self.source_type!r}")
            if self.source_id is not None and self.source_id != value:
                raise ValueError(f"Shipment.{key} ({value}) must match source_id ({self.source_id})")
        return value

    @validates("source_type")
    def _validate_source_type(self, key, value):
        if value not in self.VALID_SOURCE_TYPES:
            raise ValueError(f"Invalid source_type {value!r}")
        return value

    def __repr__(self):
        return f"<Shipment {self.source_type}#{self.source_id} {self.status}>"
