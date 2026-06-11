"""
Tenant Model - Multi-Tenant System
نموذج المستأجر - نظام متعدد المستأجرين
"""

from datetime import datetime, timezone
from extensions import db
from utils.currency_utils import context_aware_default_currency
from decimal import Decimal


class Tenant(db.Model):
    """
    معلومات الكراج/الشركة المستأجرة للنظام
    """
    __tablename__ = 'tenants'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Basic Info - معلومات أساسية
    name = db.Column(db.String(200), nullable=False, unique=True)
    name_ar = db.Column(db.String(200), nullable=False)
    name_en = db.Column(db.String(200))
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    
    # Business Type - نوع النشاط
    business_type = db.Column(db.String(50), default='general')  # retail, wholesale, services, etc.
    industry = db.Column(db.String(100))  # automotive, heavy_equipment, etc.
    
    # Contact Info - معلومات التواصل
    address_ar = db.Column(db.Text)
    address_en = db.Column(db.Text)
    city = db.Column(db.String(100))
    country = db.Column(db.String(100), default='UAE')
    
    phone_1 = db.Column(db.String(50))
    phone_2 = db.Column(db.String(50))
    mobile = db.Column(db.String(50))
    email = db.Column(db.String(120))
    website = db.Column(db.String(200))
    
    # Legal Info - معلومات قانونية
    tax_number = db.Column(db.String(100), index=True)  # TRN
    commercial_register = db.Column(db.String(100))
    license_number = db.Column(db.String(100))
    license_expiry = db.Column(db.Date)
    
    # Branding - العلامة التجارية
    logo_url = db.Column(db.String(500))
    logo_dark_url = db.Column(db.String(500))
    favicon_url = db.Column(db.String(500))
    brand_color_primary = db.Column(db.String(20), default='#007A3D')
    brand_color_secondary = db.Column(db.String(20), default='#D4AF37')
    
    # Subscription - الاشتراك
    subscription_plan = db.Column(db.String(50), default='basic')  # basic, pro, enterprise
    subscription_start = db.Column(db.DateTime)
    subscription_end = db.Column(db.DateTime)
    is_trial = db.Column(db.Boolean, default=False)
    trial_days_remaining = db.Column(db.Integer, default=0)
    
    # Limits - الحدود
    max_users = db.Column(db.Integer, default=5)
    max_products = db.Column(db.Integer, default=1000)
    max_customers = db.Column(db.Integer, default=500)
    max_suppliers = db.Column(db.Integer, default=200)
    max_branches = db.Column(db.Integer, default=3)
    max_warehouses = db.Column(db.Integer, default=2)
    max_storage_mb = db.Column(db.Integer, default=1024)  # 1GB
    max_invoices_per_month = db.Column(db.Integer, default=1000)
    max_sales_per_month = db.Column(db.Integer, default=5000)
    data_retention_days = db.Column(db.Integer, default=365)
    
    # Features - المميزات المفعلة
    enable_multi_warehouse = db.Column(db.Boolean, default=True)
    enable_multi_currency = db.Column(db.Boolean, default=True)
    enable_gl = db.Column(db.Boolean, default=True)
    enable_ai = db.Column(db.Boolean, default=True)
    enable_reports = db.Column(db.Boolean, default=True)
    enable_api = db.Column(db.Boolean, default=False)
    enable_pos = db.Column(db.Boolean, default=True)
    enable_payroll = db.Column(db.Boolean, default=True)
    enable_cheques = db.Column(db.Boolean, default=True)
    enable_expenses = db.Column(db.Boolean, default=True)
    enable_store = db.Column(db.Boolean, default=False)
    allow_data_export = db.Column(db.Boolean, default=True)
    allow_custom_integrations = db.Column(db.Boolean, default=False)
    
    # Preferences - التفضيلات
    default_currency = db.Column(db.String(3), default=context_aware_default_currency)  # TODO: use Config.DEFAULT_CURRENCY
    default_language = db.Column(db.String(10), default='ar')
    timezone = db.Column(db.String(50), default='Asia/Dubai')
    date_format = db.Column(db.String(20), default='%Y-%m-%d')
    time_format = db.Column(db.String(20), default='%H:%M')
    
    # Financial Settings - إعدادات مالية
    fiscal_year_start = db.Column(db.Integer, default=1)  # Month: 1-12
    enable_tax = db.Column(db.Boolean, default=True)
    default_tax_rate = db.Column(db.Numeric(5, 2), default=Decimal('5.00'))
    vat_country = db.Column(db.String(2), default='AE')  # AE, IL, PS
    vat_number = db.Column(db.String(100))
    
    # Status - الحالة
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_suspended = db.Column(db.Boolean, default=False, index=True)
    suspension_reason = db.Column(db.Text)
    
    # Meta
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    
    # Relationships
    created_by_user = db.relationship('User', foreign_keys=[created_by])
    
    def __repr__(self):
        return f'<Tenant {self.name}>'
    
    @staticmethod
    def get_current():
        """Current tenant for branding/settings — never leaks another company to logged-in users."""
        try:
            from flask_login import current_user
            from utils.tenanting import get_active_tenant_id, is_platform_owner
            if current_user and getattr(current_user, "is_authenticated", False):
                active_tid = get_active_tenant_id(current_user)
                if active_tid:
                    tenant = Tenant.query.filter_by(id=int(active_tid), is_active=True).first()
                    if tenant:
                        return tenant
                if not is_platform_owner(current_user):
                    rel = getattr(current_user, "tenant", None)
                    if rel and getattr(rel, "is_active", False):
                        return rel
                    return None
        except Exception:
            pass

        tenant = Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).first()
        if not tenant:
            # Create default tenant
            tenant = Tenant(
                name='Default System',
                name_ar='النظام الافتراضي',
                slug='default',
                business_type='general'
            )
            db.session.add(tenant)
            db.session.commit()
        else:
            updated = False
            if (tenant.name_ar or '').strip() == 'كراج افتراضي':
                tenant.name_ar = 'النظام الافتراضي'
                updated = True
            if (tenant.name or '').strip() == 'Default Garage':
                tenant.name = 'Default System'
                updated = True
            if (tenant.business_type or '').strip() == 'garage':
                tenant.business_type = 'general'
                updated = True
            if updated:
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
        return tenant
    
    def is_subscription_active(self):
        """Check if subscription is active"""
        if self.subscription_end:
            return datetime.now(timezone.utc) < self.subscription_end
        return True
    
    def get_remaining_days(self):
        """Get remaining subscription days"""
        if self.subscription_end:
            delta = self.subscription_end - datetime.now(timezone.utc)
            return max(0, delta.days)
        return 9999
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'name_ar': self.name_ar,
            'slug': self.slug,
            'business_type': self.business_type,
            'country': self.country,
            'default_currency': self.default_currency,
            'is_active': self.is_active,
            'subscription_plan': self.subscription_plan,
        }

