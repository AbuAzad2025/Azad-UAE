from datetime import datetime, timezone
from extensions import db

class Branch(db.Model):
    __tablename__ = 'branches'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'name', name='uq_branches_tenant_name'),
        db.UniqueConstraint('tenant_id', 'code', name='uq_branches_tenant_code'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), nullable=False)  # e.g., RAM, HEB

    # Location & Contact
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(50), nullable=True)
    phone = db.Column(db.String(50), nullable=True)

    # Status
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_main = db.Column(db.Boolean, default=False) # Is this the HQ?

    # Pricing Method - هل الأسعار في هذا الفرع تشمل الضريبة؟
    # NULL = يرث من إعدادات التينانت
    prices_include_vat = db.Column(db.Boolean, default=None, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    tenant = db.relationship('Tenant', backref='branches')

    # Relationships (Will be populated by backrefs from other models)
    # users = db.relationship('User', backref='branch')
    # warehouses = db.relationship('Warehouse', backref='branch')
    # sales = db.relationship('Sale', backref='branch')
    # ...

    def __repr__(self):
        return f'<Branch {self.name} ({self.code})>'
