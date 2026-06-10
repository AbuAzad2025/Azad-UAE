"""Online store settings — one store per tenant, bound to one online warehouse."""
from datetime import datetime, timezone

from extensions import db


class TenantStore(db.Model):
    __tablename__ = 'tenant_stores'

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False, index=True)

    is_enabled = db.Column(db.Boolean, default=False, nullable=False)
    # Platform-owner hard lock (force-OFF). When True the store is forced closed
    # regardless of is_enabled, and the tenant owner cannot re-enable it.
    platform_disabled = db.Column(db.Boolean, default=False, nullable=False, server_default='false')
    store_slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200))
    tagline = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    whatsapp = db.Column(db.String(50))
    email = db.Column(db.String(120))
    min_order_amount = db.Column(db.Numeric(15, 3), nullable=True)
    delivery_note = db.Column(db.String(500))

    logo_path = db.Column(db.String(255))
    meta_title = db.Column(db.String(200))
    meta_description = db.Column(db.String(500))
    meta_keywords = db.Column(db.String(500))
    meta_title_en = db.Column(db.String(200))
    meta_description_en = db.Column(db.String(500))
    return_policy_ar = db.Column(db.Text)
    return_policy_en = db.Column(db.Text)
    low_stock_threshold = db.Column(db.Numeric(15, 3), default=5)
    notify_whatsapp_on_order = db.Column(db.Boolean, default=True, nullable=False)
    notify_email_on_order = db.Column(db.Boolean, default=True, nullable=False)
    subdomain = db.Column(db.String(100), unique=True, index=True)
    custom_domain = db.Column(db.String(255), unique=True, index=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    tenant = db.relationship('Tenant', backref=db.backref('store', uselist=False), foreign_keys=[tenant_id])
    warehouse = db.relationship('Warehouse', foreign_keys=[warehouse_id])

    def __repr__(self):
        return f'<TenantStore tenant={self.tenant_id} slug={self.store_slug}>'

    def logo_url(self):
        if not self.logo_path:
            return None
        path = self.logo_path.lstrip('/')
        if path.startswith('static/'):
            path = path[7:]
        return f'/static/{path}' if not path.startswith('uploads/') else f'/static/{path}'

    def seo_title(self, lang='ar') -> str:
        if lang == 'en' and self.meta_title_en:
            return self.meta_title_en
        return self.meta_title or self.title or ''

    def seo_description(self, lang='ar') -> str:
        if lang == 'en' and self.meta_description_en:
            return self.meta_description_en
        return self.meta_description or self.tagline or ''

    def return_policy(self, lang='ar') -> str:
        if lang == 'en' and self.return_policy_en:
            return self.return_policy_en
        return self.return_policy_ar or ''
