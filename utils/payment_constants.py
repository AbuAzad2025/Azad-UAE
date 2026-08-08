"""Payment method constants and normalization."""

PAYMENT_METHOD_ALIASES = {
    "cash": "cash",
    "cash_mobile": "cash",
    "card": "card",
    "credit_card": "card",
    "debit_card": "card",
    "bank": "bank_transfer",
    "bank_transfer": "bank_transfer",
    "transfer": "bank_transfer",
    "wire": "bank_transfer",
    "cheque": "cheque",
    "check": "cheque",
    "e_wallet": "e_wallet",
    "wallet": "e_wallet",
    "digital_wallet": "e_wallet",
    "apple_pay": "e_wallet",
    "google_pay": "e_wallet",
    "samsung_pay": "e_wallet",
    "crypto": "crypto",
    "bitcoin": "crypto",
    "ethereum": "crypto",
    "usdt": "crypto",
    "crypto_currency": "crypto",
    "other": "other",
    "other_method": "other",
}


def normalize_payment_method_code(method):
    """Normalize legacy payment method codes to canonical values."""
    if method is None:
        return method
    value = str(method).strip().lower()
    return PAYMENT_METHOD_ALIASES.get(value, value)