"""UAE localization strategy — country plugin, not global default."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from utils.localization.uae import UAEStrategy


class TestUAEStrategyPlugin:
    def test_country_metadata(self):
        s = UAEStrategy()
        assert s.country_code == "AE"
        assert s.currency == "AED"
        assert s.supports_qr is True

    def test_calculate_tax_default_rate(self):
        s = UAEStrategy()
        result = s.calculate_tax(Decimal("100"))
        assert result["tax_amount"] == Decimal("5.00")
        assert result["total_amount"] == Decimal("105.00")
        assert result["rate_applied"] == Decimal("5.00")

    def test_calculate_tax_custom_rate(self):
        s = UAEStrategy()
        result = s.calculate_tax(Decimal("200"), tax_rate=Decimal("10"))
        assert result["tax_amount"] == Decimal("20.00")

    def test_format_tax_return(self):
        s = UAEStrategy()
        report = s.format_tax_return(Decimal("100"), Decimal("30"), "2026-01-01", "2026-03-31")
        assert report["country"] == "AE"
        assert report["net_payable"] == Decimal("70")
        assert report["format"] == "fta_vat201_v1"
        assert report["currency"] == "AED"

    def test_generate_einvoice_uses_total_aed(self):
        s = UAEStrategy()
        sale = MagicMock(id=42, total_aed=Decimal("1050"))
        result = s.generate_einvoice(sale)
        assert "1050" in result["xml_payload"]
        assert result["format"] == "fta_ubl_xml"
        assert result["qr_base64"]

    def test_generate_einvoice_falls_back_to_amount_aed(self):
        s = UAEStrategy()
        sale = MagicMock(spec=["id", "amount_aed"])
        sale.id = 7
        sale.amount_aed = Decimal("500")
        result = s.generate_einvoice(sale)
        assert "500" in result["xml_payload"]
