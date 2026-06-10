from extensions import db
from datetime import datetime, timezone

class ShopAbandonedCart(db.Model):
    __tablename__ = 'shop_abandoned_carts'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    account_id = db.Column(db.Integer, db.ForeignKey('shop_customer_accounts.id', ondelete='CASCADE'), nullable=True, index=True)
    email = db.Column(db.String(200), nullable=True)
    cart_data = db.Column(db.Text, nullable=True)
    reminder_sent_at = db.Column(db.DateTime, nullable=True)
    reminder_count = db.Column(db.Integer, default=0, nullable=False)
    recovered = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, index=True, default=lambda: datetime.now(timezone.utc))

    tenant = db.relationship('Tenant', backref=db.backref('abandoned_carts', lazy='dynamic'))
    account = db.relationship('ShopCustomerAccount', backref=db.backref('abandoned_carts', lazy='dynamic'))
