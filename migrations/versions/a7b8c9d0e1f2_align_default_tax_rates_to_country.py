"""Align tenants' placeholder VAT rates to their country's statutory rate.

Tenant.default_tax_rate was created with a hardcoded 5.00 (the UAE rate)
regardless of the tenant's vat_country, so a PS/IL/SA tenant that never
customised its rate invoices at 5% instead of its country's statutory
16/17/15%. This revision backfills only tenants still on the placeholder
(5.00) whose vat_country is not AE; tenants with a deliberately customised
rate are untouched. Rates come from utils/country_tax.py (single source of
truth) at upgrade time.

Revision ID: a7b8c9d0e1f2
Revises: d7e8f9a0b1c2
"""

from alembic import op
from sqlalchemy import text

revision = "a7b8c9d0e1f2"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None

_PLACEHOLDER = "5.00"


def _country_rates() -> dict:
    from utils.country_tax import COUNTRY_TAX_PROFILES

    return {code: str(p["vat_rate"]) for code, p in COUNTRY_TAX_PROFILES.items()}


def upgrade():
    rates = _country_rates()
    for code, rate in rates.items():
        if code == "AE":
            continue
        op.execute(
            text(
                "UPDATE tenants SET default_tax_rate = :rate "
                "WHERE default_tax_rate = :placeholder AND vat_country = :code"
            ).bindparams(rate=rate, placeholder=_PLACEHOLDER, code=code)
        )


def downgrade():
    # Restore the placeholder for the same rows upgrade() touched.
    rates = _country_rates()
    for code in rates:
        if code == "AE":
            continue
        op.execute(
            text(
                "UPDATE tenants SET default_tax_rate = :placeholder "
                "WHERE vat_country = :code AND default_tax_rate = :rate"
            ).bindparams(placeholder=_PLACEHOLDER, code=code, rate=rates[code])
        )
