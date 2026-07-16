"""
NullStrategy — Returns zero tax / empty reports for unsupported countries.
"""

from decimal import Decimal
from .engine import LocalizationStrategy


class NullStrategy(LocalizationStrategy):
    country_code = 'XX'
    country_name = 'Unknown / Not Supported'
    default_vat_rate = Decimal('0')
    currency = 'AED'

    def calculate_tax(self, amount: Decimal, tax_rate: Decimal | None = None) -> dict:
        return {
            'tax_amount': Decimal('0'),
            'net_amount': amount,
            'total_amount': amount,
            'rate_applied': Decimal('0'),
        }

    def format_tax_return(self, output_vat: Decimal, input_vat: Decimal,
                         period_start: str, period_end: str) -> dict:
        return {
            'country': self.country_code,
            'output_vat': Decimal('0'),
            'input_vat': Decimal('0'),
            'net_payable': Decimal('0'),
            'period_start': period_start,
            'period_end': period_end,
            'format': 'null',
        }

    def generate_einvoice(self, sale) -> dict:
        return {
            'xml_payload': '<invoice/>',
            'qr_base64': '',
            'invoice_hash': '',
            'format': 'null',
        }
