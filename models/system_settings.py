"""
System Settings Model
نموذج إعدادات النظام الشاملة
"""

from datetime import datetime, timezone
from extensions import db
from utils.currency_utils import context_aware_default_currency
from decimal import Decimal
import json


class SystemSettings(db.Model):
    """
    إعدادات النظام العامة - قابلة للتعديل من لوحة المالك
    """

    __tablename__ = "system_settings"

    id = db.Column(db.Integer, primary_key=True)

    # System Identity - هوية النظام
    system_name = db.Column(db.String(200), default="Azad ERP System")
    system_version = db.Column(db.String(20), default="2.0.0")
    system_mode = db.Column(db.String(20), default="production")  # development, production

    # UI Settings - إعدادات الواجهة
    theme = db.Column(db.String(50), default="modern")  # modern, classic, custom
    primary_color = db.Column(db.String(20), default="#007A3D")
    secondary_color = db.Column(db.String(20), default="#D4AF37")
    sidebar_color = db.Column(db.String(20), default="#1a1a1a")
    navbar_color = db.Column(db.String(20), default="#2d2d2d")

    # Layout - التخطيط
    sidebar_position = db.Column(db.String(20), default="right")  # right, left
    layout_style = db.Column(db.String(20), default="fixed")  # fixed, boxed, fluid
    enable_dark_mode = db.Column(db.Boolean, default=True)
    default_dark_mode = db.Column(db.Boolean, default=False)

    default_language = db.Column(db.String(10), default="ar")
    available_languages = db.Column(db.Text, default='["ar", "en"]')  # JSON array
    rtl_enabled = db.Column(db.Boolean, default=True)

    timezone = db.Column(db.String(50), default="Asia/Dubai")
    date_format = db.Column(db.String(30), default="%Y-%m-%d")
    time_format = db.Column(db.String(30), default="%H:%M")
    datetime_format = db.Column(db.String(50), default="%Y-%m-%d %H:%M")

    default_currency = db.Column(
        db.String(3), default=context_aware_default_currency
    )  # TODO: use Config.DEFAULT_CURRENCY
    currency_symbol = db.Column(
        db.String(10), default=context_aware_default_currency
    )  # TODO: use Config.DEFAULT_CURRENCY
    currency_position = db.Column(db.String(10), default="after")  # before, after
    decimal_places = db.Column(db.Integer, default=2)

    enable_tax = db.Column(db.Boolean, default=True)
    tax_name_ar = db.Column(db.String(100), default="ضريبة القيمة المضافة")
    tax_name_en = db.Column(db.String(100), default="VAT")
    default_tax_rate = db.Column(db.Numeric(5, 2), default=Decimal("5.00"))
    tax_number_required = db.Column(db.Boolean, default=True)

    enable_sales = db.Column(db.Boolean, default=True)
    enable_purchases = db.Column(db.Boolean, default=True)
    enable_inventory = db.Column(db.Boolean, default=True)
    enable_customers = db.Column(db.Boolean, default=True)
    enable_suppliers = db.Column(db.Boolean, default=True)
    enable_expenses = db.Column(db.Boolean, default=True)
    enable_gl = db.Column(db.Boolean, default=True)
    enable_reports = db.Column(db.Boolean, default=True)
    enable_ai_assistant = db.Column(db.Boolean, default=True)
    enable_pos = db.Column(db.Boolean, default=True)
    enable_ecommerce = db.Column(db.Boolean, default=False)

    enable_barcode_scanner = db.Column(db.Boolean, default=True)
    enable_multi_warehouse = db.Column(db.Boolean, default=True)
    enable_multi_currency = db.Column(db.Boolean, default=True)
    enable_discounts = db.Column(db.Boolean, default=True)
    enable_returns = db.Column(db.Boolean, default=True)
    enable_batches = db.Column(db.Boolean, default=False)
    enable_serials = db.Column(db.Boolean, default=False)

    # Security - الأمان
    session_timeout = db.Column(db.Integer, default=60)  # minutes
    password_min_length = db.Column(db.Integer, default=6)
    password_require_uppercase = db.Column(db.Boolean, default=False)
    password_require_numbers = db.Column(db.Boolean, default=False)
    password_require_special = db.Column(db.Boolean, default=False)
    max_login_attempts = db.Column(db.Integer, default=5)
    lockout_duration = db.Column(db.Integer, default=30)  # minutes

    # Notifications - الإشعارات
    enable_email_notifications = db.Column(db.Boolean, default=False)
    enable_sms_notifications = db.Column(db.Boolean, default=False)
    enable_push_notifications = db.Column(db.Boolean, default=False)
    low_stock_notification = db.Column(db.Boolean, default=True)

    items_per_page = db.Column(db.Integer, default=25)
    enable_caching = db.Column(db.Boolean, default=True)
    cache_ttl = db.Column(db.Integer, default=300)  # seconds
    enable_compression = db.Column(db.Boolean, default=True)

    auto_backup_enabled = db.Column(db.Boolean, default=True)
    backup_frequency = db.Column(db.String(20), default="daily")  # daily, weekly, monthly
    backup_retention_days = db.Column(db.Integer, default=30)

    enable_api = db.Column(db.Boolean, default=False)
    api_rate_limit = db.Column(db.Integer, default=100)  # requests per minute

    # Custom Settings - إعدادات مخصصة (JSON)
    custom_settings = db.Column(db.Text)

    smtp_server = db.Column(db.String(200))
    smtp_port = db.Column(db.Integer, default=587)
    smtp_username = db.Column(db.String(200))
    smtp_password = db.Column(db.String(200))
    smtp_use_tls = db.Column(db.Boolean, default=True)
    email_from = db.Column(db.String(200))

    sms_provider = db.Column(db.String(50))
    sms_api_key = db.Column(db.String(200))
    sms_sender_name = db.Column(db.String(50))
    sms_enabled = db.Column(db.Boolean, default=False)

    whatsapp_api_url = db.Column(db.String(500))
    whatsapp_api_key = db.Column(db.String(200))
    whatsapp_phone_number = db.Column(db.String(20))
    whatsapp_enabled = db.Column(db.Boolean, default=False)

    notification_templates = db.Column(db.Text)

    vat_enabled = db.Column(db.Boolean, default=False)
    vat_number = db.Column(db.String(50))
    tax_id_number = db.Column(db.String(50))

    # Azad Platform Fees - رسوم منصة أزاد
    azad_platform_fee_rate = db.Column(db.Numeric(5, 2), default=Decimal("1.00"))
    subscription_monthly_fee_aed = db.Column(db.Numeric(15, 3), default=Decimal("0.000"))
    subscription_yearly_fee_aed = db.Column(db.Numeric(15, 3), default=Decimal("0.000"))
    subscription_perpetual_fee_aed = db.Column(db.Numeric(15, 3), default=Decimal("0.000"))

    auto_update_rates = db.Column(db.Boolean, default=False)

    owner_whitelist_ips = db.Column(db.Text)

    # Meta
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)

    user = db.relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return f"<SystemSettings {self.system_name}>"

    @staticmethod
    def get_current():
        """Get current system settings or create default"""
        settings = SystemSettings.query.filter_by(is_active=True).first()
        if not settings:
            settings = SystemSettings()
            db.session.add(settings)
            db.session.flush()
        return settings

    def get_custom_setting(self, key, default=None):
        """Get custom setting by key"""
        if self.custom_settings:
            try:
                custom = json.loads(self.custom_settings)
                return custom.get(key, default)
            except Exception:
                return default
        return default

    def set_custom_setting(self, key, value):
        """Set custom setting"""
        custom = {}
        if self.custom_settings:
            try:
                custom = json.loads(self.custom_settings)
            except Exception:
                import logging

                logging.getLogger(__name__).debug("Failed to parse custom_settings JSON", exc_info=True)
        custom[key] = value
        self.custom_settings = json.dumps(custom, ensure_ascii=False)

    def to_dict(self):
        return {
            "system_name": self.system_name,
            "system_version": self.system_version,
            "theme": self.theme,
            "default_language": self.default_language,
            "default_currency": self.default_currency,
            "timezone": self.timezone,
            "is_active": self.is_active,
        }
