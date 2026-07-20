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

    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(200), nullable=False, unique=True)
    name_ar = db.Column(db.String(200), nullable=False)
    name_en = db.Column(db.String(200))
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)

    business_type = db.Column(db.String(50), default="general")  # retail, wholesale, services, etc.
    industry = db.Column(db.String(100))  # automotive, heavy_equipment, etc.

    # Contact Info - معلومات التواصل
    address_ar = db.Column(db.Text)
    address_en = db.Column(db.Text)
    city = db.Column(db.String(100))
    country = db.Column(db.String(100), default="PS")

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
    brand_color_primary = db.Column(db.String(20), default="#007A3D")
    brand_color_secondary = db.Column(db.String(20), default="#D4AF37")

    # Subscription - الاشتراك
    subscription_plan = db.Column(db.String(50), default="basic")  # basic, pro, enterprise
    subscription_plan_duration = db.Column(db.String(20), default="monthly")  # monthly, annual, lifetime
    subscription_start = db.Column(db.DateTime)
    subscription_end = db.Column(db.DateTime)
    is_trial = db.Column(db.Boolean, default=False)
    trial_days_remaining = db.Column(db.Integer, default=0)

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
    enable_auto_backup = db.Column(db.Boolean, default=True)

    # Preferences - التفضيلات
    default_currency = db.Column(
        db.String(3), default=context_aware_default_currency
    )  # TODO: use Config.DEFAULT_CURRENCY
    default_language = db.Column(db.String(10), default="ar")
    timezone = db.Column(db.String(50), default="Asia/Hebron")
    date_format = db.Column(db.String(20), default="%Y-%m-%d")
    time_format = db.Column(db.String(20), default="%H:%M")

    # Financial Settings - إعدادات مالية
    fiscal_year_start = db.Column(db.Integer, default=1)  # Month: 1-12
    enable_tax = db.Column(db.Boolean, default=True)
    default_tax_rate = db.Column(db.Numeric(5, 2), default=Decimal("5.00"))
    vat_country = db.Column(db.String(2), default="PS")  # PS, IL, AE

    # Dynamic Base Currency - العملة الأساسية الديناميكية للمستأجر
    base_currency = db.Column(db.String(3), default="ILS")  # ILS, AED, USD, JOD, etc.

    # Pricing Method - هل الأسعار تشمل الضريبة؟
    prices_include_vat = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def get_base_currency(self):
        """Return the tenant's base currency. Falls back to default_currency if base_currency is not set."""
        return (self.base_currency or self.default_currency or "ILS").strip().upper()

    def get_currency_for_display(self):
        """Return the currency symbol for the tenant's base currency."""
        from utils.currency_utils import get_currency_symbol

        return get_currency_symbol(self.get_base_currency)

    vat_number = db.Column(db.String(100))

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_suspended = db.Column(db.Boolean, default=False, index=True)
    suspension_reason = db.Column(db.Text)

    # Meta
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    created_by_user = db.relationship("User", foreign_keys=[created_by])

    def business_type_label(self, lang="ar"):
        from services.industry_service import BUSINESS_TYPE_LABELS

        code = self.business_type or "general"
        labels = BUSINESS_TYPE_LABELS.get(code)
        if not labels:
            return code
        ar, en = labels
        return f"{ar} / {en}" if lang == "both" else ar

    def __repr__(self):
        return f"<Tenant {self.name}>"

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
            import logging

            logger = logging.getLogger("azad.security")
            logger.debug("Failed to resolve active tenant from user relationship", exc_info=True)

        import logging

        logger = logging.getLogger("azad.security")
        logger.warning("Tenant.get_current() returned None — unauthenticated or no active tenant resolved")
        return None

    @property
    def is_lifetime(self):
        return self.subscription_plan_duration == "lifetime"

    def is_subscription_active(self):
        if self.is_lifetime:
            return True
        if self.subscription_end:
            return datetime.now(timezone.utc) < self.subscription_end
        return True

    def get_remaining_days(self):
        if self.is_lifetime:
            return 9999
        if self.subscription_end:
            delta = self.subscription_end - datetime.now(timezone.utc)
            return max(0, delta.days)
        return 9999

    def get_subscription_duration_display(self, lang="ar"):
        labels = {"monthly": "شهري", "annual": "سنوي", "lifetime": "مدى الحياة"}
        if lang == "en":
            labels = {"monthly": "Monthly", "annual": "Annual", "lifetime": "Lifetime"}
        return labels.get(self.subscription_plan_duration, self.subscription_plan_duration)

    def extend_subscription(self, days: int) -> "Tenant":
        """Extend (or set, if unset) the subscription end date by ``days``.

        Pure ORM mutation — the caller must wrap this in an atomic transaction.
        A negative ``days`` value shortens the subscription.
        """
        from datetime import timedelta

        if days == 0:
            return self
        now = datetime.now(timezone.utc)
        base = self.subscription_end
        if not isinstance(base, datetime):
            base = now
        elif base < now:
            base = now
        self.subscription_end = base + timedelta(days=days)
        self.updated_at = now
        return self

    def set_subscription_end(self, end_value) -> "Tenant":
        """Set an explicit subscription end. ``end_value`` may be a datetime,
        ISO string, or None (clear). Pure ORM — caller wraps in a transaction.
        """
        if end_value is None or end_value == "":
            self.subscription_end = None
        elif isinstance(end_value, str):
            from datetime import datetime as _dt

            self.subscription_end = _dt.fromisoformat(end_value)
        else:
            self.subscription_end = end_value
        self.updated_at = datetime.now(timezone.utc)
        return self

    def apply_subscription_plan(
        self,
        plan: str | None,
        duration: str | None = None,
        is_trial: bool | None = None,
    ) -> "Tenant":
        """Update the subscription plan label / duration / trial flag.

        Pure ORM — caller wraps in an atomic transaction.
        """
        if plan is not None:
            self.subscription_plan = plan
        if duration is not None:
            self.subscription_plan_duration = duration
        if is_trial is not None:
            self.is_trial = bool(is_trial)
        self.updated_at = datetime.now(timezone.utc)
        return self

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "name_ar": self.name_ar,
            "slug": self.slug,
            "business_type": self.business_type,
            "country": self.country,
            "default_currency": self.default_currency,
            "is_active": self.is_active,
            "subscription_plan": self.subscription_plan,
            "subscription_plan_duration": self.subscription_plan_duration,
            "subscription_end": (self.subscription_end.isoformat() if self.subscription_end else None),
            "enable_auto_backup": self.enable_auto_backup,
            "is_trial": self.is_trial,
        }
