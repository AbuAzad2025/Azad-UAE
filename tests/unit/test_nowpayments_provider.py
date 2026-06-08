from decimal import Decimal
from unittest.mock import patch


class TestNowPaymentsProvider:
    def test_api_key_reads_from_config(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider()
            assert provider.api_key == app.config.get("NOWPAYMENTS_API_KEY", "")

    def test_ipn_secret_reads_from_config(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider()
            assert provider.ipn_secret == app.config.get("NOWPAYMENTS_IPN_SECRET", "")

    def test_api_base_is_production(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider()
            assert provider.api_base == "https://api.nowpayments.io/v1"

    def test_timeout_default(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider()
            assert provider.timeout == 30

    def test_is_sandbox_false(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider()
            assert provider.is_sandbox is False

    def test_min_donation_amount(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider()
            assert provider.min_donation_amount == Decimal("10")

    def test_supported_cryptos(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider()
            assert provider.supported_cryptos == ["btc", "eth", "usdt", "usdc", "bnb"]

    def test_base_url_fallback(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider()
            assert provider.base_url.startswith("http")

    def test_build_webhook_url(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider()
            url = provider.build_webhook_url()
            assert "/payment-vault/webhook/nowpayments" in url

    def test_is_configured_false_when_no_key(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider()
            if not provider.api_key:
                assert provider.is_configured() is False

    def test_is_configured_true_when_key_set(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider(app=app)
            with patch.object(app, "config", {"NOWPAYMENTS_API_KEY": "test_key_123"}):
                assert provider.is_configured() is True

    def test_headers_structure(self, app):
        with app.app_context():
            from services.payments.nowpayments_provider import NowPaymentsProvider
            provider = NowPaymentsProvider()
            headers = provider.headers()
            assert "x-api-key" in headers
            assert "Content-Type" in headers

    def test_explicit_app_override(self, app):
        from flask import Flask
        test_app = Flask(__name__)
        test_app.config["NOWPAYMENTS_API_KEY"] = "override_key"
        from services.payments.nowpayments_provider import NowPaymentsProvider
        provider = NowPaymentsProvider(app=test_app)
        assert provider.api_key == "override_key"
