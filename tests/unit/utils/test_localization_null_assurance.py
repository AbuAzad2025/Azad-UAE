"""Null localization strategy — zero-tax fallback for unsupported countries."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from utils.localization.null import NullStrategy


class TestNullStrategy:
    def test_calculate_tax_zero(self):
        s = NullStrategy()
        result = s.calculate_tax(Decimal("250"))
        assert result["tax_amount"] == Decimal("0")
        assert result["total_amount"] == Decimal("250")
        assert result["rate_applied"] == Decimal("0")

    def test_format_tax_return(self):
        s = NullStrategy()
        report = s.format_tax_return(
            Decimal("10"), Decimal("5"), "2026-01-01", "2026-06-30"
        )
        assert report["country"] == "XX"
        assert report["net_payable"] == Decimal("0")
        assert report["format"] == "null"

    def test_generate_einvoice_minimal(self):
        s = NullStrategy()
        sale = MagicMock()
        result = s.generate_einvoice(sale)
        assert result["xml_payload"] == "<invoice/>"
        assert result["qr_base64"] == ""
        assert result["format"] == "null"
