from datetime import datetime, timezone

import requests
from flask import current_app
from flask_mail import Message

from extensions import mail
from models.integration_settings import IntegrationSettings
from utils.db_safety import atomic_transaction


class IntegrationService:
    TESTABLE_SERVICES = ("email", "currency_api")

    _CURRENCY_PROVIDER_URLS = {
        "exchangerate": "https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}",
        "fixer": "https://data.fixer.io/api/latest?access_key={api_key}&base={base}",
        "currencyapi": "https://api.currencyapi.com/v3/latest?apikey={api_key}&base_currency={base}",
    }

    @staticmethod
    def get_integrations_context():
        whatsapp = IntegrationSettings.get_service_config("whatsapp")
        email = IntegrationSettings.get_service_config("email")
        redis = IntegrationSettings.get_service_config("redis")
        currency_api = IntegrationSettings.get_service_config("currency_api")

        return {
            "whatsapp": {
                "enabled": whatsapp.enabled,
                "config": whatsapp.get_config(),
                "last_tested": whatsapp.last_tested_at,
                "status": whatsapp.last_test_status or "not_configured",
            },
            "email": {
                "enabled": email.enabled,
                "config": email.get_config(),
                "last_tested": email.last_tested_at,
                "status": email.last_test_status or "not_configured",
            },
            "redis": {
                "enabled": redis.enabled,
                "config": redis.get_config(),
                "last_tested": redis.last_tested_at,
                "status": redis.last_test_status or "not_configured",
            },
            "currency_api": {
                "enabled": currency_api.enabled,
                "config": currency_api.get_config(),
                "last_tested": currency_api.last_tested_at,
                "status": currency_api.last_test_status or "not_configured",
            },
        }

    @staticmethod
    def _record_test_result(integration, ok, message):
        """تسجيل نتيجة الاختبار في السجل — كتابة واحدة ذرية."""
        with atomic_transaction(f"integration_test_{integration.service_name}"):
            integration.last_tested_at = datetime.now(timezone.utc)
            integration.last_test_status = "success" if ok else "failed"
            integration.last_test_message = message

    @staticmethod
    def test_email():
        """إرسال رسالة اختبار عبر flask_mail إلى البريد المهيأ. Returns (ok, message)."""
        integration = IntegrationSettings.get_service_config("email")
        config = integration.get_config()
        sender_email = (config.get("from_email") or config.get("smtp_user") or "").strip()
        sender_name = (config.get("from_name") or config.get("sender_name") or "").strip()
        if not sender_email:
            message = "البريد الإلكتروني غير مهيأ — أدخل SMTP Username أو بريد المُرسل أولاً"
            IntegrationService._record_test_result(integration, False, message)
            return False, message
        try:
            msg = Message(
                subject="اختبار الاتصال بالبريد الإلكتروني",
                recipients=[sender_email],
                body="هذه رسالة اختبار من لوحة المالك للتحقق من إعدادات البريد الإلكتروني (SMTP).",
                sender=(sender_name, sender_email) if sender_name else sender_email,
            )
            mail.send(msg)
        except Exception as exc:
            current_app.logger.exception("Integration email test failed")
            IntegrationService._record_test_result(integration, False, str(exc))
            return False, f"فشل إرسال رسالة الاختبار: {exc}"
        message = f"تم إرسال رسالة اختبار إلى {sender_email} بنجاح"
        IntegrationService._record_test_result(integration, True, message)
        return True, message

    @staticmethod
    def _build_currency_test_url(config):
        """بناء رابط الاختبار من الرابط المخزن أو من قالب المزود مع المفتاح والعملة الأساسية."""
        api_url = (config.get("api_url") or "").strip()
        api_key = (config.get("api_key") or "").strip()
        base = (config.get("base_currency") or "USD").strip().upper() or "USD"
        if api_url:
            return api_url.replace("{api_key}", api_key).replace("{base}", base)
        if not api_key:
            return None
        provider = (config.get("api_provider") or "exchangerate").strip()
        template = IntegrationService._CURRENCY_PROVIDER_URLS.get(provider)
        if not template:
            return None
        return template.format(api_key=api_key, base=base)

    @staticmethod
    def test_currency_api():
        """طلب GET خفيف ضد API أسعار الصرف المهيأ. Returns (ok, message)."""
        integration = IntegrationSettings.get_service_config("currency_api")
        config = integration.get_config()
        url = IntegrationService._build_currency_test_url(config)
        if not url:
            message = "API أسعار الصرف غير مهيأ — أدخل API Key أو رابط API أولاً"
            IntegrationService._record_test_result(integration, False, message)
            return False, message
        try:
            response = requests.get(url, timeout=8)
        except Exception as exc:
            current_app.logger.exception("Currency API test request failed")
            IntegrationService._record_test_result(integration, False, str(exc))
            return False, f"فشل الاتصال بخدمة أسعار الصرف: {exc}"
        if response.status_code != 200:
            message = f"استجابة غير ناجحة من الخدمة (HTTP {response.status_code})"
            current_app.logger.warning("Currency API test got HTTP %s", response.status_code)
            IntegrationService._record_test_result(integration, False, message)
            return False, message
        try:
            response.json()
        except ValueError:
            message = "الرد من الخدمة ليس JSON صالحاً"
            current_app.logger.warning("Currency API test returned non-JSON body")
            IntegrationService._record_test_result(integration, False, message)
            return False, message
        message = "تم الاتصال بخدمة أسعار الصرف بنجاح"
        IntegrationService._record_test_result(integration, True, message)
        return True, message
