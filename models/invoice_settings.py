"""
Invoice & Receipt Header Settings Model
نموذج إعدادات ترويسات الفواتير وسندات القبض
"""

from datetime import UTC, datetime
from decimal import Decimal

from extensions import db


class InvoiceSettings(db.Model):
    """
    إعدادات ترويسات الفواتير وسندات القبض — لكل شركة (tenant) سجل مستقل.
    """

    __tablename__ = "invoice_settings"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Company Info - معلومات الشركة
    company_name_ar = db.Column(db.String(200), nullable=False, default="")
    company_name_en = db.Column(db.String(200), nullable=False, default="")

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

    tax_number = db.Column(db.String(100))  # الرقم الضريبي
    commercial_register = db.Column(db.String(100))  # السجل التجاري
    license_number = db.Column(db.String(100))  # رقم الرخصة

    # Bank Info - معلومات البنك
    bank_name = db.Column(db.String(200))
    bank_account_number = db.Column(db.String(100))
    iban = db.Column(db.String(100))
    swift_code = db.Column(db.String(50))

    # Invoice Design - تصميم الفاتورة
    header_color = db.Column(db.String(20), default="#667eea")  # لون الترويسة
    accent_color = db.Column(db.String(20), default="#764ba2")  # اللون الثانوي
    text_color = db.Column(db.String(20), default="#333333")

    show_logo = db.Column(db.Boolean, default=True)
    logo_position = db.Column(db.String(20), default="left")  # left, center, right
    logo_size = db.Column(db.String(20), default="medium")  # small, medium, large

    # Footer - الذيل
    footer_text_ar = db.Column(db.Text)
    footer_text_en = db.Column(db.Text)
    show_terms = db.Column(db.Boolean, default=True)

    # Terms & Conditions - الشروط والأحكام
    terms_conditions_ar = db.Column(db.Text)
    terms_conditions_en = db.Column(db.Text)

    # Payment Terms - شروط الدفع
    payment_terms_ar = db.Column(db.Text, default="الدفع نقداً أو بالتحويل البنكي")
    payment_terms_en = db.Column(db.Text, default="Payment by cash or bank transfer")

    # Notes - ملاحظات
    default_invoice_note_ar = db.Column(db.Text)
    default_invoice_note_en = db.Column(db.Text)
    default_receipt_note_ar = db.Column(db.Text)
    default_receipt_note_en = db.Column(db.Text)

    # QR Code - رمز الاستجابة السريعة
    enable_qr_code = db.Column(db.Boolean, default=True)
    qr_position = db.Column(db.String(20), default="bottom-right")

    # Watermark - العلامة المائية
    enable_watermark = db.Column(db.Boolean, default=False)
    watermark_text = db.Column(db.String(200))
    watermark_image_path = db.Column(db.String(500))  # Watermark image path
    watermark_opacity = db.Column(db.Numeric(3, 2), default=Decimal("0.10"))

    # Print Settings - إعدادات الطباعة
    paper_size = db.Column(db.String(20), default="A4")  # A4, A5, Letter
    orientation = db.Column(db.String(20), default="portrait")  # portrait, landscape

    default_language = db.Column(db.String(10), default="ar")  # ar, en, both

    # Additional Fields - حقول إضافية
    show_barcode = db.Column(db.Boolean, default=True)
    show_page_numbers = db.Column(db.Boolean, default=True)
    show_due_date = db.Column(db.Boolean, default=True)

    # Social Media - وسائل التواصل
    facebook_url = db.Column(db.String(200))
    instagram_url = db.Column(db.String(200))
    whatsapp_number = db.Column(db.String(50))

    active_template = db.Column(db.String(50), default="modern")  # modern, classic, minimal

    # Meta
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), index=True)

    tenant = db.relationship("Tenant", backref="invoice_settings", foreign_keys=[tenant_id])
    user = db.relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return f"<InvoiceSettings {self.company_name_ar}>"

    @staticmethod
    def _seed_from_tenant(settings, tenant):
        """Explicitly copy the current tenant profile into an edit/seed candidate.

        This never happens while rendering. It remains for controlled legacy data
        migration and should not be called by document generation.
        """
        if not tenant:
            return settings
        mapping = (
            ("name_ar", "company_name_ar", "company_name_en"),
            ("address_ar", "address_ar", None),
            ("address_en", "address_en", None),
            ("phone_1", "phone_1", None),
            ("phone_2", "phone_2", None),
            ("email", "email", None),
            ("website", "website", None),
            ("tax_number", "tax_number", None),
            ("commercial_register", "commercial_register", None),
            ("license_number", "license_number", None),
        )
        for tenant_field, target, _ in mapping:
            value = getattr(tenant, tenant_field, None)
            if value not in (None, ""):
                setattr(settings, target, value)
        if tenant.name_en not in (None, ""):
            settings.company_name_en = tenant.name_en
        elif tenant.name not in (None, ""):
            settings.company_name_en = tenant.name
        for tenant_field, target in (
            ("bank_name", "bank_name"),
            ("bank_account_number", "bank_account_number"),
            ("iban", "iban"),
            ("swift_code", "swift_code"),
            ("payment_terms_ar", "payment_terms_ar"),
            ("payment_terms_en", "payment_terms_en"),
            ("footer_text_ar", "footer_text_ar"),
            ("footer_text_en", "footer_text_en"),
            ("default_invoice_note_ar", "default_invoice_note_ar"),
            ("default_invoice_note_en", "default_invoice_note_en"),
            ("invoice_header_color", "header_color"),
            ("invoice_accent_color", "accent_color"),
            ("active_invoice_template", "active_template"),
            ("logo_url", "logo_url"),
        ):
            value = getattr(tenant, tenant_field, None)
            if value not in (None, ""):
                setattr(settings, target, value)
        return settings

    @staticmethod
    def get_active(tenant_id=None, user=None):
        """Return a detached profile snapshot for rendering.

        Compatibility name retained for older callers. This method never creates
        an invoice-settings row; document profile ownership is ``Tenant``.
        """
        if tenant_id is None and user is not None:
            try:
                from utils.tenanting import get_active_tenant_id

                tenant_id = get_active_tenant_id(user)
            except Exception:
                import logging

                logging.getLogger(__name__).debug("Failed to resolve tenant_id from user", exc_info=True)
        if tenant_id is None:
            return None
        from utils.invoice_profile import resolve_print_profile

        return resolve_print_profile(int(tenant_id))

    @staticmethod
    def company_print_context(tenant_id=None):
        """Resolve the unified print context from the pinned tenant profile."""
        from services.invoice_profile_service import get_company_print_context

        return get_company_print_context(tenant_id=tenant_id)

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "company_name_ar": self.company_name_ar,
            "company_name_en": self.company_name_en,
            "logo_url": self.logo_url,
            "address_ar": self.address_ar,
            "address_en": self.address_en,
            "phone_1": self.phone_1,
            "phone_2": self.phone_2,
            "email": self.email,
            "website": self.website,
            "tax_number": self.tax_number,
            "header_color": self.header_color,
            "accent_color": self.accent_color,
            "active_template": self.active_template,
            "default_language": self.default_language,
            "enable_qr_code": self.enable_qr_code,
            "show_logo": self.show_logo,
            "show_barcode": self.show_barcode,
        }
