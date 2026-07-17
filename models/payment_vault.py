"""
Payment Vault Model - وحدة الدفع السرية
نموذج محمي بكلمة مرور منفصلة للدفع والتبرعات
"""

from datetime import datetime, timezone
from extensions import db


def _utc_now():
    return datetime.now(timezone.utc)
from decimal import Decimal
from werkzeug.security import generate_password_hash, check_password_hash


class PaymentVault(db.Model):
    """
    خزينة الدفع السرية - محمية بكلمة مرور منفصلة
    """

    __tablename__ = "payment_vault"

    id = db.Column(db.Integer, primary_key=True)

    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        unique=True,
    )

    # Vault Security - أمان الخزينة
    vault_password_hash = db.Column(db.String(255), nullable=False)  # كلمة مرور الخزينة
    vault_name = db.Column(db.String(100), default="Payment Vault")  # اسم الخزينة
    is_locked = db.Column(db.Boolean, default=True)  # هل مقفلة
    last_access = db.Column(db.DateTime, default=_utc_now)  # آخر وصول

    # Payment Gateway Settings - إعدادات بوابات الدفع
    nowpayments_api_key = db.Column(db.String(255))  # NOWPayments API Key
    nowpayments_ipn_secret = db.Column(db.String(255))  # IPN Secret
    bitcoin_address = db.Column(db.String(255))  # عنوان Bitcoin
    ethereum_address = db.Column(db.String(255))  # عنوان Ethereum
    usdt_address = db.Column(db.String(255))  # عنوان USDT

    # PayPal Settings - إعدادات PayPal
    paypal_client_id = db.Column(db.String(255))  # PayPal Client ID
    paypal_client_secret = db.Column(db.String(255))  # PayPal Secret (مشفر)
    paypal_business_email = db.Column(db.String(200))  # البريد التجاري
    paypal_mode = db.Column(db.String(20), default="sandbox")  # sandbox أو live

    # Bank Account Settings - الحساب البنكي للشركة
    bank_name = db.Column(db.String(200))  # اسم البنك
    bank_account_name = db.Column(db.String(200))  # اسم صاحب الحساب
    bank_account_number = db.Column(db.String(100))  # رقم الحساب
    bank_iban = db.Column(db.String(50))  # IBAN
    bank_swift_code = db.Column(db.String(20))  # SWIFT/BIC Code
    bank_branch = db.Column(db.String(200))  # اسم الفرع
    bank_country = db.Column(db.String(100))  # البلد
    bank_currency = db.Column(db.String(10), default="USD")  # العملة

    # Stripe Settings - إعدادات Stripe
    stripe_publishable_key = db.Column(db.String(255))  # Public Key
    stripe_secret_key = db.Column(db.String(255))  # Secret Key (مشفر)
    stripe_webhook_secret = db.Column(db.String(255))  # Webhook Secret

    # Other Payment Gateways - بوابات أخرى
    mollie_api_key = db.Column(db.String(255))  # Mollie
    square_access_token = db.Column(db.String(255))  # Square
    razorpay_key_id = db.Column(db.String(255))  # Razorpay
    razorpay_key_secret = db.Column(db.String(255))  # Razorpay Secret

    # Payment Limits - حدود الدفع
    min_donation_amount = db.Column(
        db.Numeric(10, 2), default=Decimal("10.00")
    )  # الحد الأدنى
    max_donation_amount = db.Column(
        db.Numeric(10, 2), default=Decimal("10000.00")
    )  # الحد الأقصى
    daily_limit = db.Column(
        db.Numeric(15, 2), default=Decimal("50000.00")
    )  # الحد اليومي

    # Azad Donation Page — controlled from secret vault
    donations_enabled = db.Column(db.Boolean, default=False)
    donation_page_enabled = db.Column(db.Boolean, default=False)
    donation_title_ar = db.Column(db.String(200), default="ادعم شركة أزاد")
    donation_title_en = db.Column(db.String(200), default="Support Azad Systems")
    donation_intro_ar = db.Column(db.Text)
    donation_intro_en = db.Column(db.Text)
    donation_debit_account = db.Column(db.String(20), default="1120")
    donation_credit_account = db.Column(db.String(20), default="4200")

    # Security Settings - إعدادات الأمان
    require_2fa = db.Column(db.Boolean, default=True)  # يتطلب مصادقة ثنائية
    auto_lock_minutes = db.Column(db.Integer, default=30)  # قفل تلقائي بعد دقائق
    max_failed_attempts = db.Column(db.Integer, default=3)  # محاولات فاشلة
    failed_attempts = db.Column(db.Integer, default=0)  # عدد المحاولات الفاشلة

    created_at = db.Column(db.DateTime, default=_utc_now, index=True)
    updated_at = db.Column(
        db.DateTime, default=_utc_now, onupdate=_utc_now
    )

    @classmethod
    def get_platform_vault(cls):
        """Return the Azad/platform vault."""
        return cls.query.filter(cls.tenant_id.is_(None)).order_by(cls.id.asc()).first()

    @classmethod
    def get_tenant_vault(cls, tenant_id):
        """Return the vault for a concrete project/tenant."""
        if tenant_id is None:
            return None
        return (
            cls.query.filter_by(tenant_id=int(tenant_id)).order_by(cls.id.asc()).first()
        )

    def set_vault_password(self, password):
        """تعيين كلمة مرور الخزينة"""
        self.vault_password_hash = generate_password_hash(
            password, method="pbkdf2:sha256"
        )

    def check_vault_password(self, password):
        """التحقق من كلمة مرور الخزينة"""
        return check_password_hash(self.vault_password_hash, password)

    def unlock_vault(self, password):
        """فتح الخزينة"""
        if self.check_vault_password(password):
            self.is_locked = False
            self.last_access = _utc_now()
            self.failed_attempts = 0
            db.session.flush()
            return True
        else:
            self.failed_attempts = (self.failed_attempts or 0) + 1
            db.session.flush()
            return False

    def lock_vault(self):
        """قفل الخزينة"""
        self.is_locked = True
        db.session.flush()

    def is_vault_accessible(self):
        """التحقق من إمكانية الوصول للخزينة"""
        if self.is_locked:
            return False

        # التحقق من انتهاء صلاحية الجلسة
        if self.auto_lock_minutes > 0:
            time_diff = _utc_now() - self.last_access
            if time_diff.total_seconds() > (self.auto_lock_minutes * 60):
                self.lock_vault()
                return False

        return True

    def reset_failed_attempts(self):
        """إعادة تعيين المحاولات الفاشلة"""
        self.failed_attempts = 0
        db.session.flush()

    def is_locked_out(self):
        """التحقق من القفل بسبب المحاولات الفاشلة"""
        return (self.failed_attempts or 0) >= self.max_failed_attempts


class PaymentTransaction(db.Model):
    """
    معاملات الدفع - محمية داخل الخزينة
    """

    __tablename__ = "payment_transactions"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    transaction_id = db.Column(
        db.String(100), unique=True, nullable=False
    )  # معرف المعاملة
    amount_usd = db.Column(db.Numeric(15, 2), nullable=False)  # المبلغ بالدولار
    amount_crypto = db.Column(db.Numeric(20, 8))  # المبلغ بالعملة الرقمية
    crypto_currency = db.Column(db.String(10), nullable=False)  # العملة الرقمية

    # Payment Details - تفاصيل الدفع
    payment_address = db.Column(db.String(255))  # عنوان الدفع
    payment_status = db.Column(db.String(20), default="pending")  # حالة الدفع
    payment_method = db.Column(db.String(50), default="crypto")  # طريقة الدفع

    # Customer Info - معلومات العميل
    customer_email = db.Column(db.String(255))  # إيميل العميل
    customer_name = db.Column(db.String(255))  # اسم العميل
    customer_phone = db.Column(db.String(50))  # هاتف العميل

    # Security - الأمان
    ip_address = db.Column(db.String(50))  # عنوان IP
    user_agent = db.Column(db.String(500))  # User Agent
    is_verified = db.Column(db.Boolean, default=False)  # هل تم التحقق

    created_at = db.Column(db.DateTime, default=_utc_now, index=True)
    updated_at = db.Column(
        db.DateTime, default=_utc_now, onupdate=_utc_now
    )
    completed_at = db.Column(db.DateTime)  # وقت الإكمال

    vault_id = db.Column(
        db.Integer, db.ForeignKey("payment_vault.id"), nullable=False, index=True
    )
    vault = db.relationship("PaymentVault", backref="transactions")
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

    def to_dict(self):
        """تحويل إلى قاموس"""
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "amount_usd": float(self.amount_usd),
            "amount_crypto": float(self.amount_crypto) if self.amount_crypto else None,
            "crypto_currency": self.crypto_currency,
            "payment_address": self.payment_address,
            "payment_status": self.payment_status,
            "payment_method": self.payment_method,
            "customer_email": self.customer_email,
            "customer_name": self.customer_name,
            "is_verified": self.is_verified,
            "created_at": self.created_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }


class PaymentLog(db.Model):
    """
    سجل الدفع - محمي داخل الخزينة
    """

    __tablename__ = "payment_logs"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Log Info - معلومات السجل
    action = db.Column(db.String(100), nullable=False)  # العملية
    description = db.Column(db.Text)  # الوصف
    level = db.Column(db.String(20), default="info")  # مستوى السجل

    # Transaction Reference - مرجع المعاملة
    transaction_id = db.Column(db.String(100))  # معرف المعاملة
    amount = db.Column(db.Numeric(15, 2))  # المبلغ

    # Security - الأمان
    ip_address = db.Column(db.String(50))  # عنوان IP
    user_agent = db.Column(db.String(500))  # User Agent

    created_at = db.Column(db.DateTime, default=_utc_now, index=True)

    vault_id = db.Column(
        db.Integer, db.ForeignKey("payment_vault.id"), nullable=False, index=True
    )
    vault = db.relationship("PaymentVault", backref="logs")
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

    @staticmethod
    def log_action(
        vault_id,
        action,
        description,
        level="info",
        transaction_id=None,
        amount=None,
        ip_address=None,
        user_agent=None,
        tenant_id=None,
    ):
        """تسجيل عمل"""
        log = PaymentLog(
            vault_id=vault_id,
            tenant_id=tenant_id,
            action=action,
            description=description,
            level=level,
            transaction_id=transaction_id,
            amount=amount,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.session.add(log)
        db.session.flush()
        return log
