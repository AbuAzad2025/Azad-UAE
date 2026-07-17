from datetime import datetime, timezone
from extensions import db


class ProductSerial(db.Model):
    __tablename__ = "product_serials"
    __table_args__ = (
        db.UniqueConstraint(
            "tenant_id", "serial_number", name="uq_serial_tenant_serial"
        ),
        db.Index(
            "ix_serial_tenant_imei1",
            "tenant_id",
            "imei1",
            sqlite_where=db.text("imei1 IS NOT NULL AND imei1 != ''"),
            postgresql_where=db.text("imei1 IS NOT NULL AND imei1 != ''"),
        ),
        db.Index(
            "ix_serial_tenant_imei2",
            "tenant_id",
            "imei2",
            sqlite_where=db.text("imei2 IS NOT NULL AND imei2 != ''"),
            postgresql_where=db.text("imei2 IS NOT NULL AND imei2 != ''"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=False, index=True
    )
    warehouse_id = db.Column(
        db.Integer, db.ForeignKey("warehouses.id"), nullable=True, index=True
    )

    serial_number = db.Column(db.String(100), nullable=False, index=True)
    imei1 = db.Column(db.String(15), nullable=True, index=True)
    imei2 = db.Column(db.String(15), nullable=True, index=True)
    model_number = db.Column(db.String(50), nullable=True)
    iccid = db.Column(db.String(20), nullable=True)

    # Lifecycle Status
    status = db.Column(db.String(20), default="available", index=True)
    # available: In stock, ready to sell
    # sold: Sold to customer
    # returned: Returned by customer (faulty/good)
    # defective: Marked as bad/damaged
    # lost: Lost/Stolen

    purchase_line_id = db.Column(
        db.Integer, db.ForeignKey("purchase_lines.id"), nullable=True, index=True
    )  # Where did we get it?
    sale_line_id = db.Column(
        db.Integer, db.ForeignKey("sale_lines.id"), nullable=True, index=True
    )  # Who did we sell it to?

    # Warranty Info (Calculated from Sale Date)
    warranty_start_date = db.Column(db.DateTime, nullable=True)
    warranty_end_date = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = db.relationship(
        "Tenant", backref="product_serials", foreign_keys=[tenant_id]
    )
    product = db.relationship("Product", backref="serials")
    purchase_line = db.relationship("PurchaseLine", backref="serials")
    sale_line = db.relationship("SaleLine", backref="serials")
    warehouse = db.relationship("Warehouse", foreign_keys=[warehouse_id])

    def __repr__(self):
        return f"<Serial {self.serial_number} ({self.status})>"
