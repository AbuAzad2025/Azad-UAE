"""
Base LocalizationStrategy — Abstract interface for country-specific compliance.
"""

from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation


def coerce_decimal(value, default=None):
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


class LocalizationStrategy(ABC):
    """Base class for per-country tax, e-invoice, and compliance logic."""

    country_code: str = 'XX'
    country_name: str = 'Unknown'
    default_vat_rate: Decimal = Decimal('0')
    currency: str = 'AED'
    supports_wps: bool = False
    supports_qr: bool = False
    zatca_phase: int = 0

    @abstractmethod
    def calculate_tax(self, amount: Decimal, tax_rate: Decimal = None) -> dict:
        """
        Return dict with: tax_amount, net_amount, total_amount, rate_applied.
        """

    @abstractmethod
    def format_tax_return(self, output_vat: Decimal, input_vat: Decimal,
                         period_start: str, period_end: str) -> dict:
        """
        Return country-specific VAT return structure.
        """

    @abstractmethod
    def generate_einvoice(self, sale) -> dict:
        """
        Return dict with: xml_payload, qr_base64, invoice_hash.
        """

    def get_wps_format(self, employees: list) -> dict:
        """
        Return WPS SIF format (Palestine only by default).
        Override in subclass if supported.
        """
        raise NotImplementedError(f"WPS not supported for {self.country_code}")

    def validate_tax_number(self, tax_number: str) -> bool:
        """Validate country-specific tax registration number."""
        return bool(tax_number and len(tax_number) >= 5)
