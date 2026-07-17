"""
PalestineStrategy — 16% VAT, multi-currency (ILS/JOD/USD), PMA XML, WPS SIF.
"""

import re
from decimal import Decimal, ROUND_HALF_UP

from .engine import LocalizationStrategy, coerce_decimal

_VAT_ID_PATTERN = re.compile(r"^\d{9,11}$")
_TWO_PLACES = Decimal("0.01")
_SUPPORTED_CURRENCIES = frozenset({"ILS", "JOD", "USD"})


class PalestineStrategy(LocalizationStrategy):
    country_code = "PS"
    country_name = "Palestine"
    default_vat_rate = Decimal("16.00")
    currency = "ILS"
    supports_wps = True

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

    def convert_to_local_currency(
        self, amount, from_currency: str, to_currency: str | None = None
    ):
        target = (to_currency or self.currency).upper()
        source = (from_currency or self.currency).upper()
        if source not in _SUPPORTED_CURRENCIES and source != target:
            raise ValueError(f"Unsupported source currency for Palestine: {source}")
        if source == target:
            return Decimal(str(amount))
        from utils.helpers import convert_currency

        return Decimal(str(convert_currency(amount, source, target))).quantize(
            _TWO_PLACES,
            rounding=ROUND_HALF_UP,
        )

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
            "format": "pma_xml_v1",
            "currency": self.currency,
        }

    def validate_tax_number(self, tax_number: str) -> bool:
        if not tax_number:
            return False
        cleaned = re.sub(r"\D", "", str(tax_number).strip())
        return bool(_VAT_ID_PATTERN.match(cleaned))

    def generate_einvoice(self, sale) -> dict:
        rate = self._resolve_vat_rate(sale)
        total = self._sale_total(sale)
        tax = (
            (total * rate / (Decimal("100") + rate)).quantize(
                _TWO_PLACES,
                rounding=ROUND_HALF_UP,
            )
            if rate > 0
            else Decimal("0")
        )
        xml = f"""<Invoice>
  <Country>PS</Country>
  <TaxRate>{rate}</TaxRate>
  <TaxAmount>{tax}</TaxAmount>
  <Total>{total}</Total>
</Invoice>"""
        return {
            "xml_payload": xml,
            "qr_base64": "",
            "invoice_hash": "",
            "format": "pma_mof_xml",
        }

    def get_wps_format(self, employees: list) -> dict:
        lines = [
            "HDR|EmployeeID|BankCode|Name|IBAN|NetSalary",
        ]
        for emp in employees:
            lines.append(
                f"EDR|{emp.get('employee_id', '')}|{emp.get('bank_code', '')}|"
                f"{emp.get('name', '')}|{emp.get('iban', '')}|"
                f"{emp.get('net_salary', 0)}"
            )
        return {
            "format": "wps_sif",
            "file_extension": ".sif",
            "lines": lines,
            "encoding": "utf-8",
            "record_count": len(employees),
        }
