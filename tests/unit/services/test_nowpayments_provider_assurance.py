"""NOWPayments provider — config surface and webhook URL builder."""
from __future__ import annotations

import pytest


class TestNowPaymentsProvider:
    def test_config_from_app(self, app):
        app.config.update(
            NOWPAYMENTS_API_KEY='key-123',
            NOWPAYMENTS_IPN_SECRET='secret',
            BASE_URL='https://erp.example.com/',
        )
        from services.payments.nowpayments_provider import NowPaymentsProvider
        with app.app_context():
            provider = NowPaymentsProvider()
            assert provider.api_key == 'key-123'
            assert provider.ipn_secret == 'secret'
            assert provider.base_url == 'https://erp.example.com'
            assert provider.is_configured() is True
            assert provider.build_webhook_url().endswith('/payment-vault/webhook/nowpayments')
            assert 'x-api-key' in provider.headers()

    def test_defaults_when_unconfigured(self, app):
        from services.payments.nowpayments_provider import NowPaymentsProvider
        with app.app_context():
            provider = NowPaymentsProvider()
            assert provider.is_configured() is False
            assert provider.api_base == 'https://api.nowpayments.io/v1'
            assert provider.timeout == 30
            assert provider.is_sandbox is False
            assert 'btc' in provider.supported_cryptos

    def test_all_properties(self, app):
        from services.payments.nowpayments_provider import NowPaymentsProvider
        with app.app_context():
            p = NowPaymentsProvider()
            _ = p.api_key, p.ipn_secret, p.api_base, p.timeout, p.is_sandbox, p.min_donation_amount
            assert p.supported_cryptos
