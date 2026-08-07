"""Payment method normalization utilities."""

from utils.constants import PAYMENT_METHOD_ALIASES


def normalize_payment_method_code(method):
    """Normalize legacy payment method codes to canonical values."""
    if method is None:
        return method
    value = str(method).strip().lower()
    from utils.constants import PAYMENT_METHOD_ALIASES
    return PAYMENT_METHOD_ALIASES.get(value, value)