"""Store notifications — email/WhatsApp dispatch, templates, tenant isolation."""

from __future__ import annotations

from unittest.mock import MagicMock


def _sale_and_store():
    line = MagicMock()
    line.product = MagicMock()
    line.product.name = "Item A"
    line.product_id = 1
    line.quantity = 2
    customer = MagicMock(phone="0501234567")
    customer.name = "Ali"
    sale = MagicMock(
        id=99,
        sale_number="SO-99",
        customer=customer,
        lines=[line],
        checkout_payment_method="online_pay",
        total_amount=250,
        currency="AED",
    )
    store = MagicMock(
        title="My Store",
        email="owner@store.com",
        notify_email_on_order=True,
        notify_whatsapp_on_order=True,
        whatsapp="+971501234567",
        phone=None,
    )
    return sale, store


class TestOrderSummary:
    """_order_summary / _safe_log_text — template assembly."""

    def test_arabic_summary_includes_customer_and_items(self):
        sale, store = _sale_and_store()
        from services.store_notification_service import StoreNotificationService

        text = StoreNotificationService._order_summary(sale, store, "ar")
        assert "طلب جديد" in text
        assert "SO-99" in text
        assert "Item A" in text

    def test_english_summary_fallback(self):
        sale, store = _sale_and_store()
        from services.store_notification_service import StoreNotificationService

        text = StoreNotificationService._order_summary(sale, store, "en")
        assert "New order" in text
        assert "Payment:" in text

    def test_safe_log_text_strips_non_ascii(self):
        from services.store_notification_service import StoreNotificationService

        assert "?" in StoreNotificationService._safe_log_text("مرحبا")

    def test_safe_log_text_none_returns_empty(self):
        from services.store_notification_service import StoreNotificationService

        assert StoreNotificationService._safe_log_text(None) == ""


class TestEmailDispatch:
    """notify_new_order — email channel triggers and fallbacks."""

    def test_skips_when_mail_not_configured(self, app, mocker):
        sale, store = _sale_and_store()
        app.config.pop("MAIL_USERNAME", None)
        app.config.pop("MAIL_PASSWORD", None)
        with app.app_context():
            from flask import current_app

            logger = MagicMock()
            mocker.patch.object(current_app, "logger", logger)
            from services.store_notification_service import StoreNotificationService

            StoreNotificationService.notify_new_order(sale, store)
        skip_calls = [c for c in logger.info.call_args_list if c.args and "mail not configured" in str(c.args[0])]
        assert skip_calls

    def test_skips_when_notify_email_disabled(self, app, mocker):
        sale, store = _sale_and_store()
        store.notify_email_on_order = False
        mock_mail = mocker.patch("services.store_notification_service.mail", create=True)
        mocker.patch("services.store_notification_service.current_app").logger = MagicMock()

        from services.store_notification_service import StoreNotificationService

        with app.app_context():
            StoreNotificationService.notify_new_order(sale, store)
        mock_mail.send.assert_not_called()

    def test_skips_when_no_valid_recipient(self, app, mocker):
        sale, store = _sale_and_store()
        store.email = "not-an-email"
        mocker.patch("services.store_notification_service.current_app").logger = MagicMock()

        from services.store_notification_service import StoreNotificationService

        with app.app_context():
            StoreNotificationService.notify_new_order(sale, store)

    def test_sends_email_when_mail_configured(self, app, mocker):
        sale, store = _sale_and_store()
        app.config["MAIL_USERNAME"] = "user"
        app.config["MAIL_PASSWORD"] = "pass"
        mock_mail = MagicMock()
        mocker.patch("extensions.mail", mock_mail)
        mocker.patch("flask_mail.Message")
        mocker.patch(
            "flask.url_for",
            return_value="https://app/store/admin/orders/99",
        )

        from services.store_notification_service import StoreNotificationService

        with app.app_context():
            StoreNotificationService.notify_new_order(sale, store)
        mock_mail.send.assert_called_once()

    def test_mail_failure_logged_not_raised(self, app, mocker):
        sale, store = _sale_and_store()
        app.config["MAIL_USERNAME"] = "u"
        app.config["MAIL_PASSWORD"] = "p"
        mock_mail = MagicMock()
        mock_mail.send.side_effect = RuntimeError("smtp down")
        mocker.patch("extensions.mail", mock_mail)
        mocker.patch("flask_mail.Message")
        mocker.patch(
            "flask.url_for",
            side_effect=Exception("no route"),
        )

        from flask import current_app
        from services.store_notification_service import StoreNotificationService

        with app.app_context():
            logger = MagicMock()
            mocker.patch.object(current_app, "logger", logger)
            StoreNotificationService.notify_new_order(sale, store)
        logger.warning.assert_called()


class TestWhatsAppLink:
    """whatsapp_admin_link — SMS-style deep link per store."""

    def test_returns_none_when_disabled(self):
        sale, store = _sale_and_store()
        store.notify_whatsapp_on_order = False
        from services.store_notification_service import StoreNotificationService

        assert StoreNotificationService.whatsapp_admin_link(sale, store) is None

    def test_builds_wa_me_link_with_encoded_text(self):
        sale, store = _sale_and_store()
        from services.store_notification_service import StoreNotificationService

        link = StoreNotificationService.whatsapp_admin_link(sale, store)
        assert link.startswith("https://wa.me/971501234567")
        assert "text=" in link

    def test_no_phone_returns_none(self):
        sale, store = _sale_and_store()
        store.whatsapp = ""
        store.phone = ""
        from services.store_notification_service import StoreNotificationService

        assert StoreNotificationService.whatsapp_admin_link(sale, store) is None
