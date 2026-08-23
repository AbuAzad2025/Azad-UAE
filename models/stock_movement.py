"""StockMovement model - tracks all stock movements across warehouses."""

from datetime import UTC, datetime

from extensions import db


class StockMovement(db.Model):
    __tablename__ = "stock_movements"

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
        db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    movement_type = db.Column(db.String(20), nullable=False, index=True)

    quantity = db.Column(db.Numeric(15, 3), nullable=False)

    reference_type = db.Column(db.String(50))
    reference_id = db.Column(db.Integer)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    notes = db.Column(db.Text)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    product = db.relationship("Product", back_populates="stock_movements")
    warehouse = db.relationship("Warehouse", back_populates="stock_movements")
    user = db.relationship("User", foreign_keys=[user_id])
    tenant = db.relationship("Tenant", backref="stock_movements", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<StockMovement {self.movement_type} {self.quantity}>"

    def get_type_display(self, lang="ar"):
        types = {
            "purchase": {"ar": "شراء", "en": "Purchase"},
            "sale": {"ar": "بيع", "en": "Sale"},
            "adjustment": {"ar": "تسوية", "en": "Adjustment"},
            "return": {"ar": "إرجاع", "en": "Return"},
            "damage": {"ar": "تالف", "en": "Damage"},
            "transfer": {"ar": "تحويل", "en": "Transfer"},
        }
        return types.get(self.movement_type, {}).get(lang, self.movement_type)

    def to_dict(self):
        return {
            "id": self.id,
            "product": self.product.name if self.product else None,
            "movement_type": self.movement_type,
            "quantity": float(self.quantity),
            "reference": (f"{self.reference_type} #{self.reference_id}" if self.reference_type else None),
            "created_at": self.created_at.isoformat(),
        }
