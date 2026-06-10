"""
Invoice & Receipt Header Settings Model
نموذج إعدادات ترويسات الفواتير وسندات القبض
"""

from datetime import datetime, timezone
from extensions import db
from decimal import Decimal


class InvoiceSettings(db.Model):
    """
    إعدادات ترويسات الفواتير وسندات القبض — لكل شركة (tenant) سجل مستقل.
    """
    __tablename__ = 'invoice_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Company Info - معلومات الشركة
    company_name_ar = db.Column(db.String(200), nullable=False, default='شركة أزاد')
    company_name_en = db.Column(db.String(200), nullable=False, default='Azad Company')
    
    # Logos - الشعارات
    logo_url = db.Column(db.String(500))  # Main logo (URL)
    logo_path = db.Column(db.String(500))  # Uploaded logo path
    stamp_url = db.Column(db.String(500))  # Company stamp
    signature_url = db.Column(db.String(500))  # Authorized signature
    
    # Contact Info - معلومات التواصل
    address_ar = db.Column(db.Text)
    address_en = db.Column(db.Text)
    phone_1 = db.Column(db.String(50))
    phone_2 = db.Column(db.String(50))
    email = db.Column(db.String(100))
    website = db.Column(db.String(200))
    
    # Business Info - المعلومات التجارية
    tax_number = db.Column(db.String(100))  # الرقم الضريبي
    commercial_register = db.Column(db.String(100))  # السجل التجاري
    license_number = db.Column(db.String(100))  # رقم الرخصة
    
    # Bank Info - معلومات البنك
    bank_name = db.Column(db.String(200))
    bank_account_number = db.Column(db.String(100))
    iban = db.Column(db.String(100))
    swift_code = db.Column(db.String(50))
    
    # Invoice Design - تصميم الفاتورة
    header_color = db.Column(db.String(20), default='#667eea')  # لون الترويسة
    accent_color = db.Column(db.String(20), default='#764ba2')  # اللون الثانوي
    text_color = db.Column(db.String(20), default='#333333')
    
    # Header Layout - تخطيط الترويسة
    show_logo = db.Column(db.Boolean, default=True)
    logo_position = db.Column(db.String(20), default='left')  # left, center, right
    logo_size = db.Column(db.String(20), default='medium')  # small, medium, large
    
    # Footer - الذيل
    footer_text_ar = db.Column(db.Text)
    footer_text_en = db.Column(db.Text)
    show_terms = db.Column(db.Boolean, default=True)
    
    # Terms & Conditions - الشروط والأحكام
    terms_conditions_ar = db.Column(db.Text)
    terms_conditions_en = db.Column(db.Text)
    
    # Payment Terms - شروط الدفع
    payment_terms_ar = db.Column(db.Text, default='الدفع نقداً أو بالتحويل البنكي')
    payment_terms_en = db.Column(db.Text, default='Payment by cash or bank transfer')
    
    # Notes - ملاحظات
    default_invoice_note_ar = db.Column(db.Text)
    default_invoice_note_en = db.Column(db.Text)
    default_receipt_note_ar = db.Column(db.Text)
    default_receipt_note_en = db.Column(db.Text)
    
    # QR Code - رمز الاستجابة السريعة
    enable_qr_code = db.Column(db.Boolean, default=True)
    qr_position = db.Column(db.String(20), default='bottom-right')
    
    # Watermark - العلامة المائية
    enable_watermark = db.Column(db.Boolean, default=False)
    watermark_text = db.Column(db.String(200))
    watermark_image_path = db.Column(db.String(500))  # Watermark image path
    watermark_opacity = db.Column(db.Numeric(3, 2), default=Decimal('0.10'))
    
    # Print Settings - إعدادات الطباعة
    paper_size = db.Column(db.String(20), default='A4')  # A4, A5, Letter
    orientation = db.Column(db.String(20), default='portrait')  # portrait, landscape
    
    # Language - اللغة
    default_language = db.Column(db.String(10), default='ar')  # ar, en, both
    
    # Additional Fields - حقول إضافية
    show_barcode = db.Column(db.Boolean, default=True)
    show_page_numbers = db.Column(db.Boolean, default=True)
    show_due_date = db.Column(db.Boolean, default=True)
    
    # Social Media - وسائل التواصل
    facebook_url = db.Column(db.String(200))
    instagram_url = db.Column(db.String(200))
    whatsapp_number = db.Column(db.String(50))
    
    # Active Template - القالب النشط
    active_template = db.Column(db.String(50), default='modern')  # modern, classic, minimal
    
    # Meta
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    
    # Relationships
    tenant = db.relationship('Tenant', backref='invoice_settings', foreign_keys=[tenant_id])
    user = db.relationship('User', foreign_keys=[updated_by])
    
    def __repr__(self):
        return f'<InvoiceSettings {self.company_name_ar}>'
    
    @staticmethod
    def _seed_from_tenant(settings, tenant):
        if not tenant:
            return settings
        settings.company_name_ar = tenant.name_ar or tenant.name or settings.company_name_ar
        settings.company_name_en = tenant.name_en or tenant.name or settings.company_name_en
        settings.address_ar = tenant.address_ar or settings.address_ar
        settings.address_en = tenant.address_en or settings.address_en
        settings.phone_1 = tenant.phone_1 or tenant.mobile or settings.phone_1
        settings.email = tenant.email or settings.email
        settings.tax_number = tenant.tax_number or settings.tax_number
        settings.commercial_register = tenant.commercial_register or settings.commercial_register
        settings.license_number = tenant.license_number or settings.license_number
        return settings

    @staticmethod
    def get_active(tenant_id=None):
        """Active invoice settings for the given or current tenant.

        Tenant-specific rows are created on demand when tenant_id is known.
        Without tenant context, returns an existing legacy global row if any —
        never auto-creates active tenant_id=NULL settings.
        """
        from flask_login import current_user

        if tenant_id is None:
            try:
                if current_user and getattr(current_user, 'is_authenticated', False):
                    from utils.tenanting import get_active_tenant_id
                    tenant_id = get_active_tenant_id()
            except Exception:
                pass

        if tenant_id is not None:
            tid = int(tenant_id)
            settings = InvoiceSettings.query.filter_by(
                is_active=True, tenant_id=tid
            ).first()
            if settings:
                return settings
            from models.tenant import Tenant
            tenant = db.session.get(Tenant, tid)
            settings = InvoiceSettings(is_active=True, tenant_id=tid)
            InvoiceSettings._seed_from_tenant(settings, tenant)
            db.session.add(settings)
            db.session.commit()
            return settings

        return InvoiceSettings.query.filter_by(is_active=True).filter(
            InvoiceSettings.tenant_id.is_(None)
        ).first()

    @staticmethod
    def company_print_context(tenant_id=None):
        """Tenant branding with per-tenant invoice settings fallback for print views."""
        from models.tenant import Tenant
        from utils.tenant_branding import get_print_header_context

        if tenant_id is None:
            tenant = Tenant.get_current()
            tenant_id = tenant.id if tenant else None
        else:
            tenant = db.session.get(Tenant, int(tenant_id))

        branding = get_print_header_context(tenant_id)
        settings = InvoiceSettings.get_active(tenant_id)
        return tenant, settings, {
            'name_ar': branding['company_name_ar'],
            'name_en': branding['company_name_en'],
            'address': branding['address_ar'] or branding['address_en'],
            'phone': branding['phone'],
            'email': branding['email'],
            'tax_number': branding['tax_number'],
            'logo_url': branding['logo_url'],
        }
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'company_name_ar': self.company_name_ar,
            'company_name_en': self.company_name_en,
            'logo_url': self.logo_url,
            'address_ar': self.address_ar,
            'address_en': self.address_en,
            'phone_1': self.phone_1,
            'phone_2': self.phone_2,
            'email': self.email,
            'website': self.website,
            'tax_number': self.tax_number,
            'header_color': self.header_color,
            'accent_color': self.accent_color,
            'active_template': self.active_template,
            'default_language': self.default_language,
            'enable_qr_code': self.enable_qr_code,
            'show_logo': self.show_logo,
            'show_barcode': self.show_barcode,
        }

