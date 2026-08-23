"""Warehouse and ProductWarehouseStock models."""

from datetime import UTC, datetime

from extensions import db


class Warehouse(db.Model):
    __tablename__ = "warehouses"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_warehouses_tenant_name"),
        db.UniqueConstraint("tenant_id", "code", name="uq_warehouses_tenant_code"),
    )

    TYPE_PHYSICAL = "physical"
    TYPE_ONLINE = "online"
    WAREHOUSE_TYPES = (TYPE_PHYSICAL, TYPE_ONLINE)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
    code = db.Column(db.String(50))
    location = db.Column(db.String(255))
    warehouse_type = db.Column(db.String(20), default=TYPE_PHYSICAL, nullable=False, index=True)

    parent_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), index=True)
    branch_id = db.Column(
        db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True
    )  # Linked Branch

    manager_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_main = db.Column(db.Boolean, default=False)
    allow_negative_inventory = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)

    extra_fields = db.Column(db.JSON, default=dict)

    parent = db.relationship("Warehouse", remote_side=[id], backref="sub_warehouses")
    manager = db.relationship("User", foreign_keys=[manager_id])
    branch = db.relationship("Branch", backref="warehouses", foreign_keys=[branch_id])
    tenant = db.relationship("Tenant", backref="warehouses", foreign_keys=[tenant_id])
    warehouse_stocks = db.relationship("ProductWarehouseStock", back_populates="warehouse", lazy="dynamic")
    stock_movements = db.relationship("StockMovement", back_populates="warehouse", lazy="dynamic")

    def __repr__(self):
        return f"<Warehouse {self.name}>"

    @property
    def is_online(self):
        return (self.warehouse_type or self.TYPE_PHYSICAL) == self.TYPE_ONLINE

    def type_label_ar(self):
        return "أونلاين" if self.is_online else "فعلي"


class ProductWarehouseStock(db.Model):
    __tablename__ = "product_warehouse_stock"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "product_id", "warehouse_id", name="uq_product_warehouse_stock"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    warehouse_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = db.Column(db.Numeric(15, 3), default=0, nullable=False)

    warehouse_barcode = db.Column(db.String(100), nullable=True)
    warehouse_description_ar = db.Column(db.Text, nullable=True)
    warehouse_description_en = db.Column(db.Text, nullable=True)
    warehouse_country_of_origin = db.Column(db.String(100), nullable=True)

    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    product = db.relationship("Product", back_populates="warehouse_stocks")
    warehouse = db.relationship("Warehouse", back_populates="warehouse_stocks")
    tenant = db.relationship("Tenant", backref="product_warehouse_stocks", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<ProductWarehouseStock P#{self.product_id} W#{self.warehouse_id} qty={self.quantity}>"
