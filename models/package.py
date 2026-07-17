"""
Package model for system packages
"""

from extensions import db
from datetime import datetime


class Package(db.Model):
    """Package model for system subscription packages"""

    __tablename__ = "packages"

    id = db.Column(db.Integer, primary_key=True)
    name_ar = db.Column(db.String(100), nullable=False)  # اسم الباقة بالعربية
    name_en = db.Column(db.String(100), nullable=False)  # اسم الباقة بالإنجليزية
    slug = db.Column(db.String(50), unique=True, nullable=False)  # للرابط
    icon = db.Column(db.String(50), default="📦")  # أيقونة الباقة
    price = db.Column(db.Float, nullable=False)  # السعر بالدولار
    currency = db.Column(db.String(10), default="USD")

    # وصف الباقة
    description_ar = db.Column(db.Text)
    description_en = db.Column(db.Text)

    # الميزات (JSON array)
    features = db.Column(db.JSON, default=list)  # قائمة بالميزات

    # الإعدادات
    is_active = db.Column(db.Boolean, default=True, index=True)  # هل الباقة نشطة
    is_featured = db.Column(db.Boolean, default=False)  # باقة مميزة
    badge_text = db.Column(db.String(50))  # نص الشارة (مثل: الأكثر شعبية)
    badge_color = db.Column(db.String(20), default="primary")  # لون الشارة

    # الترتيب والأولوية
    sort_order = db.Column(db.Integer, default=0)  # ترتيب العرض

    # مدة الدعم الفني
    support_duration_months = db.Column(db.Integer, default=3)

    # الصلاحيات والحدود
    max_users = db.Column(db.Integer)  # عدد المستخدمين
    max_branches = db.Column(db.Integer)  # عدد الفروع
    has_ai = db.Column(db.Boolean, default=False)  # ذكاء اصطناعي
    has_whatsapp = db.Column(db.Boolean, default=False)  # تكامل واتساب
    has_pos = db.Column(db.Boolean, default=False)  # نقاط البيع
    has_advanced_reports = db.Column(db.Boolean, default=False)  # تقارير متقدمة
    has_customization = db.Column(db.Boolean, default=False)  # تخصيص
    has_training = db.Column(db.Boolean, default=False)  # تدريب
    has_priority_support = db.Column(db.Boolean, default=False)  # دعم أولوية

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<Package {self.name_ar}>"

    def to_dict(self):
        """Convert package to dictionary"""
        return {
            "id": self.id,
            "name_ar": self.name_ar,
            "name_en": self.name_en,
            "slug": self.slug,
            "icon": self.icon,
            "price": self.price,
            "currency": self.currency,
            "description_ar": self.description_ar,
            "description_en": self.description_en,
            "features": self.features,
            "is_active": self.is_active,
            "is_featured": self.is_featured,
            "badge_text": self.badge_text,
            "badge_color": self.badge_color,
            "sort_order": self.sort_order,
            "support_duration_months": self.support_duration_months,
            "max_users": self.max_users,
            "max_branches": self.max_branches,
            "has_ai": self.has_ai,
            "has_whatsapp": self.has_whatsapp,
            "has_pos": self.has_pos,
            "has_advanced_reports": self.has_advanced_reports,
            "has_customization": self.has_customization,
            "has_training": self.has_training,
            "has_priority_support": self.has_priority_support,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PackagePurchase(db.Model):
    """Model for package purchases"""

    __tablename__ = "package_purchases"

    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(
        db.Integer, db.ForeignKey("packages.id"), nullable=False, index=True
    )

    # بيانات المشتري
    customer_name = db.Column(db.String(200), nullable=False)
    customer_email = db.Column(db.String(200), nullable=False)
    customer_phone = db.Column(db.String(50))
    company_name = db.Column(db.String(200))

    # بيانات الدفع
    payment_method = db.Column(
        db.String(50), nullable=False
    )  # crypto, card, paypal, bank
    payment_status = db.Column(
        db.String(50), default="pending"
    )  # pending, completed, failed, refunded
    amount_paid = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="USD")

    # معلومات إضافية للدفع
    transaction_id = db.Column(db.String(200))
    payment_details = db.Column(db.JSON)  # تفاصيل إضافية

    # الحالة
    activation_status = db.Column(
        db.String(50), default="pending"
    )  # pending, activated, expired
    activation_date = db.Column(db.DateTime)
    expiry_date = db.Column(db.DateTime)

    # ملاحظات
    notes = db.Column(db.Text)

    # ربط العملية المالية بالمستأجر
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), nullable=True, index=True
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # العلاقات
    package = db.relationship("Package", backref="purchases")
    tenant = db.relationship("Tenant", backref="package_purchases")

    def __repr__(self):
        return f"<PackagePurchase {self.customer_email} - {self.package.name_ar if self.package else 'N/A'}>"

    def to_dict(self):
        """Convert purchase to dictionary"""
        return {
            "id": self.id,
            "package_id": self.package_id,
            "tenant_id": self.tenant_id,
            "package_name": self.package.name_ar if self.package else None,
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "customer_phone": self.customer_phone,
            "company_name": self.company_name,
            "payment_method": self.payment_method,
            "payment_status": self.payment_status,
            "amount_paid": self.amount_paid,
            "currency": self.currency,
            "transaction_id": self.transaction_id,
            "activation_status": self.activation_status,
            "activation_date": (
                self.activation_date.isoformat() if self.activation_date else None
            ),
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
