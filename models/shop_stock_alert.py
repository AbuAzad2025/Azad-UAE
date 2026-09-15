from datetime import UTC, datetime

from extensions import db


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
        db.DateTime(timezone=True),
        nullable=False,
        index=True,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "email", "product_id", name="uq_stock_alert_tenant_email_product"),
        db.Index("ix_stock_alerts_tenant_product", "tenant_id", "product_id"),
        db.Index("ix_stock_alerts_tenant_email", "tenant_id", "email"),
    )
