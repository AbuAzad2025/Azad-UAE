"""
KSAStrategy — 15% VAT (configurable), ZATCA Phase 2 simplified invoice QR.
"""

from decimal import Decimal
from .engine import LocalizationStrategy


class KSAStrategy(LocalizationStrategy):
    country_code = 'SA'
    country_name = 'Saudi Arabia'
    default_vat_rate = Decimal('15.00')
    currency = 'SAR'
    supports_qr = True
    zatca_phase = 2

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
            'format': 'zatca_vat_v3',
            'currency': self.currency,
        }

    def generate_einvoice(self, sale) -> dict:
        # ZATCA Phase 2 simplified invoice XML + QR base64
        total = sale.total_aed if hasattr(sale, 'total_aed') else sale.amount_aed
        tax = total * self.default_vat_rate / Decimal('100')
        xml = f"""<Invoice>
  <ID>{sale.id}</ID>
  <IssueDate>{sale.sale_date if hasattr(sale, 'sale_date') else ''}</IssueDate>
  <TaxTotal><TaxAmount currencyID="SAR">{tax}</TaxAmount></TaxTotal>
  <LegalMonetaryTotal><TaxInclusiveAmount currencyID="SAR">{total}</TaxInclusiveAmount></LegalMonetaryTotal>
</Invoice>"""
        import base64
        qr_data = f"ZATCA|{self.default_vat_rate}|{total}|{sale.id}"
        qr_b64 = base64.b64encode(qr_data.encode()).decode()
        return {
            'xml_payload': xml,
            'qr_base64': qr_b64,
            'invoice_hash': '',
            'format': 'zatca_simplified_xml',
        }
