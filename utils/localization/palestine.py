"""
PalestineStrategy — 16% VAT, multi-currency (ILS/JOD/USD), PMA XML, WPS SIF.
"""

from decimal import Decimal
from .engine import LocalizationStrategy


class PalestineStrategy(LocalizationStrategy):
    country_code = 'PS'
    country_name = 'Palestine'
    default_vat_rate = Decimal('16.00')
    currency = 'ILS'
    supports_wps = True

    def calculate_tax(self, amount: Decimal, tax_rate: Decimal = None) -> dict:
        rate = tax_rate if tax_rate is not None else self.default_vat_rate
        tax = (amount * rate / Decimal('100')).quantize(Decimal('0.01'))
        total = amount + tax
        return {
            'tax_amount': tax,
            'net_amount': amount,
            'total_amount': total,
            'rate_applied': rate,
        }

    def format_tax_return(self, output_vat: Decimal, input_vat: Decimal,
                         period_start: str, period_end: str) -> dict:
        net_payable = output_vat - input_vat
        return {
            'country': self.country_code,
            'output_vat': output_vat,
            'input_vat': input_vat,
            'net_payable': net_payable,
            'period_start': period_start,
            'period_end': period_end,
            'format': 'pma_xml_v1',
            'currency': self.currency,
        }

    def generate_einvoice(self, sale) -> dict:
        # Ministry of Finance XML placeholder
        xml = f"""<Invoice>
  <Country>PS</Country>
  <TaxRate>16.00</TaxRate>
  <Total>{sale.total_aed if hasattr(sale, 'total_aed') else sale.amount_aed}</Total>
</Invoice>"""
        return {
            'xml_payload': xml,
            'qr_base64': '',
            'invoice_hash': '',
            'format': 'pma_mof_xml',
        }

    def get_wps_format(self, employees: list) -> dict:
        """
        WPS SIF (Salary Information File) format for Palestine.
        employees: list of dicts with keys: employee_id, name, iban, bank_code, net_salary
        """
        lines = []
        lines.append('EDR|BankCode|EmployerName|PayrollDate|RecordCount')
        for idx, emp in enumerate(employees, 1):
            lines.append(
                f"{emp.get('employee_id', '')}|{emp.get('bank_code', '')}|"
                f"{emp.get('name', '')}|{emp.get('iban', '')}|"
                f"{emp.get('net_salary', 0)}"
            )
        return {
            'format': 'wps_sif',
            'file_extension': '.sif',
            'lines': lines,
            'encoding': 'utf-8',
        }
