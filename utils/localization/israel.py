"""
IsraelStrategy — 18% VAT, ILS, Israeli Tax Authority VAT report, 9-digit ID.

VAT and corporate rates come from utils/country_tax.py (single source of
truth); this strategy only carries the e-invoice/report formatting for IL.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

from utils.country_tax import vat_rate_for_country

from .engine import LocalizationStrategy, coerce_decimal

_VAT_ID_PATTERN = re.compile(r"^\d{9}$")
_TWO_PLACES = Decimal("0.01")


class IsraelStrategy(LocalizationStrategy):
    country_code = "IL"
    country_name = "Israel"
    default_vat_rate = vat_rate_for_country("IL")
    currency = "ILS"

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
        return {
            "tax_amount": tax,
            "net_amount": amount,
            "total_amount": amount + tax,
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
            "format": "il_vat_v1",
            "currency": self.currency,
        }

    def validate_tax_number(self, tax_number: str) -> bool:
        if not tax_number:
            return False
        cleaned = re.sub(r"\D", "", str(tax_number).strip())
        return bool(_VAT_ID_PATTERN.match(cleaned))

    def generate_einvoice(self, sale) -> dict:
        from utils.einvoice_document import build_invoice_xml, invoice_sha256_hex, tenant_for_sale

        tenant = tenant_for_sale(sale)
        currency = (getattr(sale, "currency", None) or self.currency).strip() or self.currency
        xml_payload = build_invoice_xml(
            sale,
            tenant,
            country="IL",
            currency=currency,
            profile_id="reporting",
        )
        return {
            "xml_payload": xml_payload,
            "qr_base64": "",
            "invoice_hash": invoice_sha256_hex(xml_payload),
            # Israel requires the allocation number (מספר הקצאה) from the
            # Tax Authority's invoice-allocation API for invoices above the
            # statutory thresholds; the API call happens on submission with
            # the tenant's credentials. This is the document that gets submitted.
            "format": "il_ubl_xml",
        }
