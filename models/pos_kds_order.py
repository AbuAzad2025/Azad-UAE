from datetime import datetime, timezone
from extensions import db


class PosKdsOrder(db.Model):
    __tablename__ = 'pos_kds_orders'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('pos_sessions.id'), nullable=True, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True)

    order_number = db.Column(db.String(50), nullable=False)
    items_json = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False, index=True)
    priority = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    sale = db.relationship('Sale', foreign_keys=[sale_id])
    session = db.relationship('PosSession', foreign_keys=[session_id])
