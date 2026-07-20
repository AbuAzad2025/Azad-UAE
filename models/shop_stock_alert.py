from extensions import db
from datetime import datetime, timezone


class ShopStockAlert(db.Model):
    __tablename__ = "shop_stock_alerts"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = db.Column(db.String(200), nullable=False)
    is_notified = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (db.UniqueConstraint("email", "product_id", name="uq_stock_alert_email_product"),)
