"""Storefront discount coupons — per tenant."""
from datetime import datetime, timezone

from extensions import db


class StoreCoupon(db.Model):
    __tablename__ = 'store_coupons'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'code', name='uq_store_coupon_tenant_code'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    code = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.String(255))
    discount_percent = db.Column(db.Numeric(5, 2))
    discount_amount = db.Column(db.Numeric(15, 3))
    min_order_amount = db.Column(db.Numeric(15, 3))
    max_uses = db.Column(db.Integer)
    used_count = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    valid_from = db.Column(db.DateTime)
    valid_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    tenant = db.relationship('Tenant', backref=db.backref('store_coupons', lazy='dynamic'))

    @staticmethod
    def normalize_code(code: str) -> str:
        return (code or '').strip().upper()

    def is_valid_now(self) -> bool:
        if not self.is_active:
            return False
        now = datetime.now(timezone.utc)
        if self.valid_from and self.valid_from.replace(tzinfo=timezone.utc) > now:
            return False
        if self.valid_until and self.valid_until.replace(tzinfo=timezone.utc) < now:
            return False
        if self.max_uses is not None and int(self.used_count or 0) >= int(self.max_uses):
            return False
        return True
