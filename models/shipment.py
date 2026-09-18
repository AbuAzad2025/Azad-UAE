from datetime import UTC, datetime
from decimal import Decimal

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
    VALID_SOURCE_TYPES = frozenset({"sale", "purchase_return", "field_sale", "delivery"})
    VALID_STATUSES = frozenset(
        {"pending", "draft", "in_transit", "arrived", "selling", "closed", "cancelled", "delivered"}
    )
    source_type = db.Column(db.String(20), nullable=False)
    source_id = db.Column(db.Integer, nullable=False, index=True)  # LEGACY polymorphic — retained
    # Explicit FKs (F-02 remediation)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"), index=True, nullable=True)
    purchase_return_id = db.Column(
        db.Integer, db.ForeignKey("purchase_returns.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Field-sales expedition (pre-invoice) — nullable to keep legacy rows valid
    shipment_number = db.Column(db.String(50), unique=True, index=True, nullable=True)
    from_warehouse_id = db.Column(
        db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    destination_warehouse_id = db.Column(
        db.Integer, db.ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    destination_name = db.Column(db.String(200), nullable=True)
    destination_type = db.Column(db.String(20), nullable=False, default="site")
    total_value = db.Column(db.Numeric(15, 3), nullable=False, default=Decimal("0.000"))
    total_quantity = db.Column(db.Numeric(15, 3), nullable=False, default=Decimal("0.000"))
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    shipped_at = db.Column(db.DateTime(timezone=True), nullable=True)
    arrived_at = db.Column(db.DateTime(timezone=True), nullable=True)
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    notes = db.Column(db.Text, nullable=True)
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

    __table_args__ = (
        db.Index("ix_shipment_source", "tenant_id", "source_type", "source_id"),
        db.Index("ix_shipments_tenant_status", "tenant_id", "status"),
        db.Index("ix_shipments_warehouse", "from_warehouse_id"),
        db.Index("ix_shipments_destination", "destination_warehouse_id"),
        db.CheckConstraint(
            "status IN ('pending','draft','in_transit','arrived','selling','closed','cancelled','delivered')",
            name="ck_shipments_status_valid_new",
        ),
        db.CheckConstraint("total_value >= 0", name="ck_shipments_total_non_negative_new"),
    )

    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])
    sale = db.relationship("Sale", foreign_keys=[sale_id])
    purchase_return = db.relationship("PurchaseReturn", foreign_keys=[purchase_return_id])
    from_warehouse = db.relationship("Warehouse", foreign_keys=[from_warehouse_id])
    destination_warehouse = db.relationship("Warehouse", foreign_keys=[destination_warehouse_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id])
    lines = db.relationship("ShipmentLine", back_populates="shipment", cascade="all, delete-orphan", lazy="joined")

    _EXPLICIT_FKS = ("sale_id", "purchase_return_id")

    @validates("sale_id", "purchase_return_id")
    def _validate_exactly_one_explicit(self, key, value):
        """F-02: exactly one explicit FK must be set, matching source_type."""
        if value is not None:
            others = [f for f in self._EXPLICIT_FKS if f != key and getattr(self, f, None) is not None]
            if others:
                raise ValueError(f"Shipment can reference exactly one explicit FK, {key} vs {others}")
            expected = {"sale_id": "sale", "purchase_return_id": "purchase_return"}[key]
            if self.source_type and self.source_type not in ("field_sale", "delivery") and self.source_type != expected:
                raise ValueError(f"Shipment.{key} requires source_type={expected!r}, got {self.source_type!r}")
            if (
                self.source_id is not None
                and self.source_id != value
                and self.source_type in ("sale", "purchase_return")
            ):
                raise ValueError(f"Shipment.{key} ({value}) must match source_id ({self.source_id})")
        return value

    @validates("source_type")
    def _validate_source_type(self, key, value):
        if value not in self.VALID_SOURCE_TYPES:
            raise ValueError(f"Invalid source_type {value!r}")
        return value

    @validates("destination_name")
    def _validate_destination(self, key, value):
        if self.source_type in ("field_sale", "delivery") and (not value or not str(value).strip()):
            raise ValueError("destination_name (موقع الإرسالية) مطلوب")
        return str(value).strip() if value else value

    @property
    def status_ar(self):
        return {
            "pending": "قيد الانتظار",
            "draft": "مسودة",
            "in_transit": "في الطريق",
            "arrived": "وصلت",
            "selling": "قيد البيع",
            "closed": "مغلقة",
            "cancelled": "ملغاة",
            "delivered": "تم التسليم",
        }.get(self.status, self.status)

    @property
    def is_editable(self):
        return self.status in ("draft", "pending")

    @property
    def is_closable(self):
        return self.status in ("arrived", "selling")

    def calculate_totals(self):
        qty = sum((Decimal(str(line.quantity)) for line in self.lines), Decimal("0"))
        val = sum((Decimal(str(line.line_total)) for line in self.lines), Decimal("0"))
        self.total_quantity = qty
        self.total_value = val

    def __repr__(self):
        return f"<Shipment {self.shipment_number or self.source_type + '#' + str(self.source_id)} {self.status}>"


class ShipmentLine(db.Model):
    __tablename__ = "shipment_lines"

    __table_args__ = (
        db.Index("ix_shipment_lines_shipment", "shipment_id"),
        db.Index("ix_shipment_lines_product", "product_id"),
        db.CheckConstraint("quantity > 0", name="ck_shipmentline_qty_positive"),
        db.CheckConstraint("unit_cost >= 0", name="ck_shipmentline_cost_non_negative"),
        db.CheckConstraint("line_total >= 0", name="ck_shipmentline_total_non_negative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    quantity_invoiced = db.Column(db.Numeric(15, 3), nullable=False, default=Decimal("0.000"))
    unit_cost = db.Column(db.Numeric(15, 3), nullable=False, default=Decimal("0.000"))
    unit_price = db.Column(db.Numeric(15, 3), nullable=False, default=Decimal("0.000"))
    line_total = db.Column(db.Numeric(15, 3), nullable=False, default=Decimal("0.000"))
    notes = db.Column(db.String(255))

    shipment = db.relationship("Shipment", back_populates="lines")
    product = db.relationship("Product")

    def calculate_line_total(self):
        self.line_total = Decimal(str(self.quantity)) * Decimal(str(self.unit_cost))

    @property
    def quantity_remaining(self):
        return (Decimal(str(self.quantity)) - Decimal(str(self.quantity_invoiced))).quantize(Decimal("0.001"))

    def __repr__(self):
        return f"<ShipmentLine {self.product_id} x {self.quantity}>"
