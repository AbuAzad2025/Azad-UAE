from extensions import db
from datetime import datetime, timezone

class ShopLoyalty(db.Model):
    __tablename__ = 'shop_loyalty'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('shop_customer_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    points = db.Column(db.Integer, default=0, nullable=False)
    points_earned = db.Column(db.Integer, default=0, nullable=False)
    points_redeemed = db.Column(db.Integer, default=0, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    account = db.relationship('ShopCustomerAccount', backref=db.backref('loyalty', uselist=False))

class ShopLoyaltyTransaction(db.Model):
    __tablename__ = 'shop_loyalty_transactions'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('shop_customer_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=True, index=True)
    points = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, index=True, default=lambda: datetime.now(timezone.utc))
