import os

NOWPAYMENTS_API_KEY = os.environ.get("NOWPAYMENTS_API_KEY", "")
NOWPAYMENTS_IPN_SECRET = os.environ.get("NOWPAYMENTS_IPN_SECRET", "")

port = os.environ.get("PORT", "5000")
BASE_URL = f"http://localhost:{port}"

MIN_DONATION_AMOUNT = 10
SUPPORTED_CRYPTOS = ['btc', 'eth', 'usdt', 'usdc', 'bnb']
