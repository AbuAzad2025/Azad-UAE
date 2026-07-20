"""Platform-wide payment methods for tenant online stores."""

from datetime import datetime, timezone
import json
import re

from extensions import db

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


class StorePaymentMethod(db.Model):
    __tablename__ = "store_payment_methods"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name_ar = db.Column(db.String(120), nullable=False)
    name_en = db.Column(db.String(120), nullable=False)
    description_ar = db.Column(db.Text)
    description_en = db.Column(db.Text)
    icon = db.Column(db.String(80), default="fas fa-money-bill-wave")
    is_enabled = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_builtin = db.Column(db.Boolean, default=False, nullable=False)
    sort_order = db.Column(db.Integer, default=100, nullable=False)
    config_json = db.Column(db.Text)
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

    def get_config(self) -> dict:
        if not self.config_json:
            return {}
        try:
            data = json.loads(self.config_json)
            return data if isinstance(data, dict) else {}
        except (TypeError, ValueError):
            return {}

    def set_config(self, data: dict):
        self.config_json = json.dumps(data or {}, ensure_ascii=False)

    def display_name(self, lang="ar") -> str:
        if lang == "en" and self.name_en:
            return self.name_en
        return self.name_ar or self.name_en or self.code

    def display_description(self, lang="ar") -> str:
        if lang == "en" and self.description_en:
            return self.description_en
        return self.description_ar or self.description_en or ""

    @staticmethod
    def normalize_code(raw: str) -> str:
        code = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not CODE_PATTERN.match(code):
            raise ValueError("رمز طريقة الدفع: حروف إنجليزية صغيرة وأرقام وشرطة سفلية فقط.")
        return code

    def __repr__(self):
        return f"<StorePaymentMethod {self.code} enabled={self.is_enabled}>"
