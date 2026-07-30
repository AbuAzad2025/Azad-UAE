"""Single source of truth for regional fallback values (multi-country SaaS).

Every module that needs a regional default when tenant/system data is missing
MUST import from here — never hardcode a country, currency, VAT country, or
timezone literal. All values are deployment-configurable via environment:

    DEFAULT_CURRENCY      (default "ILS")
    DEFAULT_COUNTRY       (default "PS")
    DEFAULT_VAT_COUNTRY   (default: falls back to DEFAULT_COUNTRY)
    DEFAULT_TIMEZONE      (default "Asia/Dubai")

Historical note: the codebase previously scattered conflicting literals
("ILS"/"AED", "PS"/"AE", "Asia/Hebron"/"Asia/Dubai") across config.py,
models/tenant.py, utils/tax_settings.py and utils/tenant_branding.py, so a
tenant with missing fields could see a mixed regional identity. This module
ends that drift.
"""

import os

__all__ = [
    "FALLBACK_CURRENCY",
    "FALLBACK_COUNTRY",
    "FALLBACK_VAT_COUNTRY",
    "FALLBACK_TIMEZONE",
]


def _env(key: str, default: str) -> str:
    val = (os.environ.get(key) or "").strip()
    return val or default


FALLBACK_CURRENCY = _env("DEFAULT_CURRENCY", "ILS").upper()
FALLBACK_COUNTRY = _env("DEFAULT_COUNTRY", "PS")
FALLBACK_VAT_COUNTRY = _env("DEFAULT_VAT_COUNTRY", FALLBACK_COUNTRY).upper()
FALLBACK_TIMEZONE = _env("DEFAULT_TIMEZONE", "Asia/Dubai")
