from decimal import Decimal
from flask import current_app


class NowPaymentsProvider:
    def __init__(self, app=None):
        self._app = app

    def _cfg(self, key, default=None):
        app = self._app or current_app
        return app.config.get(key, default)

    @property
    def api_key(self):
        return self._cfg("NOWPAYMENTS_API_KEY", "")

    @property
    def ipn_secret(self):
        return self._cfg("NOWPAYMENTS_IPN_SECRET", "")

    @property
    def api_base(self):
        return "https://api.nowpayments.io/v1"

    @property
    def timeout(self):
        return 30

    @property
    def is_sandbox(self):
        return False

    @property
    def min_donation_amount(self):
        return Decimal("10")

    @property
    def supported_cryptos(self):
        return ["btc", "eth", "usdt", "usdc", "bnb"]

    @property
    def base_url(self):
        return (self._cfg("BASE_URL") or "http://localhost:5000").rstrip("/")

    def build_webhook_url(self):
        return f"{self.base_url}/payment-vault/webhook/nowpayments"

    def is_configured(self):
        return bool(self.api_key)

    def headers(self):
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }
