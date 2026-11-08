"""
KSAStrategy — 15% VAT, ZATCA simplified-invoice UBL 2.1 XML + TLV QR.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

from utils.country_tax import vat_rate_for_country

from .engine import LocalizationStrategy, coerce_decimal

_TRN_PATTERN = re.compile(r"^3\d{14}$")
_TWO_PLACES = Decimal("0.01")


class KSAStrategy(LocalizationStrategy):
    country_code = "SA"
    country_name = "Saudi Arabia"
    default_vat_rate = vat_rate_for_country("SA")
    currency = "SAR"
    supports_qr = True
    # Simplified-invoice QR (TLV tags 1-6) + XML hash — Phase 1 artifact.
    # Phase 2 (CSID-issued signing/stamping) requires the tenant's ZATCA
    # onboarding credentials; do not advertise it until it exists.
    zatca_phase = 1

    def _resolve_vat_rate(self, sale=None, tax_rate: Decimal | None = None) -> Decimal:
        coerced = coerce_decimal(tax_rate)
        if coerced is not None:
            return coerced
        if sale is not None:
            sale_rate = coerce_decimal(getattr(sale, "tax_rate", None))
            if sale_rate is not None:
                return sale_rate
        return self.default_vat_rate

    @staticmethod
    def _sale_total(sale) -> Decimal:
        for attr in ("total_aed", "amount_aed", "total_amount", "amount"):
            amount = coerce_decimal(getattr(sale, attr, None))
            if amount is not None:
                return amount
        return Decimal("0")

    def calculate_tax(self, amount: Decimal, tax_rate: Decimal | None = None) -> dict:
        rate = self._resolve_vat_rate(tax_rate=tax_rate)
        amount = Decimal(str(amount))
        if rate <= 0:
            return {
                "tax_amount": Decimal("0"),
                "net_amount": amount,
                "total_amount": amount,
                "rate_applied": Decimal("0"),
            }
        tax = (amount * rate / Decimal("100")).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        total = amount + tax
        return {
            "tax_amount": tax,
            "net_amount": amount,
            "total_amount": total,
            "rate_applied": rate,
        }

    def format_tax_return(
        self,
        output_vat: Decimal,
        input_vat: Decimal,
        period_start: str,
        period_end: str,
    ) -> dict:
        net_payable = Decimal(str(output_vat)) - Decimal(str(input_vat))
        return {
            "country": self.country_code,
            "output_vat": output_vat,
            "input_vat": input_vat,
            "net_payable": net_payable,
            "period_start": period_start,
            "period_end": period_end,
            "format": "zatca_vat_v3",
            "currency": self.currency,
        }

    def validate_tax_number(self, tax_number: str) -> bool:
        if not tax_number:
            return False
        cleaned = re.sub(r"\D", "", str(tax_number).strip())
        return bool(_TRN_PATTERN.match(cleaned))

    def generate_einvoice(self, sale) -> dict:
        from utils.einvoice_document import tenant_for_sale, zatca_document

        tenant = tenant_for_sale(sale)
        currency = (getattr(sale, "currency", None) or self.currency).strip() or self.currency
        return zatca_document(sale, tenant, currency=currency)
