from datetime import UTC, datetime

from extensions import db


class WarehouseTransfer(db.Model):
    __tablename__ = "warehouse_transfers"
    __table_args__ = (db.UniqueConstraint("tenant_id", "transfer_number", name="uq_warehouse_transfers_number"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transfer_number = db.Column(db.String(50), nullable=False, index=True)

    from_warehouse_id = db.Column(
        db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    to_warehouse_id = db.Column(
        db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True)

    status = db.Column(db.String(20), default="draft", nullable=False, index=True)
    transfer_date = db.Column(
        db.Date,
        default=lambda: datetime.now(UTC).date(),
        nullable=False,
        index=True,
    )
    completed_date = db.Column(db.Date, nullable=True)

    requested_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    received_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)

    notes = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    from_warehouse = db.relationship("Warehouse", foreign_keys=[from_warehouse_id])
    to_warehouse = db.relationship("Warehouse", foreign_keys=[to_warehouse_id])
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    requester = db.relationship("User", foreign_keys=[requested_by])
    approver = db.relationship("User", foreign_keys=[approved_by])
    receiver = db.relationship("User", foreign_keys=[received_by])
    lines = db.relationship(
        "WarehouseTransferLine", back_populates="transfer", lazy="joined", cascade="all, delete-orphan"
    )
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id], backref="warehouse_transfers")

    def __repr__(self):
        return f"<WarehouseTransfer {self.transfer_number}>"

    @property
    def status_ar(self):
        labels = {
            "draft": "مسودة",
            "approved": "موافق عليه",
            "in_transit": "قيد النقل",
            "completed": "مكتمل",
            "cancelled": "ملغي",
        }
        return labels.get(self.status, self.status)


class WarehouseTransferLine(db.Model):
    __tablename__ = "warehouse_transfer_lines"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transfer_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouse_transfers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    requested_quantity = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    received_quantity = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    notes = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

    transfer = db.relationship("WarehouseTransfer", back_populates="lines")
    product = db.relationship("Product", foreign_keys=[product_id])

    def __repr__(self):
        return f"<WarehouseTransferLine product={self.product_id} qty={self.requested_quantity}>"
