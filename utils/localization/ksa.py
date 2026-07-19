"""
KSAStrategy — 15% VAT (configurable), ZATCA Phase 2 simplified invoice QR.
"""

import base64
import hashlib
import re
from decimal import Decimal, ROUND_HALF_UP

from .engine import LocalizationStrategy, coerce_decimal

_TRN_PATTERN = re.compile(r"^3\d{14}$")
_TWO_PLACES = Decimal("0.01")


class KSAStrategy(LocalizationStrategy):
    country_code = "SA"
    country_name = "Saudi Arabia"
    default_vat_rate = Decimal("15.00")
    currency = "SAR"
    supports_qr = True
    zatca_phase = 2

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

    @staticmethod
    def _extract_tax_from_inclusive(
        total: Decimal, rate: Decimal
    ) -> tuple[Decimal, Decimal]:
        total = Decimal(str(total))
        rate = Decimal(str(rate))
        if rate <= 0:
            return total, Decimal("0")
        net = (total / (Decimal("1") + rate / Decimal("100"))).quantize(
            _TWO_PLACES,
            rounding=ROUND_HALF_UP,
        )
        tax = (total - net).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        return net, tax

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
        tax = (amount * rate / Decimal("100")).quantize(
            _TWO_PLACES, rounding=ROUND_HALF_UP
        )
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

    @staticmethod
    def sign_zatca_payload(payload: str) -> str:
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return digest

    def generate_einvoice(self, sale) -> dict:
        rate = self._resolve_vat_rate(sale)
        total = self._sale_total(sale)
        net, tax = self._extract_tax_from_inclusive(total, rate)
        issue_date = sale.sale_date if hasattr(sale, "sale_date") else ""
        xml = f"""<Invoice>
  <ID>{sale.id}</ID>
  <IssueDate>{issue_date}</IssueDate>
  <TaxTotal><TaxAmount currencyID="SAR">{tax}</TaxAmount></TaxTotal>
  <LegalMonetaryTotal>
    <TaxExclusiveAmount currencyID="SAR">{net}</TaxExclusiveAmount>
    <TaxInclusiveAmount currencyID="SAR">{total}</TaxInclusiveAmount>
  </LegalMonetaryTotal>
</Invoice>"""
        qr_data = f"ZATCA|{rate}|{total}|{sale.id}"
        qr_b64 = base64.b64encode(qr_data.encode()).decode()
        invoice_hash = self.sign_zatca_payload(xml)
        return {
            "xml_payload": xml,
            "qr_base64": qr_b64,
            "invoice_hash": invoice_hash,
            "format": "zatca_simplified_xml",
        }
