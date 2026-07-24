"""FEFO stock batches — one row per received lot (behind ``enable_batches``)."""

from __future__ import annotations

from datetime import datetime, timezone

from extensions import db


class StockBatch(db.Model):
    """Remaining quantity of one received lot, at its receipt cost.

    Consumed in FEFO order (soonest ``expiry_date`` first, NULLS LAST, then
    oldest ``received_at``) when the global ``enable_batches`` toggle is on.
    The MWAC ProductWarehouseCost ledger remains the stock ledger — batches
    are the per-lot cost overlay used for COGS while the toggle is enabled.
    """

    __tablename__ = "stock_batches"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=False,
        index=True,
    )
    warehouse_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouses.id"),
        nullable=False,
        index=True,
    )
    quantity = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    unit_cost = db.Column(db.Numeric(15, 4), nullable=False, default=0)
    expiry_date = db.Column(db.Date, nullable=True, index=True)
    received_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    reference_type = db.Column(db.String(40), nullable=True)
    reference_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
