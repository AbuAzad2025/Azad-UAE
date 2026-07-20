"""
Integration Settings Model
نموذج إعدادات التكاملات الخارجية (WhatsApp, Email, Redis, APIs)
"""

from datetime import datetime, timezone
from extensions import db
import json


class IntegrationSettings(db.Model):
    """
    إعدادات التكاملات الخارجية - قابلة للتعديل من لوحة المالك
    كل تكامل (service) له سجل منفصل
    """

    __tablename__ = "integration_settings"
    __table_args__ = (db.UniqueConstraint("tenant_id", "service_name", name="uq_integration_settings_tenant_service"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    service_name = db.Column(db.String(50), nullable=False, index=True)

    # Enable/Disable - تفعيل/تعطيل
    enabled = db.Column(db.Boolean, default=False)

    config_data = db.Column(db.Text)  # JSON for flexibility

    last_tested_at = db.Column(db.DateTime)  # آخر اختبار
    last_test_status = db.Column(db.String(20))  # success, failed
    last_test_message = db.Column(db.Text)  # رسالة الاختبار

    # Meta
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)

    user = db.relationship("User", foreign_keys=[updated_by])
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<IntegrationSettings {self.service_name} {'✅' if self.enabled else '❌'}>"

    @staticmethod
    def get_service_config(service_name, tenant_id=None):
        """
        الحصول على إعدادات خدمة معينة
        """
        q = IntegrationSettings.query.filter_by(service_name=service_name)
        if tenant_id is not None:
            q = q.filter_by(tenant_id=tenant_id)
        integration = q.first()
        if not integration:
            # إنشاء سجل جديد بإعدادات افتراضية
            integration = IntegrationSettings(
                service_name=service_name,
                tenant_id=tenant_id,
                enabled=False,
                config_data=json.dumps({}, ensure_ascii=False),
            )
            db.session.add(integration)
            db.session.flush()
        return integration

    def get_config(self):
        """
        الحصول على البيانات المخزنة كـ dict
        """
        if self.config_data:
            try:
                return json.loads(self.config_data)
            except Exception:
                return {}
        return {}

    def set_config(self, config_dict):
        """
        حفظ البيانات كـ JSON
        """
        self.config_data = json.dumps(config_dict, ensure_ascii=False)

    def get_value(self, key, default=None):
        """
        الحصول على قيمة معينة من الإعدادات
        """
        config = self.get_config()
        return config.get(key, default)

    def set_value(self, key, value):
        """
        حفظ قيمة معينة
        """
        config = self.get_config()
        config[key] = value
        self.set_config(config)

    def to_dict(self):
        return {
            "id": self.id,
            "service_name": self.service_name,
            "enabled": self.enabled,
            "config": self.get_config(),
            "last_tested_at": (self.last_tested_at.isoformat() if self.last_tested_at else None),
            "last_test_status": self.last_test_status,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
