"""
UAEStrategy — 5% VAT, AED-only for tax reporting, FTA XML + QR, WPS SIF.
"""

from decimal import Decimal

from .engine import LocalizationStrategy


class UAEStrategy(LocalizationStrategy):
    country_code = "AE"
    country_name = "UAE"
    default_vat_rate = Decimal("5.00")
    currency = "AED"
    supports_qr = True
    supports_wps = True

    def calculate_tax(self, amount: Decimal, tax_rate: Decimal | None = None) -> dict:
        rate = tax_rate if tax_rate is not None else self.default_vat_rate
        tax = (amount * rate / Decimal("100")).quantize(Decimal("0.01"))
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
        net_payable = output_vat - input_vat
        return {
            "country": self.country_code,
            "output_vat": output_vat,
            "input_vat": input_vat,
            "net_payable": net_payable,
            "period_start": period_start,
            "period_end": period_end,
            "format": "fta_vat201_v1",
            "currency": self.currency,
        }

    def generate_einvoice(self, sale) -> dict:
        total = sale.total_aed if hasattr(sale, "total_aed") else sale.amount_aed
        tax = total * self.default_vat_rate / Decimal("100")
        xml = f"""<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">
  <ID>{sale.id}</ID>
  <TaxTotal><TaxAmount currencyID="AED">{tax}</TaxAmount></TaxTotal>
  <LegalMonetaryTotal><TaxInclusiveAmount currencyID="AED">{total}</TaxInclusiveAmount></LegalMonetaryTotal>
</Invoice>"""
        qr_data = f"VAT:{self.default_vat_rate}|Total:{total}|Sale:{sale.id}"
        import base64

        qr_b64 = base64.b64encode(qr_data.encode()).decode()
        return {
            "xml_payload": xml,
            "qr_base64": qr_b64,
            "invoice_hash": "",
            "format": "fta_ubl_xml",
        }

    def get_wps_format(self, employees: list) -> dict:
        """
        Generate UAE WPS SIF (Salary Information File) in CSV format.

        The UAE WPS SIF follows MOHRE/CPA requirements:
        - Header record: company info, total employees, total amount
        - Employee records: WPS ID, IBAN, bank code, salary details
        - Currency is always AED
        """
        lines = []
        total_amount = Decimal("0")
        record_count = 0

        for emp in employees:
            net = Decimal(str(emp.get("net_salary", 0)))
            total_amount += net
            record_count += 1

            lines.append(
                f"EDR|{emp.get('wps_id', emp.get('employee_id', ''))}|"
                f"{emp.get('iban', '')}|"
                f"{emp.get('bank_code', '')}|"
                f"{emp.get('name', '')}|"
                f"{emp.get('basic_salary', 0)}|"
                f"{emp.get('allowances', 0)}|"
                f"{net}|"
                f"{emp.get('currency', 'AED')}|"
                f"{emp.get('payment_date', '')}"
            )

        header = f"HDR|{self.currency}|{record_count}|{total_amount}|"
        lines.insert(0, header)
        lines.append(f"TRL|{record_count}|{total_amount}")

        content = "\n".join(lines) + "\n"

        return {
            "format": "wps_sif",
            "file_extension": ".csv",
            "content": content,
            "lines": [header] + lines[1:] + [f"TRL|{record_count}|{total_amount}"],
            "encoding": "utf-8",
            "record_count": record_count,
            "total_amount": total_amount,
            "currency": self.currency,
        }
