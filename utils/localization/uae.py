"""
UAEStrategy — 5% VAT, AED-only for tax reporting, FTA XML + QR.
"""

from decimal import Decimal
from .engine import LocalizationStrategy


class UAEStrategy(LocalizationStrategy):
    country_code = 'AE'
    country_name = 'UAE'
    default_vat_rate = Decimal('5.00')
    currency = 'AED'
    supports_qr = True

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
            'format': 'fta_vat201_v1',
            'currency': self.currency,
        }

    def generate_einvoice(self, sale) -> dict:
        # FTA-compliant XML + TLV-encoded QR placeholder
        total = sale.total_aed if hasattr(sale, 'total_aed') else sale.amount_aed
        tax = total * self.default_vat_rate / Decimal('100')
        xml = f"""<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">
  <ID>{sale.id}</ID>
  <TaxTotal><TaxAmount currencyID="AED">{tax}</TaxAmount></TaxTotal>
  <LegalMonetaryTotal><TaxInclusiveAmount currencyID="AED">{total}</TaxInclusiveAmount></LegalMonetaryTotal>
</Invoice>"""
        # TLV-encoded QR (simplified placeholder)
        qr_data = f"VAT:{self.default_vat_rate}|Total:{total}|Sale:{sale.id}"
        import base64
        qr_b64 = base64.b64encode(qr_data.encode()).decode()
        return {
            'xml_payload': xml,
            'qr_base64': qr_b64,
            'invoice_hash': '',
            'format': 'fta_ubl_xml',
        }
